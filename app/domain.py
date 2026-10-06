from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


def _money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Product:
    id: int
    sku: str
    barcode: str
    name: str
    unit: str
    price: int
    stock: float
    active: bool = True


@dataclass
class CartLine:
    product: Product
    qty: int = 1
    discount_percent: Decimal = Decimal("0")

    @property
    def gross(self) -> int:
        return self.product.price * self.qty

    @property
    def discount_amount(self) -> int:
        pct = max(Decimal("0"), min(Decimal("100"), self.discount_percent))
        return _money(Decimal(self.gross) * pct / Decimal("100"))

    @property
    def total(self) -> int:
        return self.gross - self.discount_amount


class Cart:
    def __init__(self, tax_percent: float = 0.0) -> None:
        self.lines: list[CartLine] = []
        self.cart_discount_percent = Decimal("0")
        self.tax_percent = Decimal(str(tax_percent))

    def clear(self) -> None:
        self.lines.clear()
        self.cart_discount_percent = Decimal("0")

    def add_product(self, product: Product, qty: int = 1) -> None:
        if qty <= 0:
            raise ValueError("Qty harus lebih dari 0")
        for line in self.lines:
            if line.product.id == product.id:
                if line.qty + qty > int(product.stock):
                    raise ValueError(f"Stok {product.name} tidak mencukupi")
                line.qty += qty
                return
        if qty > int(product.stock):
            raise ValueError(f"Stok {product.name} tidak mencukupi")
        self.lines.append(CartLine(product=product, qty=qty))

    def increment(self, index: int) -> None:
        line = self.lines[index]
        if line.qty + 1 > int(line.product.stock):
            raise ValueError(f"Stok {line.product.name} tidak mencukupi")
        line.qty += 1

    def decrement(self, index: int) -> None:
        line = self.lines[index]
        if line.qty <= 1:
            self.remove(index)
        else:
            line.qty -= 1

    def remove(self, index: int) -> None:
        self.lines.pop(index)

    @property
    def item_count(self) -> int:
        return sum(line.qty for line in self.lines)

    @property
    def subtotal(self) -> int:
        return sum(line.gross for line in self.lines)

    @property
    def item_discount_total(self) -> int:
        return sum(line.discount_amount for line in self.lines)

    @property
    def after_item_discount(self) -> int:
        return self.subtotal - self.item_discount_total

    @property
    def cart_discount_amount(self) -> int:
        pct = max(Decimal("0"), min(Decimal("100"), self.cart_discount_percent))
        return _money(Decimal(self.after_item_discount) * pct / Decimal("100"))

    @property
    def discount_total(self) -> int:
        return self.item_discount_total + self.cart_discount_amount

    @property
    def taxable_amount(self) -> int:
        return self.subtotal - self.discount_total

    @property
    def tax_total(self) -> int:
        pct = max(Decimal("0"), self.tax_percent)
        return _money(Decimal(self.taxable_amount) * pct / Decimal("100"))

    @property
    def grand_total(self) -> int:
        return self.taxable_amount + self.tax_total
