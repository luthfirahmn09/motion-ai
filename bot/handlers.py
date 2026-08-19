import os
import re
import time
import uuid
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.keyboards import (
    api_settings_keyboard,
    back_to_settings_keyboard,
    confirm_keyboard,
    dashboard_keyboard,
    payment_fallback_keyboard,
    payment_keyboard,
    plan_keyboard,
    settings_keyboard,
)
from bot.states import (
    CONFIRM_PROCESS, DASHBOARD, REG_CONFIRM, REG_NAME, REG_PHONE, REG_PLAN,
    SET_API_KEY, SETTINGS_MENU, WAIT_PHOTO, WAIT_VIDEO,
)
from db.crud import (
    create_job,
    create_pending_transaction,
    create_registration,
    get_active_plans,
    get_latest_job,
    get_or_create_user,
    get_subscription_state,
    get_user,
    get_user_jobs,
    set_user_api_key,
)
from db.database import SessionLocal
from db.models import SubscriptionPlan, User
from utils.file_handler import cleanup, download_telegram_file, validate_photo, validate_video
from utils.logger import logger
from utils.rate_limiter import check_user_quota, increment_daily_quota, mark_user_active

TEMP_DIR = os.getenv("TEMP_DIR", "./storage")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

try:
    from worker.tasks import process_motion_transfer
except ImportError:
    process_motion_transfer = None


def _telegram_cdn_url(file_path: str) -> str:
    if file_path.startswith("http"):
        return file_path
    return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"


def _dashboard_text(db_user: User) -> str:
    name = db_user.first_name or "kamu"
    days_left = max(0, (db_user.subscription_expires_at - datetime.utcnow()).days)
    features = db_user.features or "motion_control"
    feature_lines = ""
    if "motion_control" in features.split(","):
        feature_lines += "  • 🎬 Motion Control\n"
    return (
        f"👋 Selamat datang, <b>{name}</b>!\n\n"
        f"📦 <b>Fitur tersedia:</b>\n{feature_lines}\n"
        f"💳 Subscription: <b>{days_left} hari</b> tersisa\n\n"
        "Pilih menu di bawah:"
    )


