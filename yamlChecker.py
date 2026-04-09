import os
import sys
import platform
import subprocess
import re
import json

from pathlib import Path 

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLineEdit, QLabel,
    QFileDialog, QTabWidget, QSpinBox,
    QDialog, QCheckBox, QFrame
)

from PySide6.QtGui import (
    QColor, QTextCharFormat, QFont, QPalette, QSyntaxHighlighter
)

from PySide6.QtCore import Qt


# ==================================================
# 경로 축약 함수
# ==================================================
def shorten_path(path, root=None, depth=4):
    p = Path(path)

    if root:
        try:
            p = p.resolve().relative_to(Path(root).resolve())
        except Exception:
            p = p.resolve()
    else:
        p = p.resolve()

    parts = list(p.parts)

    if len(parts) > depth:
        trimmed = parts[-depth:]
        shortened = True
    else:
        trimmed = parts
        shortened = False

    result = "/".join(trimmed)

    if shortened:
        result = ".../" + result

    return result


# ==================================================
# 파일명 제거 옵션
# ==================================================
def process_path_display(path, root, depth, hide_filename):
    path = path.replace("\\", "/")

    if hide_filename:
        if "/" in path:
            path = path.rsplit("/", 1)[0]

    short = shorten_path(path, root, depth)

    return short


# ==================================================
# 파일 열기
# ==================================================
def open_file(path):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        print(e)


# ==================================================
# 검색 옵션 다이얼로그
# ==================================================
class SearchOptionsDialog(QDialog):
    def __init__(self, parent=None, init_options=None):
        super().__init__(parent)

        # None 방지용
        init_options = init_options or {}

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        layout = QVBoxLayout()

        # 타이틀 바
        title_layout = QVBoxLayout()

        title_label = QLabel("검색 옵션")
        title_label.setAlignment(Qt.AlignCenter)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ccc;")

        title_layout.addWidget(title_label)
        title_layout.addWidget(line)

        layout.addLayout(title_layout)

        # Depth 옵션
        depth_layout = QHBoxLayout()
        depth_label = QLabel("경로 표시 깊이")

        self.depth_spin = QSpinBox()
        self.depth_spin.setMinimum(1)
        self.depth_spin.setMaximum(10)
        self.depth_spin.setValue(init_options.get("depth", 3))

        depth_layout.addWidget(depth_label)
        depth_layout.addStretch()
        depth_layout.addWidget(self.depth_spin)

        layout.addLayout(depth_layout)

        # 파일명 숨김 옵션
        hide_file_layout = QHBoxLayout()

        hide_file_label = QLabel("파일명 숨김")
        self.hide_file_checkbox = QCheckBox()
        self.hide_file_checkbox.setChecked(init_options.get("hide_filename", False))

        def on_hide_label_click(event):
            self.hide_file_checkbox.toggle()
            QLabel.mousePressEvent(hide_file_label, event)

        hide_file_label.mousePressEvent = on_hide_label_click

        hide_file_layout.addWidget(hide_file_label)
        hide_file_layout.addStretch()
        hide_file_layout.addWidget(self.hide_file_checkbox)

        layout.addLayout(hide_file_layout)

        # Regex 옵션
        regex_layout = QHBoxLayout()

        regex_label = QLabel("정규식 사용")
        self.regex_checkbox = QCheckBox()
        self.regex_checkbox.setChecked(init_options.get("use_regex", False))

        # -----------------------------
        # 라벨 클릭 이벤트
        # -----------------------------
        def on_label_click(event):
            self.regex_checkbox.toggle()
            QLabel.mousePressEvent(regex_label, event)

        regex_label.mousePressEvent = on_label_click

        regex_layout.addWidget(regex_label)
        regex_layout.addStretch()
        regex_layout.addWidget(self.regex_checkbox)

        layout.addLayout(regex_layout)

        # -----------------------------
        # 버튼
        # -----------------------------
        btn_layout = QHBoxLayout()

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)

        layout.addSpacing(20)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    # -----------------------------
    # 옵션 반환
    # -----------------------------
    def get_options(self):
        return {
            "depth": self.depth_spin.value(),
            "hide_filename": self.hide_file_checkbox.isChecked(),
            "use_regex": self.regex_checkbox.isChecked()
        }

    # -----------------------------
    # 모달 창 드래그 기능
    # -----------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._drag_pos = event.globalPosition().toPoint()


# ==================================================
# 문제 라인 검사 함수
# ==================================================
def is_problem_line(line: str):

    if ":" not in line:
        return False

    parts = line.split(":", 1)
    value = parts[1].strip()

    return value == "" or value == "''"


# ==================================================
# 하이라이터
# ==================================================
class ResultHighlighter(QSyntaxHighlighter):
    def __init__(self, document, app_instance, current_query=""):
        super().__init__(document)
        self.app = app_instance
        self.current_query = current_query.strip()

    def highlightBlock(self, text):
        if not text:
            return

        first_space = text.find(" ")

        if first_space > 0:
            self.setFormat(0, first_space, self.app.format_path())
            self.setFormat(first_space + 1, len(text), self.app.format_value())

        # 문제 라인 검사 (우선 적용)
        content = text[first_space + 1:] if first_space > 0 else text

        if is_problem_line(content):
            self.setFormat(
                first_space + 1 if first_space > 0 else 0,
                len(content),
                self.app.format_empty()
            )
            return

        # 검색어 하이라이트
        if not self.current_query:
            return

        lower = text.lower()
        q = self.current_query.lower()

        start = 0
        while True:
            idx = lower.find(q, start)
            if idx == -1:
                break

            self.setFormat(idx, len(q), self.app.format_key())
            start = idx + len(q)


