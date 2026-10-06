import tempfile
import unittest
from pathlib import Path

from app.database import Database
from app.domain import Cart
from app.operations import CashMovementService, CustomerService, RefundService, AuditService
from app.services import AuthService, CatalogService, SaleService, ShiftService


class ProductionControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "pos-stage2-test.db")
        self.db.initialize()
        self.auth = AuthService(self.db)
        self.catalog = CatalogService(self.db)
        self.sales = SaleService(self.db)
        self.shifts = ShiftService(self.db)
        self.customers = CustomerService(self.db)
        self.cash = CashMovementService(self.db)
        self.refunds = RefundService(self.db)
        self.audit = AuditService(self.db)
        self.cashier = self.auth.authenticate("kasir", "kasir123")
        self.supervisor = self.auth.authenticate_supervisor(
            "supervisor", "supervisor123"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _sale(self, shift_id, *, qty=2, customer=None):
        product = self.catalog.get_by_barcode_or_sku("8997001000059")
        cart = Cart()
        cart.add_product(product, qty)
        cart.set_line_discount(0, 10)
        cart.cart_discount_percent = 5
        sale = self.sales.complete_sale(
            cart=cart,
            cashier_user_id=self.cashier["id"],
            customer_name=customer["name"] if customer else "",
            customer_id=customer["id"] if customer else None,
            customer_member_no=customer["member_no"] if customer else None,
            shift_id=shift_id,
            payments=[{"method": "Tunai", "amount": cart.grand_total}],
        )
        return product, cart, sale

    def test_member_identity_is_attached_to_sale(self):
        shift = self.shifts.open_shift(self.cashier["id"], 100_000)
        member = self.customers.search("BRIN-0001")[0]
        _, _, sale = self._sale(shift["id"], customer=member)
        self.assertEqual(sale["customer_id"], member["id"])
        self.assertEqual(sale["customer_member_no"], "BRIN-0001")
        self.assertEqual(sale["customer_name"], member["name"])

    def test_partial_then_full_refund_restores_stock_and_invoice_total(self):
        shift = self.shifts.open_shift(self.cashier["id"], 200_000)
        product, cart, sale = self._sale(shift["id"], qty=2)
        stock_after_sale = self.catalog.get_by_id(product.id).stock

        context = self.refunds.get_context(sale["invoice_no"])
        sale_item_id = context["items"][0]["id"]

        first = self.refunds.create_refund(
            invoice_no=sale["invoice_no"],
            selections={sale_item_id: 1},
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            shift_id=shift["id"],
            refund_method="Tunai",
            reason="Retur 1 barang",
        )
        self.assertGreater(first["total_amount"], 0)
        self.assertEqual(self.catalog.get_by_id(product.id).stock, stock_after_sale + 1)

        second = self.refunds.create_refund(
            invoice_no=sale["invoice_no"],
            selections={sale_item_id: 1},
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            shift_id=shift["id"],
            refund_method="Tunai",
            reason="Retur barang kedua",
        )
        self.assertEqual(
            first["total_amount"] + second["total_amount"],
            sale["grand_total"],
        )
        self.assertEqual(self.catalog.get_by_id(product.id).stock, product.stock)

        final_context = self.refunds.get_context(sale["invoice_no"])
        self.assertEqual(final_context["remaining_refundable_total"], 0)
        self.assertEqual(final_context["items"][0]["available_qty"], 0)

    def test_refund_and_cash_movements_change_expected_drawer_cash(self):
        shift = self.shifts.open_shift(self.cashier["id"], 100_000)
        _, cart, sale = self._sale(shift["id"], qty=1)
        summary_after_sale = self.shifts.summary(shift["id"])
        self.assertEqual(
            summary_after_sale["expected_cash_now"],
            100_000 + cart.grand_total,
        )

        context = self.refunds.get_context(sale["invoice_no"])
        sale_item_id = context["items"][0]["id"]
        refund = self.refunds.create_refund(
            invoice_no=sale["invoice_no"],
            selections={sale_item_id: 1},
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            shift_id=shift["id"],
            refund_method="Tunai",
            reason="Barang dikembalikan",
        )
        summary_after_refund = self.shifts.summary(shift["id"])
        self.assertEqual(
            summary_after_refund["expected_cash_now"],
            100_000 + cart.grand_total - refund["total_amount"],
        )

        self.cash.record(
            shift_id=shift["id"],
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            movement_type="IN",
            amount=20_000,
            reason="Tambah uang kecil",
        )
        self.cash.record(
            shift_id=shift["id"],
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            movement_type="OUT",
            amount=5_000,
            reason="Setor sebagian kas",
        )
        final_summary = self.shifts.summary(shift["id"])
        self.assertEqual(
            final_summary["expected_cash_now"],
            100_000 + cart.grand_total - refund["total_amount"] + 15_000,
        )
        self.assertEqual(final_summary["cash_in"], 20_000)
        self.assertEqual(final_summary["cash_out"], 5_000)
        self.assertEqual(final_summary["cash_refund"], refund["total_amount"])

    def test_void_is_blocked_after_refund(self):
        shift = self.shifts.open_shift(self.cashier["id"], 50_000)
        _, _, sale = self._sale(shift["id"], qty=2)
        context = self.refunds.get_context(sale["invoice_no"])
        sale_item_id = context["items"][0]["id"]

        self.refunds.create_refund(
            invoice_no=sale["invoice_no"],
            selections={sale_item_id: 1},
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            shift_id=shift["id"],
            refund_method="Transfer",
            reason="Partial refund",
        )

        with self.assertRaises(ValueError):
            self.sales.void_sale(
                sale["invoice_no"],
                self.supervisor["id"],
                "Tidak boleh setelah refund",
            )

    def test_critical_operations_write_audit_events(self):
        shift = self.shifts.open_shift(self.cashier["id"], 75_000)
        self.cash.record(
            shift_id=shift["id"],
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            movement_type="IN",
            amount=10_000,
            reason="Tambah pecahan",
        )
        _, _, sale = self._sale(shift["id"], qty=1)
        context = self.refunds.get_context(sale["invoice_no"])
        self.refunds.create_refund(
            invoice_no=sale["invoice_no"],
            selections={context["items"][0]["id"]: 1},
            cashier_user_id=self.cashier["id"],
            approved_by=self.supervisor["id"],
            shift_id=shift["id"],
            refund_method="Transfer",
            reason="Audit test",
        )

        actions = {event["action"] for event in self.audit.list_recent()}
        self.assertIn("SHIFT_OPENED", actions)
        self.assertIn("CASH_IN", actions)
        self.assertIn("SALE_COMPLETED", actions)
        self.assertIn("REFUND_COMPLETED", actions)


if __name__ == "__main__":
    unittest.main()
