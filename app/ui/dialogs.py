from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
)

from app.config import format_rupiah
from app.domain import Product
from app.hardware import EscPosHardwareService, HardwareError
from app.services import AuthService, CatalogService, ReceiptService, SaleService


PAYMENT_METHODS = ["Tunai", "QRIS", "Kartu Debit/Kredit", "Transfer"]


class ProductSearchDialog(QDialog):
    def __init__(self, catalog_service: CatalogService, term: str = "", parent=None) -> None:
        super().__init__(parent)
        self.catalog_service = catalog_service
        self.selected_product: Product | None = None
        self.setWindowTitle("Cari Produk")
        self.resize(820, 520)

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit(term)
        self.search_input.setPlaceholderText("Nama barang, SKU, atau barcode...")
        layout.addWidget(self.search_input)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["SKU", "Barcode", "Nama", "Stok", "Harga"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        add_button = QPushButton("Tambahkan")
        add_button.setObjectName("PrimaryButton")
        buttons.addButton(add_button, QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)

        self.search_input.textChanged.connect(self.reload)
        self.table.doubleClicked.connect(self.accept_selected)
        add_button.clicked.connect(self.accept_selected)
        buttons.rejected.connect(self.reject)
        self.reload(term)

    def reload(self, term: str = "") -> None:
        products = self.catalog_service.search(term)
        self.table.setRowCount(len(products))
        for row, product in enumerate(products):
            self.table.setItem(row, 0, QTableWidgetItem(product.sku))
            self.table.setItem(row, 1, QTableWidgetItem(product.barcode))
            self.table.setItem(row, 2, QTableWidgetItem(product.name))
            self.table.setItem(row, 3, QTableWidgetItem(f"{product.stock:g} {product.unit}"))
            self.table.setItem(row, 4, QTableWidgetItem(format_rupiah(product.price)))
            self.table.item(row, 0).setData(Qt.UserRole, product)
        self.table.resizeColumnsToContents()

    def accept_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Pilih Produk", "Pilih satu produk terlebih dahulu.")
            return
        self.selected_product = self.table.item(row, 0).data(Qt.UserRole)
        self.accept()


class PaymentDialog(QDialog):
    def __init__(self, total: int, parent=None) -> None:
        super().__init__(parent)
        self.total = total
        self.setWindowTitle("Pembayaran")
        self.setMinimumWidth(470)

        layout = QVBoxLayout(self)
        title = QLabel(f"Total {format_rupiah(total)}")
        title.setObjectName("GrandTotal")
        layout.addWidget(title)

        form = QFormLayout()
        self.method1 = QComboBox()
        self.method1.addItems(PAYMENT_METHODS)
        self.paid1 = self._money_spin(total)
        form.addRow("Metode pembayaran 1", self.method1)
        form.addRow("Nominal 1", self.paid1)

        self.split_check = QCheckBox("Split pembayaran / dua metode")
        form.addRow("", self.split_check)

        self.method2 = QComboBox()
        self.method2.addItems(PAYMENT_METHODS)
        self.method2.setCurrentText("QRIS")
        self.paid2 = self._money_spin(0)
        self.method2.setEnabled(False)
        self.paid2.setEnabled(False)
        form.addRow("Metode pembayaran 2", self.method2)
        form.addRow("Nominal 2", self.paid2)

        self.remaining_label = QLabel(format_rupiah(0))
        self.change_label = QLabel(format_rupiah(0))
        form.addRow("Sisa yang harus dibayar", self.remaining_label)
        form.addRow("Kembalian", self.change_label)
        layout.addLayout(form)

        quick = QHBoxLayout()
        for amount in (10_000, 20_000, 50_000, 100_000):
            button = QPushButton(f"+{amount//1000}K")
            button.clicked.connect(
                lambda _=False, x=amount: self.paid1.setValue(self.paid1.value() + x)
            )
            quick.addWidget(button)
        exact = QPushButton("Uang Pas")
        exact.clicked.connect(self._set_exact)
        quick.addWidget(exact)
        layout.addLayout(quick)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Selesaikan")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        layout.addWidget(buttons)

        self.split_check.toggled.connect(self._toggle_split)
        self.paid1.valueChanged.connect(self._update_totals)
        self.paid2.valueChanged.connect(self._update_totals)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        self._update_totals()

    @staticmethod
    def _money_spin(value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 2_147_483_647)
        spin.setSingleStep(1000)
        spin.setGroupSeparatorShown(True)
        spin.setValue(value)
        return spin

    def _toggle_split(self, enabled: bool) -> None:
        self.method2.setEnabled(enabled)
        self.paid2.setEnabled(enabled)
        if enabled:
            first = self.total // 2
            self.paid1.setValue(first)
            self.paid2.setValue(self.total - first)
        else:
            self.paid1.setValue(self.total)
            self.paid2.setValue(0)
        self._update_totals()

    def _set_exact(self) -> None:
        if self.split_check.isChecked():
            self.paid2.setValue(max(0, self.total - self.paid1.value()))
        else:
            self.paid1.setValue(self.total)

    def _update_totals(self) -> None:
        total_paid = self.paid1.value()
        if self.split_check.isChecked():
            total_paid += self.paid2.value()
        remaining = max(0, self.total - total_paid)
        change = max(0, total_paid - self.total)
        self.remaining_label.setText(format_rupiah(remaining))
        self.change_label.setText(format_rupiah(change))

    def _validate(self) -> None:
        payments = self.payments
        total_paid = sum(payment["amount"] for payment in payments)
        if total_paid < self.total:
            QMessageBox.warning(
                self,
                "Pembayaran Kurang",
                "Total nominal pembayaran belum mencukupi total transaksi.",
            )
            return
        if total_paid > self.total and not any(p["method"] == "Tunai" for p in payments):
            QMessageBox.warning(
                self,
                "Pembayaran Tidak Valid",
                "Kelebihan pembayaran hanya dapat diberikan sebagai kembalian tunai.",
            )
            return
        self.accept()

    @property
    def payments(self) -> list[dict]:
        items = [{"method": self.method1.currentText(), "amount": self.paid1.value()}]
        if self.split_check.isChecked() and self.paid2.value() > 0:
            items.append({"method": self.method2.currentText(), "amount": self.paid2.value()})
        return [item for item in items if item["amount"] > 0]

    @property
    def payment_method(self) -> str:
        return " + ".join(dict.fromkeys(p["method"] for p in self.payments))

    @property
    def paid_amount(self) -> int:
        return sum(p["amount"] for p in self.payments)

    @property
    def change_amount(self) -> int:
        return max(0, self.paid_amount - self.total)


class OpenShiftDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Buka Shift Kasir")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Masukkan saldo kas awal sebelum transaksi pertama."))

        form = QFormLayout()
        self.opening_cash = QSpinBox()
        self.opening_cash.setRange(0, 2_147_483_647)
        self.opening_cash.setSingleStep(10_000)
        self.opening_cash.setGroupSeparatorShown(True)
        form.addRow("Kas awal", self.opening_cash)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Buka Shift")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class CloseShiftDialog(QDialog):
    def __init__(self, summary: dict, parent=None) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setWindowTitle("Tutup Shift Kasir")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Dibuka", QLabel(str(summary["opened_at"])))
        form.addRow("Jumlah transaksi", QLabel(str(summary["sales_count"])))
        form.addRow("Gross sales", QLabel(format_rupiah(summary["sales_total"])))
        form.addRow("Jumlah refund", QLabel(str(summary.get("refund_count", 0))))
        form.addRow("Total refund", QLabel(format_rupiah(summary.get("refund_total", 0))))
        form.addRow("Net sales", QLabel(format_rupiah(summary.get("net_sales_total", summary["sales_total"]))))
        form.addRow("Kas awal", QLabel(format_rupiah(summary["opening_cash"])))
        form.addRow("Penerimaan tunai", QLabel(format_rupiah(summary["cash_received"])))
        form.addRow("Kembalian tunai", QLabel(format_rupiah(summary["cash_change"])))
        form.addRow("Refund tunai", QLabel(format_rupiah(summary.get("cash_refund", 0))))
        form.addRow("Cash in", QLabel(format_rupiah(summary.get("cash_in", 0))))
        form.addRow("Cash out", QLabel(format_rupiah(summary.get("cash_out", 0))))
        form.addRow("Kas seharusnya", QLabel(format_rupiah(summary["expected_cash_now"])))

        self.closing_cash = QSpinBox()
        self.closing_cash.setRange(0, 2_147_483_647)
        self.closing_cash.setSingleStep(10_000)
        self.closing_cash.setGroupSeparatorShown(True)
        self.closing_cash.setValue(summary["expected_cash_now"])
        self.difference = QLabel(format_rupiah(0))
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Catatan selisih/penutupan (opsional)")
        form.addRow("Kas fisik saat tutup", self.closing_cash)
        form.addRow("Selisih", self.difference)
        form.addRow("Catatan", self.notes)
        layout.addLayout(form)

        if summary["payment_breakdown"]:
            breakdown = " • ".join(
                f"{row['method']}: {format_rupiah(row['amount'])}"
                for row in summary["payment_breakdown"]
            )
            info = QLabel(f"Breakdown pembayaran: {breakdown}")
            info.setWordWrap(True)
            layout.addWidget(info)

        if summary.get("refund_breakdown"):
            refund_breakdown = " • ".join(
                f"{row['method']}: {format_rupiah(row['amount'])}"
                for row in summary["refund_breakdown"]
            )
            info = QLabel(f"Breakdown refund: {refund_breakdown}")
            info.setWordWrap(True)
            layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Tutup Shift")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.closing_cash.valueChanged.connect(self._update_difference)
        self._update_difference()

    def _update_difference(self) -> None:
        value = self.closing_cash.value() - self.summary["expected_cash_now"]
        sign = "+" if value > 0 else ""
        self.difference.setText(f"{sign}{format_rupiah(value)}")


