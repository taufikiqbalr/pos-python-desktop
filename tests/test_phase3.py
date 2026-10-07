import tempfile
import unittest
from pathlib import Path

from app.database import Database
from app.domain import Cart
from app.hardware import EscPosHardwareService
from app.identity import TERMINAL_IDENTITY
from app.operations import CustomerService
from app.services import AuthService, CatalogService, SaleService, ShiftService
from app.sync import SyncService


class FakeInventoryApi:
    def lookup_product(self, code):
        if code != "REMOTE-001":
            return None
        return {
            "sku": "REMOTE-001",
            "barcode": "990000000001",
            "name": "Produk Remote",
            "unit": "pcs",
            "price": 25000,
            "stock": 7,
            "active": True,
        }

    def search_products(self, term, limit=100):
        product = self.lookup_product("REMOTE-001")
        return [product] if "remote" in term.lower() or not term else []


class FakeMembershipApi:
    def search_members(self, term, limit=100):
        return [
            {
                "member_no": "API-0001",
                "name": "Anggota API",
                "phone": "081234567890",
                "email": "api@example.local",
                "membership_type": "MEMBER",
                "active": True,
            }
        ]


class Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "phase3.db")
        self.db.initialize()
        self.auth = AuthService(self.db)
        self.cashier = self.auth.authenticate("kasir", "kasir123")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sale_has_terminal_identity_and_outbox_event(self):
        catalog = CatalogService(self.db)
        shifts = ShiftService(self.db)
        sales = SaleService(self.db)
        shift = shifts.open_shift(self.cashier["id"], 100_000)

        product = catalog.get_by_barcode_or_sku("8997002000010")
        cart = Cart()
        cart.add_product(product)

        sale = sales.complete_sale(
            cart=cart,
            cashier_user_id=self.cashier["id"],
            customer_name="",
            payments=[{"method": "Tunai", "amount": product.price}],
            shift_id=shift["id"],
        )

        self.assertEqual(sale["store_id"], TERMINAL_IDENTITY.store_id)
        self.assertEqual(sale["register_id"], TERMINAL_IDENTITY.register_id)
        self.assertEqual(sale["device_id"], TERMINAL_IDENTITY.device_id)

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, aggregate_id, store_id, register_id, device_id
                FROM integration_outbox
                ORDER BY id
                """
            ).fetchall()

        event_types = [row["event_type"] for row in rows]
        self.assertIn("shift.opened", event_types)
        self.assertIn("sale.completed", event_types)
        sale_event = next(row for row in rows if row["event_type"] == "sale.completed")
        self.assertEqual(sale_event["aggregate_id"], sale["invoice_no"])
        self.assertEqual(sale_event["store_id"], TERMINAL_IDENTITY.store_id)

        sync = SyncService(self.db)
        self.assertGreaterEqual(sync.pending_count(), 2)

    def test_remote_inventory_is_cached_locally(self):
        catalog = CatalogService(
            self.db,
            inventory_api=FakeInventoryApi(),
            fallback_local=True,
        )
        product = catalog.get_by_barcode_or_sku("REMOTE-001")
        self.assertIsNotNone(product)
        self.assertEqual(product.name, "Produk Remote")
        self.assertEqual(product.price, 25000)

        local_catalog = CatalogService(self.db)
        cached = local_catalog.get_by_barcode_or_sku("REMOTE-001")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.stock, 7)

    def test_remote_membership_is_cached_locally(self):
        members = CustomerService(
            self.db,
            membership_api=FakeMembershipApi(),
            fallback_local=True,
        )
        result = members.search("API-0001")
        self.assertEqual(result[0]["member_no"], "API-0001")
        self.assertEqual(result[0]["name"], "Anggota API")

        local_members = CustomerService(self.db)
        cached = local_members.search("API-0001")
        self.assertEqual(cached[0]["name"], "Anggota API")

    def test_default_hardware_mode_does_not_require_escpos_import(self):
        hardware = EscPosHardwareService()
        status = hardware.status()
        # CI/default configuration keeps hardware optional.
        if not status.printer_enabled:
            self.assertIn("disabled", status.description.lower())


if __name__ == "__main__":
    unittest.main()