# ---------------------------------------------------------------------------
# Entry point: /start /buat /new
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    db = SessionLocal()
    try:
        user = get_or_create_user(db, tg_user.id, tg_user.username, tg_user.first_name)
        state = get_subscription_state(user)
    finally:
        db.close()

    context.user_data.clear()

    if state == "banned":
        await update.message.reply_text("🚫 Akun kamu dibanned. Hubungi admin.")
        return ConversationHandler.END

    if state == "wishlist":
        await update.message.reply_text(
            "⏳ <b>Pendaftaran dalam proses verifikasi.</b>\n\n"
            "Admin sedang mengecek pembayaran kamu.\n"
            "Kamu akan dinotifikasi setelah akun diaktifkan.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    if state == "expired":
        await update.message.reply_text(
            "⏰ <b>Subscription kamu sudah habis.</b>\n\n"
            "Hubungi admin untuk perpanjang.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    if state == "active":
        db = SessionLocal()
        try:
            user = get_user(db, tg_user.id)
            await update.message.reply_text(
                _dashboard_text(user),
                reply_markup=dashboard_keyboard(),
                parse_mode="HTML",
            )
        finally:
            db.close()
        return DASHBOARD

    # unregistered → start registration flow
    await update.message.reply_text(
        "👋 Halo! Akun kamu belum terdaftar.\n\n"
        "📝 <b>Form Pendaftaran</b>\n\n"
        "Ketik <b>nama lengkap</b> kamu:",
        parse_mode="HTML",
    )
    return REG_NAME


async def start_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    db = SessionLocal()
    try:
        user = get_or_create_user(db, tg_user.id, tg_user.username, tg_user.first_name)
        state = get_subscription_state(user)
    finally:
        db.close()

    if state != "active":
        await update.message.reply_text("❌ Akun belum aktif. Ketik /start untuk info lebih lanjut.")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚙️ <b>Account Settings</b>\n\nPilih menu:",
        reply_markup=settings_keyboard(),
        parse_mode="HTML",
    )
    return SETTINGS_MENU


# ---------------------------------------------------------------------------
# Registration flow
# ---------------------------------------------------------------------------

async def receive_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Nama terlalu pendek. Coba lagi:")
        return REG_NAME

    context.user_data["reg_name"] = name
    await update.message.reply_text(
        f"✅ Nama: <b>{name}</b>\n\n"
        "Ketik <b>nomor HP</b> kamu:\n"
        "<i>Contoh: 08123456789 atau +628123456789</i>",
        parse_mode="HTML",
    )
    return REG_PHONE


async def receive_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not re.match(r'^(\+62|62|0)\d{8,12}$', phone):
        await update.message.reply_text(
            "❌ Format nomor HP tidak valid.\n"
            "Contoh: 08123456789 atau +628123456789\nCoba lagi:"
        )
        return REG_PHONE

    context.user_data["reg_phone"] = phone

    db = SessionLocal()
    try:
        plans = get_active_plans(db)
        if not plans:
            await update.message.reply_text(
                "❌ Tidak ada paket tersedia saat ini. Hubungi admin."
            )
            return ConversationHandler.END

        await update.message.reply_text(
            f"✅ No. HP: <b>{phone}</b>\n\n"
            "💳 Pilih <b>paket subscription</b>:",
            reply_markup=plan_keyboard(plans),
            parse_mode="HTML",
        )
    finally:
        db.close()
    return REG_PLAN


async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "reg_cancel":
        context.user_data.clear()
        await query.edit_message_text("Pendaftaran dibatalkan. Ketik /start untuk mulai ulang.")
        return ConversationHandler.END

    plan_id = int(query.data.split("_")[1])
    reg_name = context.user_data.get("reg_name")
    reg_phone = context.user_data.get("reg_phone")
    tg_user = update.effective_user

    db = SessionLocal()
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        if not plan:
            await query.edit_message_text("❌ Paket tidak ditemukan.")
            return ConversationHandler.END

        context.user_data["reg_plan_id"] = plan.id
        context.user_data["reg_plan_name"] = plan.name
        context.user_data["reg_plan_price"] = plan.price or 0

        create_registration(db, tg_user.id, tg_user.username, reg_name, reg_phone, plan.id)

        order_id = f"reg-{tg_user.id}-{int(time.time())}"
        context.user_data["reg_order_id"] = order_id
        create_pending_transaction(
            db,
            user_id=tg_user.id,
            plan_id=plan.id,
            amount=plan.price or 0,
            midtrans_order_id=order_id,
        )
    finally:
        db.close()

    price_str = f"Rp {plan.price:,}" if plan.price else "Hubungi admin untuk harga"

    payment_url = None
    if plan.price:
        try:
            from api.midtrans_client import create_snap_transaction
            result = create_snap_transaction(
                order_id=order_id,
                amount=plan.price,
                first_name=reg_name,
                phone=reg_phone,
                item_name=f"Subscription {plan.name}",
            )
            payment_url = result.get("redirect_url")
        except Exception as e:
            logger.error(f"Midtrans create transaction failed: {e}")

    summary = (
        f"📋 <b>Konfirmasi Pendaftaran</b>\n\n"
        f"Nama: <b>{reg_name}</b>\n"
        f"No. HP: <b>{reg_phone}</b>\n"
        f"Paket: <b>{plan.name}</b>\n"
        f"Harga: <b>{price_str}</b>"
    )

    if payment_url:
        await query.edit_message_text(
            summary + "\n\nKlik <b>Bayar Sekarang</b> untuk lanjut ke pembayaran.\n"
            "Akun langsung aktif setelah pembayaran berhasil.",
            reply_markup=payment_keyboard(payment_url),
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            summary + "\n\n⚠️ Gagal membuat link pembayaran. Hubungi admin.",
            reply_markup=payment_fallback_keyboard(),
            parse_mode="HTML",
        )
    return REG_CONFIRM


async def confirm_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles back_to_plans from REG_CONFIRM screen."""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        plans = get_active_plans(db)
    finally:
        db.close()

    if not plans:
        await query.edit_message_text("❌ Tidak ada paket tersedia. Hubungi admin.")
        return ConversationHandler.END

    await query.edit_message_text(
        "💳 Pilih <b>paket subscription</b>:",
        reply_markup=plan_keyboard(plans),
        parse_mode="HTML",
    )
    return REG_PLAN


# ---------------------------------------------------------------------------
# DASHBOARD state
# ---------------------------------------------------------------------------

async def handle_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "start_motion":
        db = SessionLocal()
        try:
            user = get_user(db, update.effective_user.id)
            has_api_key = bool(user and user.user_api_key)
        finally:
            db.close()

        if not has_api_key:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            await query.edit_message_text(
                "⚠️ <b>API Key belum diset.</b>\n\n"
                "Kamu perlu memasukkan Freepik API Key sendiri\n"
                "sebelum bisa menggunakan Motion Control.\n\n"
                "Pergi ke <b>Account Settings → 🔑 API Settings</b> untuk set.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔑 Set API Key Sekarang", callback_data="open_settings")],
                ]),
                parse_mode="HTML",
            )
            return SETTINGS_MENU

        context.user_data.clear()
        await query.edit_message_text(
            "📸 <b>Motion Control</b>\n\n"
            "Kirim <b>foto full body</b> kamu sekarang (maks 10MB):",
            parse_mode="HTML",
        )
        return WAIT_PHOTO

    if query.data == "open_settings":
        await query.edit_message_text(
            "⚙️ <b>Account Settings</b>\n\nPilih menu:",
            reply_markup=settings_keyboard(),
            parse_mode="HTML",
        )
        return SETTINGS_MENU

    return DASHBOARD


# ---------------------------------------------------------------------------
# SETTINGS_MENU state
# ---------------------------------------------------------------------------

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "back_to_dashboard":
        db = SessionLocal()
        try:
            user = get_user(db, user_id)
            if not user:
                await query.edit_message_text("❌ Akun tidak ditemukan.")
                return ConversationHandler.END
            await query.edit_message_text(
                _dashboard_text(user),
                reply_markup=dashboard_keyboard(),
                parse_mode="HTML",
            )
        finally:
            db.close()
        return DASHBOARD

    if data == "open_settings":
        await query.edit_message_text(
            "⚙️ <b>Account Settings</b>\n\nPilih menu:",
            reply_markup=settings_keyboard(),
            parse_mode="HTML",
        )
        return SETTINGS_MENU

    if data == "set_account":
        db = SessionLocal()
        try:
            user = get_user(db, user_id)
            name = user.first_name or "N/A"
            username = f"@{user.username}" if user.username else "N/A"
            phone = user.phone_number or "N/A"
            sub_exp = (
                user.subscription_expires_at.strftime("%d %b %Y")
                if user.subscription_expires_at else "N/A"
            )
            features = user.features or "motion_control"
            plan_name = user.selected_plan.name if user.selected_plan else "N/A"
        finally:
            db.close()
        await query.edit_message_text(
            f"👤 <b>Account Info</b>\n\n"
            f"Nama: <b>{name}</b>\n"
            f"Username: <b>{username}</b>\n"
            f"No. HP: <b>{phone}</b>\n"
            f"Telegram ID: <code>{user_id}</code>\n"
            f"Paket: <b>{plan_name}</b>\n"
            f"Subscription s/d: <b>{sub_exp}</b>\n"
            f"Fitur aktif: <b>{features}</b>",
            reply_markup=back_to_settings_keyboard(),
            parse_mode="HTML",
        )
        return SETTINGS_MENU

    if data == "set_api":
        db = SessionLocal()
        try:
            user = get_user(db, user_id)
            key = user.user_api_key if user else None
        finally:
            db.close()
        if key and len(key) > 8:
            key_display = f"✅ Sudah diset (<code>...{key[-8:]}</code>)"
        elif key:
            key_display = "✅ Sudah diset"
        else:
            key_display = "❌ Belum diset"
        await query.edit_message_text(
            f"🔑 <b>API Settings</b>\n\n"
            f"Status: {key_display}\n\n"
            "Dapatkan API key kamu di:\n"
            "🔗 <a href=\"https://www.magnific.com/api\">magnific.com → Login → API</a>",
            reply_markup=api_settings_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return SETTINGS_MENU

    if data == "api_tutorial":
        await query.edit_message_text(
            "📹 <b>Tutorial: Cara Dapat Freepik API Key</b>\n\n"
            "Tonton video tutorial lengkap di link berikut:\n"
            "👉 <a href=\"https://google.com\">Tonton Tutorial</a>\n\n"
            "<i>Link akan diupdate ke video tutorial resmi segera.</i>",
            reply_markup=back_to_settings_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return SETTINGS_MENU

    if data == "set_api_input":
        context.user_data["awaiting_api_key"] = True
        await query.edit_message_text(
            "🔑 <b>Masukkan API Key kamu:</b>\n\n"
            "<i>Ketik dan kirim teks API key-nya.</i>",
            parse_mode="HTML",
        )
        return SET_API_KEY

    if data == "del_api_key":
        db = SessionLocal()
        try:
            set_user_api_key(db, user_id, None)
        finally:
            db.close()
        await query.edit_message_text(
            "🗑 <b>API Key dihapus.</b>\nSekarang pakai API key global.",
            reply_markup=back_to_settings_keyboard(),
            parse_mode="HTML",
        )
        return SETTINGS_MENU

    if data == "set_subscription":
        db = SessionLocal()
        try:
            user = get_user(db, user_id)
            sub_exp = user.subscription_expires_at if user else None
            plan_name = user.selected_plan.name if user and user.selected_plan else "N/A"
        finally:
            db.close()
        if sub_exp:
            days_left = max(0, (sub_exp - datetime.utcnow()).days)
            exp_str = sub_exp.strftime("%d %b %Y")
            status = f"✅ Aktif hingga <b>{exp_str}</b> ({days_left} hari lagi)"
        else:
            status = "❌ Tidak aktif"
        await query.edit_message_text(
            f"💳 <b>Subscription</b>\n\n"
            f"Paket: <b>{plan_name}</b>\n"
            f"Status: {status}\n\n"
            "Untuk perpanjang, hubungi admin.",
            reply_markup=back_to_settings_keyboard(),
            parse_mode="HTML",
        )
        return SETTINGS_MENU

    if data == "set_history":
        db = SessionLocal()
        try:
            jobs = get_user_jobs(db, user_id, limit=5)
        finally:
            db.close()
        if not jobs:
            hist = "Belum ada job."
        else:
            emoji = {"queued": "🕐", "uploading": "📤", "processing": "⚙️",
                     "completed": "✅", "failed": "❌"}
            lines = []
            for j in jobs:
                e = emoji.get(j.status, "❓")
                dt = j.created_at.strftime("%d/%m %H:%M") if j.created_at else "?"
                lines.append(f"{e} <code>#{j.id[:8]}</code> — {j.status} — {dt}")
            hist = "\n".join(lines)
        await query.edit_message_text(
            f"📜 <b>History (5 terakhir)</b>\n\n{hist}",
            reply_markup=back_to_settings_keyboard(),
            parse_mode="HTML",
        )
        return SETTINGS_MENU

    return SETTINGS_MENU


# ---------------------------------------------------------------------------
# SET_API_KEY state
# ---------------------------------------------------------------------------

async def receive_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    api_key = update.message.text.strip()
    if len(api_key) < 10:
        await update.message.reply_text("❌ API key terlalu pendek. Coba lagi atau /cancel:")
        return SET_API_KEY

    db = SessionLocal()
    try:
        set_user_api_key(db, update.effective_user.id, api_key)
    finally:
        db.close()

    context.user_data.pop("awaiting_api_key", None)
    await update.message.reply_text(
        "✅ <b>API key berhasil disimpan!</b>\n\nKetik /settings untuk kembali ke menu.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# State fallbacks (must be async and return correct state)
# ---------------------------------------------------------------------------

async def wait_photo_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Saya butuh foto. Kirim foto full body kamu langsung ya!")
    return WAIT_PHOTO


async def wait_video_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Saya butuh video referensi. Kirim video yang gerakannya mau ditiru!")
    return WAIT_VIDEO


# ---------------------------------------------------------------------------
# Motion Control flow
# ---------------------------------------------------------------------------

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    photo = message.photo[-1] if message.photo else None
    doc = message.document if message.document else None

    file_id = photo.file_id if photo else doc.file_id if doc else None
    if not file_id:
        await message.reply_text("Kirim foto langsung ya, bukan link atau teks.")
        return WAIT_PHOTO

    await message.reply_text("⏳ Mengecek foto...")

    tmp_dir = os.path.join(TEMP_DIR, "tmp")
    tmp_name = f"photo_{update.effective_user.id}_{uuid.uuid4().hex}.jpg"
    save_path = await download_telegram_file(context.bot, file_id, tmp_dir, tmp_name)

    valid, err = validate_photo(save_path)
    cleanup(save_path)

    if not valid:
        await message.reply_text(f"❌ {err}\nCoba kirim foto lain.")
        return WAIT_PHOTO

    tg_file = await context.bot.get_file(file_id)
    context.user_data["photo_url"] = _telegram_cdn_url(tg_file.file_path)

    await message.reply_text(
        "✅ <b>Foto diterima!</b>\n\n"
        "Sekarang kirim <b>video referensi</b> gerakannya.\n\n"
        "<b>Tips video yang bagus:</b>\n"
        "• Durasi <b>3–30 detik</b>, ukuran maks <b>10MB</b>\n"
        "• 1 orang terlihat jelas full body\n"
        "• Kamera stabil",
        parse_mode="HTML",
    )
    return WAIT_VIDEO


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    video = message.video
    doc = message.document

    file_id = video.file_id if video else doc.file_id if doc else None
    if not file_id:
        await message.reply_text("Kirim video langsung ya, bukan link atau teks.")
        return WAIT_VIDEO

    await message.reply_text("⏳ Mengecek video...")

    tmp_dir = os.path.join(TEMP_DIR, "tmp")
    tmp_name = f"video_{update.effective_user.id}_{uuid.uuid4().hex}.mp4"
    save_path = await download_telegram_file(context.bot, file_id, tmp_dir, tmp_name)

    valid, err = validate_video(save_path)
    cleanup(save_path)

    if not valid:
        await message.reply_text(f"❌ {err}\nCoba kirim video lain.")
        return WAIT_VIDEO

    tg_file = await context.bot.get_file(file_id)
    context.user_data["video_url"] = _telegram_cdn_url(tg_file.file_path)
    context.user_data["mode"] = "std"

    await message.reply_text(
        "📋 <b>Ringkasan:</b>\n"
        "📸 Foto: siap\n"
        "🎬 Video referensi: siap\n\n"
        "Estimasi waktu: <b>2–5 menit</b>.",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    return CONFIRM_PROCESS


async def confirm_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    allowed, reason = check_user_quota(user.id)
    if not allowed:
        await query.edit_message_text(f"⚠️ {reason}")
        return ConversationHandler.END

    photo_url = context.user_data.get("photo_url")
    video_url = context.user_data.get("video_url")
    mode = context.user_data.get("mode", "std")

    if not photo_url or not video_url:
        await query.edit_message_text("❌ URL file tidak ditemukan. Ketik /buat untuk mulai ulang.")
        return ConversationHandler.END

    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        create_job(
            db,
            job_id=job_id,
            user_id=user.id,
            chat_id=update.effective_chat.id,
            photo_path=photo_url,
            video_path=video_url,
            mode=mode,
            orientation=os.getenv("KLING_ORIENTATION", "video"),
            provider="kling",
        )
    finally:
        db.close()

    mark_user_active(user.id, job_id)
    increment_daily_quota(user.id)
    if process_motion_transfer:
        process_motion_transfer.delay(job_id)

    await query.edit_message_text(
        f"✅ <b>Job diterima!</b> (#{job_id[:8]})\n\n"
        "⏳ Sedang diproses di background...\n"
        "Estimasi: <b>2–5 menit</b>. Hasilnya langsung dikirim ke sini!",
        parse_mode="HTML",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def handle_change_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("photo_url", None)
    context.user_data.pop("video_url", None)
    await query.edit_message_text("Kirim foto full body baru (maks 10MB):")
    return WAIT_PHOTO


async def handle_change_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("video_url", None)
    await query.edit_message_text("Kirim video referensi baru (maks 10MB, 3–30 detik):")
    return WAIT_VIDEO


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    msg = "Dibatalkan. Ketik /start untuk kembali ke menu."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Status command (outside conversation)
# ---------------------------------------------------------------------------

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        job = get_latest_job(db, user.id)
        if not job:
            await update.message.reply_text("Belum ada job. Ketik /buat untuk mulai.")
            return

        elapsed = ""
        if job.created_at:
            delta = datetime.utcnow() - job.created_at.replace(tzinfo=None)
            mins, secs = divmod(int(delta.total_seconds()), 60)
            elapsed = f"{mins}m {secs}s yang lalu"

        status_emoji = {
            "queued": "🕐", "uploading": "📤", "processing": "⚙️",
            "completed": "✅", "failed": "❌",
        }.get(job.status, "❓")

        text = (
            f"{status_emoji} <b>Job #{job.id[:8]}</b>\n"
            f"Status: <b>{job.status}</b>\n"
            f"Dibuat: {elapsed}\n"
        )
        if job.error_message:
            text += f"Error: <code>{job.error_message[:100]}</code>"

        await update.message.reply_text(text, parse_mode="HTML")
    finally:
        db.close()


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ketik /start untuk kembali ke menu utama.")
