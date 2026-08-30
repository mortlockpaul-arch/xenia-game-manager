import logging
import os
import re
from datetime import datetime
from glob import escape
from urllib.parse import quote

import requests
from PySide6.QtCore import (
    QThread,
    Signal,
    QSortFilterProxyModel,
)
from PySide6.QtGui import (
    QColor,
    QStandardItem,
    QStandardItemModel, QBrush, QIcon, QFont,
)
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QProgressBar,
    QTableView,
    QHeaderView, QWidget, QSizePolicy, QPlainTextEdit,
)

import updater
from db import Database
from logging_setup import setup_logger
from ui import DownloadWorker

ARCHIVES_DLC = [
    *[f"XBOX_360_DLC_{i}" for i in range(1, 6)],
    "XBOX_360_XBLA_DLC",
]
ARCHIVES_DIGITAL = [
    *[f"microsoft_xbox360_digital_part{i}" for i in range(1, 5)],
    "xblig_neowarez",
]
ARCHIVES_INDIE = [
    *[f"XBOX_360_XBLIG_{i}" for i in range(1, 4)],
    "xblig_neowarez",
]
class ArchiveSortProxyModel(QSortFilterProxyModel):
    def lessThan(self, left, right):
        if left.column() == 6:
            l = left.data(Qt.ItemDataRole.UserRole) or 0
            r = right.data(Qt.ItemDataRole.UserRole) or 0
            return int(l) < int(r)

        return super().lessThan(left, right)

class SizeItem(QStandardItem):
    def __init__(self, size):
        super().__init__(updater.UpdateManager.human_size(size))
        self.size = size

    def __lt__(self, other):
        if isinstance(other, SizeItem):
            return self.size < other.size
        return super().__lt__(other)

class Loader(QThread):

    name_parameter = "Xbox 360 DLC Content"
    fileFound = Signal(dict)
    progress = Signal(int, int)
    finishedLoading = Signal()

    def __init__(self, name_parameter="Xbox 360 DLC Content", parent=None):
        super().__init__(parent)

        self.name_parameter = name_parameter
        if self.name_parameter == "Xbox 360 Indie Games":
            self.archives = ARCHIVES_INDIE
        elif self.name_parameter == "Xbox 360 DLC Content":
            self.archives = ARCHIVES_DIGITAL
        elif self.name_parameter == "Xbox 360 DLC":
            self.archives = ARCHIVES_DLC
        else:
            self.archives = []

    def run(self):

        total = len(self.archives)

        for index, archive in enumerate(self.archives, start=1):

            try:

                data = requests.get(
                    f"https://archive.org/metadata/{archive}",
                    timeout=30,
                ).json()

                for file in data.get("files", []):

                    if "name" not in file:
                        continue

                    file["archive"] = archive
                    self.fileFound.emit(file)

            except Exception as e:
                print(e)

            self.progress.emit(index, total)

        self.finishedLoading.emit()


from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionButton, QStyle
from PySide6.QtCore import Qt, QRect

import os
import sys

def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

class CenteredCheckBoxDelegate(QStyledItemDelegate):

    def paint(self, painter, option, index):
        checked = index.data(Qt.ItemDataRole.CheckStateRole)

        checkbox = QStyleOptionButton()
        checkbox.state = QStyle.StateFlag.State_Enabled

        if checked == Qt.CheckState.Checked:
            checkbox.state |= QStyle.StateFlag.State_On
        else:
            checkbox.state |= QStyle.StateFlag.State_Off

        size = 20
        checkbox.rect = QRect(
            option.rect.x() + (option.rect.width() - size) // 2,
            option.rect.y() + (option.rect.height() - size) // 2,
            size,
            size
        )

        option.widget.style().drawControl(
            QStyle.ControlElement.CE_CheckBox,
            checkbox,
            painter
        )

    def editorEvent(self, event, model, option, index):

        if event.type() == event.Type.MouseButtonRelease:

            current = index.data(Qt.ItemDataRole.CheckStateRole)

            new_state = (
                Qt.CheckState.Unchecked
                if current == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )

            model.setData(
                index,
                new_state,
                Qt.ItemDataRole.CheckStateRole
            )

            return True

        return False

