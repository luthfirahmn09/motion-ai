import os

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.handlers import (
    cancel,
    check_status,
    confirm_generate,
    confirm_registration,
    fallback_text,
    handle_change_photo,
    handle_change_video,
    handle_dashboard_callback,
    handle_plan_selection,
    handle_settings_callback,
    receive_api_key,
    receive_photo,
    receive_reg_name,
    receive_reg_phone,
    receive_video,
    start,
    start_settings,
    wait_photo_fallback,
    wait_video_fallback,
)
from bot.states import (
    CONFIRM_PROCESS,
    DASHBOARD,
    REG_CONFIRM,
    REG_NAME,
    REG_PHONE,
    REG_PLAN,
    SET_API_KEY,
    SETTINGS_MENU,
    WAIT_PHOTO,
    WAIT_VIDEO,
)
from utils.logger import logger

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("buat", start),
            CommandHandler("new", start),
            CommandHandler("settings", start_settings),
            CallbackQueryHandler(handle_settings_callback, pattern="^open_settings$"),
        ],
        states={
            # Registration flow
            REG_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reg_name),
            ],
            REG_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reg_phone),
            ],
            REG_PLAN: [
                CallbackQueryHandler(handle_plan_selection, pattern=r"^plan_\d+$"),
                CallbackQueryHandler(handle_plan_selection, pattern="^reg_cancel$"),
            ],
            REG_CONFIRM: [
                CallbackQueryHandler(confirm_registration, pattern="^back_to_plans$"),
            ],

            # Main dashboard
            DASHBOARD: [
                CallbackQueryHandler(
                    handle_dashboard_callback,
                    pattern="^(start_motion|open_settings)$",
                ),
            ],

            # Motion Control flow
            WAIT_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_photo),
                MessageHandler(~filters.COMMAND, wait_photo_fallback),
            ],
            WAIT_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_video),
                MessageHandler(~filters.COMMAND, wait_video_fallback),
            ],
            CONFIRM_PROCESS: [
                CallbackQueryHandler(confirm_generate, pattern="^confirm$"),
                CallbackQueryHandler(handle_change_photo, pattern="^change_photo$"),
                CallbackQueryHandler(handle_change_video, pattern="^change_video$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],

            # Settings flow
            SETTINGS_MENU: [
                CallbackQueryHandler(
                    handle_settings_callback,
                    pattern="^(back_to_dashboard|open_settings|set_account|set_api|set_api_input|del_api_key|set_history|api_tutorial|set_subscription)$",
                ),
            ],
            SET_API_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_api_key),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("status", check_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    return app


def main():
    app = build_application()

    if WEBHOOK_URL:
        from contextlib import asynccontextmanager

        import uvicorn
        from fastapi import FastAPI, Request
        from telegram import Update

        @asynccontextmanager
        async def lifespan(fastapi_app):
            await app.initialize()
            await app.bot.set_webhook(
                url=f"{WEBHOOK_URL}/webhook",
                allowed_updates=["message", "callback_query"],
            )
            await app.start()
            logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
            yield
            await app.stop()

        fastapi_app = FastAPI(lifespan=lifespan)

        @fastapi_app.post("/webhook")
        async def webhook(request: Request):
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.process_update(update)
            return {"ok": True}

        @fastapi_app.get("/health")
        async def health():
            return {"status": "ok"}

        @fastapi_app.post("/midtrans/notification")
        async def midtrans_notification(request: Request):
            notif = await request.json()

            from api.midtrans_client import is_payment_success, verify_notification
            from db.crud import activate_user_by_order_id
            from db.database import SessionLocal as _SL

            if not verify_notification(notif):
                logger.warning(f"Midtrans invalid signature: {notif.get('order_id')}")
                return {"ok": False, "error": "invalid signature"}

            if not is_payment_success(notif):
                return {"ok": True, "status": "ignored"}

            order_id = notif.get("order_id", "")
            payment_ref = notif.get("transaction_id", order_id)

            db = _SL()
            try:
                user = activate_user_by_order_id(db, order_id, payment_ref)
            finally:
                db.close()

            if not user:
                logger.error(f"Midtrans webhook: no transaction found for order_id={order_id}")
                return {"ok": False, "error": "order not found"}

            plan_name = user.selected_plan.name if user.selected_plan else ""
            exp_str = (
                user.subscription_expires_at.strftime("%d %b %Y")
                if user.subscription_expires_at else ""
            )
            text = (
                f"✅ <b>Pembayaran berhasil!</b>\n\n"
                f"Akun kamu sudah aktif.\n"
                f"Paket: <b>{plan_name}</b>\n"
                f"Aktif hingga: <b>{exp_str}</b>\n\n"
                "Ketik /start untuk mulai menggunakan bot."
            )
            import httpx as _httpx
            try:
                async with _httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": user.id, "text": text, "parse_mode": "HTML"},
                        timeout=10,
                    )
            except Exception as e:
                logger.error(f"Failed to send payment success message to {user.id}: {e}")

            return {"ok": True}

        uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)
    else:
        logger.info("Starting in POLLING mode (local dev)")
        app.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
