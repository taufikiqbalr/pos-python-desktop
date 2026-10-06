from __future__ import annotations

from datetime import datetime
from pathlib import Path
import secrets

from app.config import RECEIPT_DIR, STORE_ADDRESS, STORE_NAME, STORE_PHONE, format_rupiah
from app.database import Database
from app.domain import Cart, Product
from app.security import verify_password


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def authenticate(self, username: str, password: str) -> dict | None:
        username = username.strip().lower()
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, username, full_name, role, password_hash, active FROM users WHERE lower(username)=?",
                (username,),
            ).fetchone()
        if not row or not row["active"] or not verify_password(password, row["password_hash"]):
            return None
        return {k: row[k] for k in ("id", "username", "full_name", "role")}


class CatalogService:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _to_product(row) -> Product:
        return Product(
            id=row["id"],
            sku=row["sku"],
            barcode=row["barcode"],
            name=row["name"],
            unit=row["unit"],
            price=row["price"],
            stock=row["stock"],
            active=bool(row["active"]),
        )

    def get_by_barcode_or_sku(self, code: str) -> Product | None:
        code = code.strip()
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM products
                WHERE active=1 AND (barcode=? OR lower(sku)=lower(?))
                LIMIT 1
                """,
                (code, code),
            ).fetchone()
        return self._to_product(row) if row else None

    def search(self, term: str = "", limit: int = 100) -> list[Product]:
        term = term.strip()
        like = f"%{term}%"
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM products
                WHERE active=1
                  AND (?='' OR name LIKE ? OR sku LIKE ? OR barcode LIKE ?)
                ORDER BY name ASC
                LIMIT ?
                """,
                (term, like, like, like, limit),
            ).fetchall()
        return [self._to_product(row) for row in rows]


class SaleService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _new_invoice_no(self, conn) -> str:
        while True:
            invoice = f"POS-{datetime.now():%Y%m%d-%H%M%S}-{secrets.randbelow(10000):04d}"
            exists = conn.execute("SELECT 1 FROM sales WHERE invoice_no=?", (invoice,)).fetchone()
            if not exists:
                return invoice

    def complete_sale(
        self,
        *,
        cart: Cart,
        cashier_user_id: int,
        customer_name: str,
        payment_method: str,
        paid_amount: int,
        change_amount: int,
        notes: str = "",
    ) -> dict:
        if not cart.lines:
            raise ValueError("Keranjang masih kosong")
        if paid_amount < cart.grand_total:
            raise ValueError("Nominal pembayaran kurang")

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            invoice_no = self._new_invoice_no(conn)
            sale_cur = conn.execute(
                """
                INSERT INTO sales(
                    invoice_no, cashier_user_id, customer_name, subtotal,
                    discount_total, tax_total, grand_total, payment_method,
                    paid_amount, change_amount, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_no,
                    cashier_user_id,
                    customer_name.strip() or None,
                    cart.subtotal,
                    cart.discount_total,
                    cart.tax_total,
                    cart.grand_total,
                    payment_method,
                    paid_amount,
                    change_amount,
                    notes.strip() or None,
                ),
            )
            sale_id = sale_cur.lastrowid

            for line in cart.lines:
                stock_row = conn.execute(
                    "SELECT stock FROM products WHERE id=? AND active=1",
                    (line.product.id,),
                ).fetchone()
                if not stock_row or stock_row["stock"] < line.qty:
                    raise ValueError(f"Stok {line.product.name} berubah/tidak mencukupi")

                conn.execute(
                    """
                    INSERT INTO sale_items(
                        sale_id, product_id, sku, product_name, qty,
                        unit_price, discount_amount, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sale_id,
                        line.product.id,
                        line.product.sku,
                        line.product.name,
                        line.qty,
                        line.product.price,
                        line.discount_amount,
                        line.total,
                    ),
                )
                conn.execute(
                    "UPDATE products SET stock=stock-?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (line.qty, line.product.id),
                )

        return self.get_sale(invoice_no)

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.invoice_no, s.customer_name, s.grand_total, s.payment_method,
                       s.created_at, u.full_name AS cashier_name
                FROM sales s
                JOIN users u ON u.id=s.cashier_user_id
                ORDER BY s.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_sale(self, invoice_no: str) -> dict:
        with self.db.connect() as conn:
            sale = conn.execute(
                """
                SELECT s.*, u.full_name AS cashier_name
                FROM sales s JOIN users u ON u.id=s.cashier_user_id
                WHERE s.invoice_no=?
                """,
                (invoice_no,),
            ).fetchone()
            if not sale:
                raise ValueError("Transaksi tidak ditemukan")
            items = conn.execute(
                "SELECT * FROM sale_items WHERE sale_id=? ORDER BY id",
                (sale["id"],),
            ).fetchall()
        data = dict(sale)
        data["items"] = [dict(item) for item in items]
        return data


