from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
import secrets

from app.audit import write_audit
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

    def authenticate_supervisor(self, username: str, password: str) -> dict | None:
        user = self.authenticate(username, password)
        if not user or user["role"] not in {"supervisor", "admin"}:
            return None
        return user


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

    def get_by_id(self, product_id: int) -> Product | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id=? AND active=1",
                (product_id,),
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


class ShiftService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_open_shift(self, cashier_user_id: int) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM shifts
                WHERE cashier_user_id=? AND status='OPEN'
                ORDER BY id DESC LIMIT 1
                """,
                (cashier_user_id,),
            ).fetchone()
        return dict(row) if row else None

    def open_shift(self, cashier_user_id: int, opening_cash: int) -> dict:
        if opening_cash < 0:
            raise ValueError("Kas awal tidak boleh negatif")
        if self.get_open_shift(cashier_user_id):
            raise ValueError("Kasir masih memiliki shift yang aktif")
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO shifts(cashier_user_id, opening_cash) VALUES (?, ?)",
                (cashier_user_id, opening_cash),
            )
            shift_id = cur.lastrowid
            write_audit(
                conn,
                user_id=cashier_user_id,
                action="SHIFT_OPENED",
                entity_type="shift",
                entity_id=shift_id,
                metadata={"opening_cash": opening_cash},
            )
            row = conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
        return dict(row)

    def summary(self, shift_id: int) -> dict:
        with self.db.connect() as conn:
            shift = conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
            if not shift:
                raise ValueError("Shift tidak ditemukan")

            sales = conn.execute(
                """
                SELECT COUNT(*) AS sales_count,
                       COALESCE(SUM(grand_total), 0) AS sales_total
                FROM sales
                WHERE shift_id=? AND status='COMPLETED'
                """,
                (shift_id,),
            ).fetchone()

            cash = conn.execute(
                """
                SELECT COALESCE(SUM(sp.amount), 0) AS cash_received
                FROM sale_payments sp
                JOIN sales s ON s.id=sp.sale_id
                WHERE s.shift_id=? AND s.status='COMPLETED' AND sp.method='Tunai'
                """,
                (shift_id,),
            ).fetchone()

            cash_change = conn.execute(
                """
                SELECT COALESCE(SUM(s.change_amount), 0) AS cash_change
                FROM sales s
                WHERE s.shift_id=? AND s.status='COMPLETED'
                  AND EXISTS (
                      SELECT 1 FROM sale_payments sp
                      WHERE sp.sale_id=s.id AND sp.method='Tunai'
                  )
                """,
                (shift_id,),
            ).fetchone()

            refunds = conn.execute(
                """
                SELECT COUNT(*) AS refund_count,
                       COALESCE(SUM(total_amount), 0) AS refund_total,
                       COALESCE(SUM(CASE WHEN refund_method='Tunai' THEN total_amount ELSE 0 END), 0)
                           AS cash_refund
                FROM refunds
                WHERE shift_id=?
                """,
                (shift_id,),
            ).fetchone()

            movements = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN movement_type='IN' THEN amount ELSE 0 END), 0) AS cash_in,
                    COALESCE(SUM(CASE WHEN movement_type='OUT' THEN amount ELSE 0 END), 0) AS cash_out
                FROM cash_movements
                WHERE shift_id=?
                """,
                (shift_id,),
            ).fetchone()

            breakdown_rows = conn.execute(
                """
                SELECT sp.method, COALESCE(SUM(sp.amount), 0) AS amount
                FROM sale_payments sp
                JOIN sales s ON s.id=sp.sale_id
                WHERE s.shift_id=? AND s.status='COMPLETED'
                GROUP BY sp.method
                ORDER BY sp.method
                """,
                (shift_id,),
            ).fetchall()

            refund_breakdown_rows = conn.execute(
                """
                SELECT refund_method AS method, COALESCE(SUM(total_amount), 0) AS amount
                FROM refunds
                WHERE shift_id=?
                GROUP BY refund_method
                ORDER BY refund_method
                """,
                (shift_id,),
            ).fetchall()

        result = dict(shift)
        result["sales_count"] = int(sales["sales_count"])
        result["sales_total"] = int(sales["sales_total"])
        result["refund_count"] = int(refunds["refund_count"])
        result["refund_total"] = int(refunds["refund_total"])
        result["net_sales_total"] = result["sales_total"] - result["refund_total"]
        result["cash_received"] = int(cash["cash_received"])
        result["cash_change"] = int(cash_change["cash_change"])
        result["cash_refund"] = int(refunds["cash_refund"])
        result["cash_in"] = int(movements["cash_in"])
        result["cash_out"] = int(movements["cash_out"])
        result["expected_cash_now"] = (
            result["opening_cash"]
            + result["cash_received"]
            - result["cash_change"]
            - result["cash_refund"]
            + result["cash_in"]
            - result["cash_out"]
        )
        result["payment_breakdown"] = [dict(row) for row in breakdown_rows]
        result["refund_breakdown"] = [dict(row) for row in refund_breakdown_rows]
        return result

    def close_shift(self, shift_id: int, closing_cash: int, notes: str = "") -> dict:
        if closing_cash < 0:
            raise ValueError("Kas akhir tidak boleh negatif")
        summary = self.summary(shift_id)
        if summary["status"] != "OPEN":
            raise ValueError("Shift sudah ditutup")
        expected = summary["expected_cash_now"]
        difference = closing_cash - expected
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE shifts
                SET closing_cash=?, expected_cash=?, cash_difference=?,
                    close_notes=?, closed_at=CURRENT_TIMESTAMP, status='CLOSED'
                WHERE id=? AND status='OPEN'
                """,
                (closing_cash, expected, difference, notes.strip() or None, shift_id),
            )
            write_audit(
                conn,
                user_id=int(summary["cashier_user_id"]),
                action="SHIFT_CLOSED",
                entity_type="shift",
                entity_id=shift_id,
                metadata={
                    "expected_cash": expected,
                    "closing_cash": closing_cash,
                    "cash_difference": difference,
                    "notes": notes.strip(),
                },
            )
        result = self.summary(shift_id)
        result["closing_cash"] = closing_cash
        result["cash_difference"] = difference
        return result

class SaleService:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _new_code(conn, *, prefix: str, table: str, column: str) -> str:
        while True:
            code = f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}-{secrets.randbelow(10000):04d}"
            exists = conn.execute(
                f"SELECT 1 FROM {table} WHERE {column}=?",
                (code,),
            ).fetchone()
            if not exists:
                return code

    def complete_sale(
        self,
        *,
        cart: Cart,
        cashier_user_id: int,
        customer_name: str,
        payments: list[dict] | None = None,
        shift_id: int | None = None,
        notes: str = "",
        customer_id: int | None = None,
        customer_member_no: str | None = None,
        payment_method: str | None = None,
        paid_amount: int | None = None,
        change_amount: int | None = None,
    ) -> dict:
        if not cart.lines:
            raise ValueError("Keranjang masih kosong")

        if payments is None:
            if not payment_method or paid_amount is None:
                raise ValueError("Informasi pembayaran belum lengkap")
            payments = [{"method": payment_method, "amount": int(paid_amount)}]

        normalized_payments: list[dict] = []
        for payment in payments:
            method = str(payment.get("method", "")).strip()
            amount = int(payment.get("amount", 0))
            if method and amount > 0:
                normalized_payments.append(
                    {
                        "method": method,
                        "amount": amount,
                        "reference": str(payment.get("reference", "")).strip() or None,
                    }
                )

        total_paid = sum(item["amount"] for item in normalized_payments)
        if total_paid < cart.grand_total:
            raise ValueError("Nominal pembayaran kurang")

        computed_change = total_paid - cart.grand_total
        if computed_change > 0 and not any(p["method"] == "Tunai" for p in normalized_payments):
            raise ValueError("Kelebihan pembayaran hanya diperbolehkan jika ada pembayaran tunai")

        if change_amount is not None and change_amount != computed_change:
            raise ValueError("Nilai kembalian tidak konsisten dengan total pembayaran")

        methods = list(dict.fromkeys(p["method"] for p in normalized_payments))
        method_summary = " + ".join(methods)

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            if shift_id is not None:
                shift = conn.execute(
                    """
                    SELECT id FROM shifts
                    WHERE id=? AND cashier_user_id=? AND status='OPEN'
                    """,
                    (shift_id, cashier_user_id),
                ).fetchone()
                if not shift:
                    raise ValueError("Shift kasir tidak aktif")

            resolved_customer_name = customer_name.strip() or None
            resolved_member_no = customer_member_no.strip() if customer_member_no else None
            if customer_id is not None:
                customer = conn.execute(
                    """
                    SELECT id, member_no, name FROM customers
                    WHERE id=? AND active=1
                    """,
                    (customer_id,),
                ).fetchone()
                if not customer:
                    raise ValueError("Data anggota/pelanggan tidak aktif atau tidak ditemukan")
                resolved_customer_name = customer["name"]
                resolved_member_no = customer["member_no"]

            invoice_no = self._new_code(
                conn,
                prefix="POS",
                table="sales",
                column="invoice_no",
            )
            sale_cur = conn.execute(
                """
                INSERT INTO sales(
                    invoice_no, cashier_user_id, shift_id, customer_id,
                    customer_member_no, customer_name, subtotal,
                    discount_total, tax_total, grand_total, payment_method,
                    paid_amount, change_amount, notes, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED')
                """,
                (
                    invoice_no,
                    cashier_user_id,
                    shift_id,
                    customer_id,
                    resolved_member_no,
                    resolved_customer_name,
                    cart.subtotal,
                    cart.discount_total,
                    cart.tax_total,
                    cart.grand_total,
                    method_summary,
                    total_paid,
                    computed_change,
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

            conn.executemany(
                """
                INSERT INTO sale_payments(sale_id, method, amount, reference)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (sale_id, p["method"], p["amount"], p["reference"])
                    for p in normalized_payments
                ],
            )
            write_audit(
                conn,
                user_id=cashier_user_id,
                action="SALE_COMPLETED",
                entity_type="sale",
                entity_id=invoice_no,
                metadata={
                    "grand_total": cart.grand_total,
                    "payment_method": method_summary,
                    "shift_id": shift_id,
                    "customer_member_no": resolved_member_no,
                },
            )

        return self.get_sale(invoice_no)

    def hold_cart(
        self,
        *,
        cart: Cart,
        cashier_user_id: int,
        customer_name: str,
        notes: str = "",
        customer_id: int | None = None,
        customer_member_no: str | None = None,
    ) -> dict:
        if not cart.lines:
            raise ValueError("Keranjang masih kosong")
        payload = [
            {
                "product_id": line.product.id,
                "sku": line.product.sku,
                "qty": line.qty,
                "discount_percent": str(line.discount_percent),
            }
            for line in cart.lines
        ]
        with self.db.connect() as conn:
            resolved_customer_name = customer_name.strip() or None
            resolved_member_no = customer_member_no.strip() if customer_member_no else None
            if customer_id is not None:
                customer = conn.execute(
                    "SELECT id, member_no, name FROM customers WHERE id=? AND active=1",
                    (customer_id,),
                ).fetchone()
                if not customer:
                    raise ValueError("Data anggota/pelanggan tidak aktif atau tidak ditemukan")
                resolved_customer_name = customer["name"]
                resolved_member_no = customer["member_no"]

            hold_no = self._new_code(
                conn,
                prefix="HOLD",
                table="held_sales",
                column="hold_no",
            )
            conn.execute(
                """
                INSERT INTO held_sales(
                    hold_no, cashier_user_id, customer_id, customer_member_no,
                    customer_name, cart_discount_percent, notes, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hold_no,
                    cashier_user_id,
                    customer_id,
                    resolved_member_no,
                    resolved_customer_name,
                    str(cart.cart_discount_percent),
                    notes.strip() or None,
                    json.dumps(payload),
                ),
            )
            write_audit(
                conn,
                user_id=cashier_user_id,
                action="HOLD_CREATED",
                entity_type="held_sale",
                entity_id=hold_no,
                metadata={"customer_member_no": resolved_member_no, "item_count": cart.item_count},
            )
        return self.get_held(hold_no, cashier_user_id)

    def list_held(self, cashier_user_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM held_sales
                WHERE cashier_user_id=?
                ORDER BY id DESC
                """,
                (cashier_user_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item["payload_json"])
            item["item_count"] = sum(int(line["qty"]) for line in payload)
            result.append(item)
        return result

    def get_held(self, hold_no: str, cashier_user_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM held_sales
                WHERE hold_no=? AND cashier_user_id=?
                """,
                (hold_no, cashier_user_id),
            ).fetchone()
        if not row:
            raise ValueError("Transaksi hold tidak ditemukan")
        data = dict(row)
        data["items"] = json.loads(data.pop("payload_json"))
        return data

    def delete_held(
        self,
        hold_no: str,
        cashier_user_id: int,
        audit_action: str = "HOLD_DELETED",
    ) -> None:
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM held_sales WHERE hold_no=? AND cashier_user_id=?",
                (hold_no, cashier_user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("Transaksi hold tidak ditemukan")
            write_audit(
                conn,
                user_id=cashier_user_id,
                action=audit_action,
                entity_type="held_sale",
                entity_id=hold_no,
            )

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.invoice_no, s.customer_member_no, s.customer_name,
                       s.grand_total, s.payment_method, s.status, s.created_at,
                       u.full_name AS cashier_name,
                       COALESCE((
                           SELECT SUM(r.total_amount)
                           FROM refunds r
                           WHERE r.original_sale_id=s.id
                       ), 0) AS refund_total
                FROM sales s
                JOIN users u ON u.id=s.cashier_user_id
                ORDER BY s.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item["status"] == "VOIDED":
                item["display_status"] = "VOIDED"
            elif item["refund_total"] >= item["grand_total"] and item["refund_total"] > 0:
                item["display_status"] = "REFUNDED"
            elif item["refund_total"] > 0:
                item["display_status"] = "PARTIAL REFUND"
            else:
                item["display_status"] = "COMPLETED"
            result.append(item)
        return result

    def get_sale(self, invoice_no: str) -> dict:
        with self.db.connect() as conn:
            sale = conn.execute(
                """
                SELECT s.*, u.full_name AS cashier_name,
                       vu.full_name AS voided_by_name
                FROM sales s
                JOIN users u ON u.id=s.cashier_user_id
                LEFT JOIN users vu ON vu.id=s.voided_by
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
            payments = conn.execute(
                "SELECT method, amount, reference FROM sale_payments WHERE sale_id=? ORDER BY id",
                (sale["id"],),
            ).fetchall()
            refunds = conn.execute(
                """
                SELECT r.refund_no, r.refund_method, r.total_amount, r.reason,
                       r.created_at, a.full_name AS approved_by_name
                FROM refunds r
                JOIN users a ON a.id=r.approved_by
                WHERE r.original_sale_id=?
                ORDER BY r.id
                """,
                (sale["id"],),
            ).fetchall()
        data = dict(sale)
        data["items"] = [dict(item) for item in items]
        data["payments"] = [dict(payment) for payment in payments]
        if not data["payments"] and data.get("payment_method"):
            data["payments"] = [
                {
                    "method": data["payment_method"],
                    "amount": data["paid_amount"],
                    "reference": None,
                }
            ]
        data["refunds"] = [dict(row) for row in refunds]
        data["refund_total"] = sum(int(row["total_amount"]) for row in data["refunds"])
        return data

    def void_sale(self, invoice_no: str, supervisor_user_id: int, reason: str) -> dict:
        reason = reason.strip()
        if not reason:
            raise ValueError("Alasan void wajib diisi")

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            sale = conn.execute(
                "SELECT * FROM sales WHERE invoice_no=?",
                (invoice_no,),
            ).fetchone()
            if not sale:
                raise ValueError("Transaksi tidak ditemukan")
            if sale["status"] != "COMPLETED":
                raise ValueError("Transaksi sudah tidak berstatus COMPLETED")
            if conn.execute(
                "SELECT 1 FROM refunds WHERE original_sale_id=? LIMIT 1",
                (sale["id"],),
            ).fetchone():
                raise ValueError("Transaksi yang sudah memiliki refund tidak dapat di-void")

            if sale["shift_id"]:
                shift = conn.execute(
                    "SELECT status FROM shifts WHERE id=?",
                    (sale["shift_id"],),
                ).fetchone()
                if shift and shift["status"] != "OPEN":
                    raise ValueError(
                        "Transaksi dari shift yang sudah ditutup tidak dapat di-void. "
                        "Gunakan proses return/refund."
                    )

            items = conn.execute(
                "SELECT product_id, qty FROM sale_items WHERE sale_id=?",
                (sale["id"],),
            ).fetchall()
            for item in items:
                conn.execute(
                    """
                    UPDATE products
                    SET stock=stock+?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (item["qty"], item["product_id"]),
                )

            conn.execute(
                """
                UPDATE sales
                SET status='VOIDED', voided_at=CURRENT_TIMESTAMP,
                    void_reason=?, voided_by=?
                WHERE id=?
                """,
                (reason, supervisor_user_id, sale["id"]),
            )
            write_audit(
                conn,
                user_id=supervisor_user_id,
                action="SALE_VOIDED",
                entity_type="sale",
                entity_id=invoice_no,
                metadata={"reason": reason},
            )

        return self.get_sale(invoice_no)

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
        if sale.get("status") == "VOIDED":
            lines.append("*** TRANSAKSI VOID ***".center(width))
        if sale.get("customer_name"):
            lines.append(f"Pelanggan: {sale['customer_name']}")
        if sale.get("customer_member_no"):
            lines.append(f"No. Anggota: {sale['customer_member_no']}")
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
            ]
        )
        for payment in sale.get("payments", []):
            lines.append(
                f"{('Bayar ' + payment['method']):<24}{format_rupiah(payment['amount']):>18}"
            )
        lines.append(f"{'Kembali':<24}{format_rupiah(sale['change_amount']):>18}")
        if sale.get("refund_total", 0):
            lines.append(f"{'Sudah direfund':<24}{format_rupiah(sale['refund_total']):>18}")
        if sale.get("status") == "VOIDED":
            lines.extend(
                [
                    "-" * width,
                    f"Void: {sale.get('void_reason') or '-'}",
                    f"Otorisasi: {sale.get('voided_by_name') or '-'}",
                ]
            )
        lines.extend(["=" * width, "Terima kasih".center(width)])
        return "\n".join(lines)

    def render_html(self, sale: dict) -> str:
        item_rows = "".join(
            f"<tr><td>{escape(str(item['product_name']))}<br>"
            f"<small>{item['qty']} x {format_rupiah(item['unit_price'])}</small></td>"
            f"<td style='text-align:right'>{format_rupiah(item['line_total'])}</td></tr>"
            for item in sale["items"]
        )
        customer = (
            f"<div>Pelanggan: {escape(str(sale['customer_name']))}</div>"
            if sale.get("customer_name")
            else ""
        )
        member = (
            f"<div>No. Anggota: {escape(str(sale['customer_member_no']))}</div>"
            if sale.get("customer_member_no")
            else ""
        )
        refunded = (
            f"<tr><td>Sudah direfund</td><td align='right'>{format_rupiah(sale.get('refund_total', 0))}</td></tr>"
            if sale.get("refund_total", 0)
            else ""
        )
        payment_rows = "".join(
            f"<tr><td>Bayar {escape(str(payment['method']))}</td>"
            f"<td align='right'>{format_rupiah(payment['amount'])}</td></tr>"
            for payment in sale.get("payments", [])
        )
        void_banner = (
            "<div style='text-align:center;color:#b42318'><b>TRANSAKSI VOID</b></div>"
            if sale.get("status") == "VOIDED"
            else ""
        )
        void_detail = (
            f"<hr><div>Alasan void: {escape(str(sale.get('void_reason') or '-'))}</div>"
            f"<div>Otorisasi: {escape(str(sale.get('voided_by_name') or '-'))}</div>"
            if sale.get("status") == "VOIDED"
            else ""
        )
        return f"""
        <html><body style="font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt;">
          <div style="text-align:center"><b>{escape(STORE_NAME)}</b><br>{escape(STORE_ADDRESS)}<br>Telp: {escape(STORE_PHONE)}</div>
          {void_banner}
          <hr>
          <div>No: {escape(str(sale['invoice_no']))}</div><div>Waktu: {escape(str(sale['created_at']))}</div>
          <div>Kasir: {escape(str(sale['cashier_name']))}</div>{customer}{member}
          <hr>
          <table width="100%">{item_rows}</table>
          <hr>
          <table width="100%">
            <tr><td>Subtotal</td><td align="right">{format_rupiah(sale['subtotal'])}</td></tr>
            <tr><td>Diskon</td><td align="right">-{format_rupiah(sale['discount_total'])}</td></tr>
            <tr><td>Pajak</td><td align="right">{format_rupiah(sale['tax_total'])}</td></tr>
            <tr><td><b>TOTAL</b></td><td align="right"><b>{format_rupiah(sale['grand_total'])}</b></td></tr>
            {payment_rows}
            <tr><td>Kembali</td><td align="right">{format_rupiah(sale['change_amount'])}</td></tr>
            {refunded}
          </table>
          {void_detail}
          <hr><div style="text-align:center">Terima kasih</div>
        </body></html>
        """

    def save_text(self, sale: dict) -> Path:
        target = self.output_dir / f"{sale['invoice_no']}.txt"
        target.write_text(self.render_text(sale), encoding="utf-8")
        return target
