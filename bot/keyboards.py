from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ---------------------------------------------------------------------------
# Dashboard & Settings
# ---------------------------------------------------------------------------

def dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Motion Control", callback_data="start_motion")],
        [InlineKeyboardButton("⚙️ Account Settings", callback_data="open_settings")],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Account", callback_data="set_account")],
        [InlineKeyboardButton("🔑 API Settings", callback_data="set_api")],
        [InlineKeyboardButton("📜 History", callback_data="set_history")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_dashboard")],
    ])


def api_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Set / Ganti API Key", callback_data="set_api_input")],
        [InlineKeyboardButton("🗑 Hapus API Key", callback_data="del_api_key")],
        [InlineKeyboardButton("📹 Tutorial Cara Dapat API Key", callback_data="api_tutorial")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="open_settings")],
    ])


def back_to_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali", callback_data="open_settings")],
    ])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def plan_keyboard(plans: list) -> InlineKeyboardMarkup:
    buttons = []
    for plan in plans:
        price_str = f"Rp {plan.price:,}" if plan.price else "Hubungi admin untuk harga"
        label = f"📅 {plan.name} — {price_str}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"plan_{plan.id}")])
    buttons.append([InlineKeyboardButton("❌ Batal", callback_data="reg_cancel")])
    return InlineKeyboardMarkup(buttons)


def payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Bayar Sekarang", url=payment_url)],
        [InlineKeyboardButton("⬅️ Kembali ke Pilih Paket", callback_data="back_to_plans")],
    ])


def payment_fallback_keyboard() -> InlineKeyboardMarkup:
    """Used when Midtrans URL unavailable."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali ke Pilih Paket", callback_data="back_to_plans")],
    ])


# ---------------------------------------------------------------------------
# Motion Control
# ---------------------------------------------------------------------------

def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Standard 720p — Hemat", callback_data="mode_std")],
        [InlineKeyboardButton("✨ Pro 1080p — Terbaik", callback_data="mode_pro")],
    ])



def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Generate Sekarang", callback_data="confirm")],
        [
            InlineKeyboardButton("🔄 Ganti Foto", callback_data="change_photo"),
            InlineKeyboardButton("🎬 Ganti Video", callback_data="change_video"),
        ],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ])
