from __future__ import annotations

from dataclasses import dataclass

from app.config import (
    CASH_DRAWER_ENABLED,
    CASH_DRAWER_PIN,
    PRINTER_HOST,
    PRINTER_MODE,
    PRINTER_PORT,
    PRINTER_PROFILE,
    PRINTER_USB_PRODUCT_ID,
    PRINTER_USB_VENDOR_ID,
)


class HardwareError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareStatus:
    printer_mode: str
    printer_enabled: bool
    drawer_enabled: bool
    description: str


class EscPosHardwareService:
    """Optional ESC/POS adapter.

    python-escpos is imported only when a hardware operation is requested.
    This keeps the core POS runnable without printer drivers/dependencies.
    """

    def __init__(self) -> None:
        self.mode = PRINTER_MODE
        self.drawer_enabled = CASH_DRAWER_ENABLED

    @property
    def printer_enabled(self) -> bool:
        return self.mode in {"network", "usb"}

    def status(self) -> HardwareStatus:
        if self.mode == "network":
            description = f"Network ESC/POS {PRINTER_HOST}:{PRINTER_PORT}"
        elif self.mode == "usb":
            description = (
                "USB ESC/POS "
                f"VID=0x{PRINTER_USB_VENDOR_ID:04x} "
                f"PID=0x{PRINTER_USB_PRODUCT_ID:04x}"
            )
        else:
            description = "ESC/POS disabled; Qt print preview remains available"
        return HardwareStatus(
            printer_mode=self.mode,
            printer_enabled=self.printer_enabled,
            drawer_enabled=self.drawer_enabled,
            description=description,
        )

    def _connect(self):
        if not self.printer_enabled:
            raise HardwareError(
                "ESC/POS printer belum diaktifkan. Atur POS_PRINTER_MODE=network atau usb."
            )

        try:
            from escpos.printer import Network, Usb
        except ImportError as exc:
            raise HardwareError(
                "Dukungan ESC/POS belum terpasang. Install requirements-hardware.txt."
            ) from exc

        try:
            if self.mode == "network":
                if not PRINTER_HOST:
                    raise HardwareError("POS_PRINTER_HOST belum dikonfigurasi.")
                return Network(
                    PRINTER_HOST,
                    port=PRINTER_PORT,
                    profile=PRINTER_PROFILE,
                    timeout=5,
                )

            if not PRINTER_USB_VENDOR_ID or not PRINTER_USB_PRODUCT_ID:
                raise HardwareError(
                    "POS_PRINTER_USB_VENDOR_ID dan POS_PRINTER_USB_PRODUCT_ID wajib diisi."
                )
            return Usb(
                PRINTER_USB_VENDOR_ID,
                PRINTER_USB_PRODUCT_ID,
                profile=PRINTER_PROFILE,
            )
        except HardwareError:
            raise
        except Exception as exc:
            raise HardwareError(f"Tidak dapat terhubung ke printer: {exc}") from exc

    @staticmethod
    def _close(printer) -> None:
        try:
            close = getattr(printer, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    def print_text(self, text: str, *, cut: bool = True) -> None:
        printer = self._connect()
        try:
            printer.text(text.rstrip() + "\n")
            if cut:
                printer.cut()
        except Exception as exc:
            raise HardwareError(f"Gagal mencetak ke printer ESC/POS: {exc}") from exc
        finally:
            self._close(printer)

    def print_sale(self, sale: dict, receipt_service) -> None:
        self.print_text(receipt_service.render_text(sale), cut=True)

    def test_print(self) -> None:
        self.print_text(
            "KOPERASI BRIN POS\n"
            "ESC/POS DEVICE TEST\n"
            "Printer tersambung dengan baik.\n",
            cut=True,
        )

    def open_cash_drawer(self) -> None:
        if not self.drawer_enabled:
            raise HardwareError(
                "Cash drawer belum diaktifkan. Atur POS_CASH_DRAWER_ENABLED=true."
            )
        if CASH_DRAWER_PIN not in {2, 5}:
            raise HardwareError("POS_CASH_DRAWER_PIN harus 2 atau 5.")

        printer = self._connect()
        try:
            printer.cashdraw(CASH_DRAWER_PIN)
        except Exception as exc:
            raise HardwareError(f"Gagal membuka cash drawer: {exc}") from exc
        finally:
            self._close(printer)
