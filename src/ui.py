# ui.py
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import partial

import sys
import threading
from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QRect, QThread, Signal, QObject, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QMessageBox,
    QHeaderView, QPlainTextEdit, QGroupBox, QLabel, QSizePolicy, QMainWindow, QFormLayout, QToolButton, QFileDialog,
    QFrame, QGraphicsDropShadowEffect, QProgressBar, QCheckBox,
)
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QGuiApplication, QIcon

import db
from archive_window import ArchiveBrowser
from download import TUDownloadWorker
from config import save_config, load_config, load_xenia_manager_config, get_app_dir
from edge_import import use_xenia_manager_content_folder_for_edge
from extract import extract_archives
from model import GameTableModel
from db import Database, Compatibility
from remove_empty_folders import remove_empty_folders
from updater import UpdateWorker, UpdateManager
from utils import smart_title_case, xenia_edge_optimise_settings, show_differences
from xboxunity_api import login_xboxunity, test_connectivity
from xminst import XeniaManagerInstaller


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


class ClickOverlay(QWidget):
    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def mousePressEvent(self, event):
        self.launcher.close_drawer()

@dataclass
class WidgetInfo:
    checkbox: QCheckBox
    path: QLineEdit
    button: QPushButton
    name: str
    config_key_installed: str
    config_key_path: str


class DownloadWorker(QThread):
    log = Signal(str)
    overall_progress = Signal(int, int, str)
    file_progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, files):
        super().__init__()
        self.files = files

    def run(self):
        downloads_dir = Path.cwd() / "downloads"
        downloads_dir.mkdir(exist_ok=True)

        try:
            for i, file in enumerate(self.files, 1):
                destination = downloads_dir / file["filename"]

                self.overall_progress.emit(
                    i,
                    len(self.files),
                    file["filename"]
                )

                self.updater = UpdateManager()

                self.updater.log.connect(self.log)
                self.updater.progress.connect(self.file_progress)
                self.updater.finished.connect(self.finished)
                self.updater.error.connect(self.error)

                self.updater.download_file(
                    url=file["url"],
                    archive_org=True,
                    path=destination
                )

            extract_archives(
                downloads_dir,
                self.log.emit,
                remove_archives=False
            )

        except Exception as e:
            self.error.emit(str(e))
            return

        self.finished.emit()

class ExtractWorker(QObject):
    finished = Signal()
    log = Signal(str)

    def __init__(self, folders):
        super().__init__()
        self.folders = folders

    @Slot()
    def run(self):
        try:
            for folder in self.folders:
                extract_archives(
                    folder=folder,
                    log_callback=self.log.emit,
                    remove_archives=True,
                )
        finally:
            self.finished.emit()

