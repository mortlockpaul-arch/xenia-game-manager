import sys
import subprocess
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


EASYXNB_DIR = Path(r"C:\source\EasyXNB")
EASYXNB_EXE = EASYXNB_DIR / r"bin\x86\Debug\net461\EasyXnb.exe"

class EasyXnbGui(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EasyXnb Launcher")
        self.resize(800, 650)

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(EASYXNB_DIR))
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_output)
        self.process.finished.connect(self.process_finished)

        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # ---------------------------------------------------------
        # Directories
        # ---------------------------------------------------------

        paths = QGroupBox("Directories")
        paths_layout = QFormLayout(paths)

        self.input_directory = QLineEdit()
        self.intermediate_directory = QLineEdit("default")
        self.output_directory = QLineEdit("default")

        paths_layout.addRow(
            "Input:",
            self.path_row(self.input_directory, self.browse_input),
        )

        paths_layout.addRow(
            "Intermediate:",
            self.path_row(
                self.intermediate_directory,
                self.browse_intermediate,
            ),
        )

        paths_layout.addRow(
            "Output:",
            self.path_row(
                self.output_directory,
                self.browse_output,
            ),
        )

        layout.addWidget(paths)

        # ---------------------------------------------------------
        # Compilation
        # ---------------------------------------------------------

        compilation = QGroupBox("Compilation")
        compilation_layout = QVBoxLayout(compilation)

        self.compile_fonts = QCheckBox("Compile Fonts")
        self.compile_materials = QCheckBox("Compile Materials")
        self.compile_textures = QCheckBox("Compile Textures")
        self.ignore_png = QCheckBox("Ignore PNG files")

        self.compile_textures.setChecked(True)
        self.ignore_png.setChecked(True)

        compilation_layout.addWidget(self.compile_fonts)
        compilation_layout.addWidget(self.compile_materials)
        compilation_layout.addWidget(self.compile_textures)
        compilation_layout.addWidget(self.ignore_png)

        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Target Profile:"))

        self.target_profile = QComboBox()
        self.target_profile.addItems(["Reach", "HiDef"])
        self.target_profile.setCurrentText("Reach")

        profile_layout.addWidget(self.target_profile)
        profile_layout.addStretch()

        compilation_layout.addLayout(profile_layout)

        layout.addWidget(compilation)

        # ---------------------------------------------------------
        # Options
        # ---------------------------------------------------------

        options = QGroupBox("Options")
        options_layout = QVBoxLayout(options)

        self.compress_output = QCheckBox("Compress output")
        self.rebuild_all = QCheckBox("Rebuild all")
        self.close_immediately = QCheckBox("Close immediately")
        self.wait_on_error = QCheckBox("Wait on error")

        options_layout.addWidget(self.compress_output)
        options_layout.addWidget(self.rebuild_all)
        options_layout.addWidget(self.close_immediately)
        options_layout.addWidget(self.wait_on_error)

        layout.addWidget(options)

        # ---------------------------------------------------------
        # Run
        # ---------------------------------------------------------

        run_layout = QHBoxLayout()

        self.run_button = QPushButton("Run EasyXnb")
        self.run_button.clicked.connect(self.run_easyxnb)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_process)

        run_layout.addWidget(self.run_button)
        run_layout.addWidget(self.stop_button)

        layout.addLayout(run_layout)

        # ---------------------------------------------------------
        # Output
        # ---------------------------------------------------------

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)

        layout.addWidget(self.output, 1)

        self.statusBar().showMessage("Ready")

    # -------------------------------------------------------------
    # UI helpers
    # -------------------------------------------------------------

    def path_row(self, edit, callback):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        button = QPushButton("...")
        button.setFixedWidth(35)
        button.clicked.connect(callback)

        layout.addWidget(edit, 1)
        layout.addWidget(button)

        return widget

    def browse_input(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select EasyXnb input directory",
        )

        if path:
            self.input_directory.setText(path)

    def browse_intermediate(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select intermediate directory",
        )

        if path:
            self.intermediate_directory.setText(path)

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select output directory",
        )

        if path:
            self.output_directory.setText(path)

    # -------------------------------------------------------------
    # EasyXnb
    # -------------------------------------------------------------

    def build_arguments(self):
        args = []

        def add(name, value):
            args.extend([name, value])

        add("CompileFonts", str(self.compile_fonts.isChecked()).lower())
        add("CompileMaterials", str(self.compile_materials.isChecked()).lower())
        add("CompileTextures", str(self.compile_textures.isChecked()).lower())
        add("IgnorePng", str(self.ignore_png.isChecked()).lower())

        add("TargetProfile", self.target_profile.currentText())

        add(
            "CompressOutput",
            str(self.compress_output.isChecked()).lower(),
        )

        add(
            "RebuildAll",
            str(self.rebuild_all.isChecked()).lower(),
        )

        add(
            "CloseImmediately",
            str(self.close_immediately.isChecked()).lower(),
        )

        add(
            "WaitOnError",
            str(self.wait_on_error.isChecked()).lower(),
        )

        if self.input_directory.text():
            add("InputDirectory", self.input_directory.text())

        if self.intermediate_directory.text():
            add(
                "IntermediateDirectory",
                self.intermediate_directory.text(),
            )

        if self.output_directory.text():
            add("OutputDirectory", self.output_directory.text())

        return args

    def run_easyxnb(self):
        if not EASYXNB_EXE.exists():
            QMessageBox.critical(
                self,
                "EasyXnb not found",
                f"Could not find:\n\n{EASYXNB_EXE}",
            )
            return

        self.output.clear()

        args = self.build_arguments()

        self.output.appendPlainText(
            f"Working directory:\n{EASYXNB_DIR}\n"
        )
        self.output.appendPlainText(
            f"Executable:\n{EASYXNB_EXE}\n"
        )
        self.output.appendPlainText(
            f"Arguments:\n{' '.join(args)}\n"
        )
        self.output.appendPlainText("\n--- EasyXnb output ---\n")

        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.process.start(str(EASYXNB_EXE), args)

        if not self.process.waitForStarted(3000):
            self.output.appendPlainText(
                f"Failed to start EasyXnb:\n"
                f"{self.process.errorString()}"
            )
            self.run_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )

        if data:
            self.output.appendPlainText(data.rstrip())

        data = bytes(self.process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )

        if data:
            self.output.appendPlainText(data.rstrip())

    def process_finished(self, exit_code, exit_status):
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        self.output.appendPlainText(
            f"\n--- EasyXnb finished: {exit_code} ---"
        )

        self.statusBar().showMessage(
            f"Finished with exit code {exit_code}"
        )

    def stop_process(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = EasyXnbGui()
    window.show()

    sys.exit(app.exec())