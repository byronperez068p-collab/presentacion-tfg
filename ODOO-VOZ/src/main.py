
import logging
import sys
import os

# Asegurar que src esté en el path si se ejecuta directamente
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from src.config import TELEGRAM_TOKEN, ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS, WEBHOOK_URL, PORT, validate_config
from src.odoo_client import OdooConnector
from src.ai_processor import AIProcessor
from src.bot_handlers import start, button_handler, voice_handler, text_handler, error_handler

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

logger = logging.getLogger("SuperBot2.Main")

async def post_init(application):
    logger.info("Bot is ready and initialized.")
    # Optional: Send "Bot Started" message to last known chat if persistence logic exists here

def main():
    if not validate_config():
        sys.exit(1)

    # 1. Inicializar Servicios
    odoo = OdooConnector(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS)
    if not odoo.connect():
        sys.exit(1)

    ai = AIProcessor(odoo)

    # 2. Construir Aplicación
    app_builder = ApplicationBuilder().token(TELEGRAM_TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60)
    app_builder.post_init(post_init)
    application = app_builder.build()

    # 3. Inyectar Dependencias
    application.bot_data['odoo'] = odoo
    application.bot_data['ai'] = ai

    # 4. Registrar Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_error_handler(error_handler)

    # 5. Modo de Ejecución
    if WEBHOOK_URL:
        logger.info(f"🚀 Iniciando en modo WEBHOOK escuchando en puerto {PORT}...")
        logger.info(f"🔗 URL: {WEBHOOK_URL}")
        
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="telegram",
            webhook_url=f"{WEBHOOK_URL}/telegram"
        )
    else:
        logger.info("⚠️ WEBHOOK_URL no definido. Iniciando en modo POLLING (Solo para desarrollo local)...")
        if os.getenv("K_SERVICE"):
             logger.warning("🚨 ESTÁS EN CLOUD RUN SIN WEBHOOK. EL BOT SE DETENDRÁ.")
        
        application.run_polling()

if __name__ == "__main__":
    main()
