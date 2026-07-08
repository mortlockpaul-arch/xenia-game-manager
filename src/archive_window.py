import os
import re
import requests
from urllib.parse import quote

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QSortFilterProxyModel,
)

from PySide6.QtGui import (
    QColor,
    QStandardItem,
    QStandardItemModel, QBrush, QIcon,
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
    QHeaderView,
)

from db import Database

ARCHIVES = [
    *[f"XBOX_360_DLC_{i}" for i in range(1, 6)],
    "XBOX_360_XBLA_DLC",
]

class Loader(QThread):

    fileFound = Signal(dict)
    progress = Signal(int, int)
    finishedLoading = Signal()

    def run(self):

        total = len(ARCHIVES)

        for index, archive in enumerate(ARCHIVES, start=1):

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

from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionButton, QStyle
from PySide6.QtCore import Qt, QRect
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

    def __init__(self, db, parent=None):

        super().__init__(parent)

        self.db = db

        self.setWindowTitle("Archive.org DLC Browser")
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
        self.ok_button.clicked.connect(self.accept)
        top.addWidget(self.ok_button)
        top.addWidget(QLabel("Search"))
        top.addWidget(self.search)
        top.addWidget(self.refresh)

        layout.addLayout(top)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

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

        self.proxy = QSortFilterProxyModel()
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

        self.load_archive()
        self.apply_style()


    def load_games(self):

        try:

            cur = self.db.conn.execute(
                "SELECT game_id, title, disc_type FROM games"
            )

            self.games = {
                row["game_id"].upper(): {
                    "title": row["title"],
                    "disc_type": row["disc_type"],
                }
                for row in cur
            }


        except Exception:
            self.games = {}

    @staticmethod
    def get_title_id(filename):

        m = re.search(r"([0-9A-Fa-f]{8})", filename)

        if m:
            return m.group(1).upper()

        return ""

    def load_archive(self):

        self.model.removeRows(0, self.model.rowCount())

        self.loader = Loader()

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
        game_info = None
        # First try exact Title ID
        if title_id:
            game_info = self.games.get(title_id)
            if game_info and game_info["disc_type"] == expected_disc_type:
                game = game_info["title"]
                disc_type = game_info["disc_type"]

        # Fall back to fuzzy word matching
        if not game:

            filename_words = set(normalise_name(filename).split())

            best_score = 0
            best_match = None

            for _title_id, game_info in self.games.items():

                if game_info["disc_type"] != expected_disc_type:
                    continue

                game_name = game_info["title"]
                game_words = set(normalise_name(game_name).split())

                if not game_words:
                    continue

                # Ignore extremely short names
                if len("".join(game_words)) < 3:
                    continue

                matched = len(game_words & filename_words)

                # All words must match
                if matched != len(game_words):
                    continue

                # Prefer longer titles
                score = matched * 100 + sum(len(w) for w in game_words)

                if score > best_score:
                    best_score = score
                    best_match = (
                        _title_id,
                        game_name,
                        game_info["disc_type"],
                    )

            if best_match:
                title_id = best_match[0]
                game = best_match[1]
                disc_type = best_match[2]

        # installed = bool(game)
        #
        # title_id = self.get_title_id(filename)
        #
        # game = self.games.get(title_id, "")

        size = int(file.get("size", 0)) / 1024 / 1024

        check_item = QStandardItem()
        check_item.setCheckable(True)
        check_item.setEditable(False)
        check_item.setData(
            Qt.CheckState.Unchecked,
            Qt.ItemDataRole.CheckStateRole
        )

        row = [
            check_item,
            QStandardItem(game),
            QStandardItem(title_id),
            QStandardItem(disc_type),
            QStandardItem(file["archive"]),
            QStandardItem(filename),
            QStandardItem(f"{size:.2f}"),
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
            Qt.UserRole,
        )

        if title_id:

            for item in row:
                item.setForeground(QBrush(QColor("#81C784")))

        self.model.appendRow(row)

    def check_all(self):

        for row in range(self.model.rowCount()):
            self.model.item(row, 0).setCheckState(Qt.Checked)

    def uncheck_all(self):

        for row in range(self.model.rowCount()):
            self.model.item(row, 0).setCheckState(Qt.Unchecked)

    def selected_files(self):

        files = []

        for row in range(self.model.rowCount()):

            if self.model.item(row, 0).checkState() == Qt.Checked:

                files.append(
                    self.model.item(row, 5).data(Qt.UserRole)
                )

        return files

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    db = Database()
    dlg = ArchiveBrowser(db=db)
    dlg.exec()

    print(dlg.selected_files())

    sys.exit(app.exec())