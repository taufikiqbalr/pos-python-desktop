from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import DATABASE_PATH
from app.security import hash_password


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DATABASE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'cashier',
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL UNIQUE,
                    barcode TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    unit TEXT NOT NULL DEFAULT 'pcs',
                    price INTEGER NOT NULL CHECK(price >= 0),
                    stock REAL NOT NULL DEFAULT 0 CHECK(stock >= 0),
                    active INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
                CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
                CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);

                CREATE TABLE IF NOT EXISTS shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cashier_user_id INTEGER NOT NULL,
                    opening_cash INTEGER NOT NULL DEFAULT 0,
                    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    closing_cash INTEGER,
                    expected_cash INTEGER,
                    cash_difference INTEGER,
                    close_notes TEXT,
                    closed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    FOREIGN KEY(cashier_user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_shifts_cashier_status
                    ON shifts(cashier_user_id, status);

                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_no TEXT NOT NULL UNIQUE,
                    cashier_user_id INTEGER NOT NULL,
                    shift_id INTEGER,
                    customer_name TEXT,
                    subtotal INTEGER NOT NULL,
                    discount_total INTEGER NOT NULL DEFAULT 0,
                    tax_total INTEGER NOT NULL DEFAULT 0,
                    grand_total INTEGER NOT NULL,
                    payment_method TEXT NOT NULL,
                    paid_amount INTEGER NOT NULL,
                    change_amount INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'COMPLETED',
                    voided_at TEXT,
                    void_reason TEXT,
                    voided_by INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(cashier_user_id) REFERENCES users(id),
                    FOREIGN KEY(shift_id) REFERENCES shifts(id),
                    FOREIGN KEY(voided_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS sale_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    qty INTEGER NOT NULL CHECK(qty > 0),
                    unit_price INTEGER NOT NULL,
                    discount_amount INTEGER NOT NULL DEFAULT 0,
                    line_total INTEGER NOT NULL,
                    FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS sale_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER NOT NULL,
                    method TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    reference TEXT,
                    FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sale_payments_sale
                    ON sale_payments(sale_id);

                CREATE TABLE IF NOT EXISTS held_sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hold_no TEXT NOT NULL UNIQUE,
                    cashier_user_id INTEGER NOT NULL,
                    customer_name TEXT,
                    cart_discount_percent TEXT NOT NULL DEFAULT '0',
                    notes TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(cashier_user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_held_sales_cashier
                    ON held_sales(cashier_user_id, created_at);
                """
            )
            # Lightweight migrations for databases created by earlier MVP versions.
            self._ensure_column(conn, "sales", "shift_id", "INTEGER")
            self._ensure_column(conn, "sales", "status", "TEXT NOT NULL DEFAULT 'COMPLETED'")
            self._ensure_column(conn, "sales", "voided_at", "TEXT")
            self._ensure_column(conn, "sales", "void_reason", "TEXT")
            self._ensure_column(conn, "sales", "voided_by", "INTEGER")
            self._seed_users(conn)
            self._seed_products(conn)

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _seed_users(conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if existing:
            return
        conn.executemany(
            "INSERT INTO users(username, full_name, role, password_hash) VALUES (?, ?, ?, ?)",
            [
                ("kasir", "Kasir Demo", "cashier", hash_password("kasir123")),
                ("supervisor", "Supervisor Demo", "supervisor", hash_password("supervisor123")),
            ],
        )

    @staticmethod
    def _seed_products(conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if existing:
            return
        products = [
            ("BRIN-TS-001", "8997001000011", "Kaos BRIN Navy - M", "pcs", 95000, 25),
            ("BRIN-TS-002", "8997001000028", "Kaos BRIN Navy - L", "pcs", 95000, 25),
            ("BRIN-JK-001", "8997001000035", "Jaket BRIN", "pcs", 225000, 12),
            ("BRIN-CP-001", "8997001000042", "Topi BRIN", "pcs", 75000, 18),
            ("BRIN-MG-001", "8997001000059", "Mug BRIN", "pcs", 55000, 30),
            ("BRIN-TB-001", "8997001000066", "Tumbler BRIN 500ml", "pcs", 125000, 20),
            ("TOKO-AM-001", "8997002000010", "Air Mineral 600ml", "btl", 5000, 100),
            ("TOKO-KP-001", "8997002000027", "Kopi Botol", "btl", 10000, 60),
            ("TOKO-RT-001", "8997002000034", "Roti Cokelat", "pcs", 8500, 45),
            ("TOKO-SN-001", "8997002000041", "Snack Kentang", "pcs", 12000, 50),
            ("ATK-PEN-001", "8997003000019", "Pulpen Gel Hitam", "pcs", 6000, 80),
            ("ATK-NB-001", "8997003000026", "Notebook A5", "pcs", 18000, 40),
        ]
        conn.executemany(
            "INSERT INTO products(sku, barcode, name, unit, price, stock) VALUES (?, ?, ?, ?, ?, ?)",
            products,
        )
