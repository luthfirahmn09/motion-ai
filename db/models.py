from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey,
    Integer, String, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)          # e.g. "30 Hari"
    days = Column(Integer, nullable=False)
    price = Column(Integer, default=0)             # IDR, 0 = TBD
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)      # Telegram user_id
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    jobs_today = Column(Integer, default=0)
    last_reset = Column(Date, default=func.current_date())

    # Account status: whitelist | banned
    account_status = Column(String, default="whitelist", nullable=False)

    # Subscription lifecycle: None (never registered) | wishlist | active | expired
    subscription_status = Column(String, nullable=True)
    subscription_expires_at = Column(DateTime, nullable=True)
    selected_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)

    # Feature flags (comma-separated)
    features = Column(String, nullable=True, default="motion_control")

    # User's own Freepik API key (optional, fallback to global env)
    user_api_key = Column(String, nullable=True)

    selected_plan = relationship("SubscriptionPlan")
    jobs = relationship("Job", back_populates="user")


class SubscriptionTransaction(Base):
    __tablename__ = "subscription_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)

    # new_registration | renewal | manual_override
    transaction_type = Column(String, nullable=False)
    amount = Column(Integer, nullable=True)          # IDR paid, None = manual/free

    # before/after for audit trail
    prev_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    prev_expires_at = Column(DateTime, nullable=True)
    new_expires_at = Column(DateTime, nullable=True)

    note = Column(String, nullable=True)             # admin note or payment ref
    midtrans_order_id = Column(String, nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User")
    plan = relationship("SubscriptionPlan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)          # UUID
    user_id = Column(BigInteger, ForeignKey("users.id"))
    chat_id = Column(BigInteger)

    photo_path = Column(String, nullable=True)
    video_path = Column(String, nullable=True)

    replicate_id = Column(String, nullable=True)   # Freepik task_id

    # Status: queued → uploading → processing → completed | failed
    status = Column(String, default="queued")
    progress = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)

    output_path = Column(String, nullable=True)

    provider = Column(String, default="kling")
    mode = Column(String, default="std")
    orientation = Column(String, default="video")
    # aspect_ratio = Column(String, default="9:16", nullable=True)  # TODO: belum aktif

    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="jobs")
