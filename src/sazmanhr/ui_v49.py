"""Native v4.9 management pages for the HRM desktop client."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


V49_REFERENCE_PAGES = (
    "formalChart",
    "statusChart",
    "personnelDirectory",
    "personnelEducation",
    "jobFamilies",
    "personnelAge",
    "reports",
    "imports",
    "users",
    "history",
    "systemHealth",
    "settings",
)

PERMISSION_LABELS = {
    "read": "مشاهده اطلاعات",
    "edit_personnel": "ایجاد و ویرایش پرسنل",
    "delete_personnel": "حذف پرسنل",
    "edit_chart": "ویرایش چارت سازمانی",
    "edit_dashboard": "ویرایش داشبورد",
    "view_audit": "مشاهده سوابق ممیزی",
    "manage_users": "مدیریت کاربران",
    "backup": "تهیه نسخه پشتیبان",
    "restore": "بازیابی نسخه پشتیبان",
    "manage_workflows": "مدیریت گردش کار",
    "manage_movements": "ثبت جابه‌جایی‌های پرسنلی",
    "reverse_movements": "ابطال آخرین جابه‌جایی پرسنلی",
    "view_monitoring": "مشاهده سلامت سیستم",
    "manage_security": "مدیریت امنیت و MFA",
}


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())


def _text(value: Any, fallback: str = "—") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def _configure_table(table: QTableWidget) -> None:
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)


def _fill_table(table: QTableWidget, rows: list[dict[str, Any]], columns: tuple[tuple[str, str], ...]) -> None:
    table.setRowCount(len(rows))
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels([title for _, title in columns])
    for row_no, row in enumerate(rows):
        for column_no, (key, _) in enumerate(columns):
            item = QTableWidgetItem(_text(row.get(key), ""))
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row_no, column_no, item)


class V49Page(QWidget):
    page_key = ""

    def __init__(self, window, title: str, subtitle: str = ""):
        super().__init__()
        self.window = window
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(26, 22, 26, 26)
        self.layout.setSpacing(15)
        header = QFrame()
        header.setObjectName("pageHero")
        header_box = QHBoxLayout(header)
        header_box.setContentsMargins(20, 16, 20, 16)
        copy = QVBoxLayout()
        eyebrow = QLabel("سامانه یکپارچه منابع انسانی • نمای بومی v4.9")
        eyebrow.setObjectName("eyebrow")
        heading = QLabel(title)
        heading.setObjectName("title")
        copy.addWidget(eyebrow)
        copy.addWidget(heading)
        if subtitle:
            detail = QLabel(subtitle)
            detail.setObjectName("muted")
            detail.setWordWrap(True)
            copy.addWidget(detail)
        header_box.addLayout(copy, 1)
        refresh = QPushButton("تازه‌سازی")
        refresh.setProperty("secondary", True)
        refresh.clicked.connect(self.refresh)
        header_box.addWidget(refresh)
        self.layout.addWidget(header)
        scroll.setWidget(self.body)
        outer.addWidget(scroll)

    def call(self, method: str, path: str, data=None, query=None):
        return self.window.call(method, path, data, query)

    def refresh(self) -> None:
        pass


class MetricGrid(QWidget):
    def __init__(self, definitions: tuple[tuple[str, str], ...], parent=None):
        super().__init__(parent)
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, (key, title) in enumerate(definitions):
            card = QFrame()
            card.setObjectName("metricCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 14, 18, 14)
            caption = QLabel(title)
            caption.setObjectName("cardCaption")
            value = QLabel("—")
            value.setObjectName("cardValue")
            note = QLabel("محاسبه زنده")
            note.setObjectName("metricNote")
            box.addWidget(caption)
            box.addWidget(value)
            box.addWidget(note)
            self.values[key] = value
            grid.addWidget(card, index // 4, index % 4)

    def update_values(self, values: dict[str, Any]) -> None:
        for key, label in self.values.items():
            label.setText(_text(values.get(key), "۰"))


class DistributionCard(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 16)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        box.addWidget(heading)
        if subtitle:
            detail = QLabel(subtitle)
            detail.setObjectName("muted")
            detail.setWordWrap(True)
            box.addWidget(detail)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        box.addLayout(self.rows)
        box.addStretch()

    def set_items(self, items: list[dict[str, Any]], *, empty_message: str = "داده‌ای ثبت نشده است.") -> None:
        _clear_layout(self.rows)
        clean = [item for item in items if int(item.get("count", 0) or 0) > 0]
        maximum = max((int(item.get("count", 0)) for item in clean), default=0)
        if not clean:
            empty = QLabel(empty_message)
            empty.setObjectName("emptyState")
            empty.setWordWrap(True)
            self.rows.addWidget(empty)
            return
        for item in clean[:12]:
            top = QHBoxLayout()
            label = QLabel(_text(item.get("label")))
            value = QLabel(str(int(item.get("count", 0))))
            value.setObjectName("distributionValue")
            top.addWidget(label, 1)
            top.addWidget(value)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, max(1, maximum))
            bar.setValue(int(item.get("count", 0)))
            bar.setFixedHeight(8)
            self.rows.addLayout(top)
            self.rows.addWidget(bar)


class StatusChartPage(V49Page):
    page_key = "statusChart"

    def __init__(self, window):
        super().__init__(window, "وضعیت چارت", "داشبورد زنده استقرار نیروی انسانی، پست‌های مصوب و مقایسه واحدها")
        self.metrics = MetricGrid((
            ("personnel", "کل پرسنل"), ("positions", "پست‌های فعال"),
            ("unassigned", "فاقد پست"), ("approved_chart_total", "جمع چارت مصوب"),
            ("approved_fixed_posts", "پست ثابت"), ("approved_named_posts", "پست بانام"),
            ("chart_pages", "صفحات چارت"), ("units", "واحدهای سازمانی"),
        ))
        self.layout.addWidget(self.metrics)
        distributions = QHBoxLayout()
        self.employment = DistributionCard("ترکیب نیروی انسانی", "توزیع بر اساس گروه استخدامی")
        self.status = DistributionCard("وضعیت‌های پرسنلی", "فعال، انتقالی، بازنشسته و سایر وضعیت‌ها")
        distributions.addWidget(self.employment, 1)
        distributions.addWidget(self.status, 1)
        self.layout.addLayout(distributions)
        title = QLabel("مقایسه حوزه‌های زیرمجموعه")
        title.setObjectName("sectionTitle")
        self.layout.addWidget(title)
        self.units = QTableWidget()
        _configure_table(self.units)
        self.units.setMinimumHeight(330)
        self.layout.addWidget(self.units)

    def refresh(self) -> None:
        payload = self.call("GET", "/api/analytics")
        if not payload:
            return
        self.metrics.update_values(payload.get("summary", {}))
        distributions = payload.get("distributions", {})
        self.employment.set_items(distributions.get("employment", []))
        self.status.set_items(distributions.get("status", []))
        _fill_table(self.units, payload.get("unit_comparison", []), (
            ("unit", "واحد سازمانی"), ("personnel", "تعداد پرسنل"), ("unassigned", "فاقد پست"),
        ))


class PersonnelEducationPage(V49Page):
    page_key = "personnelEducation"

    def __init__(self, window):
        super().__init__(window, "تحصیلات پرسنل", "توزیع سطح تحصیلات و سنجش کامل‌بودن اطلاعات آموزشی")
        self.metrics = MetricGrid((
            ("personnel", "کل پرسنل"), ("known_education", "دارای اطلاعات تحصیلی"),
            ("missing_education", "فاقد اطلاعات تحصیلی"), ("education_coverage", "پوشش اطلاعات (%)"),
        ))
        self.layout.addWidget(self.metrics)
        self.distribution = DistributionCard("توزیع مقاطع تحصیلی", "اطلاعات فقط به‌صورت تجمیعی نمایش داده می‌شود")
        self.layout.addWidget(self.distribution)

    def refresh(self) -> None:
        payload = self.call("GET", "/api/analytics")
        if not payload:
            return
        total = int(payload.get("summary", {}).get("personnel", 0) or 0)
        missing = int(payload.get("quality", {}).get("missing_education", total) or 0)
        known = max(0, total - missing)
        coverage = round((known * 100 / total), 1) if total else 0
        self.metrics.update_values({
            "personnel": total, "known_education": known,
            "missing_education": missing, "education_coverage": coverage,
        })
        self.distribution.set_items(
            payload.get("distributions", {}).get("education", []),
            empty_message="اطلاعات تحصیلی هنوز وارد پایگاه سازمانی نشده است؛ صفحه آماده دریافت داده خصوصی مرحله پایلوت است.",
        )


class PersonnelStatusPage(V49Page):
    page_key = "jobFamilies"

    def __init__(self, window):
        super().__init__(window, "تحلیل وضعیت پرسنل", "نمای یکپارچه نوع همکاری، حوزه فعالیت و وضعیت خدمت")
        grid = QGridLayout()
        self.employment = DistributionCard("نوع همکاری")
        self.subtype = DistributionCard("زیرگروه استخدامی")
        self.activity = DistributionCard("حوزه فعالیت")
        self.status = DistributionCard("وضعیت خدمت")
        grid.addWidget(self.employment, 0, 0)
        grid.addWidget(self.subtype, 0, 1)
        grid.addWidget(self.activity, 1, 0)
        grid.addWidget(self.status, 1, 1)
        self.layout.addLayout(grid)

    def refresh(self) -> None:
        payload = self.call("GET", "/api/analytics")
        if not payload:
            return
        values = payload.get("distributions", {})
        self.employment.set_items(values.get("employment", []))
        self.subtype.set_items(values.get("employment_subtype", []))
        self.activity.set_items(values.get("activity_area", []))
        self.status.set_items(values.get("status", []))


class PersonnelAgePage(V49Page):
    page_key = "personnelAge"

    def __init__(self, window):
        super().__init__(window, "سن پرسنل", "تحلیل بازه‌های سنی و پوشش داده‌های جمعیت‌شناختی")
        self.metrics = MetricGrid((
            ("personnel", "کل پرسنل"), ("known_age", "دارای سن معتبر"),
            ("missing_age", "فاقد اطلاعات سن"), ("age_coverage", "پوشش سن (%)"),
        ))
        self.layout.addWidget(self.metrics)
        row = QHBoxLayout()
        self.age = DistributionCard("توزیع بازه سنی")
        self.gender = DistributionCard("ترکیب جنسیت")
        row.addWidget(self.age, 1)
        row.addWidget(self.gender, 1)
        self.layout.addLayout(row)

    def refresh(self) -> None:
        payload = self.call("GET", "/api/analytics")
        if not payload:
            return
        total = int(payload.get("summary", {}).get("personnel", 0) or 0)
        missing = int(payload.get("quality", {}).get("missing_age", total) or 0)
        known = max(0, total - missing)
        self.metrics.update_values({
            "personnel": total, "known_age": known, "missing_age": missing,
            "age_coverage": round((known * 100 / total), 1) if total else 0,
        })
        values = payload.get("distributions", {})
        self.age.set_items(values.get("age", []), empty_message="تاریخ تولد یا سن معتبر هنوز وارد نشده است.")
        self.gender.set_items(values.get("gender", []))


class ReportsPage(V49Page):
    page_key = "reports"

    QUALITY_COLUMNS = (
        ("label", "کنترل کیفیت"), ("count", "تعداد رکورد نیازمند بررسی"),
    )

    def __init__(self, window):
        super().__init__(window, "داشبورد گزارش‌های مدیریتی", "شاخص‌های کلیدی، هشدارهای کیفیت داده و واحدهای پرتعداد")
        self.metrics = MetricGrid((
            ("personnel", "کل پرسنل"), ("active", "پرسنل فعال"),
            ("units", "واحدها"), ("positions", "پست‌ها"),
            ("unassigned", "فاقد پست"), ("approved_chart_total", "چارت مصوب"),
        ))
        self.layout.addWidget(self.metrics)
        tabs = QTabWidget()
        quality_tab = QWidget()
        quality_box = QVBoxLayout(quality_tab)
        quality_note = QLabel("موارد زیر خطا نیستند؛ صف پاک‌سازی و تکمیل اطلاعات برای مرحله پایلوت‌اند.")
        quality_note.setObjectName("muted")
        quality_box.addWidget(quality_note)
        self.quality = QTableWidget()
        _configure_table(self.quality)
        quality_box.addWidget(self.quality)
        units_tab = QWidget()
        units_box = QVBoxLayout(units_tab)
        self.units = QTableWidget()
        _configure_table(self.units)
        units_box.addWidget(self.units)
        tabs.addTab(quality_tab, "کیفیت اطلاعات")
        tabs.addTab(units_tab, "مقایسه واحدها")
        self.layout.addWidget(tabs)

    def refresh(self) -> None:
        payload = self.call("GET", "/api/analytics")
        if not payload:
            return
        self.metrics.update_values(payload.get("summary", {}))
        labels = {
            "missing_unit": "واحد سازمانی ثبت‌نشده",
            "missing_position": "پست سازمانی ثبت‌نشده",
            "missing_location": "محل خدمت ثبت‌نشده",
            "missing_gender": "جنسیت ثبت‌نشده",
            "missing_education": "تحصیلات ثبت‌نشده",
            "missing_age": "سن/تاریخ تولد ثبت‌نشده",
        }
        quality = [
            {"label": labels[key], "count": value}
            for key, value in payload.get("quality", {}).items() if key in labels
        ]
        _fill_table(self.quality, quality, self.QUALITY_COLUMNS)
        _fill_table(self.units, payload.get("unit_comparison", []), (
            ("unit", "واحد"), ("personnel", "پرسنل"), ("unassigned", "فاقد پست"),
        ))


class ImportPage(V49Page):
    page_key = "imports"

    def __init__(self, window):
        super().__init__(window, "ورود و به‌روزرسانی Excel", "Dry Run امن، گزارش مغایرت و کنترل هدف پیش از هر تغییر سازمانی")
        self.metrics = MetricGrid((
            ("personnel", "پرسنل فعلی"), ("expected_personnel", "هدف پرسنل"),
            ("chart_total", "چارت فعلی"), ("expected_chart", "هدف چارت"),
            ("schema_version", "نسخه Schema"), ("target_ready", "آمادگی هدف"),
        ))
        self.layout.addWidget(self.metrics)
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        self.input_dir = QLineEdit()
        self.input_dir.setPlaceholderText("پوشه فایل‌های خصوصی Excel")
        input_pick = QPushButton("انتخاب پوشه")
        input_pick.setProperty("secondary", True)
        input_pick.clicked.connect(self.choose_input)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_dir, 1)
        input_row.addWidget(input_pick)
        self.output_dir = QLineEdit()
        self.output_dir.setPlaceholderText("پوشه خصوصی گزارش خروجی")
        output_pick = QPushButton("انتخاب خروجی")
        output_pick.setProperty("secondary", True)
        output_pick.clicked.connect(self.choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir, 1)
        output_row.addWidget(output_pick)
        self.expected = QSpinBox()
        self.expected.setRange(1, 100000)
        self.expected.setValue(1356)
        form.addRow("فایل‌های ورودی:", input_row)
        form.addRow("گزارش خصوصی:", output_row)
        form.addRow("تعداد مورد انتظار:", self.expected)
        self.run_button = QPushButton("اجرای Dry Run بدون تغییر دیتابیس")
        self.run_button.clicked.connect(self.run_dry_run)
        form.addRow(self.run_button)
        self.layout.addWidget(card)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(220)
        self.output.setPlaceholderText("خروجی کنترل داده در این قسمت نمایش داده می‌شود.")
        self.layout.addWidget(self.output)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.finished.connect(self.process_finished)

    def refresh(self) -> None:
        status = self.call("GET", "/api/migration/status")
        if not status:
            return
        expected = status.get("expected", {})
        chart = status.get("chart", {})
        self.metrics.update_values({
            "personnel": status.get("personnel", 0),
            "expected_personnel": expected.get("personnel", 1356),
            "chart_total": chart.get("total", 0),
            "expected_chart": expected.get("total", 568),
            "schema_version": status.get("schema_version", 0),
            "target_ready": "آماده" if status.get("enterprise_target_ready") else "نیازمند مرحله داده واقعی",
        })

    def choose_input(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "پوشه Excel خصوصی")
        if value:
            self.input_dir.setText(value)

    def choose_output(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "پوشه گزارش خصوصی")
        if value:
            self.output_dir.setText(value)

    def _migration_command(self) -> tuple[str, list[str]]:
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable).resolve().parent / "Server" / "HRMMigration.exe"
            return str(executable), []
        return sys.executable, ["-m", "tools.real_data_migration"]

    def run_dry_run(self) -> None:
        input_dir = self.input_dir.text().strip()
        output_dir = self.output_dir.text().strip()
        if not input_dir or not output_dir:
            QMessageBox.warning(self, "مسیر ناقص", "پوشه ورودی و پوشه گزارش خصوصی را انتخاب کنید.")
            return
        program, prefix = self._migration_command()
        if getattr(sys, "frozen", False) and not Path(program).is_file():
            QMessageBox.critical(self, "ابزار مهاجرت", "HRMMigration.exe در پوشه نصب پیدا نشد.")
            return
        arguments = [*prefix, "--input-dir", input_dir, "--output-dir", output_dir,
                     "--expected-personnel", str(self.expected.value()),
                     "--expected-fixed", "536", "--expected-named", "32"]
        self.output.clear()
        self.output.append("شروع Dry Run؛ هیچ تغییری در دیتابیس اعمال نمی‌شود…")
        self.run_button.setEnabled(False)
        self.process.start(program, arguments)
        if not self.process.waitForStarted(5000):
            self.run_button.setEnabled(True)
            QMessageBox.critical(self, "ابزار مهاجرت", "اجرای ابزار مهاجرت آغاز نشد.")

    def read_process_output(self) -> None:
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        if raw:
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.output.insertPlainText(raw)

    def process_finished(self, exit_code: int, _status) -> None:
        self.run_button.setEnabled(True)
        if exit_code == 0:
            self.output.append("\nPASS: Dry Run بدون خطای مسدودکننده پایان یافت.")
        else:
            self.output.append(f"\nSTOP: Dry Run با کد {exit_code} پایان یافت؛ گزارش مغایرت را اصلاح کنید.")


class UsersPage(V49Page):
    page_key = "users"

    def __init__(self, window):
        super().__init__(window, "مدیریت کاربران", "نقش‌ها، وضعیت حساب و ریزدسترسی‌های قابل ممیزی")
        bar = QHBoxLayout()
        add = QPushButton("کاربر جدید")
        add.clicked.connect(self.add_user)
        access = QPushButton("تنظیم ریزدسترسی")
        access.setProperty("secondary", True)
        access.clicked.connect(self.edit_access)
        bar.addWidget(add)
        bar.addWidget(access)
        bar.addStretch()
        self.layout.addLayout(bar)
        self.table = QTableWidget()
        _configure_table(self.table)
        self.layout.addWidget(self.table)
        self.rows: list[dict[str, Any]] = []

    def refresh(self) -> None:
        payload = self.call("GET", "/api/users")
        if not payload:
            return
        self.rows = payload.get("items", [])
        display = []
        for row in self.rows:
            display.append({
                **row,
                "active_label": "فعال" if row.get("is_active") else "غیرفعال",
                "password_state": "نیازمند تغییر" if row.get("must_change_password") else "تثبیت‌شده",
                "access_count": len(row.get("permissions", [])),
            })
        _fill_table(self.table, display, (
            ("display_name", "نام"), ("username", "نام کاربری"), ("role", "نقش"),
            ("active_label", "وضعیت"), ("password_state", "رمز"), ("access_count", "تعداد دسترسی"),
        ))

    def selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def add_user(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("کاربر جدید")
        form = QFormLayout(dialog)
        username, name, password = QLineEdit(), QLineEdit(), QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        role = QComboBox()
        role.addItems(["admin", "editor", "viewer"])
        form.addRow("نام کاربری:", username)
        form.addRow("نام نمایشی:", name)
        form.addRow("رمز موقت:", password)
        form.addRow("نقش:", role)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted and self.call("POST", "/api/users", {
            "username": username.text(), "display_name": name.text(),
            "password": password.text(), "role": role.currentText(),
        }):
            self.refresh()

    def edit_access(self) -> None:
        selected = self.selected()
        if not selected:
            QMessageBox.information(self, "ریز‌دسترسی", "ابتدا یک کاربر را انتخاب کنید.")
            return
        if selected.get("role") == "owner":
            QMessageBox.information(self, "مالک سامانه", "دسترسی‌های مالک اصلی قابل محدودسازی نیست.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"ریز‌دسترسی — {selected.get('display_name', '')}")
        form = QFormLayout(dialog)
        combos: dict[str, QComboBox] = {}
        overrides = selected.get("permission_overrides", {})
        for permission, title in PERMISSION_LABELS.items():
            combo = QComboBox()
            combo.addItem("مطابق نقش", "")
            combo.addItem("مجاز", "allow")
            combo.addItem("مسدود", "deny")
            current = combo.findData(overrides.get(permission, ""))
            combo.setCurrentIndex(max(0, current))
            combos[permission] = combo
            form.addRow(title + ":", combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = {key: str(combo.currentData()) for key, combo in combos.items() if combo.currentData()}
        if self.call("PUT", f"/api/users/{selected['id']}/permissions", {"overrides": payload}):
            self.refresh()


class HistoryBackupPage(V49Page):
    page_key = "history"

    def __init__(self, window):
        super().__init__(window, "سوابق فعالیت و پشتیبان", "زنجیره ممیزی ضد دستکاری و کاتالوگ نسخه‌های پشتیبان")
        tabs = QTabWidget()
        history = QWidget()
        history_box = QVBoxLayout(history)
        self.chain = QLabel("وضعیت زنجیره ممیزی: —")
        self.chain.setObjectName("healthBadge")
        history_box.addWidget(self.chain)
        self.audit = QTableWidget()
        _configure_table(self.audit)
        history_box.addWidget(self.audit)
        backups = QWidget()
        backup_box = QVBoxLayout(backups)
        create = QPushButton("ایجاد پشتیبان سلامت‌سنجی‌شده")
        create.clicked.connect(self.create_backup)
        backup_box.addWidget(create, 0, Qt.AlignRight)
        self.backups = QTableWidget()
        _configure_table(self.backups)
        backup_box.addWidget(self.backups)
        tabs.addTab(history, "سوابق ممیزی")
        tabs.addTab(backups, "نسخه‌های پشتیبان")
        self.layout.addWidget(tabs)

    def refresh(self) -> None:
        audit = self.call("GET", "/api/audit")
        if audit:
            self.chain.setText("زنجیره ممیزی: " + ("سالم و تأییدشده" if audit.get("chain_valid") else "نامعتبر — بررسی فوری"))
            _fill_table(self.audit, audit.get("items", []), (
                ("occurred_at", "زمان"), ("username", "کاربر"), ("action", "عملیات"),
                ("entity_type", "نوع رکورد"), ("entity_id", "شناسه"),
            ))
        backups = self.call("GET", "/api/backups")
        if backups:
            _fill_table(self.backups, backups.get("items", []), (
                ("created_at", "زمان"), ("filename", "نام فایل"), ("kind", "نوع"),
                ("size_bytes", "حجم"), ("integrity_ok", "سلامت"),
            ))

    def create_backup(self) -> None:
        result = self.call("POST", "/api/backup", {})
        if result:
            QMessageBox.information(self, "پشتیبان", f"نسخه سالم ساخته شد:\n{result.get('filename', '')}")
            self.refresh()


class SystemHealthPage(V49Page):
    page_key = "systemHealth"

    def __init__(self, window):
        super().__init__(window, "سلامت سیستم", "پایش دیتابیس، نشست‌ها، پشتیبان، ممیزی و رویدادهای عملیاتی")
        self.metrics = MetricGrid((
            ("database_size", "حجم دیتابیس"), ("active_sessions", "نشست فعال"),
            ("unread_notifications", "اعلان خوانده‌نشده"), ("pending_workflows", "گردش کار باز"),
            ("schema_version", "نسخه Schema"), ("audit", "زنجیره ممیزی"),
        ))
        self.layout.addWidget(self.metrics)
        self.last_backup = QLabel("آخرین پشتیبان: —")
        self.last_backup.setObjectName("healthBadge")
        self.layout.addWidget(self.last_backup)
        self.events = QTableWidget()
        _configure_table(self.events)
        self.layout.addWidget(self.events)

    @staticmethod
    def _size(value: int) -> str:
        size = float(value or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return "0 B"

    def refresh(self) -> None:
        payload = self.call("GET", "/api/monitoring")
        if not payload:
            return
        metrics = payload.get("metrics", {})
        self.metrics.update_values({
            "database_size": self._size(int(metrics.get("database_size_bytes", 0) or 0)),
            "active_sessions": metrics.get("active_sessions", 0),
            "unread_notifications": metrics.get("unread_notifications", 0),
            "pending_workflows": metrics.get("pending_workflows", 0),
            "schema_version": metrics.get("schema_version", 0),
            "audit": "سالم" if metrics.get("audit_chain_valid") else "نامعتبر",
        })
        backup = metrics.get("last_backup") or {}
        self.last_backup.setText(
            "آخرین پشتیبان: " + (f"{backup.get('created_at', '')} • {backup.get('filename', '')}" if backup else "هنوز ثبت نشده")
        )
        _fill_table(self.events, payload.get("events", []), (
            ("occurred_at", "زمان"), ("level", "سطح"), ("component", "بخش"),
            ("event_code", "کد"), ("message", "شرح"),
        ))


class SettingsPage(V49Page):
    page_key = "settings"

    def __init__(self, window):
        super().__init__(window, "تنظیمات", "نشانی سرور، فاصله همگام‌سازی و اثر انگشت گواهی مورد اعتماد")
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        self.server = QLineEdit()
        self.poll = QSpinBox()
        self.poll.setRange(2, 60)
        self.fingerprint = QLineEdit()
        self.fingerprint.setReadOnly(True)
        form.addRow("نشانی سرور مرکزی:", self.server)
        form.addRow("همگام‌سازی (ثانیه):", self.poll)
        form.addRow("اثر انگشت TLS:", self.fingerprint)
        save = QPushButton("ذخیره تنظیمات")
        save.clicked.connect(self.save)
        form.addRow(save)
        self.layout.addWidget(card)
        note = QLabel("تغییر نشانی سرور در ورود بعدی اعمال می‌شود. تغییر فاصله همگام‌سازی بلافاصله فعال خواهد شد.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        self.layout.addWidget(note)

    def refresh(self) -> None:
        config = self.window.config
        self.server.setText(config.server_url)
        self.poll.setValue(config.poll_seconds)
        self.fingerprint.setText(config.tls_fingerprint or "در اتصال نخست تأیید می‌شود")

    def save(self) -> None:
        server = self.server.text().strip().rstrip("/")
        if not server.startswith(("https://", "http://")):
            QMessageBox.warning(self, "نشانی سرور", "نشانی باید با https:// یا http:// آغاز شود.")
            return
        self.window.config.server_url = server
        self.window.config.poll_seconds = self.poll.value()
        self.window.config.save()
        self.window.timer.setInterval(self.poll.value() * 1000)
        QMessageBox.information(self, "تنظیمات", "تنظیمات ذخیره شد.")
