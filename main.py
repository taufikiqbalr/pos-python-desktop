import sys

from PySide6.QtWidgets import QApplication

from app.database import Database
from app.hardware import EscPosHardwareService
from app.operations import AuditService, CashMovementService, CustomerService, RefundService
from app.services import AuthService, CatalogService, ReceiptService, SaleService, ShiftService
from app.sync import SyncService
from app.ui.login_window import LoginWindow
from app.ui.styles import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Koperasi BRIN POS")
    app.setStyleSheet(APP_STYLESHEET)

    db = Database()
    db.initialize()

    auth_service = AuthService(db)
    catalog_service = CatalogService(db)
    sale_service = SaleService(db)
    shift_service = ShiftService(db)
    customer_service = CustomerService(db)
    cash_movement_service = CashMovementService(db)
    refund_service = RefundService(db)
    audit_service = AuditService(db)
    receipt_service = ReceiptService()
    hardware_service = EscPosHardwareService()
    sync_service = SyncService(db)

    window = LoginWindow(
        auth_service=auth_service,
        catalog_service=catalog_service,
        sale_service=sale_service,
        shift_service=shift_service,
        customer_service=customer_service,
        cash_movement_service=cash_movement_service,
        refund_service=refund_service,
        audit_service=audit_service,
        receipt_service=receipt_service,
        hardware_service=hardware_service,
        sync_service=sync_service,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
