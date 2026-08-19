from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from db.models import Job, SubscriptionPlan, SubscriptionTransaction, User


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def get_user(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_or_create_user(db: Session, user_id: int, username: str = None, first_name: str = None) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if changed:
            db.commit()
    return user


def get_subscription_state(user: User | None) -> str:
    """
    Returns one of: unregistered | wishlist | active | expired | banned
    Checks subscription_expires_at for auto-expiry without writing to DB.
    """
    if not user:
        return "unregistered"
    if user.account_status == "banned":
        return "banned"
    status = user.subscription_status
    if not status:
        return "unregistered"
    if status == "wishlist":
        return "wishlist"
    if status in ("active", "expired"):
        if user.subscription_expires_at and user.subscription_expires_at > datetime.utcnow():
            return "active"
        return "expired"
    return "unregistered"


def create_registration(db: Session, user_id: int, username: str, name: str,
                        phone: str, plan_id: int) -> User:
    """Save registration request — sets subscription_status to 'wishlist'."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, username=username)
        db.add(user)
    user.first_name = name
    user.phone_number = phone
    user.selected_plan_id = plan_id
    user.subscription_status = "wishlist"
    user.account_status = "whitelist"
    db.commit()
    db.refresh(user)
    return user


def activate_user(db: Session, user_id: int, days: int | None = None,
                  features: str = "motion_control") -> User | None:
    """Admin: activate user. Uses selected_plan.days if days not given."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if days is None and user.selected_plan_id:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == user.selected_plan_id).first()
        days = plan.days if plan else 30
    days = days or 30
    user.subscription_status = "active"
    user.subscription_expires_at = datetime.utcnow() + timedelta(days=days)
    if not user.features:
        user.features = features
    db.commit()
    db.refresh(user)
    return user


def extend_subscription(db: Session, user_id: int, days: int) -> User | None:
    """Admin: extend from current expiry (or now if expired)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    base = max(datetime.utcnow(), user.subscription_expires_at or datetime.utcnow())
    user.subscription_expires_at = base + timedelta(days=days)
    user.subscription_status = "active"
    db.commit()
    db.refresh(user)
    return user


def set_user_api_key(db: Session, user_id: int, api_key: str | None) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    user.user_api_key = api_key
    db.commit()
    return True


def ban_user(db: Session, user_id: int, banned: bool = True) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.account_status = "banned" if banned else "whitelist"
        db.commit()
        db.refresh(user)
    return user


def list_users(db: Session, registered_only: bool = True, limit: int = 20, offset: int = 0) -> list[User]:
    q = db.query(User)
    if registered_only:
        q = q.filter(User.subscription_status.isnot(None))
    return q.order_by(User.created_at.desc()).limit(limit).offset(offset).all()


# ---------------------------------------------------------------------------
# Subscription Transactions
# ---------------------------------------------------------------------------

def create_pending_transaction(
    db: Session,
    user_id: int,
    plan_id: int,
    amount: int,
    midtrans_order_id: str,
) -> SubscriptionTransaction:
    """Create pending transaction before Midtrans payment completes."""
    user = db.query(User).filter(User.id == user_id).first()
    txn = SubscriptionTransaction(
        user_id=user_id,
        plan_id=plan_id,
        transaction_type="new_registration",
        amount=amount,
        prev_status=user.subscription_status if user else None,
        prev_expires_at=user.subscription_expires_at if user else None,
        new_status="active",
        midtrans_order_id=midtrans_order_id,
        note="midtrans_pending",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def activate_user_by_order_id(
    db: Session,
    midtrans_order_id: str,
    payment_ref: str | None = None,
) -> User | None:
    """Called from Midtrans webhook. Activate user and finalize transaction record."""
    txn = db.query(SubscriptionTransaction).filter(
        SubscriptionTransaction.midtrans_order_id == midtrans_order_id
    ).first()
    if not txn:
        return None

    user = db.query(User).filter(User.id == txn.user_id).first()
    if not user:
        return None

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == txn.plan_id).first()
    days = plan.days if plan else 30

    user.subscription_status = "active"
    user.subscription_expires_at = datetime.utcnow() + timedelta(days=days)
    if not user.features:
        user.features = "motion_control"

    txn.new_expires_at = user.subscription_expires_at
    txn.note = f"midtrans_paid:{payment_ref or midtrans_order_id}"

    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Subscription Plans
# ---------------------------------------------------------------------------

def get_active_plans(db: Session) -> list[SubscriptionPlan]:
    return (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.days)
        .all()
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def create_job(db: Session, job_id: str, user_id: int, chat_id: int,
               photo_path: str, video_path: str, mode: str = "std",
               orientation: str = "video",  # aspect_ratio: str = "9:16",  # TODO: belum aktif
               provider: str = "kling") -> Job:
    job = Job(
        id=job_id,
        user_id=user_id,
        chat_id=chat_id,
        photo_path=photo_path,
        video_path=video_path,
        mode=mode,
        orientation=orientation,
        # aspect_ratio=aspect_ratio,  # TODO: belum aktif
        provider=provider,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    return db.query(Job).filter(Job.id == job_id).first()


def get_latest_job(db: Session, user_id: int) -> Job | None:
    return (
        db.query(Job)
        .filter(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .first()
    )


def get_user_jobs(db: Session, user_id: int, limit: int = 10) -> list[Job]:
    return (
        db.query(Job)
        .filter(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )


def update_job_status(db: Session, job_id: str, status: str,
                      output_path: str = None, error_message: str = None):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return
    job.status = status
    if status == "processing" and not job.started_at:
        job.started_at = datetime.utcnow()
    if status in ("completed", "failed"):
        job.completed_at = datetime.utcnow()
    if output_path:
        job.output_path = output_path
    if error_message:
        job.error_message = error_message
    db.commit()


def update_job_replicate_id(db: Session, job_id: str, replicate_id: str):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.replicate_id = replicate_id
        db.commit()
