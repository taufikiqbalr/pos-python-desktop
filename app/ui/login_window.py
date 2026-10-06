from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services import (
    AuthService,
    CatalogService,
    ReceiptService,
    SaleService,
    ShiftService,
)


class LoginWindow(QMainWindow):
    def __init__(
        self,
        *,
        auth_service: AuthService,
        catalog_service: CatalogService,
        sale_service: SaleService,
        shift_service: ShiftService,
        receipt_service: ReceiptService,
    ) -> None:
        super().__init__()
        self.auth_service = auth_service
        self.catalog_service = catalog_service
        self.sale_service = sale_service
        self.shift_service = shift_service
        self.receipt_service = receipt_service
        self.pos_window = None

        self.setWindowTitle("Login - Koperasi BRIN POS")
        self.resize(900, 600)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootWidget")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(80, 70, 80, 70)

        left = QVBoxLayout()
        brand = QLabel("KOPERASI BRIN\nPOINT OF SALES")
        brand.setObjectName("Title")
        intro = QLabel(
            "Aplikasi kasir desktop untuk transaksi toko yang cepat, "
            "sederhana, dan siap diintegrasikan dengan layanan inventory terpisah."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Subtitle")
        left.addStretch()
        left.addWidget(brand)
        left.addSpacing(12)
        left.addWidget(intro)
        left.addStretch()
        outer.addLayout(left, 1)
        outer.addSpacing(50)

        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(390)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 34, 32, 34)
        title = QLabel("Login Kasir")
        title.setObjectName("Title")
        subtitle = QLabel("Masukkan akun kasir untuk memulai transaksi.")
        subtitle.setObjectName("Subtitle")
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        button = QPushButton("Masuk")
        button.setObjectName("PrimaryButton")
        demo = QLabel("Demo: kasir / kasir123")
        demo.setObjectName("Subtitle")
        demo.setAlignment(Qt.AlignCenter)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(20)
        card_layout.addWidget(self.username)
        card_layout.addWidget(self.password)
        card_layout.addSpacing(8)
        card_layout.addWidget(button)
        card_layout.addWidget(demo)
        card_layout.addStretch()
        outer.addWidget(card, 1)

        button.clicked.connect(self.login)
        self.password.returnPressed.connect(self.login)
        self.username.setFocus()

    def login(self) -> None:
        user = self.auth_service.authenticate(self.username.text(), self.password.text())
        if not user:
            QMessageBox.warning(self, "Login Gagal", "Username atau password tidak valid.")
            self.password.selectAll()
            self.password.setFocus()
            return

        from app.ui.pos_window import PosWindow

        self.pos_window = PosWindow(
            user=user,
            auth_service=self.auth_service,
            catalog_service=self.catalog_service,
            sale_service=self.sale_service,
            shift_service=self.shift_service,
            receipt_service=self.receipt_service,
            on_logout=self.show_after_logout,
        )
        self.pos_window.show()
        self.hide()
        self.password.clear()

    def show_after_logout(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.username.setFocus()
