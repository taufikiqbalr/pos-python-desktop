from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.hardware import EscPosHardwareService, HardwareError
from app.identity import TERMINAL_IDENTITY
from app.sync import SyncService


class DeviceDialog(QDialog):
    def __init__(
        self,
        *,
        hardware_service: EscPosHardwareService,
        sync_service: SyncService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.hardware_service = hardware_service
        self.sync_service = sync_service
        self.setWindowTitle("Perangkat & Sinkronisasi")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Store ID", QLabel(TERMINAL_IDENTITY.store_id))
        form.addRow("Register ID", QLabel(TERMINAL_IDENTITY.register_id))
        form.addRow("Device ID", QLabel(TERMINAL_IDENTITY.device_id))

        status = self.hardware_service.status()
        form.addRow("Printer", QLabel(status.description))
        form.addRow(
            "Cash drawer",
            QLabel("Enabled" if status.drawer_enabled else "Disabled"),
        )
        self.pending_label = QLabel()
        form.addRow("Pending sync", self.pending_label)
        layout.addLayout(form)

        test_printer = QPushButton("Test Printer ESC/POS")
        drawer = QPushButton("Buka Cash Drawer")
        sync_now = QPushButton("Sync Sekarang")
        sync_now.setObjectName("PrimaryButton")
        layout.addWidget(test_printer)
        layout.addWidget(drawer)
        layout.addWidget(sync_now)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        test_printer.clicked.connect(self.test_printer)
        drawer.clicked.connect(self.open_drawer)
        sync_now.clicked.connect(self.sync_now)
        self.refresh()

    def refresh(self) -> None:
        self.pending_label.setText(str(self.sync_service.pending_count()))

    def test_printer(self) -> None:
        try:
            self.hardware_service.test_print()
        except HardwareError as exc:
            QMessageBox.warning(self, "Printer", str(exc))
            return
        QMessageBox.information(self, "Printer", "Test print berhasil dikirim.")

    def open_drawer(self) -> None:
        try:
            self.hardware_service.open_cash_drawer()
        except HardwareError as exc:
            QMessageBox.warning(self, "Cash Drawer", str(exc))
            return
        QMessageBox.information(self, "Cash Drawer", "Perintah buka laci kas berhasil dikirim.")

    def sync_now(self) -> None:
        try:
            result = self.sync_service.sync_once()
        except Exception as exc:
            QMessageBox.critical(self, "Sinkronisasi Gagal", str(exc))
            self.refresh()
            return

        self.refresh()
        if not result["enabled"]:
            QMessageBox.information(
                self,
                "Sinkronisasi",
                "Sinkronisasi pusat belum diaktifkan. Atur POS_SYNC_ENABLED=true.",
            )
            return
        QMessageBox.information(
            self,
            "Sinkronisasi",
            f"Sent: {result['sent']}\nFailed: {result['failed']}\nPending: {result['pending']}",
        )
