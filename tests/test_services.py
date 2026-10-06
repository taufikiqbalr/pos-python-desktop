import tempfile
import unittest
from pathlib import Path

from app.database import Database
from app.domain import Cart
from app.services import AuthService, CatalogService, SaleService, ShiftService


class OperationalServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "pos-test.db")
        self.db.initialize()
        self.auth = AuthService(self.db)
        self.catalog = CatalogService(self.db)
        self.sales = SaleService(self.db)
        self.shifts = ShiftService(self.db)
        self.cashier = self.auth.authenticate("kasir", "kasir123")
        self.supervisor = self.auth.authenticate_supervisor("supervisor", "supervisor123")

    def tearDown(self):
        self.tmp.cleanup()

    def test_split_payment_and_shift_reconciliation(self):
        shift = self.shifts.open_shift(self.cashier["id"], 100_000)
        product = self.catalog.get_by_barcode_or_sku("8997002000010")
        cart = Cart()
        cart.add_product(product, 2)

        sale = self.sales.complete_sale(
            cart=cart,
            cashier_user_id=self.cashier["id"],
            customer_name="Anggota Demo",
            shift_id=shift["id"],
            payments=[
                {"method": "Tunai", "amount": 5_000},
                {"method": "QRIS", "amount": 5_000},
            ],
        )

        self.assertEqual(sale["grand_total"], 10_000)
        self.assertEqual(len(sale["payments"]), 2)
        summary = self.shifts.summary(shift["id"])
        self.assertEqual(summary["sales_count"], 1)
        self.assertEqual(summary["cash_received"], 5_000)
        self.assertEqual(summary["expected_cash_now"], 105_000)

        closed = self.shifts.close_shift(shift["id"], 105_000)
        self.assertEqual(closed["cash_difference"], 0)
        self.assertEqual(closed["status"], "CLOSED")

    def test_hold_and_resume_payload(self):
        product = self.catalog.get_by_barcode_or_sku("8997001000059")
        cart = Cart()
        cart.add_product(product, 2)
        cart.set_line_discount(0, 10)
        cart.cart_discount_percent = 5

        held = self.sales.hold_cart(
            cart=cart,
            cashier_user_id=self.cashier["id"],
            customer_name="Taufik",
            notes="Ambil lagi nanti",
        )
        loaded = self.sales.get_held(held["hold_no"], self.cashier["id"])

        self.assertEqual(loaded["customer_name"], "Taufik")
        self.assertEqual(len(loaded["items"]), 1)
        self.assertEqual(loaded["items"][0]["qty"], 2)
        self.assertEqual(loaded["items"][0]["discount_percent"], "10")
        self.sales.delete_held(held["hold_no"], self.cashier["id"])
        self.assertEqual(self.sales.list_held(self.cashier["id"]), [])

    def test_supervised_void_restores_stock(self):
        shift = self.shifts.open_shift(self.cashier["id"], 50_000)
        product = self.catalog.get_by_barcode_or_sku("8997001000059")
        stock_before = product.stock
        cart = Cart()
        cart.add_product(product)

        sale = self.sales.complete_sale(
            cart=cart,
            cashier_user_id=self.cashier["id"],
            customer_name="",
            shift_id=shift["id"],
            payments=[{"method": "Tunai", "amount": product.price}],
        )
        stock_after_sale = self.catalog.get_by_id(product.id).stock
        self.assertEqual(stock_after_sale, stock_before - 1)

        voided = self.sales.void_sale(
            sale["invoice_no"],
            self.supervisor["id"],
            "Salah scan",
        )
        self.assertEqual(voided["status"], "VOIDED")
        self.assertEqual(self.catalog.get_by_id(product.id).stock, stock_before)
        self.assertEqual(self.shifts.summary(shift["id"])["sales_count"], 0)


if __name__ == "__main__":
    unittest.main()
