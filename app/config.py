from pathlib import Path
import os

APP_NAME = "Koperasi BRIN POS"
STORE_NAME = os.getenv("POS_STORE_NAME", "Toko Koperasi BRIN")
STORE_ADDRESS = os.getenv("POS_STORE_ADDRESS", "Badan Riset dan Inovasi Nasional")
STORE_PHONE = os.getenv("POS_STORE_PHONE", "-")
CURRENCY_SYMBOL = "Rp"
TAX_PERCENT = float(os.getenv("POS_TAX_PERCENT", "0"))

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("POS_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = Path(os.getenv("POS_DB_PATH", DATA_DIR / "pos.db"))
RECEIPT_DIR = Path(os.getenv("POS_RECEIPT_DIR", BASE_DIR / "receipts"))
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)


def format_rupiah(value: int | float) -> str:
    value = int(round(value))
    return f"Rp {value:,.0f}".replace(",", ".")
