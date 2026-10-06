import unittest
from decimal import Decimal

from app.domain import Cart, Product


class CartTests(unittest.TestCase):
    def setUp(self):
        self.product = Product(1, "SKU-1", "123", "Produk", "pcs", 10000, 10)

    def test_add_and_totals(self):
        cart = Cart(tax_percent=10)
        cart.add_product(self.product, qty=2)
        cart.cart_discount_percent = Decimal("10")
        self.assertEqual(cart.subtotal, 20000)
        self.assertEqual(cart.discount_total, 2000)
        self.assertEqual(cart.tax_total, 1800)
        self.assertEqual(cart.grand_total, 19800)

    def test_item_and_cart_discount(self):
        cart = Cart()
        cart.add_product(self.product, qty=2)
        cart.set_line_discount(0, 10)
        cart.cart_discount_percent = Decimal("5")
        self.assertEqual(cart.item_discount_total, 2000)
        self.assertEqual(cart.cart_discount_amount, 900)
        self.assertEqual(cart.grand_total, 17100)

    def test_cannot_exceed_stock(self):
        cart = Cart()
        with self.assertRaises(ValueError):
            cart.add_product(self.product, qty=11)

    def test_increment_existing_line(self):
        cart = Cart()
        cart.add_product(self.product)
        cart.add_product(self.product)
        self.assertEqual(len(cart.lines), 1)
        self.assertEqual(cart.lines[0].qty, 2)


if __name__ == "__main__":
    unittest.main()
