from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.audit import write_audit
from app.database import Database


def _money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _expected_drawer_cash(conn, shift_id: int) -> int:
    shift = conn.execute(
        "SELECT opening_cash FROM shifts WHERE id=?",
        (shift_id,),
    ).fetchone()
    if not shift:
        raise ValueError("Shift tidak ditemukan")

    cash_received = conn.execute(
        """
        SELECT COALESCE(SUM(sp.amount), 0)
        FROM sale_payments sp
        JOIN sales s ON s.id=sp.sale_id
        WHERE s.shift_id=? AND s.status='COMPLETED' AND sp.method='Tunai'
        """,
        (shift_id,),
    ).fetchone()[0]
    cash_change = conn.execute(
        """
        SELECT COALESCE(SUM(s.change_amount), 0)
        FROM sales s
        WHERE s.shift_id=? AND s.status='COMPLETED'
          AND EXISTS (
              SELECT 1 FROM sale_payments sp
              WHERE sp.sale_id=s.id AND sp.method='Tunai'
          )
        """,
        (shift_id,),
    ).fetchone()[0]
    cash_refund = conn.execute(
        """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM refunds
        WHERE shift_id=? AND refund_method='Tunai'
        """,
        (shift_id,),
    ).fetchone()[0]
    movements = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN movement_type='IN' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN movement_type='OUT' THEN amount ELSE 0 END), 0)
        FROM cash_movements
        WHERE shift_id=?
        """,
        (shift_id,),
    ).fetchone()

    return int(
        shift["opening_cash"]
        + cash_received
        - cash_change
        - cash_refund
        + movements[0]
        - movements[1]
    )


class CustomerService:
    """Local development adapter for member/customer lookup.

    Replace this service with a koperasi membership API client later without
    changing the cashier UI contract.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def search(self, term: str = "", limit: int = 100) -> list[dict]:
        term = term.strip()
        like = f"%{term}%"
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, member_no, name, phone, email, membership_type, active
                FROM customers
                WHERE active=1
                  AND (
                    ?='' OR member_no LIKE ? OR name LIKE ? OR phone LIKE ? OR email LIKE ?
                  )
                ORDER BY name
                LIMIT ?
                """,
                (term, like, like, like, like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, customer_id: int) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, member_no, name, phone, email, membership_type, active
                FROM customers WHERE id=? AND active=1
                """,
                (customer_id,),
            ).fetchone()
        return dict(row) if row else None


