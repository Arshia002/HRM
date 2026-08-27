"""Modern native Qt desktop client; no browser or embedded web engine."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGraphicsScene, QGraphicsView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from . import __version__
from .api_client import ApiClient, ApiError
from .config import ClientConfig, default_client_config

APP_STYLE = """
QWidget { font-family: Tahoma, Segoe UI; font-size: 10pt; color: #172B4D; }
QMainWindow, QDialog { background: #F4F7FB; }
QFrame#sidebar { background: #12395B; border: none; }
QListWidget#nav { background: transparent; border: none; color: #EAF2F8; outline: none; }
QListWidget#nav::item { padding: 13px 16px; margin: 3px 6px; border-radius: 8px; }
QListWidget#nav::item:selected { background: #0F8B8D; color: white; }
QPushButton { background: #0F8B8D; color: white; border: none; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #0B7476; }
QPushButton[secondary="true"] { background: #E7EDF4; color: #12395B; }
QLineEdit, QComboBox, QTextEdit { background: white; border: 1px solid #C7D2E0; border-radius: 6px; padding: 7px; }
QTableWidget { background: white; border: 1px solid #D7E0EA; border-radius: 8px; gridline-color: #E7EDF4; }
QHeaderView::section { background: #EAF2F8; color: #12395B; border: none; padding: 8px; font-weight: bold; }
QLabel#title { font-size: 19pt; font-weight: 700; color: #12395B; }
QLabel#cardValue { font-size: 24pt; font-weight: 700; color: #0F8B8D; }
QFrame#card { background: white; border: 1px solid #DDE5EE; border-radius: 12px; }
"""

PERSON_FIELDS = (
    ("personnel_no", "شماره پرسنلی"), ("first_name", "نام"), ("last_name", "نام خانوادگی"),
    ("full_name", "نام کامل"), ("gender", "جنسیت"), ("organizational_unit", "واحد سازمانی"),
    ("position_code", "کد پست"), ("position_title", "عنوان پست"),
    ("employment_group", "گروه استخدامی"), ("employment_subtype", "نوع استخدام"),
    ("status", "وضعیت"), ("activity_area", "حوزه فعالیت"), ("actual_location", "محل خدمت"),
    ("company", "شرکت"), ("chart_page_no", "صفحه چارت"), ("chart_node_id", "گره چارت"),
)


def error(parent: QWidget, message: str) -> None:
    QMessageBox.critical(parent, "خطای HRM", message)


class LoginDialog(QDialog):
    def __init__(self, config: ClientConfig):
        super().__init__()
        self.config = config
        self.client: ApiClient | None = None
        self.user: dict[str, Any] | None = None
        self.setWindowTitle("ورود به HRM")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        title = QLabel("HRM | سامانه مدیریت منابع انسانی")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel("اتصال رمزنگاری‌شده به سرور مرکزی")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        form = QFormLayout()
        self.server = QLineEdit(config.server_url)
        self.username = QLineEdit("arshia.shahbazi")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.otp = QLineEdit()
        self.otp.setPlaceholderText("کد ۶ رقمی یا کد بازیابی")
        self.otp.setMaxLength(11)
        form.addRow("آدرس سرور:", self.server)
        form.addRow("نام کاربری:", self.username)
        form.addRow("رمز عبور:", self.password)
        form.addRow("کد دومرحله‌ای:", self.otp)
        layout.addLayout(form)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#B42318")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox()
        login = buttons.addButton("ورود", QDialogButtonBox.AcceptRole)
        cancel = buttons.addButton("انصراف", QDialogButtonBox.RejectRole)
        login.clicked.connect(self.submit)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def confirm_certificate(self, fingerprint: str) -> bool:
        text = ("این نخستین اتصال به سرور است. اثر انگشت گواهی را با فایل FIRST_LOGIN روی سرور مقایسه کنید:\n\n"
                f"{fingerprint}\n\nاین گواهی مورد تأیید است؟")
        return QMessageBox.question(self, "تأیید هویت سرور", text) == QMessageBox.Yes

    def submit(self) -> None:
        server = self.server.text().strip().rstrip("/")
        if not server.startswith(("https://", "http://")):
            server = "https://" + server
        if server.startswith("http://") and QMessageBox.warning(
            self, "ارتباط ناامن", "این اتصال رمزنگاری نشده است. فقط برای عیب‌یابی ادامه دهید.",
            QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
            return
        client = ApiClient(server, tls_fingerprint=self.config.tls_fingerprint,
                           certificate_prompt=self.confirm_certificate)
        try:
            client.health()
            result = client.login(self.username.text(), self.password.text(), self.otp.text())
            if result["user"].get("must_change_password"):
                self.force_password_change(client)
                result["user"]["must_change_password"] = 0
            self.config.server_url = server
            self.config.tls_fingerprint = client.tls_fingerprint
            self.config.save()
            self.client, self.user = client, result["user"]
            self.accept()
        except ApiError as exc:
            if exc.code == "mfa_required":
                self.status.setText("کد برنامه Authenticator را وارد کنید.")
                self.otp.setFocus()
            else:
                self.status.setText(str(exc))

    def force_password_change(self, client: ApiClient) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("تغییر اجباری رمز")
        form = QFormLayout(dialog)
        first, second = QLineEdit(), QLineEdit()
        first.setEchoMode(QLineEdit.Password)
        second.setEchoMode(QLineEdit.Password)
        form.addRow("رمز جدید:", first)
        form.addRow("تکرار رمز:", second)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.Accepted:
            raise ApiError("تغییر رمز اولیه لغو شد.")
        if first.text() != second.text():
            raise ApiError("دو رمز واردشده یکسان نیستند.")
        client.request("POST", "/api/change-password", {
            "current_password": self.password.text(), "new_password": first.text(),
        })


class Page(QWidget):
    def __init__(self, window: "MainWindow", title: str):
        super().__init__()
        self.window = window
        self.layout = QVBoxLayout(self)
        label = QLabel(title)
        label.setObjectName("title")
        self.layout.addWidget(label)

    def call(self, method: str, path: str, data=None, query=None):
        return self.window.call(method, path, data, query)

    def refresh(self) -> None:
        pass


class DashboardPage(Page):
    def __init__(self, window: "MainWindow"):
        super().__init__(window, "داشبورد مدیریتی")
        toolbar = QHBoxLayout()
        manage = QPushButton("مدیریت ویجت‌ها")
        manage.clicked.connect(self.manage_widgets)
        toolbar.addWidget(manage)
        toolbar.addStretch()
        self.layout.addLayout(toolbar)
        self.cards = QHBoxLayout()
        self.layout.addLayout(self.cards)
        self.widgets = QVBoxLayout()
        self.layout.addLayout(self.widgets)
        self.layout.addStretch()

    def refresh(self) -> None:
        result = self.call("GET", "/api/dashboard")
        if not result:
            return
        while self.cards.count():
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for key, title in (("personnel", "کل پرسنل"), ("active", "فعال"), ("units", "واحدها"), ("unassigned", "فاقد پست")):
            frame = QFrame()
            frame.setObjectName("card")
            box = QVBoxLayout(frame)
            caption, value = QLabel(title), QLabel(str(result["stats"].get(key, 0)))
            value.setObjectName("cardValue")
            caption.setAlignment(Qt.AlignCenter)
            value.setAlignment(Qt.AlignCenter)
            box.addWidget(caption)
            box.addWidget(value)
            self.cards.addWidget(frame)
        while self.widgets.count():
            item = self.widgets.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for widget in result["widgets"]:
            if widget["is_enabled"]:
                text = widget.get("config", {}).get("text", "")
                label = QLabel(f"{widget['title']}: {text}")
                label.setStyleSheet("background:white;border:1px solid #DDE5EE;border-radius:8px;padding:12px")
                self.widgets.addWidget(label)
        self.widget_items = result["widgets"]
        self.window.revision = int(result["stats"].get("revision", self.window.revision))

    def manage_widgets(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("مدیریت ویجت‌های داشبورد")
        dialog.resize(680, 430)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["عنوان", "نوع", "فعال"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        items = list(getattr(self, "widget_items", []))
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            for column, value in enumerate((item["title"], item["widget_type"], "بله" if item["is_enabled"] else "خیر")):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        buttons = QHBoxLayout()
        add, edit_button, delete = QPushButton("افزودن"), QPushButton("ویرایش"), QPushButton("حذف")
        buttons.addWidget(add); buttons.addWidget(edit_button); buttons.addWidget(delete); buttons.addStretch()
        layout.addLayout(buttons)

        def edit_widget(existing: dict[str, Any] | None = None) -> None:
            editor = QDialog(dialog); form = QFormLayout(editor)
            title = QLineEdit(str((existing or {}).get("title", "")))
            text = QLineEdit(str((existing or {}).get("config", {}).get("text", "")))
            form.addRow("عنوان:", title); form.addRow("متن:", text)
            controls = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            controls.accepted.connect(editor.accept); controls.rejected.connect(editor.reject); form.addRow(controls)
            if editor.exec() != QDialog.Accepted:
                return
            payload = {"title": title.text(), "widget_type": "text", "config": {"text": text.text()},
                       "position": len(items) + 1, "is_enabled": True}
            if existing:
                payload.update({"id": existing["id"], "row_version": existing["row_version"],
                                "position": existing["position"], "is_enabled": bool(existing["is_enabled"])})
            if self.call("POST", "/api/dashboard/widgets", payload):
                dialog.accept(); self.refresh()

        def selected() -> dict[str, Any] | None:
            row = table.currentRow()
            return items[row] if 0 <= row < len(items) else None

        def remove() -> None:
            item = selected()
            if item and QMessageBox.question(dialog, "حذف ویجت", "ویجت حذف شود؟") == QMessageBox.Yes:
                if self.call("DELETE", f"/api/dashboard/widgets/{item['id']}",
                             query={"version": item["row_version"]}):
                    dialog.accept(); self.refresh()

        add.clicked.connect(lambda: edit_widget())
        edit_button.clicked.connect(lambda: edit_widget(selected()) if selected() else None)
        delete.clicked.connect(remove)
        dialog.exec()


class PersonDialog(QDialog):
    def __init__(self, person: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.person = person or {}
        self.inputs: dict[str, QLineEdit] = {}
        self.setWindowTitle("ویرایش پرسنل" if person else "پرسنل جدید")
        self.setMinimumWidth(620)
        form = QFormLayout(self)
        for key, title in PERSON_FIELDS:
            field = QLineEdit(str(self.person.get(key, "") or ""))
            self.inputs[key] = field
            form.addRow(title + ":", field)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def payload(self) -> dict[str, Any]:
        value = {key: field.text() for key, field in self.inputs.items()}
        if self.person:
            value.update({"id": self.person["id"], "row_version": self.person["row_version"],
                          "extra": self.person.get("extra", {})})
        return value


class PersonnelPage(Page):
    columns = (("personnel_no", "شماره"), ("full_name", "نام کامل"),
               ("organizational_unit", "واحد"), ("position_title", "عنوان پست"),
               ("employment_group", "استخدام"), ("status", "وضعیت"))

    def __init__(self, window: "MainWindow"):
        super().__init__(window, "مدیریت پرسنل")
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("نام، شماره پرسنلی، واحد یا عنوان پست")
        self.search.returnPressed.connect(self.refresh)
        bar.addWidget(self.search)
        for title, slot, secondary in (("جستجو", self.refresh, False), ("افزودن", self.add, False),
                                        ("ویرایش", self.edit, True), ("حذف", self.delete, True)):
            button = QPushButton(title)
            button.setProperty("secondary", secondary)
            button.clicked.connect(slot)
            bar.addWidget(button)
        self.layout.addLayout(bar)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([title for _, title in self.columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit)
        self.layout.addWidget(self.table)
        self.rows: list[dict[str, Any]] = []

    def refresh(self) -> None:
        result = self.call("GET", "/api/personnel", query={"q": self.search.text(), "limit": 1000})
        if not result:
            return
        self.rows = result["items"]
        self.table.setRowCount(len(self.rows))
        for row_no, row in enumerate(self.rows):
            for column_no, (key, _) in enumerate(self.columns):
                self.table.setItem(row_no, column_no, QTableWidgetItem(str(row.get(key, "") or "")))

    def selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def add(self) -> None:
        dialog = PersonDialog(parent=self)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/personnel", dialog.payload()):
            self.refresh()

    def edit(self) -> None:
        selected = self.selected()
        if not selected:
            return
        detail = self.call("GET", f"/api/personnel/{selected['id']}")
        if not detail:
            return
        dialog = PersonDialog(detail, self)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/personnel", dialog.payload()):
            self.refresh()

    def delete(self) -> None:
        selected = self.selected()
        if selected and QMessageBox.question(self, "تأیید حذف", f"{selected['full_name']} حذف شود؟") == QMessageBox.Yes:
            if self.call("DELETE", f"/api/personnel/{selected['id']}", query={"version": selected["row_version"]}):
                self.refresh()


class ChartPage(Page):
    def __init__(self, window: "MainWindow"):
        super().__init__(window, "چارت سازمانی")
        bar = QHBoxLayout()
        self.pages = QComboBox()
        self.pages.currentIndexChanged.connect(self.load_page)
        rename = QPushButton("تغییر عنوان صفحه")
        rename.clicked.connect(self.rename)
        bar.addWidget(self.pages)
        bar.addWidget(rename)
        self.layout.addLayout(bar)
        self.view = QGraphicsView()
        self.view.setRenderHint(QPainter.Antialiasing)
        self.scene = QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        self.layout.addWidget(self.view)
        self.items: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None

    def refresh(self) -> None:
        result = self.call("GET", "/api/chart/pages")
        if not result:
            return
        self.items = result["items"]
        self.pages.blockSignals(True)
        self.pages.clear()
        self.pages.addItems([f"{item['page_no']} — {item['title']}" for item in self.items])
        self.pages.blockSignals(False)
        self.load_page()

    def load_page(self) -> None:
        index = self.pages.currentIndex()
        if not 0 <= index < len(self.items):
            return
        page = self.call("GET", f"/api/chart/pages/{self.items[index]['page_no']}")
        if not page:
            return
        self.current = page
        self.scene.clear()
        width, height = 1200.0, 800.0
        pen = QPen(QColor("#98A2B3"), 1.5)
        for line in page.get("lines", []):
            self.scene.addLine(float(line.get("x1", 0)) * width / 100,
                               float(line.get("y1", 0)) * height / 100,
                               float(line.get("x2", 0)) * width / 100,
                               float(line.get("y2", 0)) * height / 100, pen)
        for node in page.get("nodes", []):
            x, y = float(node.get("x", 0)) * width / 100, float(node.get("y", 0)) * height / 100
            w, h = max(100, float(node.get("w", 12)) * width / 100), max(45, float(node.get("h", 6)) * height / 100)
            rect = self.scene.addRect(x, y, w, h, QPen(QColor("#16877C"), 2), QColor("white"))
            text = self.scene.addText(str(node.get("text") or node.get("id", "پست")), QFont("Tahoma", 8))
            text.setTextWidth(w - 8)
            text.setPos(x + 4, y + 4)
            rect.setToolTip(str(node.get("id", "")))
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def rename(self) -> None:
        if not self.current:
            return
        dialog = QDialog(self)
        form = QFormLayout(dialog)
        title = QLineEdit(self.current["title"])
        form.addRow("عنوان:", title)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            payload = dict(self.current)
            payload["title"] = title.text()
            if self.call("PUT", f"/api/chart/pages/{self.current['page_no']}", payload):
                self.refresh()


class WorkflowPage(Page):
    columns = (("title", "عنوان"), ("workflow_type", "نوع"), ("entity_id", "موضوع"),
               ("state", "وضعیت"), ("assigned_name", "مسئول"), ("updated_at", "آخرین تغییر"))

    def __init__(self, window: "MainWindow"):
        super().__init__(window, "گردش کار و پیگیری")
        bar = QHBoxLayout()
        for title, slot in (("گردش کار جدید", self.create), ("شروع", lambda: self.transition("in_progress")),
                            ("تأیید", lambda: self.transition("approved")),
                            ("رد", lambda: self.transition("rejected")), ("تازه‌سازی", self.refresh)):
            button = QPushButton(title)
            button.clicked.connect(slot)
            bar.addWidget(button)
        bar.addStretch()
        self.layout.addLayout(bar)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([title for _, title in self.columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.layout.addWidget(self.table)
        self.rows: list[dict[str, Any]] = []

    def refresh(self) -> None:
        result = self.call("GET", "/api/workflows")
        if not result:
            return
        self.rows = result["items"]
        self.table.setRowCount(len(self.rows))
        for r, item in enumerate(self.rows):
            for c, (key, _) in enumerate(self.columns):
                self.table.setItem(r, c, QTableWidgetItem(str(item.get(key, "") or "")))

    def create(self) -> None:
        dialog = QDialog(self)
        form = QFormLayout(dialog)
        title, entity = QLineEdit(), QLineEdit()
        kind = QComboBox(); kind.addItems(["general", "contract", "leave", "document"])
        form.addRow("عنوان:", title); form.addRow("نوع:", kind); form.addRow("شناسه پرسنل/موضوع:", entity)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/workflows", {
            "title": title.text(), "workflow_type": kind.currentText(), "entity_type": "personnel",
            "entity_id": entity.text(), "payload": {},
        }):
            self.refresh()

    def transition(self, state: str) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.rows):
            return
        item = self.rows[row]
        if self.call("POST", f"/api/workflows/{item['id']}/transition",
                     {"state": state, "note": "", "row_version": item["row_version"]}):
            self.refresh()


class NotificationsPage(Page):
    def __init__(self, window: "MainWindow"):
        super().__init__(window, "اعلان‌ها")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["زمان", "سطح", "عنوان", "پیام"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.layout.addWidget(self.table)

    def refresh(self) -> None:
        result = self.call("GET", "/api/notifications")
        if not result:
            return
        rows = result["items"]
        self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            for c, key in enumerate(("created_at", "severity", "title", "message")):
                self.table.setItem(r, c, QTableWidgetItem(str(item.get(key, ""))))


class AdminPage(Page):
    def __init__(self, window: "MainWindow"):
        super().__init__(window, "مدیریت، امنیت و پایش")
        bar = QHBoxLayout()
        for title, slot in (("پشتیبان فوری", self.backup), ("فعال‌سازی MFA", self.setup_mfa),
                            ("پایش سامانه", self.monitor), ("کاربر جدید", self.add_user)):
            button = QPushButton(title); button.clicked.connect(slot); bar.addWidget(button)
        bar.addStretch(); self.layout.addLayout(bar)
        self.output = QTextEdit(); self.output.setReadOnly(True); self.layout.addWidget(self.output)

    def refresh(self) -> None:
        self.output.setPlainText(f"کاربر: {self.window.user['display_name']}\nنقش: {self.window.user['role']}\nسرور: {self.window.client.base_url}")

    def backup(self) -> None:
        result = self.call("POST", "/api/backup", {})
        if result:
            QMessageBox.information(self, "پشتیبان", f"پشتیبان سالم ساخته شد:\n{result['filename']}")

    def monitor(self) -> None:
        result = self.call("GET", "/api/monitoring")
        if result:
            metrics = result["metrics"]
            self.output.setPlainText("\n".join(f"{key}: {value}" for key, value in metrics.items()))

    def setup_mfa(self) -> None:
        password, accepted = self.get_text("فعال‌سازی MFA", "رمز عبور فعلی:", password=True)
        if not accepted:
            return
        setup = self.call("POST", "/api/mfa/setup", {"current_password": password})
        if not setup:
            return
        code, ok = self.get_text("فعال‌سازی MFA", f"این Secret را در Authenticator وارد کنید:\n{setup['secret']}\n\nکد ۶ رقمی:")
        if ok:
            result = self.call("POST", "/api/mfa/confirm", {"code": code})
            if result:
                QMessageBox.information(self, "کدهای بازیابی", "این کدها را امن نگهداری کنید:\n" + "\n".join(result["recovery_codes"]))

    def add_user(self) -> None:
        dialog = QDialog(self); form = QFormLayout(dialog)
        username, name, password = QLineEdit(), QLineEdit(), QLineEdit(); password.setEchoMode(QLineEdit.Password)
        role = QComboBox(); role.addItems(["admin", "editor", "viewer"])
        form.addRow("نام کاربری:", username); form.addRow("نام نمایشی:", name)
        form.addRow("رمز موقت:", password); form.addRow("نقش:", role)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/users", {
            "username": username.text(), "display_name": name.text(), "password": password.text(),
            "role": role.currentText(),
        }):
            QMessageBox.information(self, "کاربر", "کاربر با الزام تغییر رمز اولیه ایجاد شد.")

    def get_text(self, title: str, label: str, password: bool = False) -> tuple[str, bool]:
        dialog = QDialog(self); form = QFormLayout(dialog); text = QLineEdit(); form.addRow(label, text)
        if password:
            text.setEchoMode(QLineEdit.Password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        accepted = dialog.exec() == QDialog.Accepted
        return text.text(), accepted


class AuditPage(Page):
    def __init__(self, window: "MainWindow"):
        super().__init__(window, "ممیزی تغییرات")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["زمان", "کاربر", "عملیات", "نوع", "شناسه"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.layout.addWidget(self.table)
        self.chain = QLabel(""); self.layout.addWidget(self.chain)

    def refresh(self) -> None:
        result = self.call("GET", "/api/audit")
        if not result:
            return
        rows = result["items"]; self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            for c, key in enumerate(("occurred_at", "username", "action", "entity_type", "entity_id")):
                self.table.setItem(r, c, QTableWidgetItem(str(item.get(key, "") or "سیستم")))
        self.chain.setText("سلامت زنجیره ممیزی: " + ("تأیید شد" if result["chain_valid"] else "نامعتبر"))


class MainWindow(QMainWindow):
    def __init__(self, client: ApiClient, user: dict[str, Any], poll_seconds: int):
        super().__init__()
        self.client, self.user, self.revision = client, user, 0
        self.setWindowTitle(f"HRM {__version__} — {user['display_name']}")
        self.resize(1380, 820)
        shell = QWidget(); root = QHBoxLayout(shell); root.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        logo = QLabel("HRM\nمدیریت منابع انسانی"); logo.setStyleSheet("color:white;font-size:16pt;font-weight:bold;padding:16px")
        logo.setAlignment(Qt.AlignCenter); side.addWidget(logo)
        self.nav = QListWidget(); self.nav.setObjectName("nav"); side.addWidget(self.nav)
        logout = QPushButton("خروج امن"); logout.clicked.connect(self.close); side.addWidget(logout)
        self.stack = QStackedWidget(); root.addWidget(self.stack, 1); root.addWidget(sidebar)
        self.setCentralWidget(shell)
        definitions: list[tuple[str, Page]] = [
            ("داشبورد", DashboardPage(self)), ("پرسنل", PersonnelPage(self)), ("چارت سازمانی", ChartPage(self)),
            ("گردش کار", WorkflowPage(self)), ("اعلان‌ها", NotificationsPage(self)),
        ]
        if user["role"] in {"owner", "admin"}:
            definitions.extend((("ممیزی", AuditPage(self)), ("مدیریت و پایش", AdminPage(self))))
        self.pages: list[Page] = []
        for title, page in definitions:
            self.nav.addItem(title); self.stack.addWidget(page); self.pages.append(page)
        self.nav.currentRowChanged.connect(self.change_page); self.nav.setCurrentRow(0)
        self.statusBar().showMessage("اتصال امن برقرار است")
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll_changes); self.timer.start(max(2, poll_seconds) * 1000)

    def call(self, method: str, path: str, data=None, query=None):
        try:
            return self.client.request(method, path, data, query)
        except ApiError as exc:
            error(self, str(exc)); return None

    def change_page(self, index: int) -> None:
        if 0 <= index < len(self.pages):
            self.stack.setCurrentIndex(index); self.pages[index].refresh()

    def poll_changes(self) -> None:
        try:
            result = self.client.request("GET", "/api/changes", query={"since": self.revision})
            changed = bool(self.revision and result["items"])
            self.revision = int(result["current_revision"])
            self.statusBar().showMessage(f"متصل و همگام — بازبینی {self.revision}")
            if changed and 0 <= self.stack.currentIndex() < len(self.pages):
                self.pages[self.stack.currentIndex()].refresh()
        except ApiError:
            self.statusBar().showMessage("ارتباط با سرور قطع است؛ تلاش مجدد ادامه دارد")

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.client.logout()
        finally:
            event.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HRM Qt desktop client")
    parser.add_argument("--server")
    parser.add_argument("--tls-fingerprint", default="")
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("HRM")
    app.setApplicationVersion(__version__)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(APP_STYLE)
    config_path = default_client_config() if not args.config else __import__("pathlib").Path(args.config)
    config = ClientConfig.load(config_path)
    if args.server:
        config.server_url = args.server.rstrip("/")
    if args.tls_fingerprint:
        config.tls_fingerprint = args.tls_fingerprint
    login = LoginDialog(config)
    if login.exec() != QDialog.Accepted or not login.client or not login.user:
        return 1
    window = MainWindow(login.client, login.user, config.poll_seconds)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
