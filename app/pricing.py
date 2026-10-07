from __future__ import annotations

from decimal import Decimal

from app.identity import TERMINAL_IDENTITY
from app.integrations.clients import IntegrationError, PricingApiClient


class PricingService:
    def __init__(self, pricing_api: PricingApiClient | None = None) -> None:
        self.pricing_api = pricing_api

    @property
    def enabled(self) -> bool:
        return self.pricing_api is not None

    def quote(self, cart, member_no: str | None) -> dict:
        if not self.pricing_api:
            raise IntegrationError("Pricing API belum dikonfigurasi")

        items = [
            {
                "sku": line.product.sku,
                "barcode": line.product.barcode,
                "qty": line.qty,
                "unit_price": line.product.price,
            }
            for line in cart.lines
        ]
        if not items:
            raise ValueError("Keranjang masih kosong")

        quote = self.pricing_api.quote(
            member_no=member_no,
            items=items,
            store_id=TERMINAL_IDENTITY.store_id,
        )
        if not isinstance(quote, dict):
            raise IntegrationError("Respons Pricing API tidak valid")
        return quote

    def apply_quote(self, cart, quote: dict) -> dict:
        discounts = quote.get("line_discounts") or []
        by_sku = {}
        for item in discounts:
            sku = str(item.get("sku") or "").strip()
            if not sku:
                continue
            pct = Decimal(str(item.get("discount_percent", "0")))
            if pct < 0 or pct > 100:
                raise IntegrationError(f"discount_percent tidak valid untuk SKU {sku}")
            by_sku[sku] = pct

        applied = []
        for index, line in enumerate(cart.lines):
            pct = by_sku.get(line.product.sku, Decimal("0"))
            cart.set_line_discount(index, pct)
            if pct:
                applied.append(
                    {
                        "sku": line.product.sku,
                        "discount_percent": float(pct),
                    }
                )

        cart_pct = Decimal(str(quote.get("cart_discount_percent", "0")))
        if cart_pct < 0 or cart_pct > 100:
            raise IntegrationError("cart_discount_percent tidak valid")
        cart.cart_discount_percent = cart_pct

        return {
            "applied_lines": applied,
            "cart_discount_percent": float(cart_pct),
            "messages": quote.get("messages") or [],
            "quote_id": quote.get("quote_id"),
        }
