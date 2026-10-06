from __future__ import annotations

from PySide6.QtCore import Qt
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
    QVBoxLayout,
)

from app.config import format_rupiah
from app.operations import CashMovementService, CustomerService, RefundService
from app.services import AuthService


class CustomerSearchDialog(QDialog):
    def __init__(self, customer_service: CustomerService, parent=None) -> None:
        super().__init__(parent)
        self.customer_service = customer_service
        self.selected_customer: dict | None = None
        self.setWindowTitle("Cari Anggota / Pelanggan")
        self.resize(820, 500)

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nomor anggota, nama, telepon, atau email...")
        layout.addWidget(self.search_input)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["No. Anggota", "Nama", "Telepon", "Email", "Tipe"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        select_button = QPushButton("Pilih Anggota")
        select_button.setObjectName("PrimaryButton")
        buttons.addButton(select_button, QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)

        self.search_input.textChanged.connect(self.reload)
        self.table.doubleClicked.connect(self.accept_selected)
        select_button.clicked.connect(self.accept_selected)
        buttons.rejected.connect(self.reject)
        self.reload()

    def reload(self, term: str = "") -> None:
        rows = self.customer_service.search(term)
        self.table.setRowCount(len(rows))
        for row_index, customer in enumerate(rows):
            values = [
                customer.get("member_no") or "-",
                customer["name"],
                customer.get("phone") or "-",
                customer.get("email") or "-",
                customer.get("membership_type") or "-",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.UserRole, customer)
                self.table.setItem(row_index, col, item)
        self.table.resizeColumnsToContents()

    def accept_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Pilih Anggota", "Pilih satu anggota terlebih dahulu.")
            return
        self.selected_customer = self.table.item(row, 0).data(Qt.UserRole)
        self.accept()


class CashMovementDialog(QDialog):
    def __init__(
        self,
        *,
        shift_id: int,
        cashier_user_id: int,
        auth_service: AuthService,
        movement_service: CashMovementService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.shift_id = shift_id
        self.cashier_user_id = cashier_user_id
        self.auth_service = auth_service
        self.movement_service = movement_service
        self.result_movement: dict | None = None

        self.setWindowTitle("Cash In / Cash Out")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)

        info = QLabel(
            "Catat uang yang masuk/keluar dari laci kas di luar transaksi penjualan. "
            "Setiap pergerakan kas memerlukan otorisasi supervisor."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.movement_type = QComboBox()
        self.movement_type.addItem("Cash In", "IN")
        self.movement_type.addItem("Cash Out", "OUT")
        self.amount = QSpinBox()
        self.amount.setRange(1, 2_147_483_647)
        self.amount.setSingleStep(10_000)
        self.amount.setGroupSeparatorShown(True)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Contoh: tambah uang kecil / setor sebagian kas")
        self.supervisor_username = QLineEdit()
        self.supervisor_password = QLineEdit()
        self.supervisor_password.setEchoMode(QLineEdit.Password)

        form.addRow("Jenis", self.movement_type)
        form.addRow("Nominal", self.amount)
        form.addRow("Alasan", self.reason)
        form.addRow("Username supervisor", self.supervisor_username)
        form.addRow("Password supervisor", self.supervisor_password)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Simpan Pergerakan Kas")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _submit(self) -> None:
        supervisor = self.auth_service.authenticate_supervisor(
            self.supervisor_username.text(),
            self.supervisor_password.text(),
        )
        if not supervisor:
            QMessageBox.warning(
                self,
                "Otorisasi Gagal",
                "Username/password supervisor atau admin tidak valid.",
            )
            return
        try:
            self.result_movement = self.movement_service.record(
                shift_id=self.shift_id,
                cashier_user_id=self.cashier_user_id,
                approved_by=supervisor["id"],
                movement_type=self.movement_type.currentData(),
                amount=self.amount.value(),
                reason=self.reason.text(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Gagal Menyimpan", str(exc))
            return
        self.accept()


class RefundDialog(QDialog):
    def __init__(
        self,
        *,
        refund_service: RefundService,
        auth_service: AuthService,
        cashier_user_id: int,
        shift_id: int | None,
        invoice_no: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.refund_service = refund_service
        self.auth_service = auth_service
        self.cashier_user_id = cashier_user_id
        self.shift_id = shift_id
        self.refund_result: dict | None = None
        self.context: dict | None = None
        self.qty_inputs: dict[int, QSpinBox] = {}

        self.setWindowTitle("Return / Refund")
        self.resize(960, 650)

        layout = QVBoxLayout(self)
        invoice_row = QHBoxLayout()
        self.invoice_input = QLineEdit(invoice_no)
        self.invoice_input.setPlaceholderText("Nomor invoice POS-...")
        load_button = QPushButton("Muat Invoice")
        load_button.setObjectName("PrimaryButton")
        invoice_row.addWidget(QLabel("Invoice"))
        invoice_row.addWidget(self.invoice_input, 1)
        invoice_row.addWidget(load_button)
        layout.addLayout(invoice_row)

        self.sale_info = QLabel("Masukkan nomor invoice lalu klik Muat Invoice.")
        self.sale_info.setWordWrap(True)
        layout.addWidget(self.sale_info)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Produk", "Dibeli", "Sudah Retur", "Sisa", "Qty Retur", "Nilai Refund"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        form = QFormLayout()
        self.method = QComboBox()
        self.method.addItems(["Tunai", "QRIS", "Transfer", "Kartu Debit/Kredit"])
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Alasan return/refund wajib diisi")
        self.supervisor_username = QLineEdit()
        self.supervisor_password = QLineEdit()
        self.supervisor_password.setEchoMode(QLineEdit.Password)
        self.total_label = QLabel(format_rupiah(0))
        self.total_label.setObjectName("GrandTotal")

        form.addRow("Metode refund", self.method)
        form.addRow("Alasan", self.reason)
        form.addRow("Username supervisor", self.supervisor_username)
        form.addRow("Password supervisor", self.supervisor_password)
        form.addRow("TOTAL REFUND", self.total_label)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Proses Refund")
        buttons.button(QDialogButtonBox.Ok).setObjectName("DangerButton")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        load_button.clicked.connect(self.load_invoice)
        self.invoice_input.returnPressed.connect(self.load_invoice)

        if invoice_no:
            self.load_invoice()

    def load_invoice(self) -> None:
        invoice = self.invoice_input.text().strip()
        if not invoice:
            return
        try:
            self.context = self.refund_service.get_context(invoice)
        except ValueError as exc:
            QMessageBox.warning(self, "Invoice Tidak Dapat Dimuat", str(exc))
            self.context = None
            self.table.setRowCount(0)
            self.qty_inputs.clear()
            self.total_label.setText(format_rupiah(0))
            return

        self.sale_info.setText(
            f"Invoice {self.context['invoice_no']} • "
            f"{self.context.get('customer_name') or 'Pelanggan umum'} • "
            f"Total {format_rupiah(self.context['grand_total'])} • "
            f"Sudah direfund {format_rupiah(self.context['already_refunded_total'])}"
        )

        items = self.context["items"]
        self.table.setRowCount(len(items))
        self.qty_inputs.clear()

        for row_index, item in enumerate(items):
            values = [
                item["product_name"],
                str(item["qty"]),
                str(item["refunded_qty"]),
                str(item["available_qty"]),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(value))

            spin = QSpinBox()
            spin.setRange(0, int(item["available_qty"]))
            spin.valueChanged.connect(self.refresh_preview)
            self.table.setCellWidget(row_index, 4, spin)
            self.qty_inputs[int(item["id"])] = spin

            value_item = QTableWidgetItem(format_rupiah(0))
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_index, 5, value_item)

        self.table.resizeColumnsToContents()
        self.refresh_preview()

    def _selections(self) -> dict[int, int]:
        return {
            sale_item_id: spin.value()
            for sale_item_id, spin in self.qty_inputs.items()
            if spin.value() > 0
        }

    def refresh_preview(self) -> None:
        if not self.context:
            return
        selections = self._selections()
        if not selections:
            self.total_label.setText(format_rupiah(0))
            for row in range(self.table.rowCount()):
                self.table.item(row, 5).setText(format_rupiah(0))
            return
        try:
            preview = self.refund_service.preview(
                self.context["invoice_no"],
                selections,
            )
        except ValueError:
            return

        amount_by_item = {
            int(line["sale_item_id"]): int(line["amount"])
            for line in preview["lines"]
        }
        for row_index, item in enumerate(self.context["items"]):
            amount = amount_by_item.get(int(item["id"]), 0)
            self.table.item(row_index, 5).setText(format_rupiah(amount))
        self.total_label.setText(format_rupiah(preview["total_amount"]))

    def _submit(self) -> None:
        if not self.context:
            QMessageBox.warning(self, "Invoice Belum Dimuat", "Muat invoice terlebih dahulu.")
            return
        selections = self._selections()
        if not selections:
            QMessageBox.warning(self, "Pilih Item", "Pilih minimal satu qty item untuk diretur.")
            return
        if not self.reason.text().strip():
            QMessageBox.warning(self, "Alasan Wajib", "Alasan return/refund wajib diisi.")
            return

        supervisor = self.auth_service.authenticate_supervisor(
            self.supervisor_username.text(),
            self.supervisor_password.text(),
        )
        if not supervisor:
            QMessageBox.warning(
                self,
                "Otorisasi Gagal",
                "Username/password supervisor atau admin tidak valid.",
            )
            return

        try:
            self.refund_result = self.refund_service.create_refund(
                invoice_no=self.context["invoice_no"],
                selections=selections,
                cashier_user_id=self.cashier_user_id,
                approved_by=supervisor["id"],
                shift_id=self.shift_id,
                refund_method=self.method.currentText(),
                reason=self.reason.text(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Refund Gagal", str(exc))
            return
        self.accept()