# ==================================================
# 메인 UI
# ==================================================
class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("YAML Checker")
        self.resize(1000, 700)

        self.line_maps = {}

        self.options_file = "search_options.json"
        self.last_search_options = {
            "depth": 3,
            "hide_filename": False,
            "use_regex": False
        }

        self.load_options()

        layout = QVBoxLayout()

        # 경로
        top = QHBoxLayout()
        self.path_input = QLineEdit()

        btn = QPushButton("📁")
        btn.clicked.connect(self.select_folder)

        top.addWidget(QLabel("루트 경로"))
        top.addWidget(self.path_input)
        top.addWidget(btn)

        layout.addLayout(top)

        # 검색
        search = QHBoxLayout()
        self.key_input = QLineEdit()

        option_btn = QPushButton("⚙️")
        option_btn.clicked.connect(self.open_search_options)

        run_btn = QPushButton("🔎")
        run_btn.clicked.connect(self.run_scan)

        search.addWidget(QLabel("검색"))
        search.addWidget(self.key_input)
        search.addWidget(option_btn)
        search.addWidget(run_btn)

        layout.addLayout(search)

        # 탭 스타일 유지
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
        QTabBar::tab {
            background: #e0e0e0;
            padding: 10px 22px;
            margin-right: 6px;
            border-radius: 6px;
        }

        QTabBar::tab:selected {
            background: #e6f0ff;
            color: #0004ff;
            font-weight: bold;
        }
        """)

        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self.default_keys = [
            "version", "timestamp", "episode_name", "domain",
            "collect_place", "collect_place_description",
            "collect_device", "zed_serial", "scenario",
            "task", "name", "prompt", "hand_visible",
            "tags", "worker"
        ]

    # ==================================================
    # 옵션
    # ==================================================
    def save_options(self):
        with open(self.options_file, "w", encoding="utf-8") as f:
            json.dump(self.last_search_options, f)

    def load_options(self):
        if os.path.exists(self.options_file):
            with open(self.options_file, "r", encoding="utf-8") as f:
                self.last_search_options.update(json.load(f))

    def open_search_options(self):
        dialog = SearchOptionsDialog(self, self.last_search_options)
        if dialog.exec():
            self.last_search_options = dialog.get_options()
            self.save_options()
            self.run_scan()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self)
        if folder:
            self.path_input.setText(folder)

    # ==================================================
    # grep 검색 유지
    # ==================================================
    def run_scan(self):
        root = self.path_input.text().strip()
        if not os.path.isdir(root):
            return

        self.tabs.clear()
        self.line_maps.clear()

        user_query = self.key_input.text().strip()
        use_regex = self.last_search_options["use_regex"]

        results_default = {k: [] for k in self.default_keys}
        results_user = []

        for r, _, files in os.walk(root):
            for f in files:
                if not f.endswith(".yaml"):
                    continue

                path = os.path.join(r, f)

                try:
                    with open(path, "r", encoding="utf-8") as file:
                        for line in file:
                            line = line.rstrip("\n")

                            for key in self.default_keys:
                                if key in line:
                                    results_default[key].append((path, line))
                                    break

                            if user_query:
                                if use_regex:
                                    try:
                                        if re.search(user_query, line):
                                            results_user.append((path, line))
                                    except:
                                        pass
                                else:
                                    if user_query in line:
                                        results_user.append((path, line))

                except:
                    continue

        # 유저 쿼리 탭 우선 생성
        if user_query:
            self.add_tab(user_query, results_user, user_query)

        for key, data in results_default.items():
            if key == user_query:
                continue  # 중복 방지
            if data:
                self.add_tab(key, data, key)

    def add_tab(self, title, data, current_query):
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 11))

        self.tabs.addTab(text, title)
        self.line_maps[text] = {}

        lines = []
        root = self.path_input.text().strip()
        depth = self.last_search_options["depth"]

        for i, (path, line) in enumerate(data):
            hide_filename = self.last_search_options.get("hide_filename", False)
            short = process_path_display(path, root, depth, hide_filename)
            lines.append(f"{short} {line}")
            self.line_maps[text][i] = path

        text.setPlainText("\n".join(lines))

        text._highlighter = ResultHighlighter(
            text.document(),
            self,
            current_query=current_query
        )

        text.mouseDoubleClickEvent = lambda e, t=text: self.open_from_click(e, t)

    def open_from_click(self, event, text):
        cursor = text.cursorForPosition(event.position().toPoint())
        line = cursor.blockNumber()

        if line in self.line_maps[text]:
            open_file(self.line_maps[text][line])

    # ==================================================
    # 스타일
    # ==================================================
    def format_key(self):
        f = QTextCharFormat()
        f.setForeground(QColor("#0004ff"))
        f.setFontWeight(QFont.Bold)
        return f

    def format_path(self):
        f = QTextCharFormat()
        f.setForeground(QColor("#255e00"))
        return f

    def format_value(self):
        f = QTextCharFormat()
        f.setForeground(QColor("#000000"))
        return f

    def format_empty(self):
        f = QTextCharFormat()
        f.setForeground(QColor("#ff4444"))
        f.setBackground(QColor("#FFCECE"))
        return f


# ==================================================
# 실행
# ==================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#EAF3FF"))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.Text, Qt.black)
    palette.setColor(QPalette.Button, QColor("#DCE6F7"))
    palette.setColor(QPalette.ButtonText, Qt.black)
    palette.setColor(QPalette.Highlight, QColor("#0078d7"))
    palette.setColor(QPalette.HighlightedText, Qt.white)


    app.setPalette(palette)

    w = App()
    w.show()

    sys.exit(app.exec())