class ArchiveBrowser(QDialog):

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

    def start_download(self):
        files = self.selected_files()

        if not files:
            self.log_message("No files selected for download.")
            return

        self.log_message(f"Starting download of {len(files)} file(s)...")

        # Prevent starting another download while one is running
        self.ok_button.setEnabled(False)
        self.ok_button.setText("Downloading...")

        # Reset progress
        self.progress_overall.setValue(0)
        self.progress_current.setValue(0)
        self.overall_label.setText("0 B / 0 B (0%)")
        self.current_label.setText("Current File")

        # Keep a reference to the worker
        self.worker = DownloadWorker(files)

        self.worker.overall_progress.connect(
            self.update_overall_progress
        )

        self.worker.file_progress.connect(
            self.update_file_progress
        )

        self.worker.log.connect(
            self.log_message
        )

        self.worker.error.connect(
            self.log_message
        )

        self.worker.finished.connect(
            self.download_finished
        )

        self.worker.start()

    def download_finished(self):
        self.log_message("Finished downloading selected files.")

        self.ok_button.setEnabled(True)
        self.ok_button.setText("Download Selected")

        self.progress_current.setValue(100)

    def __init__(self, db, parent=None, name_parameter="Xbox 360 Indie Games"):

        super().__init__(parent)

        self._rainbow_index = 1
        self.db = db
        self.name_parameter = name_parameter
        self.setWindowTitle(f"Archive.org {name_parameter} Browser")
        self.resize(1200, 700)
        icon_path = resource_path("assets/icons/app.ico")
        self.setWindowIcon(QIcon(icon_path))
        self.games = {}

        self.load_games()

        layout = QVBoxLayout(self)

        top = QHBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.setClearButtonEnabled(True)
        self.refresh = QPushButton("Refresh")
        self.ok_button = QPushButton("Download Selected")
        self.ok_button.clicked.connect(self.start_download)
        top.addWidget(self.ok_button)
        top.addWidget(QLabel("Search"))
        top.addWidget(self.search)
        top.addWidget(self.refresh)

        layout.addLayout(top)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # ================= PROGRESS =================
        self.progress_overall = QProgressBar()
        self.progress_current = QProgressBar()
        self.current_label = QLabel("Current File")
        self.overall_label = QLabel("Overall")

        for bar in (self.progress_overall, self.progress_current):
            bar.setMaximumHeight(18)
            bar.setTextVisible(True)
            bar.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed
            )
            bar.setRange(0, 100)
            bar.setValue(0)

        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(10, 0, 10, 5)
        progress_layout.setSpacing(20)

        # Left side
        overall_layout = QHBoxLayout()
        overall_layout.addWidget(self.overall_label)
        overall_layout.addWidget(self.progress_overall)

        # Right side
        current_layout = QHBoxLayout()
        current_layout.addWidget(self.current_label)
        current_layout.addWidget(self.progress_current)

        # Each group gets 50% of the width
        progress_layout.addLayout(overall_layout, 1)
        progress_layout.addLayout(current_layout, 1)

        layout.addWidget(progress_widget)
        self.model = QStandardItemModel()

        self.model.setHorizontalHeaderLabels([
            "",
            "Game",
            "Title ID",
            "Type",
            "Archive",
            "Filename",
            "Size (MB)",
            "Format",
        ])

        self.proxy = ArchiveSortProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table = QTableView()

        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)

        # Hide row numbers
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(28)

        vertical_header = self.table.verticalHeader()

        vertical_header.setVisible(False)
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical_header.setDefaultSectionSize(28)

        self.table.setCornerButtonEnabled(False)

        header = self.table.horizontalHeader()

        # Prevent automatic resizing changing widths
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self.table.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate())

        # Favourite column
        self.table.setColumnWidth(0, 20)

        # Set sensible fixed widths
        self.table.setColumnWidth(1, 250)  # Game
        self.table.setColumnWidth(2, 90)  # Title ID
        self.table.setColumnWidth(3, 50)  # Type
        self.table.setColumnWidth(4, 135)  # Archive

        # Filename gets remaining space
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()

        self.select_all = QPushButton("Select All")
        self.select_none = QPushButton("Select None")

        bottom.addWidget(self.select_all)
        bottom.addWidget(self.select_none)
        bottom.addStretch()

        layout.addLayout(bottom)

        self.search.textChanged.connect(
            self.proxy.setFilterFixedString
        )

        self.refresh.clicked.connect(self.load_archive)

        self.select_all.clicked.connect(self.check_all)
        self.select_none.clicked.connect(self.uncheck_all)

        self.log_window = QPlainTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_window.setFont(QFont("Consolas", 9))
        self.log_window.setMaximumHeight(150)
        self.log_window.setPlaceholderText("Application log...")
        layout.addWidget(self.log_window)

        self.load_archive()
        self.apply_style()


    def load_games(self):
        try:
            cur = self.db.conn.execute("""
                SELECT
                    game_id,
                    title,
                    disc_type
                FROM game_view
            """)
            self.games = {
                row["game_id"].upper(): {
                    "title": row["title"],
                    "disc_type": row["disc_type"],
                }
                for row in cur
            }
        except Exception as e:
            print(e)
            raise

    @staticmethod
    def get_title_id(filename):

        m = re.search(r"([0-9A-Fa-f]{8})", filename)

        if m:
            return m.group(1).upper()

        return ""

    def load_archive(self):

        self.model.removeRows(0, self.model.rowCount())

        self.loader = Loader(name_parameter=self.name_parameter)

        self.loader.fileFound.connect(self.add_file)
        self.loader.progress.connect(self.update_progress)
        self.loader.finishedLoading.connect(
            lambda: self.progress.setValue(100)
        )

        self.loader.start()

    def update_progress(self, current, total):

        self.progress.setValue(int(current / total * 100))

    def add_file(self, file):

        filename = file["name"]

        # Ignore unwanted archive metadata files
        excluded_extensions = {
            ".xml",
            ".sqlite",
            ".torrent",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".txt",
            ".md",
            ".json",
        }

        excluded_names = {
            "__ia_thumb.jpg",
            "xbox360.jpg",
            "xbox360_thumb.jpg",
        }

        lower_name = filename.lower()

        if (
                any(lower_name.endswith(ext) for ext in excluded_extensions)
                or lower_name in excluded_names
        ):
            return

        def normalise_name(name):
            return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()

        archive = file["archive"]

        expected_disc_type = (
            "XBLA"
            if archive == "XBOX_360_XBLA_DLC"
            else "DVD"
        )

        title_id = self.get_title_id(filename)
        game = ""
        disc_type = ""

        filename_norm = normalise_name(filename)
        filename_words = set(filename_norm.split())

        # Text before the first " - "
        filename_base = re.split(r"\s+-\s+", filename, maxsplit=1)[0]
        filename_base_norm = normalise_name(filename_base)

        # ------------------------------------------------------------------
        # 1. Exact Title ID
        # ------------------------------------------------------------------

        if title_id:
            game_info = self.games.get(title_id)
            if game_info and game_info["disc_type"] == expected_disc_type:
                game = game_info["title"]
                disc_type = game_info["disc_type"]

        # ------------------------------------------------------------------
        # 2. Filename starts with game title
        # 3. Filename before " - " exactly equals game title
        # ------------------------------------------------------------------

        if not game:

            best_score = -1
            best_match = None

            for _title_id, game_info in self.games.items():

                if game_info["disc_type"] != expected_disc_type:
                    continue

                game_name = game_info["title"]
                game_norm = normalise_name(game_name)

                score = -1

                # Exact base match
                if filename_base_norm == game_norm:
                    score = 10000

                # Filename begins with title
                elif filename_norm.startswith(game_norm):
                    score = 9000 + len(game_norm)

                if score > best_score:
                    best_score = score
                    best_match = (
                        _title_id,
                        game_name,
                        game_info["disc_type"],
                    )

            if best_match:
                title_id, game, disc_type = best_match

        # ------------------------------------------------------------------
        # 4. Fuzzy word matching
        # ------------------------------------------------------------------

        if not game:

            best_score = 0
            best_match = None

            for _title_id, game_info in self.games.items():

                if game_info["disc_type"] != expected_disc_type:
                    continue

                game_name = game_info["title"]
                game_words = set(normalise_name(game_name).split())

                if not game_words:
                    continue

                matched = len(game_words & filename_words)
                ratio = matched / len(game_words)

                # Require at least 75% of title words
                if ratio < 0.75:
                    continue

                score = (
                        ratio * 1000
                        + matched * 100
                        + sum(len(w) for w in game_words)
                )

                if score > best_score:
                    best_score = score
                    best_match = (
                        _title_id,
                        game_name,
                        game_info["disc_type"],
                    )

            if best_match:
                title_id, game, disc_type = best_match

        # installed = bool(game)
        #
        # title_id = self.get_title_id(filename)
        #
        # game = self.games.get(title_id, "")

        # size = int(file.get("size", 0)) / 1024 / 1024
        size = int(file.get("size", 0))


        check_item = QStandardItem()
        check_item.setCheckable(True)
        check_item.setEditable(False)
        check_item.setData(
            Qt.CheckState.Unchecked,
            Qt.ItemDataRole.CheckStateRole
        )

        size = int(file.get("size", 0))

        size_item = QStandardItem(updater.UpdateManager.human_size(size))
        size_item.setData(size, Qt.ItemDataRole.UserRole)

        row = [
            check_item,
            QStandardItem(game),
            QStandardItem(title_id),
            QStandardItem(disc_type),
            QStandardItem(file["archive"]),
            QStandardItem(filename),
            size_item,
            QStandardItem(file.get("format", "")),
        ]

        row[5].setData(
            {
                "url": f"https://archive.org/download/{file['archive']}/{quote(filename)}",
                "archive": file["archive"],
                "filename": filename,
                "title_id": title_id,
                "game": game,
                "size": file.get("size", 0),
            },
            Qt.ItemDataRole.UserRole,
        )

        if title_id:

            for item in row:
                item.setForeground(QBrush(QColor("#81C784")))

        self.model.appendRow(row)

    def check_all(self):

        for row in range(self.model.rowCount()):
            self.model.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def uncheck_all(self):

        for row in range(self.model.rowCount()):
            self.model.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def selected_files(self):

        files = []

        for row in range(self.model.rowCount()):

            if self.model.item(row, 0).checkState() == Qt.CheckState.Checked:

                files.append(
                    self.model.item(row, 5).data(Qt.ItemDataRole.UserRole)
                )

        return files

    def open_archive_browser(self, name):
        self.archive_browser = ArchiveBrowser(
            self.db,
            self,
            name_parameter=name,
        )
        self.archive_browser.show()

    def log_message(self, message: str = "", console_log: bool = True, log_log: bool = True, clear_console: bool = False, color=None):
        if clear_console:
            self.log_window.clear()
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = escape(str(message))
        if color is None:
            color = self.RAINBOW_COLORS[self._rainbow_index]
            self._rainbow_index = (self._rainbow_index + 1) % len(self.RAINBOW_COLORS)
        # UI console
        if console_log:
            self.log_window.appendHtml(f'<span style="color: {color};">[{timestamp}] {message}</span>')
        if log_log: logging.info(message)

        return

    RAINBOW_COLORS = [
        "#FF4D4D",
        "#FF5252",
        "#FF5C5C",
        "#FF6666",
        "#FF7070",
        "#FF7A7A",
        "#FF4757",
        "#FF3F4F",
        "#FF3850",
        "#FF3048",

        "#FF493D",
        "#FF5138",
        "#FF5933",
        "#FF6130",
        "#FF692B",
        "#FF7025",
        "#FF7820",
        "#FF801B",
        "#FF8816",
        "#FF9011",

        "#FF9810",
        "#FFA00F",
        "#FFA80E",
        "#FFB00D",
        "#FFB80C",
        "#FFC00B",
        "#FFC70A",
        "#FFCE0A",
        "#FFD50A",
        "#FFDC0A",

        "#FFE20A",
        "#FFE80A",
        "#FFEE0A",
        "#FFF30A",
        "#FFF80A",
        "#FFFC12",
        "#F8FF18",
        "#EEFF20",
        "#E4FF27",
        "#DAFF2E",

        "#D0FF35",
        "#C4FF3C",
        "#B8FF43",
        "#ACFF4A",
        "#A0FF51",
        "#94FF58",
        "#88FF5F",
        "#7CFF66",
        "#70FF6D",
        "#64FF74",

        "#58FF7B",
        "#4CFF82",
        "#40FF89",
        "#34FF90",
        "#28FF97",
        "#20FF9E",
        "#18FFA5",
        "#10FFAC",
        "#08FFB3",
        "#00FFBA",

        "#00F8C4",
        "#00F0CE",
        "#00E8D8",
        "#00E0E2",
        "#00D8EC",
        "#00D0F6",
        "#00C8FF",
        "#00BFFF",
        "#18B7FF",
        "#30AFFF",

        "#48A7FF",
        "#60A0FF",
        "#7898FF",
        "#9090FF",
        "#8888FF",
        "#8080FF",
        "#7878FF",
        "#7070FF",
        "#6868FF",
        "#6060FF",

        "#6858FF",
        "#7050FF",
        "#7848FF",
        "#8040FF",
        "#8838FF",
        "#9030FF",
        "#9828FF",
        "#A020FF",
        "#A818FF",
        "#B010FF",

        "#B818FF",
        "#C020FF",
        "#C828FF",
        "#D030FF",
        "#D838FF",
        "#E040FF",
        "#E848FF",
        "#F050FF",
        "#F858FF",
        "#FF60FF",
    ]

    def update_file_progress(self, progress):
        done, total, filename = progress
        if total:
            percent = int(done * 100 / total)
        else:
            percent = 0

        self.progress_current.setRange(0, 100)
        self.progress_current.setValue(percent)

        self.current_label.setText(
            f"{filename} ({self.human_size(done)} / {self.human_size(total)})"
        )

    def update_overall_progress(self, progress):
        done, total = progress
        if total:
            percent = int(done * 100 / total)
        else:
            percent = 0

        self.progress_overall.setRange(0, 100)
        self.progress_overall.setValue(percent)

        self.overall_label.setText(
            f"{self.human_size(done)} / {self.human_size(total)} ({percent}%)"
        )

    @staticmethod
    def human_size(size):
        size = int(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    setup_logger()

    app = QApplication(sys.argv)
    dbase = Database()

    archive = {
        "indie": "Xbox 360 Indie Games",
        "digital": "Xbox 360 Digital",
        "dlc": "Xbox 360 DLC Content",
    }

    dlg = ArchiveBrowser(
        db=dbase,
        name_parameter=archive["dlc"],
    )

    dlg.show()

    sys.exit(app.exec())