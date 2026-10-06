import sys

from PySide6.QtWidgets import QApplication

from app.database import Database
from app.services import AuthService, CatalogService, ReceiptService, SaleService
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
    receipt_service = ReceiptService()

    window = LoginWindow(
        auth_service=auth_service,
        catalog_service=catalog_service,
        sale_service=sale_service,
        receipt_service=receipt_service,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
