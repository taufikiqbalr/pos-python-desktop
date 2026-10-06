from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import TAX_PERCENT, format_rupiah
from app.domain import Cart, Product
from app.services import CatalogService, ReceiptService, SaleService
from app.ui.dialogs import HistoryDialog, PaymentDialog, ProductSearchDialog, ReceiptDialog


class PosWindow(QMainWindow):
    def __init__(
        self,
        *,
        user: dict,
        catalog_service: CatalogService,
        sale_service: SaleService,
        receipt_service: ReceiptService,
        on_logout,
    ) -> None:
        super().__init__()
        self.user = user
        self.catalog_service = catalog_service
        self.sale_service = sale_service
        self.receipt_service = receipt_service
        self.on_logout = on_logout
        self.cart = Cart(tax_percent=TAX_PERCENT)

        self.setWindowTitle("Koperasi BRIN POS")
        self.resize(1360, 820)
        self._build_ui()
        self._register_shortcuts()
        self.refresh_cart()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootWidget")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 16, 18, 12)

        header = QHBoxLayout()
        title = QLabel("Koperasi BRIN POS")
        title.setObjectName("Title")
        user_label = QLabel(f"Kasir: {self.user['full_name']}  •  {self.user['role']}")
        user_label.setObjectName("Subtitle")
        history_button = QPushButton("Riwayat (F8)")
        new_button = QPushButton("Transaksi Baru (F6)")
        logout_button = QPushButton("Logout")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(user_label)
        header.addSpacing(14)
        header.addWidget(history_button)
        header.addWidget(new_button)
        header.addWidget(logout_button)
        root_layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        root_layout.addLayout(body, 1)

        left = QFrame()
        left.setObjectName("Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)

        scan_row = QHBoxLayout()
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Scan barcode / ketik SKU lalu Enter (F2)")
        self.scan_input.setClearButtonEnabled(True)
        search_button = QPushButton("Cari Produk (F3)")
        search_button.setObjectName("PrimaryButton")
        scan_row.addWidget(self.scan_input, 1)
        scan_row.addWidget(search_button)
        left_layout.addLayout(scan_row)

        self.cart_table = QTableWidget(0, 6)
        self.cart_table.setHorizontalHeaderLabels(["Produk", "SKU", "Harga", "Qty", "Diskon", "Total"])
        self.cart_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self.cart_table, 1)

        line_actions = QHBoxLayout()
        minus_button = QPushButton("− Qty")
        plus_button = QPushButton("+ Qty")
        remove_button = QPushButton("Hapus Item")
        remove_button.setObjectName("DangerButton")
        line_actions.addWidget(minus_button)
        line_actions.addWidget(plus_button)
        line_actions.addWidget(remove_button)
        line_actions.addStretch()
        left_layout.addLayout(line_actions)
        body.addWidget(left, 3)

        right = QFrame()
        right.setObjectName("Card")
        right.setMaximumWidth(410)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 20, 22, 20)
        right_layout.addWidget(QLabel("Ringkasan Transaksi"))

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Nama pelanggan (opsional)")
        right_layout.addWidget(self.customer_input)

        discount_row = QHBoxLayout()
        discount_row.addWidget(QLabel("Diskon transaksi (%)"))
        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0, 100)
        self.discount_spin.setDecimals(2)
        self.discount_spin.setSuffix(" %")
        discount_row.addWidget(self.discount_spin)
        right_layout.addLayout(discount_row)

        totals = QGridLayout()
        self.subtotal_value = QLabel()
        self.discount_value = QLabel()
        self.tax_value = QLabel()
        self.item_count_value = QLabel()
        totals.addWidget(QLabel("Jumlah item"), 0, 0)
        totals.addWidget(self.item_count_value, 0, 1, alignment=Qt.AlignRight)
        totals.addWidget(QLabel("Subtotal"), 1, 0)
        totals.addWidget(self.subtotal_value, 1, 1, alignment=Qt.AlignRight)
        totals.addWidget(QLabel("Diskon"), 2, 0)
        totals.addWidget(self.discount_value, 2, 1, alignment=Qt.AlignRight)
        totals.addWidget(QLabel(f"Pajak ({TAX_PERCENT:g}%)"), 3, 0)
        totals.addWidget(self.tax_value, 3, 1, alignment=Qt.AlignRight)
        right_layout.addLayout(totals)

        right_layout.addSpacing(12)
        label = QLabel("TOTAL")
        label.setObjectName("TotalLabel")
        self.grand_total_value = QLabel()
        self.grand_total_value.setObjectName("GrandTotal")
        self.grand_total_value.setAlignment(Qt.AlignRight)
        right_layout.addWidget(label)
        right_layout.addWidget(self.grand_total_value)

        self.notes_input = QPlainTextEdit()
        self.notes_input.setPlaceholderText("Catatan transaksi (opsional)")
        self.notes_input.setMaximumHeight(90)
        right_layout.addWidget(self.notes_input)
        right_layout.addStretch()

        self.pay_button = QPushButton("BAYAR (F4)")
        self.pay_button.setObjectName("PayButton")
        right_layout.addWidget(self.pay_button)
        body.addWidget(right, 1)

        self.statusBar().showMessage("F2 Scan • F3 Cari • F4 Bayar • F6 Baru • F8 Riwayat")

        self.scan_input.returnPressed.connect(self.scan_code)
        search_button.clicked.connect(self.open_product_search)
        minus_button.clicked.connect(self.decrement_selected)
        plus_button.clicked.connect(self.increment_selected)
        remove_button.clicked.connect(self.remove_selected)
        self.discount_spin.valueChanged.connect(self.discount_changed)
        self.pay_button.clicked.connect(self.checkout)
        new_button.clicked.connect(self.new_sale)
        history_button.clicked.connect(self.open_history)
        logout_button.clicked.connect(self.logout)

    def _register_shortcuts(self) -> None:
        shortcuts = [
            ("F2", self.focus_scan),
            ("F3", self.open_product_search),
            ("F4", self.checkout),
            ("F6", self.new_sale),
            ("F8", self.open_history),
        ]
        self._shortcuts = []
        for key, handler in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def focus_scan(self) -> None:
        self.scan_input.setFocus()
        self.scan_input.selectAll()

    def scan_code(self) -> None:
        code = self.scan_input.text().strip()
        if not code:
            return
        product = self.catalog_service.get_by_barcode_or_sku(code)
        if not product:
            self.open_product_search(code)
            return
        self.add_product(product)
        self.scan_input.clear()
        self.focus_scan()

    def open_product_search(self, term: str = "") -> None:
        dialog = ProductSearchDialog(self.catalog_service, term if isinstance(term, str) else "", self)
        if dialog.exec() and dialog.selected_product:
            self.add_product(dialog.selected_product)
            self.scan_input.clear()
            self.focus_scan()

    def add_product(self, product: Product) -> None:
        try:
            self.cart.add_product(product)
            self.refresh_cart()
            self.statusBar().showMessage(f"Ditambahkan: {product.name}", 2500)
        except ValueError as exc:
            QMessageBox.warning(self, "Tidak Bisa Menambah", str(exc))

    def selected_row(self) -> int:
        return self.cart_table.currentRow()

    def increment_selected(self) -> None:
        row = self.selected_row()
        if row < 0:
            return
        try:
            self.cart.increment(row)
            self.refresh_cart(select_row=row)
        except ValueError as exc:
            QMessageBox.warning(self, "Stok Tidak Cukup", str(exc))

    def decrement_selected(self) -> None:
        row = self.selected_row()
        if row < 0:
            return
        self.cart.decrement(row)
        self.refresh_cart(select_row=min(row, len(self.cart.lines) - 1))

    def remove_selected(self) -> None:
        row = self.selected_row()
        if row < 0:
            return
        self.cart.remove(row)
        self.refresh_cart()

    def discount_changed(self, value: float) -> None:
        self.cart.cart_discount_percent = Decimal(str(value))
        self.refresh_totals()

    def refresh_cart(self, select_row: int | None = None) -> None:
        self.cart_table.setRowCount(len(self.cart.lines))
        for row, line in enumerate(self.cart.lines):
            values = [
                line.product.name,
                line.product.sku,
                format_rupiah(line.product.price),
                str(line.qty),
                format_rupiah(line.discount_amount),
                format_rupiah(line.total),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.cart_table.setItem(row, col, item)
        self.cart_table.resizeColumnsToContents()
        if select_row is not None and select_row >= 0 and self.cart_table.rowCount() > select_row:
            self.cart_table.selectRow(select_row)
        self.refresh_totals()

    def refresh_totals(self) -> None:
        self.item_count_value.setText(str(self.cart.item_count))
        self.subtotal_value.setText(format_rupiah(self.cart.subtotal))
        self.discount_value.setText(f"- {format_rupiah(self.cart.discount_total)}")
        self.tax_value.setText(format_rupiah(self.cart.tax_total))
        self.grand_total_value.setText(format_rupiah(self.cart.grand_total))
        self.pay_button.setEnabled(bool(self.cart.lines))

    def checkout(self) -> None:
        if not self.cart.lines:
            QMessageBox.information(self, "Keranjang Kosong", "Tambahkan barang sebelum melakukan pembayaran.")
            return
        dialog = PaymentDialog(self.cart.grand_total, self)
        if not dialog.exec():
            return
        try:
            sale = self.sale_service.complete_sale(
                cart=self.cart,
                cashier_user_id=self.user["id"],
                customer_name=self.customer_input.text(),
                payment_method=dialog.payment_method,
                paid_amount=dialog.paid_amount,
                change_amount=dialog.change_amount,
                notes=self.notes_input.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Transaksi Gagal", str(exc))
            return

        self.receipt_service.save_text(sale)
        QMessageBox.information(self, "Transaksi Berhasil", f"Transaksi {sale['invoice_no']} berhasil disimpan.")
        ReceiptDialog(sale, self.receipt_service, self).exec()
        self.reset_form()

    def reset_form(self) -> None:
        self.cart.clear()
        self.customer_input.clear()
        self.notes_input.clear()
        self.discount_spin.blockSignals(True)
        self.discount_spin.setValue(0)
        self.discount_spin.blockSignals(False)
        self.refresh_cart()
        self.focus_scan()

    def new_sale(self) -> None:
        if self.cart.lines:
            answer = QMessageBox.question(
                self,
                "Transaksi Baru",
                "Keranjang saat ini akan dikosongkan. Lanjutkan?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.reset_form()

    def open_history(self) -> None:
        HistoryDialog(self.sale_service, self.receipt_service, self).exec()

    def logout(self) -> None:
        if self.cart.lines:
            answer = QMessageBox.question(
                self,
                "Logout",
                "Ada transaksi yang belum selesai. Logout dan buang keranjang?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.close()
        self.on_logout()