class GameLauncher(QMainWindow):

    def extract_downloaded_archives(self):
        base_dir = Path(__file__).resolve().parent

        self.extract_thread = QThread()
        self.extract_worker = ExtractWorker(
            [
                Path.home() / "Downloads",
                base_dir / "Downloads",
            ]
        )

        self.extract_worker.log.connect(self.log)
        self.extract_worker.moveToThread(self.extract_thread)
        self.extract_thread.started.connect(self.extract_worker.run)
        self.extract_worker.finished.connect(self.extract_thread.quit)
        self.extract_worker.finished.connect(self.extract_worker.deleteLater)
        self.extract_thread.finished.connect(self.extract_thread.deleteLater)
        self.extract_thread.start()

    def check_for_updates(self):

        self.update_worker = UpdateWorker()

        self.update_worker.log.connect(self.log)
        self.update_worker.progress.connect(self.update_progress)
        self.update_worker.error.connect(self.log)
        self.update_worker.finished.connect(
            self.update_finished
        )

        self.update_worker.start()

    def update_finished(self):
        self.log("Update check complete")

        self.update_worker.deleteLater()

    def update_progress(self, done, total):

        if total:
            percent = int((done / total) * 100)
            self.progress_current.setValue(percent)

    def __init__(self):
        super().__init__()
        self.config = None
        self.archive_button = None
        self.launch_edge = None
        self.launch_manager = None
        self.update_worker = None
        self.xenia_title_updates_path = None
        self.use_xenia_manager_content_for_edge_btn = None
        self.import_edge_btn = None
        self.console = None
        self.refresh_btn = None
        self.worker = None
        self.btn_tu = None
        self.api_key = None
        self.process = None
        self.start_time = None
        self.token = None
        self.login_btn = None
        self.entry_apikey = None
        self.entry_pass = None
        self.entry_user = None
        self.export_btn = None
        self.settings_panel = None
        self.settings_btn = None
        self.drawer_open = False
        self.drawer_anim = None
        self.overlay = None
        self.settings_drawer = None
        self.import_btn = None
        self.fix_titles_btn = None
        self.search = None
        self.table = None
        self.setWindowTitle(
            "Xenia Game Manager"
        )
        icon_path = resource_path("assets/icons/app.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.db = Database()
        self.db.init_db()
        self.model = GameTableModel()
        self.setFixedSize(1640, 950)
        self.build_ui()
        self.compatibility = Compatibility(self.db, self.log)

        self.widgets = {
            "manager": WidgetInfo(
                self.xenia_manager_installed,
                self.xenia_manager_path,
                self.browse_btn_xenia,
                "Xenia Manager",
                "xenia_manager_installed",
                "xenia_manager_path",
            ),
            "canary": WidgetInfo(
                self.xenia_canary_installed,
                self.xenia_canary_path,
                self.browse_btn_canary,
                "Xenia Canary",
                "xenia_canary_installed",
                "xenia_canary_path",
            ),
            "edge": WidgetInfo(
                self.xenia_edge_installed,
                self.xenia_edge_path,
                self.browse_btn_edge,
                "Xenia Edge",
                "xenia_edge_installed",
                "xenia_edge_path",
            ),
            "netplay": WidgetInfo(
                self.xenia_netplay_installed,
                self.xenia_netplay_path,
                self.browse_btn_netplay,
                "Xenia Netplay",
                "xenia_netplay_installed",
                "xenia_netplay_path",
            ),
            "mousehook": WidgetInfo(
                self.xenia_mousehook_installed,
                self.xenia_mousehook_path,
                self.browse_btn_mousehook,
                "Xenia Mousehook",
                "xenia_mousehook_installed",
                "xenia_mousehook_path",
            ),
        }

        self.load_saved_config()

    def create_settings_drawer(self):

        self.overlay = ClickOverlay(self)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,120);")
        self.overlay.hide()

        self.settings_drawer = QFrame(self)
        self.settings_drawer.setObjectName("settingsDrawer")
        self.settings_drawer.setFixedWidth(580)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(-5, 0)
        self.settings_drawer.setGraphicsEffect(shadow)

        self.settings_drawer.setStyleSheet("""
            QFrame#settingsDrawer {
                background-color: #1b1b1b;
                border-left: 1px solid #333;
            }
        """)

        layout = QVBoxLayout(self.settings_drawer)

        title = QLabel("Settings")
        layout.addWidget(title)

        # ---------------- LOGIN BOX ----------------
        login_box = QGroupBox("Login XboxUnity / API Key")
        login_box.setFixedWidth(520)

        login_form = QFormLayout()

        self.entry_user = QLineEdit()
        self.entry_pass = QLineEdit()
        self.entry_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_apikey = QLineEdit()

        self.entry_user.setPlaceholderText("Username")
        self.entry_pass.setPlaceholderText("Password")
        self.entry_apikey.setPlaceholderText("API Key")

        login_form.addRow("Username", self.entry_user)
        login_form.addRow("Password", self.entry_pass)
        login_form.addRow("API Key", self.entry_apikey)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.login)
        login_form.addRow(self.login_btn)

        login_box.setLayout(login_form)

        login_box.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )

        layout.addWidget(
            login_box,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        # ---------------- XENIA MANAGER PATH ----------------
        layout.addWidget(QLabel("Xenia Manager Folder"))

        xenia_row = QHBoxLayout()
        self.xenia_manager_path = QLineEdit()
        self.xenia_manager_path.setPlaceholderText("Xenia Manager location...")
        self.xenia_manager_installed = QCheckBox()
        self.xenia_manager_installed.stateChanged.connect(partial(self.checkbox_changed, checkbox_name="manager"))
        self.browse_btn_xenia = QPushButton("Browse")
        self.browse_btn_xenia.clicked.connect(partial(self.pick_xenia_path, button_name="manager"))
        xenia_row.addWidget(self.xenia_manager_installed)
        xenia_row.addWidget(self.xenia_manager_path)
        xenia_row.addWidget(self.browse_btn_xenia)

        layout.addLayout(xenia_row)

        # ---------------- XENIA CANARY PATH ----------------
        layout.addWidget(QLabel("Xenia Canary Folder"))

        canary_row = QHBoxLayout()
        self.xenia_canary_path = QLineEdit()
        self.xenia_canary_path.setPlaceholderText("Xenia Canary location...")
        self.xenia_canary_installed = QCheckBox()
        self.xenia_canary_installed.stateChanged.connect(partial(self.checkbox_changed, checkbox_name="canary"))
        self.browse_btn_canary = QPushButton("Browse")
        self.browse_btn_canary.clicked.connect(partial(self.pick_xenia_path, button_name="canary"))
        canary_row.addWidget(self.xenia_canary_installed)
        canary_row.addWidget(self.xenia_canary_path)
        canary_row.addWidget(self.browse_btn_canary)

        layout.addLayout(canary_row)

        # ---------------- XENIA NETPLAY PATH ----------------
        layout.addWidget(QLabel("Xenia Netplay Folder"))

        netplay_row = QHBoxLayout()
        self.xenia_netplay_path = QLineEdit()
        self.xenia_netplay_path.setPlaceholderText("Xenia Netplay location...")
        self.xenia_netplay_installed = QCheckBox()
        self.xenia_netplay_installed.stateChanged.connect(partial(self.checkbox_changed, checkbox_name="netplay"))
        self.browse_btn_netplay = QPushButton("Browse")
        self.browse_btn_netplay.clicked.connect(partial(self.pick_xenia_path, button_name="netplay"))
        netplay_row.addWidget(self.xenia_netplay_installed)
        netplay_row.addWidget(self.xenia_netplay_path)
        netplay_row.addWidget(self.browse_btn_netplay)

        layout.addLayout(netplay_row)

        # ---------------- XENIA MOUSEHOOK PATH ----------------
        layout.addWidget(QLabel("Xenia Mousehook Folder"))

        mousehook_row = QHBoxLayout()
        self.xenia_mousehook_path = QLineEdit()
        self.xenia_mousehook_path.setPlaceholderText("Xenia Mousehook location...")
        self.xenia_mousehook_installed = QCheckBox()
        self.xenia_mousehook_installed.stateChanged.connect(partial(self.checkbox_changed, checkbox_name="mousehook"))
        self.browse_btn_mousehook = QPushButton("Browse")
        self.browse_btn_mousehook.clicked.connect(partial(self.pick_xenia_path, button_name="mousehook"))
        mousehook_row.addWidget(self.xenia_mousehook_installed)
        mousehook_row.addWidget(self.xenia_mousehook_path)
        mousehook_row.addWidget(self.browse_btn_mousehook)

        layout.addLayout(mousehook_row)

        # ---------------- XENIA EDGE PATH ----------------
        layout.addWidget(QLabel("Xenia Edge Folder"))

        edge_row = QHBoxLayout()
        self.xenia_edge_path = QLineEdit()
        self.xenia_edge_path.setPlaceholderText("Xenia Edge location...")
        self.xenia_edge_installed = QCheckBox()
        self.xenia_edge_installed.stateChanged.connect(partial(self.checkbox_changed, checkbox_name="edge"))
        self.browse_btn_edge = QPushButton("Browse")
        self.browse_btn_edge.clicked.connect(partial(self.pick_xenia_path, button_name="edge"))
        edge_row.addWidget(self.xenia_edge_installed)
        edge_row.addWidget(self.xenia_edge_path)
        edge_row.addWidget(self.browse_btn_edge)

        layout.addLayout(edge_row)

        # ---------------- TITLE UPDATE PATH ----------------
        layout.addWidget(QLabel("Title Updates Folder"))

        title_updates_row = QHBoxLayout()
        self.xenia_title_updates_path = QLineEdit()
        self.xenia_title_updates_path.setPlaceholderText("Title Updates location...")

        browse_btn_title_updates = QPushButton("Browse")
        browse_btn_title_updates.clicked.connect(partial(self.pick_xenia_path, button_name="title_updates"))

        title_updates_row.addWidget(self.xenia_title_updates_path)
        title_updates_row.addWidget(browse_btn_title_updates)

        layout.addLayout(title_updates_row)

        self.xenia_manager_installed.setToolTip(
            "<b>Xenia Manager</b><br>"
            "Enable this if <b>Xenia Manager</b> is installed.<br>"
            "This allows the application to import your Xenia Manager Game List."
        )
        self.xenia_canary_installed.setToolTip(
            "<b>Xenia Canary</b><br>"
            "Enable this if <b>Xenia canary</b> is installed.<br>"
            "This will launch the games using Xenia Canary."
        )
        self.xenia_edge_installed.setToolTip(
            "<b>Xenia Edge</b><br>"
            "Enable this if <b>Xenia edge</b> is installed.<br>"
            "This will launch the games using Xenia Edge and allow you to import the Xenia Edge Game List."
        )
        # -----------------------
        # Tools
        # -----------------------

        tools_box = QGroupBox("Tools")

        tools_layout = QVBoxLayout()

        self.fix_titles_btn = QPushButton("Fix Titles")
        self.fix_titles_btn.clicked.connect(self.fix_titles)
        tools_layout.addWidget(self.fix_titles_btn)

        self.show_differences_btn = QPushButton("Show Xenia Manager Differences")
        self.show_differences_btn.clicked.connect(self.show_differences)
        tools_layout.addWidget(self.show_differences_btn)

        self.import_btn = QPushButton("Import Xenia Manager Game List")
        self.import_btn.clicked.connect(partial(self.import_games, "xenia_manager"))
        tools_layout.addWidget(self.import_btn)

        self.import_edge_btn = QPushButton("Import Xenia Edge Game List")
        self.import_edge_btn.clicked.connect(partial(self.import_games, "xenia_edge"))
        tools_layout.addWidget(self.import_edge_btn)
        #
        # self.export_btn = QPushButton("Update Xenia Manager Game List")
        # self.export_btn.clicked.connect(self.export_titles)
        # tools_layout.addWidget(self.export_btn)

        # self.refresh_btn = QPushButton("Refresh")
        # self.refresh_btn.clicked.connect(self.refresh)
        # tools_layout.addWidget(self.refresh_btn)

        self.xenia_edge_optimise_btn = QPushButton("Create Xenia Edge Optimised Settings")
        self.xenia_edge_optimise_btn.clicked.connect(self.on_optimize_xenia_clicked)
        tools_layout.addWidget(self.xenia_edge_optimise_btn)

        self.check_update_btn = QPushButton("Check for Updates")
        self.check_update_btn.clicked.connect(self.check_for_updates)
        self.remove_clean_btn = QPushButton("Remove Empty Folders")
        self.remove_clean_btn.clicked.connect(self.remove_clean_folders)
        self.remove_clean_btn = QPushButton("Extract Downloaded Archives")
        self.remove_clean_btn.clicked.connect(self.extract_downloaded_archives)

        self.use_xenia_manager_content_for_edge_btn = QPushButton(
            "Use Xenia Manager Unified Content folder for Xenia Edge")
        self.use_xenia_manager_content_for_edge_btn.clicked.connect(self.use_xenia_manager_content_for_edge)
        tools_layout.addWidget(self.use_xenia_manager_content_for_edge_btn)
        tools_layout.addWidget(self.remove_clean_btn)
        tools_layout.addWidget(self.check_update_btn)

        tools_box.setLayout(tools_layout)

        layout.addWidget(tools_box)

        layout.addStretch()

        buttons = [
            self.fix_titles_btn,
            self.import_btn,
            self.import_edge_btn,
            self.xenia_edge_optimise_btn,
            self.check_update_btn,
            self.use_xenia_manager_content_for_edge_btn,
            self.remove_clean_btn,
        ]

        for button in buttons:
            button.setMinimumHeight(32)

        self.settings_drawer.hide()

    from PySide6.QtWidgets import QMessageBox

    def use_xenia_manager_content_for_edge(self):
        try:
            use_xenia_manager_content_folder_for_edge(log_callback=self.log)
            QMessageBox.information(
                self,
                "Success",
                "Xenia Edge is now using the Xenia Manager content folder."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )

    def on_optimize_xenia_clicked(self):
        xenia_edge_optimise_settings(self.log)

    def remove_clean_folders(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder"
        )

        if not folder:
            return

        count = remove_empty_folders(folder, self.log)

        QMessageBox.information(
            self,
            "Finished",
            f"Removed {count} empty folder(s)."
        )

    def set_checkbox(
            self,
            checkbox_name,
            checked,
            save=True,
            *,
            placeholder=None,
            text=None,
            path_enabled=None,
            button_enabled=None,
    ):
        config = load_config()
        widget = self.widgets[checkbox_name]

        checkbox = widget.checkbox
        path = widget.path
        button = widget.button
        name = widget.name
        config_key_installed = widget.config_key_installed
        config_key_path = widget.config_key_path

        checkbox.blockSignals(True)
        checkbox.setChecked(checked)
        checkbox.blockSignals(False)

        if placeholder is None:
            placeholder = f"{name} location..." if checked else f"{name} Not Installed"

        path.setPlaceholderText(placeholder)

        if text is not None:
            path.setText(text)

        path.setEnabled(checked if path_enabled is None else path_enabled)
        button.setEnabled(checked if button_enabled is None else button_enabled)

        if save:
            config[config_key_installed] = checked
            save_config(config)

    def checkbox_changed(self, state, checkbox_name):
        checked = bool(state)
        config = load_config()

        self.set_checkbox(checkbox_name, checked)

        if checkbox_name != "manager":
            return

        manager_config = load_xenia_manager_config(Path(config["xenia_manager_path"]))

        manager_paths = {
            "canary": manager_config["emulators"]["canary"]["emulator_location"],
            "netplay": manager_config["emulators"]["netplay"]["emulator_location"],
            "mousehook": manager_config["emulators"]["mousehook"]["emulator_location"],
        }

        for emulator in ("canary", "netplay", "mousehook"):
            if checked:
                self.set_checkbox(
                    emulator,
                    True,
                    placeholder=f"Using Xenia Manager {emulator.title()} location...",
                    text=manager_paths[emulator],
                    path_enabled=False,
                    button_enabled=False,
                )
            else:
                widget = self.widgets[emulator]

                self.set_checkbox(
                    emulator,
                    config[widget.config_key_installed],
                    placeholder=f"Not Using Xenia Manager {widget.name} location...",
                    text=config[widget.config_key_path],
                    path_enabled=config[widget.config_key_installed],
                    button_enabled=config[widget.config_key_installed],
                    save=False,
                )

    def toggle_drawer(self):
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):

        self.drawer_open = True

        self.overlay.setGeometry(self.rect())
        self.overlay.show()

        self.settings_drawer.show()

        start = QRect(
            self.width(),
            0,
            self.settings_drawer.width(),
            self.height()
        )

        end = QRect(
            self.width() - self.settings_drawer.width(),
            0,
            self.settings_drawer.width(),
            self.height()
        )

        self.drawer_anim = QPropertyAnimation(
            self.settings_drawer,
            b"geometry"
        )

        self.drawer_anim.setDuration(250)
        self.drawer_anim.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )
        self.drawer_anim.setStartValue(start)
        self.drawer_anim.setEndValue(end)
        self.drawer_anim.start()

    def close_drawer(self):

        self.drawer_open = False

        start = self.settings_drawer.geometry()

        end = QRect(
            self.width(),
            0,
            self.settings_drawer.width(),
            self.height()
        )

        self.drawer_anim = QPropertyAnimation(
            self.settings_drawer,
            b"geometry"
        )

        self.drawer_anim.setDuration(200)
        self.drawer_anim.setEasingCurve(
            QEasingCurve.Type.InCubic
        )
        self.drawer_anim.setStartValue(start)
        self.drawer_anim.setEndValue(end)

        self.drawer_anim.finished.connect(
            self.settings_drawer.hide
        )

        self.drawer_anim.finished.connect(
            self.overlay.hide
        )

        self.drawer_anim.start()

    def resizeEvent(self, event):

        super().resizeEvent(event)

        if self.overlay:
            self.overlay.setGeometry(self.rect())

        if self.drawer_open:
            self.settings_drawer.setGeometry(
                self.width() - self.settings_drawer.width(),
                0,
                self.settings_drawer.width(),
                self.height()
            )

    import subprocess
    from pathlib import Path

    def launch_program(self, program):
        xenia_manager_installed = self.config["xenia_manager_installed"]
        if not xenia_manager_installed:
            exe = Path(r"C:\xenia-manager") / "XeniaManager.exe"

            if not exe.exists():
                try:
                    installer = XeniaManagerInstaller()
                    installer.install()
                    self.config["xenia_manager_installed"] = True
                    self.config["xenia_manager_path"] = str(exe)
                    save_config(self.config)
                except Exception as e:
                    QMessageBox.critical(self, "Install Failed", str(e))
                    return
        self.config = load_config()
        programs = {
            "manager": Path(self.config["xenia_manager_path"]) / "XeniaManager.exe",
            "edge": Path(self.config["xenia_edge_path"]) / "xenia_edge.exe",
        }

        exe = programs.get(program)
        if not exe or not exe.exists():
            return

        subprocess.Popen([str(exe)])

    def open_archive_browser(self):

        dlg = ArchiveBrowser(self.db, self)

        if dlg.exec():
            files = dlg.selected_files()

            self.worker = DownloadWorker(files)
            self.worker.overall_progress.connect(self.update_file_progress)
            self.worker.file_progress.connect(self.update_download_progress)
            self.worker.log.connect(self.log)
            self.worker.finished.connect(lambda: self.log("Finished"))
            self.worker.error.connect(self.log)
            self.worker.start()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.create_settings_drawer()
        main_layout = QVBoxLayout(central)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ================= LOGIN =================

        # ================= TOOLBAR =================
        toolbar = QHBoxLayout()

        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setChecked(False)
        self.settings_btn.clicked.connect(self.toggle_drawer)
        toolbar.addWidget(self.settings_btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games...")
        self.search.textChanged.connect(self.search_changed)
        toolbar.addWidget(self.search)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        #
        self.config = load_config()
        xenia_manager_installed = self.config["xenia_manager_installed"]
        button_text = "Launch Xenia Manager"
        if not xenia_manager_installed:
            button_text = "Install Xenia Manager"
        self.launch_manager = QPushButton(button_text)
        self.launch_manager.clicked.connect(partial(self.launch_program, "manager"))
        self.launch_edge = QPushButton("Launch Edge")
        self.launch_edge.clicked.connect(partial(self.launch_program, "edge"))
        self.btn_tu = QPushButton("Download Title Updates")
        self.btn_tu.clicked.connect(self.search_and_download_tus)
        self.archive_button = QPushButton("DLC Downloader")
        self.archive_button.clicked.connect(self.open_archive_browser)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.launch_manager)
        toolbar.addWidget(self.launch_edge)
        toolbar.addWidget(self.archive_button)
        toolbar.addWidget(self.btn_tu)

        # ================= PROGRESS =================
        progress_widget = QWidget()

        self.overall_label = QLabel("Overall")
        self.current_label = QLabel("Current File")

        self.progress_overall = QProgressBar()
        self.progress_current = QProgressBar()

        overall_layout = QVBoxLayout()
        overall_layout.setContentsMargins(0, 0, 0, 0)
        overall_layout.addWidget(self.overall_label)
        overall_layout.addWidget(self.progress_overall)

        current_layout = QVBoxLayout()
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.addWidget(self.current_label)
        current_layout.addWidget(self.progress_current)

        layout = QHBoxLayout(progress_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(overall_layout)
        layout.addLayout(current_layout)

        toolbar.addWidget(progress_widget)
        # 🔥 IMPORTANT: attach toolbar to main layout
        main_layout.addLayout(toolbar)

        # -------------------------
        # Table
        # -------------------------

        self.table = QTableView()

        self.table.setModel(self.model)

        self.table.setSortingEnabled(True)

        self.table.setAlternatingRowColors(True)

        self.table.doubleClicked.connect(
            self.launch_game
        )

        self.table.clicked.connect(
            self.table_clicked
        )

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        header.setStretchLastSection(False)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 32)  # ★
        self.table.setColumnWidth(1, 575)  # Number
        self.table.setColumnWidth(2, 70)  # ★
        self.table.setColumnWidth(3, 70)  # Number
        self.table.setColumnWidth(6, 135)  # Number
        self.table.setColumnWidth(4, 70)  # Number
        self.table.setColumnWidth(7, 50)  # Number
        self.table.setColumnWidth(10, 200)  # Number
        self.search.setClearButtonEnabled(True)
        self.table.verticalHeader().hide()

        main_layout.addWidget(self.table)

        self.console = QPlainTextEdit()

        self.console.setReadOnly(True)

        self.console.setMaximumHeight(100)

        self.console.setPlaceholderText(
            "Application log..."
        )

        main_layout.addWidget(self.console)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_menu)

        self.apply_style()

    def toggle_settings(self):
        self.settings_panel.setVisible(self.settings_btn.isChecked())

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Games Folder")
        if folder:
            self.log(f"Selected: {folder}")

    def search_and_download_tus(self):
        if not self.model.games:
            self.log("Error: No games loaded")
            return
        config = load_config()
        folder = config["xenia_title_updates_path"]
        if not folder:
            self.log("Error: No Folder Selected")
            return
        self.worker = TUDownloadWorker(
            games=self.model.games,
            token=self.token,
            api_key=self.api_key,
            output_folder=folder
        )
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.update_file_progress)
        self.worker.game_progress.connect(self.update_game_progress)
        self.worker.finished.connect(self.download_finished)

        self.worker.start()

    def update_file_progress(self, done, total, filename):
            self.progress_current.setMaximum(total)
            self.progress_current.setValue(done)
            self.current_label.setText(f"{filename} ({done}/{total})")

    def update_download_progress(self, done, total):
            self.progress_overall.setMaximum(total)
            self.progress_overall.setValue(done)
            self.overall_label.setText(f"({self.human_size(done)}/{self.human_size(total)})")

    def update_game_progress(self, current, total):
        self.log(f"Game progress: {current}/{total}")

    @staticmethod
    def human_size(size):
        size = int(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def download_finished(self, stats):
        self.log("\n=== SUMMARY ===")
        self.log(f"Games: {stats['games_total']}")
        self.log(f"With TUs: {stats['games_with_tu']}")
        self.log(f"Downloaded: {stats['tus_downloaded']}")
        self.log(f"Errors: {stats['errors']}")

        self.log("Done: TU download completed")

    def pick_xenia_path(self, button_name):
        folder = QFileDialog.getExistingDirectory(
            self,
            f"Select Xenia {button_name.title()} Folder"
        )
        if not folder:
            return

        key = f"xenia_{button_name}_path"

        getattr(self, key).setText(folder)

        config = load_config()
        config[f"{key}"] = folder
        save_config(config)

    def load_saved_config(self):
        self.config = load_config()
        exe = Path(r"C:\xenia-manager") / "XeniaManager.exe"
        if not exe.exists():
            installer = XeniaManagerInstaller()
            installer.install(log_callback=self.log)
            self.config["xenia_manager_installed"] = True
            self.config["xenia_manager_path"] = str(exe)
            save_config(self.config)
        self.config = load_config()
        self.set_checkbox("manager", self.config.get("xenia_manager_installed", False), save=False)
        self.set_checkbox("canary", self.config.get("xenia_canary_installed", False), save=False)
        self.set_checkbox("edge", self.config.get("xenia_edge_installed", False), save=False)
        self.entry_user.setText(self.config.get("username", ""))
        self.entry_pass.setText(self.config.get("password", ""))
        self.entry_apikey.setText(self.config.get("api_key", ""))
        self.xenia_manager_path.setText(self.config.get("xenia_manager_path", ""))
        self.xenia_canary_path.setText(self.config.get("xenia_canary_path", ""))
        self.xenia_edge_path.setText(self.config.get("xenia_edge_path", ""))
        self.xenia_title_updates_path.setText(self.config.get("xenia_title_updates_path", ""))
        if self.config.get("api_key"):
            self.api_key = self.config["api_key"]

    def login(self):
        username = self.entry_user.text().strip()
        password = self.entry_pass.text().strip()
        api_key = self.entry_apikey.text().strip()

        config = load_config()

        # Save API key mode (preferred)
        if api_key:
            config["api_key"] = api_key
            config["username"] = username
            config["password"] = password
            save_config(config)

            self.api_key = api_key
            self.log("API Key saved.")

            # optional connectivity check
            try:
                if test_connectivity():
                    self.log("XboxUnity connectivity OK.")
                else:
                    self.log("WARNING: XboxUnity connectivity issue.")
            except Exception as e:
                self.log(f"Connectivity error: {e}")

            return

        # Username/password login
        if not username or not password:
            self.log("Login Error: Enter username/password or API key")
            return

        self.log("Checking XboxUnity...")

        try:
            if not test_connectivity():
                self.log("Error: Cannot reach XboxUnity")
                return
        except Exception as e:
            self.log(str(e))
            return

        self.log("Logging in...")

        token = login_xboxunity(username, password)

        if token:
            self.token = token
            self.api_key = None

            config["username"] = username
            config["password"] = password
            config.pop("api_key", None)

            save_config(config)

            self.log("Login successful.")
        else:
            self.log("Login Failed: Invalid credentials")

    def show_table_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)

        copy_cell_action = menu.addAction("Copy Cell")
        copy_row_action = menu.addAction("Copy Row")
        copy_column_action = menu.addAction("Copy Column")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))

        if not action:
            return

        model = self.table.model()
        clipboard = QGuiApplication.clipboard()

        # -------------------------
        # Copy Cell
        # -------------------------
        if action == copy_cell_action:
            clipboard.setText(
                str(model.data(index, Qt.ItemDataRole.DisplayRole))
            )
        # -------------------------
        # Copy Row
        # -------------------------
        elif action == copy_row_action:
            row = index.row()
            values = [
                str(model.index(row, col).data())
                for col in range(model.columnCount())
            ]
            clipboard.setText("\t".join(values))

        # -------------------------
        # Copy Column
        # -------------------------
        elif action == copy_column_action:
            col = index.column()
            values = [
                str(model.index(row, col).data())
                for row in range(model.rowCount())
            ]
            clipboard.setText("\n".join(values))

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.appendPlainText(
            f"[{timestamp}] {message}"
        )
        return None

    # -------------------------
    # Search
    # -------------------------

    def export_titles(self):

        try:
            updated = self.db.export_titles_to_xenia_manager_game_list()

            QMessageBox.information(
                self,
                "Export Complete",
                f"{updated} titles written to games.json"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Export Failed",
                str(e)
            )

    def search_changed(self, text):

        self.model.load(text)

    # -------------------------
    # Refresh
    # -------------------------

    def refresh(self):
        # width = self.table.columnWidth(2)
        # print(width)
        self.model.load()

    # -------------------------
    # Favourite Click
    # -------------------------

    def table_clicked(self, index):

        if index.column() == 0:
            self.model.toggle_favourite(
                index.row()
            )

    def import_games(self, xenia_version):
        # Refresh table
        self.model.load()
        self.log("Importing games...")
        try:
            # Import games
            self.db.import_games_from_edge_or_xenia_manager(xenia_version, self.model.games, log_callback=self.log)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Failed",
                str(e)
            )

    # -------------------------
    # Launch Game
    # -------------------------

    def get_selected_row(self):
        index = self.table.selectionModel().currentIndex()
        return index.row() if index.isValid() else None

    def launch_game(self):
        xenia_exe_configuration_location = ""
        xenia_exe_path = ""
        row = self.get_selected_row()
        if row is None:
            return
        game = self.model.get_game_title(row)
        game_path = self.model.get_game_path(row)
        game_id = self.model.get_game_id(row)
        db_game_config_source = self.model.get_config_path(row)
        xenia_version = self.model.get_xenia_version(row)
        print(game, xenia_version)
        from pathlib import Path
        config = load_config()
        xenia_canary_installed = config["xenia_canary_installed"]
        xenia_edge_installed = config["xenia_edge_installed"]
        xenia_netplay_installed = config["xenia_netplay_installed"]
        xenia_mousehook_installed = config["xenia_mousehook_installed"]
        xenia_manager_installed = config["xenia_manager_installed"]
        xenia_edge_path = config["xenia_edge_path"]
        xenia_canary_path = config["xenia_canary_path"]
        xenia_netplay_path = config["xenia_netplay_path"]
        xenia_mousehook_path = config["xenia_mousehook_path"]
        xenia_version = str(xenia_version).lower()
        if xenia_manager_installed and xenia_version!="edge":
            xenia_manager_path = Path(config["xenia_manager_path"])
            xenia_manager_config = load_xenia_manager_config(xenia_manager_path)
            configuration_location = xenia_manager_config["emulators"][f"{xenia_version}"]["configuration_location"]
            xenia_emulator_location = Path(xenia_manager_config["emulators"][f"{xenia_version}"]["emulator_location"])
            xenia_exe_location = Path(xenia_manager_config["emulators"][f"{xenia_version}"]["executable_location"])
            xenia_exe_path = Path.joinpath(xenia_manager_path, xenia_exe_location)
            db_game_config_source = Path(xenia_manager_path) / db_game_config_source
            xenia_exe_configuration_location = Path.joinpath(xenia_manager_path, configuration_location)

        # "D:\RetroBat\emulators\xenia-manager\Emulators\Xenia Canary\xenia-canary.config.toml"
        # Emulators\Xenia Canary\config\007 Legends.config.toml
        if xenia_version.lower() == "canary":
            if not xenia_canary_installed:
                raise Exception("Canary not installed")
            datadir = Path(get_app_dir())
            mini_config_dir = datadir / "assets" / "settings"
            xenia_exe_path = Path(xenia_canary_path) / "xenia_canary.exe"
            xenia_exe_configuration_location = Path(xenia_canary_path) / "xenia-canary.config.toml"
            db_game_config_source = Path(xenia_canary_path).parent.parent / db_game_config_source
        if xenia_version.lower() == "netplay":
            if not xenia_netplay_installed:
                raise Exception("Netplay not installed")
            datadir = Path(get_app_dir())
            mini_config_dir = datadir / "assets" / "settings"
            xenia_exe_path = Path(xenia_netplay_path) / "xenia_canary_netplay.exe"
            xenia_exe_configuration_location = Path(xenia_netplay_path) / "xenia-canary-netplay.config.toml"
            db_game_config_source = Path(xenia_netplay_path).parent.parent / db_game_config_source
        if xenia_version.lower() == "mousehook":
            if not xenia_mousehook_installed:
                raise Exception("Mousehook not installed")
            datadir = Path(get_app_dir())
            mini_config_dir = datadir / "assets" / "settings"
            xenia_exe_path = Path(xenia_mousehook_path) / "xenia_canary_mousehook.exe"
            xenia_exe_configuration_location = Path(xenia_mousehook_path) / "xenia-canary-mousehook.config.toml"
            db_game_config_source = Path(xenia_mousehook_path).parent.parent / db_game_config_source
        if xenia_version.lower() == "edge":
            if not xenia_edge_installed:
                raise Exception("Edge not installed")
            datadir = Path(get_app_dir())
            mini_config_dir = datadir / "assets" / "settings"
            xenia_edge_path = Path(xenia_edge_path)
            xenia_exe_path = xenia_edge_path / "xenia_edge.exe"

            # Default (non-portable)
            xenia_exe_configuration_location = Path.home() / "Documents" / "Xenia" / "config"

            # Portable mode
            if (xenia_edge_path / "portable.txt").exists():
                xenia_exe_configuration_location = xenia_edge_path / "config"

        asset_config = Path(get_app_dir()) / "assets" / "settings" / f"{game_id}.toml"

        if asset_config.exists():
            shutil.copy(asset_config, xenia_exe_configuration_location)
            self.log(f"Copied {asset_config} to {xenia_exe_configuration_location}")
        elif db_game_config_source and Path(db_game_config_source).exists():
            shutil.copy(db_game_config_source, xenia_exe_configuration_location)
            self.log(f"Copied {db_game_config_source} to {xenia_exe_configuration_location}")
        else:
            self.log(f"Config Missing: {xenia_exe_configuration_location}")

        if game_path and not Path(game_path).exists():
            self.log(f"Game path Missing: {game_path}")
            raise Exception
        xenia_exe_path = Path(xenia_exe_path)
        try:
            import subprocess
            import time
            self.start_time = time.time()
            self.process = subprocess.Popen(
                [xenia_exe_path, game_path],
                cwd=os.path.dirname(xenia_canary_path)
            )

            threading.Thread(
                target=self.monitor_game,
                args=(game_id,),
                daemon=True
            ).start()

        except Exception as e:

            QMessageBox.critical(
                self,
                "Launch Error",
                str(e)
            )

    def monitor_game(self, game_id):
        while self.process.poll() is None:
            time.sleep(1)  # don’t burn CPU

        end_time = time.time()
        minutes = int((end_time - self.start_time) / 60)

        self.model.add_play_time(game_id, minutes)
        self.model.mark_played(game_id)
        self.model.load()

    # -------------------------
    # Fix Titles
    # -------------------------

    def show_differences(self):
        show_differences(self.log)

    def fix_titles(self):

        updated = 0
        with self.db.get_db() as con:

            rows = con.execute("""
                SELECT
                    game_id,
                    title
                FROM games
            """).fetchall()

            for row in rows:

                cleaned = smart_title_case(
                    row["title"]
                )

                if cleaned != row["title"]:
                    con.execute("""
                        UPDATE games
                        SET title = ?
                        WHERE game_id = ?
                    """, (
                        cleaned,
                        row["game_id"]
                    ))
                    self.log(f"Cleaned Title {row["title"]} to {cleaned}")
                    updated += 1

        self.model.load()
        self.log(f"Updated {updated} games")

    # -------------------------
    # Style
    # -------------------------

    def apply_style(self):

        self.setStyleSheet("""
        QWidget {
            background: #202124;
            color: white;
            font-size: 10pt;
        }

        QLineEdit {
            padding: 6px;
            background: #2d2f31;
            border: 1px solid #555;
        }

        QPushButton {
            padding: 6px;
            background: #3c4043;
            border: 1px solid #666;
        }

        QPushButton:hover {
            background: #4b5054;
        }

        QTableView {
            background: #1e1e1e;
            alternate-background-color: #292929;
            gridline-color: #444;
        }

        QHeaderView::section {
            background: #3c4043;
            padding: 6px;
            border: 1px solid #555;
        }
        
        QGroupBox {
            font-size: 14px;
            font-weight: bold;
            color: #e5e5e5;
            border: 1px solid #2a2a2a;
            border-radius: 10px;
            margin-top: 12px;
            padding: 10px;
            background-color: #1e1e1e;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        
        QLabel {
            color: #cfcfcf;
            font-size: 12px;
        }
        
        QLineEdit {
            background-color: #2b2b2b;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
            padding: 6px 10px;
            color: #ffffff;
            selection-background-color: #0078d7;
        }
        
        QLineEdit:focus {
            border: 1px solid #0078d7;
        }
        
        QPushButton {
            background-color: #2d2d2d;
            border: 1px solid #3a3a3a;
            padding: 6px;
            border-radius: 6px;
            color: #ffffff;
        }
        
        QPushButton:hover {
            background-color: #3a3a3a;
        }
        
        QPushButton:pressed {
            background-color: #0078d7;
        }
        """)
