from pathlib import Path
import os
import socket


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value, 0)


APP_NAME = "Koperasi BRIN POS"
STORE_NAME = os.getenv("POS_STORE_NAME", "Toko Koperasi BRIN")
STORE_ADDRESS = os.getenv("POS_STORE_ADDRESS", "Badan Riset dan Inovasi Nasional")
STORE_PHONE = os.getenv("POS_STORE_PHONE", "-")
STORE_ID = os.getenv("POS_STORE_ID", "BRIN-STORE-001")
REGISTER_ID = os.getenv("POS_REGISTER_ID", "REG-01")
DEVICE_ID = os.getenv("POS_DEVICE_ID", socket.gethostname() or "POS-DEVICE-01")

CURRENCY_SYMBOL = "Rp"
TAX_PERCENT = float(os.getenv("POS_TAX_PERCENT", "0"))

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("POS_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = Path(os.getenv("POS_DB_PATH", DATA_DIR / "pos.db"))
RECEIPT_DIR = Path(os.getenv("POS_RECEIPT_DIR", BASE_DIR / "receipts"))
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)

# ESC/POS hardware configuration.
PRINTER_MODE = os.getenv("POS_PRINTER_MODE", "disabled").strip().lower()
PRINTER_HOST = os.getenv("POS_PRINTER_HOST", "")
PRINTER_PORT = env_int("POS_PRINTER_PORT", 9100)
PRINTER_USB_VENDOR_ID = env_int("POS_PRINTER_USB_VENDOR_ID", 0)
PRINTER_USB_PRODUCT_ID = env_int("POS_PRINTER_USB_PRODUCT_ID", 0)
PRINTER_PROFILE = os.getenv("POS_PRINTER_PROFILE", "default")
CASH_DRAWER_ENABLED = env_bool("POS_CASH_DRAWER_ENABLED", False)
CASH_DRAWER_PIN = env_int("POS_CASH_DRAWER_PIN", 2)
AUTO_PRINT_RECEIPT = env_bool("POS_AUTO_PRINT_RECEIPT", False)
AUTO_OPEN_DRAWER_CASH = env_bool("POS_AUTO_OPEN_DRAWER_CASH", False)

# Central synchronization / integration configuration.
SYNC_ENABLED = env_bool("POS_SYNC_ENABLED", False)
SYNC_API_URL = os.getenv("POS_SYNC_API_URL", "").rstrip("/")
SYNC_API_TOKEN = os.getenv("POS_SYNC_API_TOKEN", "")
SYNC_TIMEOUT_SECONDS = float(os.getenv("POS_SYNC_TIMEOUT_SECONDS", "5"))


def format_rupiah(value: int | float) -> str:
    value = int(round(value))
    return f"Rp {value:,.0f}".replace(",", ".")
