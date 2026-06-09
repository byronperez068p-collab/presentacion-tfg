
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# --- TELEGRAM ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "1582432458") # Usa ID por defecto si no existe en env (retrocompatibilidad)
if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        ADMIN_ID = None

# --- GOOGLE GEMINI ---
GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash") # Modelo para Lógica y STT
TTS_MODEL = os.getenv("TTS_MODEL", "gemini-2.5-flash-preview-tts") # Modelo Dedicado TTS
VOICE_NAME = os.getenv("VOICE_NAME", "Kore") # Personalidad de la voz: Puck, Kore, Zephyr

# --- ODOO ---
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASS = os.getenv("ODOO_PASS")

# --- SERVER ---
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- CONSTANTS ---
COMMON_MODELS = {
    # CRM & Sales
    "oportunidad": "crm.lead",
    "iniciativa": "crm.lead",
    "lead": "crm.lead",
    "venta": "sale.order",
    "presupuesto": "sale.order",
    "cotizacion": "sale.order",
    "pedido": "sale.order",
    "cliente": "res.partner",
    "contacto": "res.partner",
    "proveedor": "res.partner",
    
    # Products
    "producto": "product.template",
    "articulo": "product.template",
    "servicio": "product.template",
    
    # Project
    "proyecto": "project.project",
    "tarea": "project.task",
    
    # Accounting
    "factura": "account.move",
    "pago": "account.payment",
    
    # HR
    "empleado": "hr.employee",
    "departamento": "hr.department",
    "gasto": "hr.expense",
    
    # Inventory
    "albaran": "stock.picking",
    "inventario": "stock.quant",
    
    # Calendar
    "evento": "calendar.event",
    "reunion": "calendar.event",
    "cita": "calendar.event",
}

def validate_config():
    """Valida que la configuración esencial esté presente."""
    missing = []
    if not TELEGRAM_TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
    if not GEMINI_API_KEY: missing.append("GOOGLE_GEMINI_API_KEY")
    if not ODOO_URL: missing.append("ODOO_URL")
    
    if missing:
        print(f"❌ Missing Configuration: {', '.join(missing)}")
        return False
    return True
