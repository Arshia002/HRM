"""Modern native Qt desktop client; no browser or embedded web engine."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QBoxLayout, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from . import __version__
from .api_client import ApiClient, ApiError
from .config import ClientConfig, default_client_config
from .branding import APP_NAME, COMPANY_NAME, PRODUCT_TAGLINE, PRODUCT_TITLE, logo_path

APP_STYLE = """
QWidget { font-family: Tahoma, Segoe UI; font-size: 10pt; color: #18324A; }
QMainWindow, QDialog { background: #F5F8FC; }
QFrame#sidebar { background: #102F4C; border: none; }
QFrame#topbar { background: #FFFFFF; border-bottom: 1px solid #DCE5EF; }
QFrame#brandPanel { background: #102F4C; border-radius: 20px; }
QFrame#loginPanel { background: #FFFFFF; border: 1px solid #DCE5EF; border-radius: 20px; }
QFrame#card { background: #FFFFFF; border: 1px solid #DCE5EF; border-radius: 14px; }
QFrame#softCard { background: #F9FBFD; border: 1px solid #E4EBF2; border-radius: 12px; }
QListWidget#nav { background: transparent; border: none; color: #DDE9F3; outline: none; padding: 4px; }
QListWidget#nav::item { padding: 12px 15px; margin: 3px 4px; border-radius: 9px; }
QListWidget#nav::item:hover { background: #153B5C; color: white; }
QListWidget#nav::item:selected { background: #0F8B8D; color: white; font-weight: 700; }
QPushButton { background: #0F8B8D; color: white; border: none; border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: #0B7476; }
QPushButton:pressed { background: #086467; }
QPushButton[secondary="true"] { background: #EAF0F6; color: #153B5C; }
QPushButton[secondary="true"]:hover { background: #DDE7F0; }
QPushButton[danger="true"] { background: #7F1D1D; color: white; }
QLineEdit, QComboBox, QTextEdit { background: white; border: 1px solid #C9D6E3; border-radius: 8px; padding: 8px 10px; selection-background-color: #0F8B8D; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 1px solid #0F8B8D; }
QTableWidget { background: white; border: 1px solid #DCE5EF; border-radius: 10px; gridline-color: #E7EDF4; alternate-background-color: #F9FBFD; }
QHeaderView::section { background: #EDF3F8; color: #153B5C; border: none; border-bottom: 1px solid #DCE5EF; padding: 9px; font-weight: bold; }
QLabel#title { font-size: 18pt; font-weight: 700; color: #153B5C; }
QLabel#pageTitle { font-size: 16pt; font-weight: 700; color: #153B5C; }
QLabel#muted { color: #6A7D8F; }
QLabel#brandTitle { color: white; font-size: 21pt; font-weight: 800; }
QLabel#brandSubtitle { color: #DDE9F3; font-size: 10pt; }
QLabel#cardValue { font-size: 25pt; font-weight: 800; color: #0F8B8D; }
QLabel#cardCaption { color: #6A7D8F; font-size: 9pt; font-weight: 600; }
QLabel#connectionBadge { background: #E5F5EE; color: #178A62; border-radius: 10px; padding: 5px 10px; font-weight: 700; }
QLabel#userBadge { background: #EDF3F8; color: #153B5C; border-radius: 10px; padding: 7px 11px; }
QStatusBar { background: #FFFFFF; color: #6A7D8F; border-top: 1px solid #E4EBF2; }
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
        self.setWindowIcon(QIcon(str(logo_path())))
        self.setMinimumSize(860, 520)
        self.resize(920, 560)

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)
        root.setDirection(QBoxLayout.Direction.RightToLeft)

        login_panel = QFrame()
        login_panel.setObjectName("loginPanel")
        login_panel.setMinimumWidth(420)
        login_box = QVBoxLayout(login_panel)
        login_box.setContentsMargins(34, 30, 34, 30)
        login_box.setSpacing(12)

        eyebrow = QLabel("ورود امن به سامانه")
        eyebrow.setObjectName("muted")
        title = QLabel("HRM")
        title.setObjectName("title")
        subtitle = QLabel(PRODUCT_TITLE)
        subtitle.setStyleSheet("font-size:11pt;font-weight:700;color:#31516E")
        login_box.addWidget(eyebrow)
        login_box.addWidget(title)
        login_box.addWidget(subtitle)
        login_box.addSpacing(8)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(11)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.username = QLineEdit("arshia.shahbazi")
        self.username.setPlaceholderText("نام کاربری")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("رمز عبور")
        self.otp = QLineEdit()
        self.otp.setPlaceholderText("کد ۶ رقمی یا کد بازیابی")
        self.otp.setMaxLength(11)
        self.server = QLineEdit(config.server_url)
        self.server.setPlaceholderText("https://server:8765")
        form.addRow("نام کاربری", self.username)
        form.addRow("رمز عبور", self.password)
        form.addRow("کد دومرحله‌ای", self.otp)
        form.addRow("سرور مرکزی", self.server)
        login_box.addLayout(form)

        hint = QLabel("در نصب تازه، رمز اولیه فقط برای فعال‌سازی حساب مالک معتبر است و پس از ورود باید تغییر کند.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        login_box.addWidget(hint)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#B42318;font-weight:600")
        login_box.addWidget(self.status)
        login_box.addStretch()

        actions = QHBoxLayout()
        cancel = QPushButton("انصراف")
        cancel.setProperty("secondary", True)
        login = QPushButton("ورود به HRM")
        login.setDefault(True)
        login.setMinimumWidth(140)
        login.clicked.connect(self.submit)
        cancel.clicked.connect(self.reject)
        actions.addWidget(login)
        actions.addWidget(cancel)
        login_box.addLayout(actions)

        brand_panel = QFrame()
        brand_panel.setObjectName("brandPanel")
        brand_panel.setMinimumWidth(330)
        brand_box = QVBoxLayout(brand_panel)
        brand_box.setContentsMargins(34, 38, 34, 38)
        brand_box.setSpacing(13)
        logo = QLabel()
        pixmap = QPixmap(str(logo_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        brand_box.addWidget(logo)
        brand_box.addSpacing(4)
        brand_title = QLabel("HRM")
        brand_title.setObjectName("brandTitle")
        brand_title.setAlignment(Qt.AlignCenter)
        brand_box.addWidget(brand_title)
        company = QLabel(COMPANY_NAME)
        company.setObjectName("brandSubtitle")
        company.setAlignment(Qt.AlignCenter)
        company.setWordWrap(True)
        brand_box.addWidget(company)
        brand_box.addSpacing(8)
        tagline = QLabel(PRODUCT_TAGLINE)
        tagline.setObjectName("brandSubtitle")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setWordWrap(True)
        brand_box.addWidget(tagline)
        brand_box.addStretch()
        security = QLabel("ارتباط رمزنگاری‌شده • TLS • ثبت رویدادهای مدیریتی")
        security.setObjectName("brandSubtitle")
        security.setAlignment(Qt.AlignCenter)
        security.setWordWrap(True)
        brand_box.addWidget(security)

        root.addWidget(login_panel, 5)
        root.addWidget(brand_panel, 4)
        self.password.setFocus()

    def confirm_certificate(self, fingerprint: str) -> bool:
        text = ("این نخستین اتصال به سرور است. اثر انگشت گواهی را با فایل FIRST_LOGIN روی سرور مقایسه کنید:\n\n"
                f"{fingerprint}\n\nاین گواهی مورد تأیید است؟")
        return QMessageBox.question(self, "تأیید هویت سرور", text) == QMessageBox.Yes

    def submit(self) -> None:
        self.status.setText("")
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
        dialog.setWindowTitle("فعال‌سازی امن حساب")
        dialog.setWindowIcon(QIcon(str(logo_path())))
        dialog.setMinimumWidth(500)
        outer = QVBoxLayout(dialog)
        heading = QLabel("تغییر رمز اولیه")
        heading.setObjectName("title")
        detail = QLabel("برای ادامه استفاده از HRM باید یک رمز شخصی و قوی تعیین کنید. رمز اولیه پس از این مرحله برای همیشه نامعتبر می‌شود.")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        outer.addWidget(heading)
        outer.addWidget(detail)
        form = QFormLayout()
        first, second = QLineEdit(), QLineEdit()
        first.setEchoMode(QLineEdit.Password)
        second.setEchoMode(QLineEdit.Password)
        first.setPlaceholderText("رمز جدید")
        second.setPlaceholderText("تکرار رمز جدید")
        form.addRow("رمز جدید", first)
        form.addRow("تکرار رمز", second)
        outer.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        outer.addWidget(buttons)
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
        self.layout.setContentsMargins(26, 22, 26, 22)
        self.layout.setSpacing(14)
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
        self.cards = QGridLayout()
        self.cards.setHorizontalSpacing(12)
        self.cards.setVerticalSpacing(12)
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
        for card_index, (key, title) in enumerate((("personnel", "کل پرسنل"), ("active", "پرسنل فعال"), ("units", "واحدهای سازمانی"), ("unassigned", "فاقد پست"))):
            frame = QFrame()
            frame.setObjectName("card")
            box = QVBoxLayout(frame)
            caption, value = QLabel(title), QLabel(str(result["stats"].get(key, 0)))
            caption.setObjectName("cardCaption")
            value.setObjectName("cardValue")
            caption.setAlignment(Qt.AlignRight)
            value.setAlignment(Qt.AlignRight)
            box.setContentsMargins(18, 15, 18, 15)
            box.addWidget(caption)
            box.addWidget(value)
            self.cards.addWidget(frame, 0, card_index)
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


class PersonnelProfileDialog(QDialog):
    def __init__(self, person: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("پروفایل پرسنلی")
        self.setMinimumSize(720, 560)
        outer = QVBoxLayout(self)
        heading = QLabel(str(person.get("full_name", "") or "پروفایل پرسنلی"))
        heading.setObjectName("title")
        meta = QLabel(f"شماره پرسنلی: {person.get('personnel_no', '-')}  •  وضعیت: {person.get('status', '-')}")
        meta.setObjectName("muted")
        outer.addWidget(heading); outer.addWidget(meta)
        card = QFrame(); card.setObjectName("card")
        form = QFormLayout(card)
        for key, title in PERSON_FIELDS:
            value = QLabel(str(person.get(key, "") or "—"))
            value.setWordWrap(True); value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(title + ":", value)
        assignment = person.get("assignment") or {}
        if assignment:
            form.addRow("واحد نرمال‌شده:", QLabel(str(assignment.get("unit_title", "") or "—")))
            form.addRow("پست نرمال‌شده:", QLabel(str(assignment.get("normalized_position_title", "") or "—")))
            form.addRow("کد پست نرمال‌شده:", QLabel(str(assignment.get("normalized_position_code", "") or "—")))
        outer.addWidget(card)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject); buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)


class PersonnelPage(Page):
    columns = (("personnel_no", "شماره"), ("full_name", "نام کامل"),
               ("organizational_unit", "واحد"), ("position_title", "عنوان پست"),
               ("employment_group", "استخدام"), ("status", "وضعیت"))

    def __init__(self, window: "MainWindow"):
        super().__init__(window, "مدیریت پرسنل")
        filters = QGridLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("نام، شماره پرسنلی، واحد یا عنوان پست")
        self.search.returnPressed.connect(self.refresh)
        self.unit_filter, self.employment_filter = QComboBox(), QComboBox()
        self.status_filter, self.location_filter = QComboBox(), QComboBox()
        for combo, title in ((self.unit_filter, "همه واحدها"), (self.employment_filter, "همه گروه‌های استخدامی"),
                             (self.status_filter, "همه وضعیت‌ها"), (self.location_filter, "همه محل‌های خدمت")):
            combo.addItem(title, ""); combo.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.search, 0, 0, 1, 2)
        filters.addWidget(self.unit_filter, 0, 2); filters.addWidget(self.employment_filter, 0, 3)
        filters.addWidget(self.status_filter, 1, 0); filters.addWidget(self.location_filter, 1, 1)
        search_btn = QPushButton("جستجو"); search_btn.clicked.connect(self.refresh); filters.addWidget(search_btn, 1, 2)
        reset_btn = QPushButton("پاک‌کردن فیلترها"); reset_btn.setProperty("secondary", True); reset_btn.clicked.connect(self.reset_filters); filters.addWidget(reset_btn, 1, 3)
        self.layout.addLayout(filters)
        bar = QHBoxLayout()
        for title, slot, secondary in (("پروفایل", self.profile, True), ("افزودن", self.add, False),
                                        ("ویرایش", self.edit, True), ("حذف", self.delete, True)):
            button = QPushButton(title); button.setProperty("secondary", secondary); button.clicked.connect(slot); bar.addWidget(button)
        bar.addStretch(); self.count_label = QLabel(""); self.count_label.setObjectName("muted"); bar.addWidget(self.count_label)
        self.layout.addLayout(bar)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([title for _, title in self.columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.doubleClicked.connect(self.profile)
        self.layout.addWidget(self.table)
        self.rows: list[dict[str, Any]] = []
        self._facets_loaded = False

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        return str(combo.currentData() or "")

    def _load_combo(self, combo: QComboBox, values: list[str], all_title: str) -> None:
        current = self._combo_value(combo)
        combo.blockSignals(True); combo.clear(); combo.addItem(all_title, "")
        for value in values:
            combo.addItem(value, value)
        idx = combo.findData(current); combo.setCurrentIndex(max(0, idx)); combo.blockSignals(False)

    def reset_filters(self) -> None:
        self.search.clear()
        for combo in (self.unit_filter, self.employment_filter, self.status_filter, self.location_filter):
            combo.setCurrentIndex(0)
        self.refresh()

    def refresh(self) -> None:
        result = self.call("GET", "/api/personnel", query={"q": self.search.text(), "limit": 1000,
            "unit": self._combo_value(self.unit_filter), "employment": self._combo_value(self.employment_filter),
            "status": self._combo_value(self.status_filter), "location": self._combo_value(self.location_filter)})
        if not result: return
        facets = result.get("facets", {})
        if not self._facets_loaded:
            self._load_combo(self.unit_filter, facets.get("units", []), "همه واحدها")
            self._load_combo(self.employment_filter, facets.get("employment", []), "همه گروه‌های استخدامی")
            self._load_combo(self.status_filter, facets.get("statuses", []), "همه وضعیت‌ها")
            self._load_combo(self.location_filter, facets.get("locations", []), "همه محل‌های خدمت")
            self._facets_loaded = True
        self.rows = result["items"]; self.count_label.setText(f"{result.get('total', len(self.rows))} رکورد")
        self.table.setRowCount(len(self.rows))
        for row_no, row in enumerate(self.rows):
            for column_no, (key, _) in enumerate(self.columns):
                self.table.setItem(row_no, column_no, QTableWidgetItem(str(row.get(key, "") or "")))

    def selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow(); return self.rows[row] if 0 <= row < len(self.rows) else None

    def profile(self) -> None:
        selected = self.selected()
        if not selected: return
        detail = self.call("GET", f"/api/personnel/{selected['id']}")
        if detail: PersonnelProfileDialog(detail, self).exec()

    def add(self) -> None:
        dialog = PersonDialog(parent=self)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/personnel", dialog.payload()): self.refresh()

    def edit(self) -> None:
        selected = self.selected()
        if not selected: return
        detail = self.call("GET", f"/api/personnel/{selected['id']}")
        if not detail: return
        dialog = PersonDialog(detail, self)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/personnel", dialog.payload()): self.refresh()

    def delete(self) -> None:
        selected = self.selected()
        if selected and QMessageBox.question(self, "تأیید حذف", f"{selected['full_name']} حذف شود؟") == QMessageBox.Yes:
            if self.call("DELETE", f"/api/personnel/{selected['id']}", query={"version": selected["row_version"]}): self.refresh()


class OrganizationPage(Page):
    def __init__(self, window: "MainWindow"):
        super().__init__(window, "ساختار سازمانی، واحدها و پست‌ها")
        self.summary = QHBoxLayout(); self.layout.addLayout(self.summary)
        self.tabs = QTabWidget(); self.layout.addWidget(self.tabs, 1)
        units_tab = QWidget(); units_box = QVBoxLayout(units_tab)
        units_bar = QHBoxLayout(); self.unit_search = QLineEdit(); self.unit_search.setPlaceholderText("جستجو در عنوان، کد یا محل واحد")
        self.unit_search.returnPressed.connect(self.refresh_units); units_bar.addWidget(self.unit_search)
        ub = QPushButton("جستجو"); ub.clicked.connect(self.refresh_units); units_bar.addWidget(ub); units_box.addLayout(units_bar)
        self.units_table = QTableWidget(0, 6); self.units_table.setHorizontalHeaderLabels(["کد", "عنوان واحد", "نوع", "محل", "پست‌ها", "شاغلین"])
        self.units_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.units_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        units_box.addWidget(self.units_table); self.tabs.addTab(units_tab, "واحدها")
        positions_tab = QWidget(); positions_box = QVBoxLayout(positions_tab)
        pos_bar = QHBoxLayout(); self.position_search = QLineEdit(); self.position_search.setPlaceholderText("کد، عنوان پست، واحد یا محل")
        self.position_search.returnPressed.connect(self.refresh_positions); self.occupancy_filter = QComboBox()
        self.occupancy_filter.addItem("همه پست‌ها", ""); self.occupancy_filter.addItem("پست‌های اشغال‌شده", "occupied"); self.occupancy_filter.addItem("پست‌های خالی", "vacant")
        self.occupancy_filter.currentIndexChanged.connect(self.refresh_positions)
        pos_bar.addWidget(self.position_search); pos_bar.addWidget(self.occupancy_filter)
        pb = QPushButton("جستجو"); pb.clicked.connect(self.refresh_positions); pos_bar.addWidget(pb); positions_box.addLayout(pos_bar)
        self.positions_table = QTableWidget(0, 6); self.positions_table.setHorizontalHeaderLabels(["کد", "عنوان پست", "واحد", "محل", "وضعیت اشغال", "متصدی"])
        self.positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.positions_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        positions_box.addWidget(self.positions_table); self.tabs.addTab(positions_tab, "پست‌های سازمانی")

    def refresh(self) -> None:
        info = self.call("GET", "/api/organization/summary")
        if info:
            while self.summary.count():
                item = self.summary.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            for key, title in (("units", "واحدها"), ("positions", "پست‌ها"), ("occupied_positions", "اشغال‌شده"), ("vacant_positions", "خالی")):
                card = QFrame(); card.setObjectName("softCard"); box = QVBoxLayout(card)
                value = QLabel(str(info.get(key, 0))); value.setObjectName("cardValue"); label = QLabel(title); label.setObjectName("cardCaption")
                box.addWidget(value); box.addWidget(label); self.summary.addWidget(card)
        self.refresh_units(); self.refresh_positions()

    def refresh_units(self) -> None:
        result = self.call("GET", "/api/units", query={"q": self.unit_search.text()})
        if not result: return
        rows = result.get("items", []); self.units_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            vals = (row.get("code"), row.get("title"), row.get("unit_type"), row.get("location"), row.get("positions_count"), row.get("assigned_count"))
            for c, value in enumerate(vals): self.units_table.setItem(r, c, QTableWidgetItem(str(value or "")))

    def refresh_positions(self) -> None:
        result = self.call("GET", "/api/positions", query={"q": self.position_search.text(), "occupancy": str(self.occupancy_filter.currentData() or "")})
        if not result: return
        rows = result.get("items", []); self.positions_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            occupied = "اشغال‌شده" if row.get("person_id") else "خالی"
            vals = (row.get("code"), row.get("title"), row.get("unit_title"), row.get("location"), occupied, row.get("occupant_name"))
            for c, value in enumerate(vals): self.positions_table.setItem(r, c, QTableWidgetItem(str(value or "")))


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
    NAV_ITEMS = (
        "داشبورد",
        "پرسنل",
        "واحدها و پست‌ها",
        "چارت سازمانی",
        "گردش کار",
        "اعلان‌ها",
    )

    def __init__(self, client: ApiClient, user: dict[str, Any], poll_seconds: int):
        super().__init__()
        self.client, self.user, self.revision = client, user, 0
        self.setWindowTitle(f"HRM {__version__} — {user['display_name']}")
        self.setWindowIcon(QIcon(str(logo_path())))
        self.setMinimumSize(1180, 700)
        self.resize(1380, 820)

        shell = QWidget()
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setDirection(QBoxLayout.Direction.RightToLeft)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 16)
        side.setSpacing(8)

        brand_row = QHBoxLayout()
        mark = QLabel()
        pixmap = QPixmap(str(logo_path()))
        if not pixmap.isNull():
            mark.setPixmap(pixmap.scaled(54, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        mark.setFixedSize(58, 58)
        brand_text = QVBoxLayout()
        logo = QLabel("HRM")
        logo.setStyleSheet("color:white;font-size:17pt;font-weight:800")
        company = QLabel("منابع انسانی\nتوزیع برق کرمانشاه")
        company.setStyleSheet("color:#C9D9E7;font-size:8.5pt")
        brand_text.addWidget(logo)
        brand_text.addWidget(company)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_text, 1)
        side.addLayout(brand_row)
        side.addSpacing(10)

        menu_label = QLabel("منوی اصلی")
        menu_label.setStyleSheet("color:#8FA9BF;font-size:8.5pt;padding:0 7px")
        side.addWidget(menu_label)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setSpacing(1)
        side.addWidget(self.nav, 1)

        user_panel = QFrame()
        user_panel.setObjectName("softCard")
        user_panel.setStyleSheet("QFrame#softCard{background:#153B5C;border:1px solid #1B496D;border-radius:10px} QLabel{color:white}")
        user_box = QVBoxLayout(user_panel)
        user_box.setContentsMargins(12, 10, 12, 10)
        who = QLabel(user.get("display_name") or user.get("username") or "کاربر HRM")
        who.setStyleSheet("font-weight:700;color:white")
        role = QLabel(f"نقش: {user.get('role', '-')}")
        role.setStyleSheet("color:#BCD0E0;font-size:8.5pt")
        user_box.addWidget(who)
        user_box.addWidget(role)
        side.addWidget(user_panel)
        logout = QPushButton("خروج امن")
        logout.setProperty("danger", True)
        logout.clicked.connect(self.close)
        side.addWidget(logout)
        version = QLabel(f"نسخه {__version__}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color:#8FA9BF;font-size:8pt")
        side.addWidget(version)

        content = QWidget()
        content_box = QVBoxLayout(content)
        content_box.setContentsMargins(0, 0, 0, 0)
        content_box.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(78)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(24, 12, 24, 12)
        top.setDirection(QBoxLayout.Direction.RightToLeft)
        heading = QVBoxLayout()
        self.page_title = QLabel("داشبورد")
        self.page_title.setObjectName("pageTitle")
        self.page_context = QLabel(COMPANY_NAME)
        self.page_context.setObjectName("muted")
        heading.addWidget(self.page_title)
        heading.addWidget(self.page_context)
        top.addLayout(heading, 1)
        self.connection_badge = QLabel("● اتصال امن برقرار است")
        self.connection_badge.setObjectName("connectionBadge")
        self.connection_badge.setAlignment(Qt.AlignCenter)
        top.addWidget(self.connection_badge)
        self.user_badge = QLabel(user.get("display_name") or user.get("username") or "کاربر")
        self.user_badge.setObjectName("userBadge")
        top.addWidget(self.user_badge)
        content_box.addWidget(topbar)

        self.stack = QStackedWidget()
        content_box.addWidget(self.stack, 1)
        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self.setCentralWidget(shell)

        definitions: list[tuple[str, Page]] = [
            ("داشبورد", DashboardPage(self)), ("پرسنل", PersonnelPage(self)),
            ("واحدها و پست‌ها", OrganizationPage(self)), ("چارت سازمانی", ChartPage(self)),
            ("گردش کار", WorkflowPage(self)), ("اعلان‌ها", NotificationsPage(self)),
        ]
        if user["role"] in {"owner", "admin"}:
            definitions.extend((("ممیزی", AuditPage(self)), ("مدیریت و پایش", AdminPage(self))))
        self.pages: list[Page] = []
        self.page_names: list[str] = []
        for title, page in definitions:
            self.nav.addItem(title)
            self.stack.addWidget(page)
            self.pages.append(page)
            self.page_names.append(title)
        self.nav.currentRowChanged.connect(self.change_page)
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("HRM آماده است")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_changes)
        self.timer.start(max(2, poll_seconds) * 1000)

    def call(self, method: str, path: str, data=None, query=None):
        try:
            return self.client.request(method, path, data, query)
        except ApiError as exc:
            error(self, str(exc))
            return None

    def change_page(self, index: int) -> None:
        if 0 <= index < len(self.pages):
            self.page_title.setText(self.page_names[index])
            self.stack.setCurrentIndex(index)
            self.pages[index].refresh()

    def poll_changes(self) -> None:
        try:
            result = self.client.request("GET", "/api/changes", query={"since": self.revision})
            changed = bool(self.revision and result["items"])
            self.revision = int(result["current_revision"])
            self.connection_badge.setText("● متصل و همگام")
            self.connection_badge.setStyleSheet("background:#E5F5EE;color:#178A62;border-radius:10px;padding:5px 10px;font-weight:700")
            self.statusBar().showMessage(f"همگام‌سازی انجام شد — بازبینی {self.revision}")
            if changed and 0 <= self.stack.currentIndex() < len(self.pages):
                self.pages[self.stack.currentIndex()].refresh()
        except ApiError:
            self.connection_badge.setText("● ارتباط با سرور قطع است")
            self.connection_badge.setStyleSheet("background:#FDECEC;color:#B42318;border-radius:10px;padding:5px 10px;font-weight:700")
            self.statusBar().showMessage("ارتباط با سرور قطع است؛ تلاش مجدد ادامه دارد")

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.client.logout()
        finally:
            event.accept()


class _UiSmokeClient:
    """Minimal in-process client used only to construct the frozen native shell in CI."""
    def request(self, method: str, path: str, data=None, query=None):
        if path == "/api/dashboard":
            return {
                "stats": {"personnel": 36, "active": 36, "units": 8, "unassigned": 2, "revision": 1},
                "widgets": [],
            }
        if path == "/api/organization/summary":
            return {"units": 8, "root_units": 8, "positions": 34, "occupied_positions": 32, "vacant_positions": 2}
        if path == "/api/units":
            return {"items": [{"id": "u1", "code": "U-001", "title": "معاونت منابع انسانی", "unit_type": "معاونت", "location": "ستاد", "positions_count": 4, "assigned_count": 3}]}
        if path == "/api/positions":
            return {"items": [{"id": "p1", "code": "P-001", "title": "کارشناس منابع انسانی", "unit_title": "معاونت منابع انسانی", "location": "ستاد", "person_id": "demo-1", "occupant_name": "کاربر آزمایشی"}], "total": 1}
        if path == "/api/personnel":
            return {"items": [], "total": 0, "facets": {"units": [], "employment": [], "statuses": [], "locations": []}}
        if path == "/api/changes":
            return {"items": [], "current_revision": 1}
        return {"items": []}

    def logout(self) -> None:
        return None


def run_ui_smoke(config: ClientConfig, app: QApplication) -> int:
    """Construct the login and dashboard shell without network I/O."""
    login = LoginDialog(config)
    login.ensurePolished()
    if login.minimumWidth() < 800:
        raise RuntimeError("Login shell minimum width contract failed")
    login.close()
    user = {"username": "ci.preview", "display_name": "کاربر آزمایشی", "role": "user"}
    window = MainWindow(_UiSmokeClient(), user, 60)  # type: ignore[arg-type]
    window.ensurePolished()
    app.processEvents()
    if window.minimumWidth() < 1100 or window.nav.count() < 5:
        raise RuntimeError("Main shell geometry/navigation contract failed")
    window.timer.stop()
    window.close()
    print(f"HRM native UI smoke test OK: {__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HRM Qt desktop client")
    parser.add_argument("--server")
    parser.add_argument("--tls-fingerprint", default="")
    parser.add_argument("--config")
    parser.add_argument("--smoke-test", action="store_true", help="Initialize the frozen Qt runtime and exit.")
    parser.add_argument("--ui-smoke-test", action="store_true", help="Construct the native login and dashboard shell without network I/O.")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("HRM")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(logo_path())))
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(APP_STYLE)
    if args.smoke_test:
        print(f"HRM Qt smoke test OK: {__version__}")
        return 0
    config_path = default_client_config() if not args.config else __import__("pathlib").Path(args.config)
    config = ClientConfig.load(config_path)
    if args.ui_smoke_test:
        return run_ui_smoke(config, app)
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
