"""PySide6 main window — modern desktop GUI."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cosmos_address import VERSION
from gui.qt.generator_page import GeneratorPage
from gui.qt.scanner_page import ScannerPage
from gui.qt.theme import DEFAULT_THEME, build_stylesheet, get_colors, theme_names


class NavButton(QPushButton):
    def __init__(self, text: str, *, page_index: int, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.page_index = page_index
        self.setObjectName("navBtn")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Custom Cosmos Address")
        self.setMinimumSize(980, 680)
        self.resize(1100, 780)

        self._theme_name = DEFAULT_THEME
        self._nav_buttons: list[NavButton] = []

        self._build_ui()
        self._apply_theme(self._theme_name)
        self._switch_page(0)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("contentRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(28, 24, 28, 20)
        right.setSpacing(16)
        right_wrap = QWidget()
        right_wrap.setLayout(right)
        root.addWidget(right_wrap, stretch=1)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self._page_title = QLabel("Address Generator")
        self._page_title.setObjectName("pageTitle")
        self._page_subtitle = QLabel("Find custom Bech32 addresses for Cosmos SDK chains")
        self._page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self._page_title)
        titles.addWidget(self._page_subtitle)
        header.addLayout(titles, stretch=1)
        self._header_badge = QLabel("")
        self._header_badge.setObjectName("badge")
        header.addWidget(self._header_badge, alignment=Qt.AlignmentFlag.AlignTop)
        right.addLayout(header)

        self._stack = QStackedWidget()
        self._generator_page = GeneratorPage(theme_name=self._theme_name)
        self._scanner_page = ScannerPage(theme_name=self._theme_name)
        self._generator_page.update_difficulty_badge(self._header_badge)
        self._stack.addWidget(self._generator_page)
        self._stack.addWidget(self._scanner_page)
        right.addWidget(self._stack, stretch=1)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 28, 20, 20)
        layout.setSpacing(8)

        icon = QLabel("◎")
        icon.setObjectName("brandIcon")
        layout.addWidget(icon)
        title = QLabel("Cosmos\nVanity")
        title.setObjectName("brandTitle")
        layout.addWidget(title)
        version = QLabel(f"v{VERSION}")
        version.setObjectName("brandVersion")
        layout.addWidget(version)

        sep1 = QFrame()
        sep1.setObjectName("sidebarSep")
        sep1.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep1)

        layout.addWidget(QLabel(""))  # spacing
        caption_nav = QLabel("NAVIGATION")
        caption_nav.setObjectName("sidebarCaption")
        layout.addWidget(caption_nav)

        for idx, label in enumerate(("Generator", "Balance Scanner")):
            row = QHBoxLayout()
            row.setSpacing(12)
            indicator = QFrame()
            indicator.setObjectName("navIndicator")
            indicator.setFixedWidth(3)
            indicator.setVisible(idx == 0)
            row.addWidget(indicator)

            btn = NavButton(label, page_index=idx)
            btn.clicked.connect(lambda checked, i=idx: self._switch_page(i))
            row.addWidget(btn, stretch=1)
            layout.addLayout(row)
            self._nav_buttons.append(btn)
            btn._indicator = indicator  # type: ignore[attr-defined]

        layout.addStretch()

        sep2 = QFrame()
        sep2.setObjectName("sidebarSep")
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        caption = QLabel("THEME")
        caption.setObjectName("sidebarCaption")
        layout.addWidget(caption)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(theme_names())
        self._theme_combo.setCurrentText(DEFAULT_THEME)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        layout.addWidget(self._theme_combo)

        about = QPushButton("About")
        about.setObjectName("ghostBtn")
        about.clicked.connect(self._show_about)
        layout.addWidget(about)
        return sidebar

    def _switch_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            active = i == index
            btn.setChecked(active)
            btn._indicator.setVisible(active)  # type: ignore[attr-defined]
        if index == 0:
            self._page_title.setText("Address Generator")
            self._page_subtitle.setText("Find custom Bech32 addresses for Cosmos SDK chains")
            self._header_badge.show()
            self._generator_page.update_difficulty_badge(self._header_badge)
        else:
            self._page_title.setText("Balance Scanner")
            self._page_subtitle.setText("Check on-chain balances for locally generated wallets")
            self._header_badge.hide()

    def get_generator_output_path(self) -> str:
        return self._generator_page.get_output_path()

    def _apply_theme(self, name: str) -> None:
        self._theme_name = name
        self.setStyleSheet(build_stylesheet(name) + self._nav_stylesheet())
        c = get_colors(name)
        self._header_badge.setStyleSheet(
            f"background-color: {c['card']}; color: {c['accent']}; "
            f"border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 14px;"
        )
        self._generator_page.set_theme_name(name)
        self._scanner_page.set_theme_name(name)
        if self._stack.currentIndex() == 0:
            self._generator_page.update_difficulty_badge(self._header_badge)

    def _nav_stylesheet(self) -> str:
        c = get_colors(self._theme_name)
        return f"""
        QPushButton#navBtn {{
            background: transparent;
            color: {c['fg_dim']};
            border: none;
            text-align: left;
            padding: 8px 4px;
            font-weight: 600;
        }}
        QPushButton#navBtn:hover {{
            color: {c['fg']};
        }}
        QPushButton#navBtn:checked {{
            color: {c['accent']};
        }}
        """

    def _on_theme_changed(self, name: str) -> None:
        if name:
            self._apply_theme(name)

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About",
            f"Custom Cosmos Address v{VERSION}\n\n"
            "Vanity address generator and balance scanner for Cosmos SDK chains.\n\n"
            "CLI:\n"
            "  cosmos-vanity      generate addresses\n"
            "  cosmos-scan        scan balances\n"
            "GUI:\n"
            "  cosmos-vanity-gui",
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        running_gen = self._generator_page.is_running()
        running_scan = self._scanner_page.is_running()
        if running_gen or running_scan:
            what = []
            if running_gen:
                what.append("address search")
            if running_scan:
                what.append("balance scan")
            reply = QMessageBox.question(
                self,
                "Quit",
                f"{' and '.join(what).capitalize()} is running. Stop and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._generator_page.request_stop()
            self._scanner_page.request_stop()
        event.accept()


VanityGuiApp = MainWindow


def run_app() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Custom Cosmos Address")
    app.setOrganizationName("custom-cosmos-address")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