class HoldDialog(QDialog):
    def __init__(self, sale_service: SaleService, cashier_user_id: int, parent=None) -> None:
        super().__init__(parent)
        self.sale_service = sale_service
        self.cashier_user_id = cashier_user_id
        self.selected_hold_no: str | None = None
        self.setWindowTitle("Transaksi Ditahan")
        self.resize(760, 460)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["No. Hold", "Waktu", "Pelanggan", "Item"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        resume_button = QPushButton("Lanjutkan Transaksi")
        resume_button.setObjectName("PrimaryButton")
        delete_button = QPushButton("Hapus Hold")
        delete_button.setObjectName("DangerButton")
        buttons.addButton(resume_button, QDialogButtonBox.ActionRole)
        buttons.addButton(delete_button, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

        buttons.rejected.connect(self.reject)
        resume_button.clicked.connect(self.resume_selected)
        delete_button.clicked.connect(self.delete_selected)
        self.table.doubleClicked.connect(self.resume_selected)
        self.reload()

    def reload(self) -> None:
        rows = self.sale_service.list_held(self.cashier_user_id)
        self.table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [
                item["hold_no"],
                item["created_at"],
                item.get("customer_name") or "-",
                item["item_count"],
            ]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _current_hold_no(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).text()

    def resume_selected(self) -> None:
        hold_no = self._current_hold_no()
        if not hold_no:
            QMessageBox.information(self, "Pilih Hold", "Pilih transaksi hold terlebih dahulu.")
            return
        self.selected_hold_no = hold_no
        self.accept()

    def delete_selected(self) -> None:
        hold_no = self._current_hold_no()
        if not hold_no:
            return
        answer = QMessageBox.question(
            self,
            "Hapus Hold",
            f"Hapus transaksi {hold_no}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.sale_service.delete_held(hold_no, self.cashier_user_id)
        self.reload()


class SupervisorVoidDialog(QDialog):
    def __init__(self, auth_service: AuthService, parent=None) -> None:
        super().__init__(parent)
        self.auth_service = auth_service
        self.supervisor_user: dict | None = None
        self.setWindowTitle("Otorisasi Void")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        warning = QLabel(
            "Void akan membatalkan transaksi dan mengembalikan stok. "
            "Masukkan akun supervisor/admin dan alasan."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        form = QFormLayout()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Contoh: salah scan / transaksi duplikat")
        form.addRow("Username supervisor", self.username)
        form.addRow("Password", self.password)
        form.addRow("Alasan void", self.reason)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Otorisasi & Void")
        buttons.button(QDialogButtonBox.Ok).setObjectName("DangerButton")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.reason.text().strip():
            QMessageBox.warning(self, "Alasan Wajib", "Alasan void wajib diisi.")
            return
        user = self.auth_service.authenticate_supervisor(
            self.username.text(),
            self.password.text(),
        )
        if not user:
            QMessageBox.warning(
                self,
                "Otorisasi Gagal",
                "Akun supervisor/admin atau password tidak valid.",
            )
            return
        self.supervisor_user = user
        self.accept()


class ReceiptDialog(QDialog):
    def __init__(
        self,
        sale: dict,
        receipt_service: ReceiptService,
        parent=None,
        hardware_service: EscPosHardwareService | None = None,
    ) -> None:
        super().__init__(parent)
        self.sale = sale
        self.receipt_service = receipt_service
        self.hardware_service = hardware_service
        self.setWindowTitle(f"Struk {sale['invoice_no']}")
        self.resize(500, 650)

        layout = QVBoxLayout(self)
        self.viewer = QTextBrowser()
        self.viewer.setHtml(receipt_service.render_html(sale))
        layout.addWidget(self.viewer)

        row = QHBoxLayout()
        print_button = QPushButton("Cetak Windows")
        thermal_button = QPushButton("Cetak Thermal")
        save_button = QPushButton("Simpan TXT")
        close_button = QPushButton("Tutup")
        print_button.setObjectName("PrimaryButton")
        thermal_button.setEnabled(
            bool(self.hardware_service and self.hardware_service.printer_enabled)
        )
        row.addWidget(print_button)
        row.addWidget(thermal_button)
        row.addWidget(save_button)
        row.addStretch()
        row.addWidget(close_button)
        layout.addLayout(row)

        print_button.clicked.connect(self.print_receipt)
        thermal_button.clicked.connect(self.print_thermal)
        save_button.clicked.connect(self.save_receipt)
        close_button.clicked.connect(self.accept)

    def print_receipt(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.Accepted:
            doc = QTextDocument()
            doc.setHtml(self.receipt_service.render_html(self.sale))
            doc.print_(printer)

    def print_thermal(self) -> None:
        if not self.hardware_service:
            return
        try:
            self.hardware_service.print_sale(self.sale, self.receipt_service)
        except HardwareError as exc:
            QMessageBox.warning(self, "Printer Thermal", str(exc))
            return
        QMessageBox.information(self, "Printer Thermal", "Struk berhasil dikirim ke printer.")

    def save_receipt(self) -> None:
        path = self.receipt_service.save_text(self.sale)
        QMessageBox.information(self, "Struk Disimpan", f"Struk tersimpan di:\n{path}")


class HistoryDialog(QDialog):
    def __init__(
        self,
        sale_service: SaleService,
        receipt_service: ReceiptService,
        auth_service: AuthService,
        parent=None,
        hardware_service: EscPosHardwareService | None = None,
    ) -> None:
        super().__init__(parent)
        self.sale_service = sale_service
        self.receipt_service = receipt_service
        self.auth_service = auth_service
        self.hardware_service = hardware_service
        self.setWindowTitle("Riwayat Transaksi")
        self.resize(1020, 560)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Invoice", "Waktu", "Kasir", "Pelanggan", "Metode", "Total", "Status"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        reprint = QPushButton("Lihat / Cetak Struk")
        reprint.setObjectName("PrimaryButton")
        void_button = QPushButton("Void Transaksi")
        void_button.setObjectName("DangerButton")
        buttons.addButton(reprint, QDialogButtonBox.ActionRole)
        buttons.addButton(void_button, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)
        buttons.rejected.connect(self.reject)
        reprint.clicked.connect(self.open_receipt)
        void_button.clicked.connect(self.void_selected)
        self.table.doubleClicked.connect(self.open_receipt)
        self.reload()

    def reload(self) -> None:
        rows = self.sale_service.list_recent()
        self.table.setRowCount(len(rows))
        for row_index, sale in enumerate(rows):
            values = [
                sale["invoice_no"],
                sale["created_at"],
                sale["cashier_name"],
                sale.get("customer_name") or "-",
                sale["payment_method"],
                format_rupiah(sale["grand_total"]),
                sale.get("display_status", sale["status"]),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _current_invoice(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).text()

    def open_receipt(self) -> None:
        invoice = self._current_invoice()
        if not invoice:
            return
        sale = self.sale_service.get_sale(invoice)
        ReceiptDialog(
            sale,
            self.receipt_service,
            self,
            hardware_service=self.hardware_service,
        ).exec()

    def void_selected(self) -> None:
        invoice = self._current_invoice()
        if not invoice:
            QMessageBox.information(self, "Pilih Transaksi", "Pilih transaksi terlebih dahulu.")
            return
        sale = self.sale_service.get_sale(invoice)
        if sale["status"] != "COMPLETED":
            QMessageBox.information(self, "Tidak Dapat Void", "Transaksi ini sudah di-void.")
            return

        dialog = SupervisorVoidDialog(self.auth_service, self)
        if not dialog.exec() or not dialog.supervisor_user:
            return

        try:
            self.sale_service.void_sale(
                invoice,
                dialog.supervisor_user["id"],
                dialog.reason.text(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Void Gagal", str(exc))
            return

        QMessageBox.information(self, "Void Berhasil", f"Transaksi {invoice} berhasil di-void.")
        self.reload()
