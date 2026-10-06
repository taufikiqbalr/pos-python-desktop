APP_STYLESHEET = """
QWidget {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #172033;
}
QMainWindow, QDialog, QWidget#RootWidget { background: #f5f7fb; }
QFrame#Card {
    background: white;
    border: 1px solid #e4e8f0;
    border-radius: 12px;
}
QLabel#Title { font-size: 24px; font-weight: 700; color: #10213f; }
QLabel#Subtitle { color: #657089; }
QLabel#TotalLabel { font-size: 14px; color: #657089; }
QLabel#GrandTotal { font-size: 30px; font-weight: 800; color: #0b6b4f; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background: white;
    border: 1px solid #cfd6e4;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
    border: 2px solid #1e6ad6;
}
QPushButton {
    background: #eef2f8;
    border: 1px solid #d6deeb;
    border-radius: 8px;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #e2e9f4; }
QPushButton#PrimaryButton {
    background: #1769d2;
    color: white;
    border: none;
}
QPushButton#PrimaryButton:hover { background: #0f59b8; }
QPushButton#PayButton {
    background: #0b7a57;
    color: white;
    border: none;
    font-size: 18px;
    padding: 14px;
}
QPushButton#DangerButton { background: #fff0f0; color: #b42318; border-color: #ffd0cd; }
QTableWidget {
    background: white;
    border: 1px solid #e1e6ef;
    border-radius: 10px;
    gridline-color: #edf0f5;
    selection-background-color: #dbeafe;
    selection-color: #172033;
}
QHeaderView::section {
    background: #f0f3f8;
    color: #465168;
    border: none;
    border-bottom: 1px solid #dce2ec;
    padding: 9px;
    font-weight: 700;
}
QStatusBar { background: white; border-top: 1px solid #e1e6ef; }
"""