class ReceiptService:
    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.output_dir = Path(output_dir or RECEIPT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_text(self, sale: dict) -> str:
        width = 42
        lines = [
            STORE_NAME.center(width),
            STORE_ADDRESS.center(width),
            f"Telp: {STORE_PHONE}".center(width),
            "=" * width,
            f"No: {sale['invoice_no']}",
            f"Waktu: {sale['created_at']}",
            f"Kasir: {sale['cashier_name']}",
        ]
        if sale.get("customer_name"):
            lines.append(f"Pelanggan: {sale['customer_name']}")
        lines.append("-" * width)
        for item in sale["items"]:
            lines.append(item["product_name"][:width])
            qty_price = f"{item['qty']} x {format_rupiah(item['unit_price'])}"
            lines.append(f"{qty_price:<24}{format_rupiah(item['line_total']):>18}")
            if item.get("discount_amount"):
                lines.append(f"  Diskon item: -{format_rupiah(item['discount_amount'])}")
        lines.extend(
            [
                "-" * width,
                f"{'Subtotal':<24}{format_rupiah(sale['subtotal']):>18}",
                f"{'Diskon':<24}{('-' + format_rupiah(sale['discount_total'])):>18}",
                f"{'Pajak':<24}{format_rupiah(sale['tax_total']):>18}",
                f"{'TOTAL':<24}{format_rupiah(sale['grand_total']):>18}",
                f"{'Bayar':<24}{format_rupiah(sale['paid_amount']):>18}",
                f"{'Kembali':<24}{format_rupiah(sale['change_amount']):>18}",
                f"Metode: {sale['payment_method']}",
                "=" * width,
                "Terima kasih".center(width),
            ]
        )
        return "\n".join(lines)

    def render_html(self, sale: dict) -> str:
        item_rows = "".join(
            f"<tr><td>{item['product_name']}<br><small>{item['qty']} x {format_rupiah(item['unit_price'])}</small></td>"
            f"<td style='text-align:right'>{format_rupiah(item['line_total'])}</td></tr>"
            for item in sale["items"]
        )
        customer = f"<div>Pelanggan: {sale['customer_name']}</div>" if sale.get("customer_name") else ""
        return f"""
        <html><body style="font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt;">
          <div style="text-align:center"><b>{STORE_NAME}</b><br>{STORE_ADDRESS}<br>Telp: {STORE_PHONE}</div>
          <hr>
          <div>No: {sale['invoice_no']}</div><div>Waktu: {sale['created_at']}</div>
          <div>Kasir: {sale['cashier_name']}</div>{customer}
          <hr>
          <table width="100%">{item_rows}</table>
          <hr>
          <table width="100%">
            <tr><td>Subtotal</td><td align="right">{format_rupiah(sale['subtotal'])}</td></tr>
            <tr><td>Diskon</td><td align="right">-{format_rupiah(sale['discount_total'])}</td></tr>
            <tr><td>Pajak</td><td align="right">{format_rupiah(sale['tax_total'])}</td></tr>
            <tr><td><b>TOTAL</b></td><td align="right"><b>{format_rupiah(sale['grand_total'])}</b></td></tr>
            <tr><td>Bayar</td><td align="right">{format_rupiah(sale['paid_amount'])}</td></tr>
            <tr><td>Kembali</td><td align="right">{format_rupiah(sale['change_amount'])}</td></tr>
          </table>
          <div>Metode: {sale['payment_method']}</div><hr>
          <div style="text-align:center">Terima kasih</div>
        </body></html>
        """

    def save_text(self, sale: dict) -> Path:
        target = self.output_dir / f"{sale['invoice_no']}.txt"
        target.write_text(self.render_text(sale), encoding="utf-8")
        return target
