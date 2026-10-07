from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
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

from app.config import (
    AUTO_OPEN_DRAWER_CASH,
    AUTO_PRINT_RECEIPT,
    TAX_PERCENT,
    format_rupiah,
)
from app.domain import Cart, Product
from app.hardware import EscPosHardwareService, HardwareError
from app.identity import TERMINAL_IDENTITY
from app.integrations.clients import IntegrationError
from app.operations import AuditService, CashMovementService, CustomerService, RefundService
from app.pricing import PricingService
from app.services import (
    AuthService,
    CatalogService,
    ReceiptService,
    SaleService,
    ShiftService,
)
from app.sync import SyncService
from app.ui.device_dialog import DeviceDialog
from app.ui.dialogs import (
    CloseShiftDialog,
    HistoryDialog,
    HoldDialog,
    OpenShiftDialog,
    PaymentDialog,
    ProductSearchDialog,
    ReceiptDialog,
)
from app.ui.operations_dialogs import (
    CashMovementDialog,
    CustomerSearchDialog,
    RefundDialog,
)


class PosWindow(QMainWindow):
    def __init__(
        self,
        *,
        user: dict,
        auth_service: AuthService,
        catalog_service: CatalogService,
        sale_service: SaleService,
        shift_service: ShiftService,
        customer_service: CustomerService,
        cash_movement_service: CashMovementService,
        refund_service: RefundService,
        audit_service: AuditService,
        pricing_service: PricingService,
        receipt_service: ReceiptService,
        hardware_service: EscPosHardwareService,
        sync_service: SyncService,
        on_logout,
    ) -> None:
        super().__init__()
        self.user = user
        self.auth_service = auth_service
        self.catalog_service = catalog_service
        self.sale_service = sale_service
        self.shift_service = shift_service
        self.customer_service = customer_service
        self.cash_movement_service = cash_movement_service
        self.refund_service = refund_service
        self.audit_service = audit_service
        self.pricing_service = pricing_service
        self.receipt_service = receipt_service
        self.hardware_service = hardware_service
        self.sync_service = sync_service
        self.on_logout = on_logout
        self.cart = Cart(tax_percent=TAX_PERCENT)
        self.selected_customer: dict | None = None
        self.active_shift = self.shift_service.get_open_shift(self.user["id"])

        self.setWindowTitle("Koperasi BRIN POS")
        self.resize(1440, 840)
        self._build_ui()
        self._register_shortcuts()
        self.refresh_shift_state()
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
        self.shift_label = QLabel()
        self.shift_label.setObjectName("Subtitle")
        self.shift_button = QPushButton()
        history_button = QPushButton("Riwayat (F8)")
        device_button = QPushButton("Perangkat (F12)")
        cash_button = QPushButton("Kas (F10)")
        refund_button = QPushButton("Refund (F11)")
        new_button = QPushButton("Transaksi Baru (F6)")
        logout_button = QPushButton("Logout")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(user_label)
        terminal_label = QLabel(
            f"{TERMINAL_IDENTITY.store_id}/{TERMINAL_IDENTITY.register_id}"
        )
        terminal_label.setObjectName("Subtitle")
        header.addWidget(terminal_label)
        header.addSpacing(10)
        header.addWidget(self.shift_label)
        header.addWidget(self.shift_button)
        header.addWidget(history_button)
        header.addWidget(device_button)
        header.addWidget(cash_button)
        header.addWidget(refund_button)
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
        hold_button = QPushButton("Hold (F5)")
        held_button = QPushButton("Daftar Hold (F7)")
        scan_row.addWidget(self.scan_input, 1)
        scan_row.addWidget(search_button)
        scan_row.addWidget(hold_button)
        scan_row.addWidget(held_button)
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
        item_discount_button = QPushButton("Diskon Item")
        remove_button = QPushButton("Void / Hapus Item")
        remove_button.setObjectName("DangerButton")
        line_actions.addWidget(minus_button)
        line_actions.addWidget(plus_button)
        line_actions.addWidget(item_discount_button)
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

        customer_row = QHBoxLayout()
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Nama pelanggan (opsional)")
        member_button = QPushButton("Cari Anggota")
        promo_button = QPushButton("Cek Promo")
        promo_button.setEnabled(self.pricing_service.enabled)
        customer_row.addWidget(self.customer_input, 1)
        customer_row.addWidget(member_button)
        customer_row.addWidget(promo_button)
        right_layout.addLayout(customer_row)
        self.member_label = QLabel("Pelanggan umum")
        self.member_label.setObjectName("Subtitle")
        right_layout.addWidget(self.member_label)
        self.promo_label = QLabel(
            "Promo belum dihitung"
            if self.pricing_service.enabled
            else "Pricing API belum dikonfigurasi"
        )
        self.promo_label.setObjectName("Subtitle")
        self.promo_label.setWordWrap(True)
        right_layout.addWidget(self.promo_label)

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

        self.statusBar().showMessage(
            "F2 Scan • F3 Cari • F4 Bayar • F5 Hold • F6 Baru • F7 Hold • F8 Riwayat • F9 Shift • F10 Kas • F11 Refund • F12 Perangkat"
        )

        self.scan_input.returnPressed.connect(self.scan_code)
        search_button.clicked.connect(self.open_product_search)
        hold_button.clicked.connect(self.hold_current_sale)
        held_button.clicked.connect(self.open_held_sales)
        minus_button.clicked.connect(self.decrement_selected)
        plus_button.clicked.connect(self.increment_selected)
        item_discount_button.clicked.connect(self.set_selected_item_discount)
        remove_button.clicked.connect(self.remove_selected)
        self.discount_spin.valueChanged.connect(self.discount_changed)
        self.pay_button.clicked.connect(self.checkout)
        new_button.clicked.connect(self.new_sale)
        history_button.clicked.connect(self.open_history)
        device_button.clicked.connect(self.open_device_dialog)
        cash_button.clicked.connect(self.open_cash_movement)
        refund_button.clicked.connect(self.open_refund)
        member_button.clicked.connect(self.search_customer)
        promo_button.clicked.connect(self.apply_pricing_quote)
        self.shift_button.clicked.connect(self.manage_shift)
        logout_button.clicked.connect(self.logout)

    def _register_shortcuts(self) -> None:
        shortcuts = [
            ("F2", self.focus_scan),
            ("F3", self.open_product_search),
            ("F4", self.checkout),
            ("F5", self.hold_current_sale),
            ("F6", self.new_sale),
            ("F7", self.open_held_sales),
            ("F8", self.open_history),
            ("F9", self.manage_shift),
            ("F10", self.open_cash_movement),
            ("F11", self.open_refund),
            ("F12", self.open_device_dialog),
        ]
        self._shortcuts = []
        for key, handler in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def refresh_shift_state(self) -> None:
        self.active_shift = self.shift_service.get_open_shift(self.user["id"])
        if self.active_shift:
            self.shift_label.setText(
                f"Shift #{self.active_shift['id']} • dibuka {self.active_shift['opened_at']}"
            )
            self.shift_button.setText("Tutup Shift (F9)")
            self.shift_button.setObjectName("DangerButton")
        else:
            self.shift_label.setText("Shift belum dibuka")
            self.shift_button.setText("Buka Shift (F9)")
            self.shift_button.setObjectName("PrimaryButton")
        self.shift_button.style().unpolish(self.shift_button)
        self.shift_button.style().polish(self.shift_button)
        self.refresh_totals()

    def manage_shift(self) -> None:
        self.refresh_shift_state()
        if self.active_shift:
            self.close_shift()
        else:
            self.open_shift()

    def open_shift(self) -> None:
        dialog = OpenShiftDialog(self)
        if not dialog.exec():
            return
        try:
            self.shift_service.open_shift(self.user["id"], dialog.opening_cash.value())
        except ValueError as exc:
            QMessageBox.critical(self, "Gagal Membuka Shift", str(exc))
            return
        self.refresh_shift_state()
        QMessageBox.information(self, "Shift Dibuka", "Shift kasir berhasil dibuka.")
        self.focus_scan()

    def close_shift(self) -> None:
        if not self.active_shift:
            return
        if self.cart.lines:
            QMessageBox.warning(
                self,
                "Transaksi Belum Selesai",
                "Selesaikan atau hold transaksi aktif sebelum menutup shift.",
            )
            return

        summary = self.shift_service.summary(self.active_shift["id"])
        dialog = CloseShiftDialog(summary, self)
        if not dialog.exec():
            return
        try:
            result = self.shift_service.close_shift(
                self.active_shift["id"],
                dialog.closing_cash.value(),
                dialog.notes.text(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Gagal Menutup Shift", str(exc))
            return

        QMessageBox.information(
            self,
            "Shift Ditutup",
            "Shift berhasil ditutup.\n"
            f"Kas seharusnya: {format_rupiah(result['expected_cash'])}\n"
            f"Kas fisik: {format_rupiah(result['closing_cash'])}\n"
            f"Selisih: {format_rupiah(result['cash_difference'])}",
        )
        self.refresh_shift_state()

    def search_customer(self) -> None:
        dialog = CustomerSearchDialog(self.customer_service, self)
        if not dialog.exec() or not dialog.selected_customer:
            return
        self.selected_customer = dialog.selected_customer
        self.customer_input.setText(self.selected_customer["name"])
        self.customer_input.setReadOnly(True)
        self.member_label.setText(
            f"Anggota {self.selected_customer.get('member_no') or '-'} • "
            f"{self.selected_customer.get('membership_type') or 'MEMBER'}"
        )

    def apply_pricing_quote(self) -> None:
        if not self.pricing_service.enabled:
            QMessageBox.information(
                self,
                "Pricing",
                "Pricing API belum dikonfigurasi.",
            )
            return
        if not self.cart.lines:
            QMessageBox.information(
                self,
                "Pricing",
                "Tambahkan barang sebelum menghitung promo.",
            )
            return

        member_no = (
            self.selected_customer.get("member_no")
            if self.selected_customer
            else None
        )
        try:
            quote = self.pricing_service.quote(self.cart, member_no)
            applied = self.pricing_service.apply_quote(self.cart, quote)
        except (IntegrationError, ValueError) as exc:
            QMessageBox.warning(self, "Pricing Gagal", str(exc))
            return

        self.discount_spin.blockSignals(True)
        self.discount_spin.setValue(float(self.cart.cart_discount_percent))
        self.discount_spin.blockSignals(False)
        self.refresh_cart()

        messages = [str(item) for item in applied.get("messages", []) if item]
        quote_id = applied.get("quote_id")
        parts = []
        if quote_id:
            parts.append(f"Quote: {quote_id}")
        if applied["applied_lines"]:
            parts.append(f"{len(applied['applied_lines'])} item mendapat promo")
        if applied["cart_discount_percent"]:
            parts.append(
                f"diskon transaksi {applied['cart_discount_percent']:g}%"
            )
        parts.extend(messages)
        self.promo_label.setText(" • ".join(parts) if parts else "Tidak ada promo aktif")

    def clear_customer(self) -> None:
        self.selected_customer = None
        self.customer_input.setReadOnly(False)
        self.customer_input.clear()
        self.member_label.setText("Pelanggan umum")
        if self.pricing_service.enabled:
            self.promo_label.setText("Promo belum dihitung")

    def open_cash_movement(self) -> None:
        self.refresh_shift_state()
        if not self.active_shift:
            QMessageBox.information(
                self,
                "Shift Belum Dibuka",
                "Cash-in/cash-out hanya dapat dicatat pada shift aktif.",
            )
            return
        dialog = CashMovementDialog(
            shift_id=self.active_shift["id"],
            cashier_user_id=self.user["id"],
            auth_service=self.auth_service,
            movement_service=self.cash_movement_service,
            parent=self,
        )
        if dialog.exec() and dialog.result_movement:
            movement = dialog.result_movement
            label = "Cash In" if movement["movement_type"] == "IN" else "Cash Out"
            QMessageBox.information(
                self,
                "Pergerakan Kas Tercatat",
                f"{label} {format_rupiah(movement['amount'])} berhasil dicatat.",
            )

    def open_refund(self) -> None:
        self.refresh_shift_state()
        dialog = RefundDialog(
            refund_service=self.refund_service,
            auth_service=self.auth_service,
            cashier_user_id=self.user["id"],
            shift_id=self.active_shift["id"] if self.active_shift else None,
            parent=self,
        )
        if dialog.exec() and dialog.refund_result:
            refund = dialog.refund_result
            QMessageBox.information(
                self,
                "Refund Berhasil",
                f"{refund['refund_no']} berhasil diproses sebesar "
                f"{format_rupiah(refund['total_amount'])}.",
            )

    def open_device_dialog(self) -> None:
        DeviceDialog(
            hardware_service=self.hardware_service,
            sync_service=self.sync_service,
            parent=self,
        ).exec()

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
        dialog = ProductSearchDialog(
            self.catalog_service,
            term if isinstance(term, str) else "",
            self,
        )
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

    def set_selected_item_discount(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Pilih Item", "Pilih item yang akan diberi diskon.")
            return
        line = self.cart.lines[row]
        value, ok = QInputDialog.getDouble(
            self,
            "Diskon Item",
            f"Diskon untuk {line.product.name} (%):",
            float(line.discount_percent),
            0,
            100,
            2,
        )
        if not ok:
            return
        self.cart.set_line_discount(row, value)
        self.refresh_cart(select_row=row)

    def remove_selected(self) -> None:
        row = self.selected_row()
        if row < 0:
            return
        product_name = self.cart.lines[row].product.name
        answer = QMessageBox.question(
            self,
            "Hapus Item",
            f"Hapus {product_name} dari transaksi?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.cart.remove(row)
        self.refresh_cart()

    def discount_changed(self, value: float) -> None:
        self.cart.cart_discount_percent = Decimal(str(value))
        self.refresh_totals()

    def refresh_cart(self, select_row: int | None = None) -> None:
        self.cart_table.setRowCount(len(self.cart.lines))
        for row, line in enumerate(self.cart.lines):
            discount_text = (
                f"{line.discount_percent:g}% ({format_rupiah(line.discount_amount)})"
                if line.discount_amount
                else "-"
            )
            values = [
                line.product.name,
                line.product.sku,
                format_rupiah(line.product.price),
                str(line.qty),
                discount_text,
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
        if not hasattr(self, "item_count_value"):
            return
        self.item_count_value.setText(str(self.cart.item_count))
        self.subtotal_value.setText(format_rupiah(self.cart.subtotal))
        self.discount_value.setText(f"- {format_rupiah(self.cart.discount_total)}")
        self.tax_value.setText(format_rupiah(self.cart.tax_total))
        self.grand_total_value.setText(format_rupiah(self.cart.grand_total))
        self.pay_button.setEnabled(bool(self.cart.lines) and bool(self.active_shift))

    def hold_current_sale(self) -> None:
        if not self.cart.lines:
            QMessageBox.information(self, "Keranjang Kosong", "Tidak ada transaksi untuk di-hold.")
            return
        try:
            held = self.sale_service.hold_cart(
                cart=self.cart,
                cashier_user_id=self.user["id"],
                customer_name=self.customer_input.text(),
                customer_id=self.selected_customer["id"] if self.selected_customer else None,
                customer_member_no=(
                    self.selected_customer.get("member_no") if self.selected_customer else None
                ),
                notes=self.notes_input.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Hold Gagal", str(exc))
            return
        self.reset_form()
        QMessageBox.information(
            self,
            "Transaksi Ditahan",
            f"Transaksi disimpan sebagai {held['hold_no']}.",
        )

    def open_held_sales(self) -> None:
        if self.cart.lines:
            QMessageBox.warning(
                self,
                "Keranjang Masih Aktif",
                "Hold transaksi aktif terlebih dahulu sebelum membuka transaksi lain.",
            )
            return

        dialog = HoldDialog(self.sale_service, self.user["id"], self)
        if not dialog.exec() or not dialog.selected_hold_no:
            return

        try:
            held = self.sale_service.get_held(dialog.selected_hold_no, self.user["id"])
            restored_cart = Cart(tax_percent=TAX_PERCENT)
            for item in held["items"]:
                product = self.catalog_service.get_by_id(int(item["product_id"]))
                if not product:
                    raise ValueError(f"Produk {item['sku']} sudah tidak aktif/tidak ditemukan")
                restored_cart.add_product(product, int(item["qty"]))
                restored_cart.set_line_discount(
                    len(restored_cart.lines) - 1,
                    Decimal(str(item.get("discount_percent", "0"))),
                )
            restored_cart.cart_discount_percent = Decimal(
                str(held.get("cart_discount_percent", "0"))
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Tidak Dapat Melanjutkan Hold", str(exc))
            return

        self.cart = restored_cart
        held_customer_id = held.get("customer_id")
        self.selected_customer = (
            self.customer_service.get(int(held_customer_id))
            if held_customer_id is not None
            else None
        )
        if self.selected_customer:
            self.customer_input.setReadOnly(True)
            self.customer_input.setText(self.selected_customer["name"])
            self.member_label.setText(
                f"Anggota {self.selected_customer.get('member_no') or '-'} • "
                f"{self.selected_customer.get('membership_type') or 'MEMBER'}"
            )
        else:
            self.customer_input.setReadOnly(False)
            self.customer_input.setText(held.get("customer_name") or "")
            self.member_label.setText("Pelanggan umum")
        self.notes_input.setPlainText(held.get("notes") or "")
        self.discount_spin.blockSignals(True)
        self.discount_spin.setValue(float(self.cart.cart_discount_percent))
        self.discount_spin.blockSignals(False)
        self.sale_service.delete_held(
            dialog.selected_hold_no,
            self.user["id"],
            audit_action="HOLD_RESUMED",
        )
        self.refresh_cart()
        self.focus_scan()

    def checkout(self) -> None:
        if not self.cart.lines:
            QMessageBox.information(
                self,
                "Keranjang Kosong",
                "Tambahkan barang sebelum melakukan pembayaran.",
            )
            return

        self.refresh_shift_state()
        if not self.active_shift:
            answer = QMessageBox.question(
                self,
                "Shift Belum Dibuka",
                "Transaksi hanya dapat dibayar pada shift aktif. Buka shift sekarang?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self.open_shift()
            if not self.active_shift:
                return

        dialog = PaymentDialog(self.cart.grand_total, self)
        if not dialog.exec():
            return
        try:
            sale = self.sale_service.complete_sale(
                cart=self.cart,
                cashier_user_id=self.user["id"],
                customer_name=self.customer_input.text(),
                customer_id=self.selected_customer["id"] if self.selected_customer else None,
                customer_member_no=(
                    self.selected_customer.get("member_no") if self.selected_customer else None
                ),
                payments=dialog.payments,
                shift_id=self.active_shift["id"],
                notes=self.notes_input.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Transaksi Gagal", str(exc))
            return

        self.receipt_service.save_text(sale)

        hardware_warnings = []
        if AUTO_PRINT_RECEIPT and self.hardware_service.printer_enabled:
            try:
                self.hardware_service.print_sale(sale, self.receipt_service)
            except HardwareError as exc:
                hardware_warnings.append(f"Auto print gagal: {exc}")

        uses_cash = any(
            payment.get("method") == "Tunai"
            for payment in sale.get("payments", [])
        )
        if (
            uses_cash
            and AUTO_OPEN_DRAWER_CASH
            and self.hardware_service.drawer_enabled
        ):
            try:
                self.hardware_service.open_cash_drawer()
            except HardwareError as exc:
                hardware_warnings.append(f"Cash drawer gagal: {exc}")

        message = f"Transaksi {sale['invoice_no']} berhasil disimpan."
        if hardware_warnings:
            message += "\n\n" + "\n".join(hardware_warnings)
            QMessageBox.warning(self, "Transaksi Berhasil - Perangkat", message)
        else:
            QMessageBox.information(self, "Transaksi Berhasil", message)

        ReceiptDialog(
            sale,
            self.receipt_service,
            self,
            hardware_service=self.hardware_service,
        ).exec()
        self.reset_form()

    def reset_form(self) -> None:
        self.cart.clear()
        self.clear_customer()
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
        HistoryDialog(
            self.sale_service,
            self.receipt_service,
            self.auth_service,
            self,
            hardware_service=self.hardware_service,
        ).exec()

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

        self.refresh_shift_state()
        if self.active_shift:
            answer = QMessageBox.question(
                self,
                "Shift Masih Aktif",
                "Shift kasir masih terbuka. Logout tanpa menutup shift?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self.close()
        self.on_logout()
