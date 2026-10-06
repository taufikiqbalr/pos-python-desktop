from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
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
from app.services import CatalogService, ReceiptService, SaleService


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
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        title = QLabel(f"Total {format_rupiah(total)}")
        title.setObjectName("GrandTotal")
        layout.addWidget(title)

        form = QFormLayout()
        self.method = QComboBox()
        self.method.addItems(["Tunai", "QRIS", "Kartu Debit/Kredit", "Transfer"])
        self.paid = QSpinBox()
        self.paid.setRange(0, 2_147_483_647)
        self.paid.setSingleStep(1000)
        self.paid.setGroupSeparatorShown(True)
        self.paid.setValue(total)
        self.change_label = QLabel(format_rupiah(0))
        form.addRow("Metode", self.method)
        form.addRow("Nominal dibayar", self.paid)
        form.addRow("Kembalian", self.change_label)
        layout.addLayout(form)

        quick = QHBoxLayout()
        for amount in (10_000, 20_000, 50_000, 100_000):
            button = QPushButton(f"+{amount//1000}K")
            button.clicked.connect(lambda _=False, x=amount: self.paid.setValue(self.paid.value() + x))
            quick.addWidget(button)
        exact = QPushButton("Uang Pas")
        exact.clicked.connect(lambda: self.paid.setValue(self.total))
        quick.addWidget(exact)
        layout.addLayout(quick)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Selesaikan")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        layout.addWidget(buttons)

        self.method.currentTextChanged.connect(self._method_changed)
        self.paid.valueChanged.connect(self._update_change)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        self._update_change()

    def _method_changed(self, method: str) -> None:
        cash = method == "Tunai"
        self.paid.setEnabled(cash)
        if not cash:
            self.paid.setValue(self.total)
        self._update_change()

    def _update_change(self) -> None:
        change = max(0, self.paid.value() - self.total)
        self.change_label.setText(format_rupiah(change))

    def _validate(self) -> None:
        if self.paid.value() < self.total:
            QMessageBox.warning(self, "Pembayaran Kurang", "Nominal pembayaran belum mencukupi total transaksi.")
            return
        self.accept()

    @property
    def payment_method(self) -> str:
        return self.method.currentText()

    @property
    def paid_amount(self) -> int:
        return self.paid.value()

    @property
    def change_amount(self) -> int:
        return max(0, self.paid.value() - self.total)


class ReceiptDialog(QDialog):
    def __init__(self, sale: dict, receipt_service: ReceiptService, parent=None) -> None:
        super().__init__(parent)
        self.sale = sale
        self.receipt_service = receipt_service
        self.setWindowTitle(f"Struk {sale['invoice_no']}")
        self.resize(500, 650)

        layout = QVBoxLayout(self)
        self.viewer = QTextBrowser()
        self.viewer.setHtml(receipt_service.render_html(sale))
        layout.addWidget(self.viewer)

        row = QHBoxLayout()
        print_button = QPushButton("Cetak")
        save_button = QPushButton("Simpan TXT")
        close_button = QPushButton("Tutup")
        print_button.setObjectName("PrimaryButton")
        row.addWidget(print_button)
        row.addWidget(save_button)
        row.addStretch()
        row.addWidget(close_button)
        layout.addLayout(row)

        print_button.clicked.connect(self.print_receipt)
        save_button.clicked.connect(self.save_receipt)
        close_button.clicked.connect(self.accept)

    def print_receipt(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.Accepted:
            doc = QTextDocument()
            doc.setHtml(self.receipt_service.render_html(self.sale))
            doc.print_(printer)

    def save_receipt(self) -> None:
        path = self.receipt_service.save_text(self.sale)
        QMessageBox.information(self, "Struk Disimpan", f"Struk tersimpan di:\n{path}")


class HistoryDialog(QDialog):
    def __init__(self, sale_service: SaleService, receipt_service: ReceiptService, parent=None) -> None:
        super().__init__(parent)
        self.sale_service = sale_service
        self.receipt_service = receipt_service
        self.setWindowTitle("Riwayat Transaksi")
        self.resize(900, 540)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Invoice", "Waktu", "Kasir", "Pelanggan", "Metode", "Total"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        reprint = QPushButton("Lihat / Cetak Struk")
        reprint.setObjectName("PrimaryButton")
        buttons.addButton(reprint, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)
        buttons.rejected.connect(self.reject)
        reprint.clicked.connect(self.open_receipt)
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
            ]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def open_receipt(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        invoice = self.table.item(row, 0).text()
        sale = self.sale_service.get_sale(invoice)
        ReceiptDialog(sale, self.receipt_service, self).exec()