class CashMovementService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        *,
        shift_id: int,
        cashier_user_id: int,
        approved_by: int,
        movement_type: str,
        amount: int,
        reason: str,
    ) -> dict:
        movement_type = movement_type.upper().strip()
        reason = reason.strip()
        if movement_type not in {"IN", "OUT"}:
            raise ValueError("Jenis pergerakan kas harus IN atau OUT")
        if amount <= 0:
            raise ValueError("Nominal kas harus lebih dari 0")
        if not reason:
            raise ValueError("Alasan cash-in/cash-out wajib diisi")

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            shift = conn.execute(
                """
                SELECT id FROM shifts
                WHERE id=? AND cashier_user_id=? AND status='OPEN'
                """,
                (shift_id, cashier_user_id),
            ).fetchone()
            if not shift:
                raise ValueError("Shift kasir tidak aktif")

            if movement_type == "OUT":
                available_cash = _expected_drawer_cash(conn, shift_id)
                if amount > available_cash:
                    raise ValueError(
                        "Cash out melebihi kas yang tersedia di laci "
                        f"({available_cash})"
                    )

            cur = conn.execute(
                """
                INSERT INTO cash_movements(
                    shift_id, cashier_user_id, approved_by,
                    movement_type, amount, reason
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    shift_id,
                    cashier_user_id,
                    approved_by,
                    movement_type,
                    amount,
                    reason,
                ),
            )
            movement_id = cur.lastrowid
            write_audit(
                conn,
                user_id=cashier_user_id,
                action=f"CASH_{movement_type}",
                entity_type="cash_movement",
                entity_id=movement_id,
                metadata={
                    "shift_id": shift_id,
                    "amount": amount,
                    "reason": reason,
                    "approved_by": approved_by,
                },
            )
            row = conn.execute(
                """
                SELECT cm.*, u.full_name AS approved_by_name
                FROM cash_movements cm
                JOIN users u ON u.id=cm.approved_by
                WHERE cm.id=?
                """,
                (movement_id,),
            ).fetchone()
        return dict(row)

    def list_for_shift(self, shift_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT cm.*, u.full_name AS approved_by_name
                FROM cash_movements cm
                JOIN users u ON u.id=cm.approved_by
                WHERE cm.shift_id=?
                ORDER BY cm.id DESC
                """,
                (shift_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class RefundService:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _allocate_sale_total(items: list[dict], grand_total: int) -> dict[int, int]:
        """Allocate final invoice total across sale lines deterministically.

        This incorporates transaction-level discount/tax into line refund values
        while guaranteeing that a full return of every line equals grand_total.
        """
        base = sum(max(0, int(item["line_total"])) for item in items)
        if base <= 0:
            return {int(item["id"]): 0 for item in items}

        raw = []
        allocated_sum = 0
        for item in items:
            share = Decimal(grand_total) * Decimal(int(item["line_total"])) / Decimal(base)
            floor_value = int(share.to_integral_value(rounding="ROUND_FLOOR"))
            remainder = share - Decimal(floor_value)
            raw.append((int(item["id"]), floor_value, remainder))
            allocated_sum += floor_value

        remainder_amount = grand_total - allocated_sum
        raw.sort(key=lambda row: (row[2], row[0]), reverse=True)
        allocations = {item_id: floor_value for item_id, floor_value, _ in raw}
        for index in range(remainder_amount):
            item_id = raw[index % len(raw)][0]
            allocations[item_id] += 1
        return allocations

    def get_context(self, invoice_no: str) -> dict:
        with self.db.connect() as conn:
            sale = conn.execute(
                """
                SELECT s.*, u.full_name AS cashier_name
                FROM sales s
                JOIN users u ON u.id=s.cashier_user_id
                WHERE s.invoice_no=?
                """,
                (invoice_no.strip(),),
            ).fetchone()
            if not sale:
                raise ValueError("Invoice tidak ditemukan")
            if sale["status"] == "VOIDED":
                raise ValueError("Transaksi void tidak dapat direfund")

            item_rows = conn.execute(
                "SELECT * FROM sale_items WHERE sale_id=? ORDER BY id",
                (sale["id"],),
            ).fetchall()
            items = [dict(row) for row in item_rows]
            allocations = self._allocate_sale_total(items, int(sale["grand_total"]))

            refunded_rows = conn.execute(
                """
                SELECT ri.sale_item_id,
                       COALESCE(SUM(ri.qty), 0) AS refunded_qty,
                       COALESCE(SUM(ri.amount), 0) AS refunded_amount
                FROM refund_items ri
                JOIN refunds r ON r.id=ri.refund_id
                WHERE r.original_sale_id=?
                GROUP BY ri.sale_item_id
                """,
                (sale["id"],),
            ).fetchall()
            refunded = {
                int(row["sale_item_id"]): {
                    "qty": int(row["refunded_qty"]),
                    "amount": int(row["refunded_amount"]),
                }
                for row in refunded_rows
            }

        data = dict(sale)
        context_items = []
        for item in items:
            item_id = int(item["id"])
            prior = refunded.get(item_id, {"qty": 0, "amount": 0})
            allocated_total = allocations[item_id]
            available_qty = int(item["qty"]) - prior["qty"]
            context_items.append(
                {
                    **item,
                    "allocated_refund_total": allocated_total,
                    "refunded_qty": prior["qty"],
                    "refunded_amount": prior["amount"],
                    "available_qty": available_qty,
                    "remaining_refund_amount": max(0, allocated_total - prior["amount"]),
                }
            )

        data["items"] = context_items
        data["already_refunded_total"] = sum(
            item["refunded_amount"] for item in context_items
        )
        data["remaining_refundable_total"] = max(
            0,
            int(data["grand_total"]) - data["already_refunded_total"],
        )
        return data

    def preview(self, invoice_no: str, selections: dict[int, int]) -> dict:
        context = self.get_context(invoice_no)
        lines = []
        total = 0
        for item in context["items"]:
            sale_item_id = int(item["id"])
            qty = int(selections.get(sale_item_id, 0))
            if qty <= 0:
                continue
            if qty > item["available_qty"]:
                raise ValueError(
                    f"Qty retur {item['product_name']} melebihi sisa yang dapat diretur"
                )

            original_qty = int(item["qty"])
            old_returned_qty = int(item["refunded_qty"])
            new_returned_qty = old_returned_qty + qty
            allocated_total = int(item["allocated_refund_total"])

            cumulative_entitlement = _money(
                Decimal(allocated_total)
                * Decimal(new_returned_qty)
                / Decimal(original_qty)
            )
            amount = cumulative_entitlement - int(item["refunded_amount"])
            amount = max(0, amount)

            lines.append(
                {
                    "sale_item_id": sale_item_id,
                    "product_id": int(item["product_id"]),
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "qty": qty,
                    "amount": amount,
                }
            )
            total += amount

        if not lines:
            raise ValueError("Pilih minimal satu item untuk diretur")
        if total <= 0:
            raise ValueError("Nilai refund tidak valid")
        return {
            "invoice_no": invoice_no,
            "sale_id": int(context["id"]),
            "lines": lines,
            "total_amount": total,
        }

    def create_refund(
        self,
        *,
        invoice_no: str,
        selections: dict[int, int],
        cashier_user_id: int,
        approved_by: int,
        shift_id: int | None,
        refund_method: str,
        reason: str,
    ) -> dict:
        refund_method = refund_method.strip()
        reason = reason.strip()
        if not refund_method:
            raise ValueError("Metode refund wajib dipilih")
        if not reason:
            raise ValueError("Alasan return/refund wajib diisi")
        if not selections:
            raise ValueError("Pilih minimal satu item untuk diretur")

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            sale = conn.execute(
                """
                SELECT * FROM sales
                WHERE invoice_no=?
                """,
                (invoice_no.strip(),),
            ).fetchone()
            if not sale:
                raise ValueError("Invoice tidak ditemukan")
            if sale["status"] == "VOIDED":
                raise ValueError("Transaksi void tidak dapat direfund")

            item_rows = conn.execute(
                "SELECT * FROM sale_items WHERE sale_id=? ORDER BY id",
                (sale["id"],),
            ).fetchall()
            items = [dict(row) for row in item_rows]
            allocations = self._allocate_sale_total(items, int(sale["grand_total"]))

            refunded_rows = conn.execute(
                """
                SELECT ri.sale_item_id,
                       COALESCE(SUM(ri.qty), 0) AS refunded_qty,
                       COALESCE(SUM(ri.amount), 0) AS refunded_amount
                FROM refund_items ri
                JOIN refunds r ON r.id=ri.refund_id
                WHERE r.original_sale_id=?
                GROUP BY ri.sale_item_id
                """,
                (sale["id"],),
            ).fetchall()
            refunded = {
                int(row["sale_item_id"]): {
                    "qty": int(row["refunded_qty"]),
                    "amount": int(row["refunded_amount"]),
                }
                for row in refunded_rows
            }

            selected_lines = []
            total_amount = 0
            item_by_id = {int(item["id"]): item for item in items}
            for sale_item_id_raw, qty_raw in selections.items():
                sale_item_id = int(sale_item_id_raw)
                qty = int(qty_raw)
                if qty <= 0:
                    continue
                item = item_by_id.get(sale_item_id)
                if not item:
                    raise ValueError("Item refund tidak sesuai dengan invoice")

                prior = refunded.get(sale_item_id, {"qty": 0, "amount": 0})
                available_qty = int(item["qty"]) - prior["qty"]
                if qty > available_qty:
                    raise ValueError(
                        f"Qty refund {item['product_name']} melebihi sisa yang dapat diretur"
                    )

                new_returned_qty = prior["qty"] + qty
                allocated_total = allocations[sale_item_id]
                cumulative_entitlement = _money(
                    Decimal(allocated_total)
                    * Decimal(new_returned_qty)
                    / Decimal(int(item["qty"]))
                )
                amount = max(0, cumulative_entitlement - prior["amount"])
                if amount <= 0:
                    raise ValueError(
                        f"Nilai refund {item['product_name']} tidak valid"
                    )

                selected_lines.append(
                    {
                        "sale_item_id": sale_item_id,
                        "product_id": int(item["product_id"]),
                        "sku": item["sku"],
                        "product_name": item["product_name"],
                        "qty": qty,
                        "amount": amount,
                    }
                )
                total_amount += amount

            if not selected_lines:
                raise ValueError("Pilih minimal satu item untuk diretur")
            if total_amount <= 0:
                raise ValueError("Nilai refund tidak valid")

            if refund_method == "Tunai":
                if shift_id is None:
                    raise ValueError("Refund tunai membutuhkan shift kasir aktif")
                shift = conn.execute(
                    """
                    SELECT id FROM shifts
                    WHERE id=? AND cashier_user_id=? AND status='OPEN'
                    """,
                    (shift_id, cashier_user_id),
                ).fetchone()
                if not shift:
                    raise ValueError("Shift kasir tidak aktif untuk refund tunai")
                available_cash = _expected_drawer_cash(conn, shift_id)
                if total_amount > available_cash:
                    raise ValueError(
                        "Refund tunai melebihi kas yang tersedia di laci "
                        f"({available_cash})"
                    )

            refund_no = self._new_code(conn)
            cur = conn.execute(
                """
                INSERT INTO refunds(
                    refund_no, original_sale_id, cashier_user_id, shift_id,
                    approved_by, refund_method, total_amount, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    refund_no,
                    sale["id"],
                    cashier_user_id,
                    shift_id,
                    approved_by,
                    refund_method,
                    total_amount,
                    reason,
                ),
            )
            refund_id = cur.lastrowid

            for line in selected_lines:
                conn.execute(
                    """
                    INSERT INTO refund_items(
                        refund_id, sale_item_id, product_id, sku,
                        product_name, qty, amount
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        refund_id,
                        line["sale_item_id"],
                        line["product_id"],
                        line["sku"],
                        line["product_name"],
                        line["qty"],
                        line["amount"],
                    ),
                )
                conn.execute(
                    """
                    UPDATE products
                    SET stock=stock+?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (line["qty"], line["product_id"]),
                )

            write_audit(
                conn,
                user_id=cashier_user_id,
                action="REFUND_COMPLETED",
                entity_type="refund",
                entity_id=refund_no,
                metadata={
                    "invoice_no": invoice_no,
                    "amount": total_amount,
                    "method": refund_method,
                    "approved_by": approved_by,
                    "reason": reason,
                },
            )

            row = conn.execute(
                """
                SELECT r.*, s.invoice_no, u.full_name AS cashier_name,
                       a.full_name AS approved_by_name
                FROM refunds r
                JOIN sales s ON s.id=r.original_sale_id
                JOIN users u ON u.id=r.cashier_user_id
                JOIN users a ON a.id=r.approved_by
                WHERE r.id=?
                """,
                (refund_id,),
            ).fetchone()
            result_items = conn.execute(
                "SELECT * FROM refund_items WHERE refund_id=? ORDER BY id",
                (refund_id,),
            ).fetchall()

        result = dict(row)
        result["items"] = [dict(item) for item in result_items]
        return result

    def list_for_invoice(self, invoice_no: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*, s.invoice_no, u.full_name AS cashier_name,
                       a.full_name AS approved_by_name
                FROM refunds r
                JOIN sales s ON s.id=r.original_sale_id
                JOIN users u ON u.id=r.cashier_user_id
                JOIN users a ON a.id=r.approved_by
                WHERE s.invoice_no=?
                ORDER BY r.id DESC
                """,
                (invoice_no,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _new_code(conn) -> str:
        import secrets
        from datetime import datetime

        while True:
            code = f"RFD-{datetime.now():%Y%m%d-%H%M%S}-{secrets.randbelow(10000):04d}"
            if not conn.execute(
                "SELECT 1 FROM refunds WHERE refund_no=?",
                (code,),
            ).fetchone():
                return code


class AuditService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_recent(self, limit: int = 200) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT ae.*, u.full_name AS user_name
                FROM audit_events ae
                LEFT JOIN users u ON u.id=ae.user_id
                ORDER BY ae.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
