import os
import sys
import yaml
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
# YAML 로드
# ==================================================
def load_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except Exception as e:
        return None, str(e)


# ==================================================
# 검색 조건 생성기
# ==================================================
def build_match_function(query: str):
    query = query.strip()

    if " OR " in query:
        tokens = [t.strip().lower() for t in query.split(" OR ") if t.strip()]

        return lambda k, v: any(
            token in str(k).lower() or token in str(v).lower()
            for token in tokens
        )

    tokens = [t.strip().lower() for t in query.split() if t.strip()]

    return lambda k, v: all(
        token in str(k).lower() or token in str(v).lower()
        for token in tokens
    )


def build_key_highlight_function(query: str):
    query = query.strip()

    if not query:
        return lambda key_text: False

    if " OR " in query:
        tokens = [t.strip().lower() for t in query.split(" OR ") if t.strip()]

        return lambda key_text: any(
            token in str(key_text).lower()
            for token in tokens
        )

    tokens = [t.strip().lower() for t in query.split() if t.strip()]

    return lambda key_text: all(
        token in str(key_text).lower()
        for token in tokens
    )


# ==================================================
# 사용자 입력 query 파싱
# ==================================================
def parse_user_queries(text: str):
    raw_queries = [q.strip() for q in text.split(",") if q.strip()]

    unique_queries = []
    seen = set()

    for q in raw_queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return unique_queries


# ==================================================
# 결과 하이라이터
# ==================================================
class ResultHighlighter(QSyntaxHighlighter):
    def __init__(self, document, app_instance, current_query=""):
        super().__init__(document)
        self.app = app_instance
        self.current_query = current_query.strip()
        self.key_matcher = build_key_highlight_function(self.current_query)

    def highlightBlock(self, text):
        if not text:
            return

        first_space = text.find(" ")

        if first_space > 0:
            folder_end = first_space
            content_start = first_space + 1

            self.setFormat(0, folder_end, self.app.format_path())
            self.setFormat(content_start, len(text) - content_start, self.app.format_value())
        else:
            content_start = 0
            self.setFormat(0, len(text), self.app.format_value())

        if first_space > 0 and ":" in text:
            remain = text[content_start:]
            colon_index = remain.find(":")

            if colon_index >= 0:
                key = remain[:colon_index].strip()

                if key in self.app.default_keys:
                    value = remain[colon_index + 1:].strip()

                    if value == "" or value == "''":
                        self.setFormat(
                            content_start,
                            len(text) - content_start,
                            self.app.format_empty()
                        )
                        return

        if not self.current_query:
            return

        query = self.current_query.lower()
        lower_text = text.lower()

        start = content_start

        while True:
            idx = lower_text.find(query, start)
            if idx == -1:
                break

            length = len(query)
            self.setFormat(idx, length, self.app.format_key())
            start = idx + length


# ==================================================
# 검색 옵션 다이얼로그
# ==================================================
class SearchOptionsDialog(QDialog):
    def __init__(self, parent=None, init_options=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        layout = QVBoxLayout()

        # -----------------------------
        # 타이틀 바
        # -----------------------------
        title_layout = QVBoxLayout()

        title_label = QLabel("검색 옵션")
        title_label.setAlignment(Qt.AlignCenter)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ccc;")

        title_layout.addWidget(title_label)
        title_layout.addWidget(line)

        layout.addLayout(title_layout)

        # Depth
        depth_layout = QHBoxLayout()
        depth_label = QLabel("경로 표시 깊이")

        self.depth_spin = QSpinBox()
        self.depth_spin.setMinimum(1)
        self.depth_spin.setMaximum(10)

        default_depth = init_options.get("depth", 3) if init_options else 3
        self.depth_spin.setValue(default_depth)

        depth_layout.addWidget(depth_label)
        depth_layout.addStretch()
        depth_layout.addWidget(self.depth_spin)
        layout.addLayout(depth_layout)

        # Regex
        regex_layout = QHBoxLayout()

        regex_label = QLabel("정규식 사용")
        self.regex_checkbox = QCheckBox()

        default_regex = init_options.get("use_regex", False) if init_options else False
        self.regex_checkbox.setChecked(default_regex)

        # 라벨 클릭 이벤트
        regex_label.mousePressEvent = lambda e: (
            self.regex_checkbox.toggle(),
            QLabel.mousePressEvent(regex_label, e)
        )

        regex_layout.addWidget(regex_label)
        regex_layout.addStretch()
        regex_layout.addWidget(self.regex_checkbox)

        layout.addLayout(regex_layout)

        # 버튼
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

    def get_options(self):
        return {
            "depth": self.depth_spin.value(),
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
# 메인 UI
# ==================================================
class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("YAML Checker")
        self.resize(1000, 700)

        self.line_maps = {}

        # -------------------------
        # 옵션 저장
        # -------------------------
        self.options_file = "search_options.json"

        self.last_search_options = {
            "depth": 3,
            "use_regex": False
        }

        self.load_options()

        layout = QVBoxLayout()

        # -------------------------
        # 경로 입력
        # -------------------------
        top = QHBoxLayout()

        path_label = QLabel("루트 경로")
        top.addWidget(path_label)

        self.path_input = QLineEdit()
        top.addWidget(self.path_input)

        browse_btn = QPushButton("📁")
        browse_btn.clicked.connect(self.select_folder)
        top.addWidget(browse_btn)

        layout.addLayout(top)

        # -------------------------
        # 검색 영역
        # -------------------------
        search_layout = QHBoxLayout()

        search_label = QLabel("추가 검색")
        search_layout.addWidget(search_label)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("추가 key 입력 (콤마 구분)")
        search_layout.addWidget(self.key_input)

        # 옵션 버튼
        search_option_btn = QPushButton("⚙️")
        search_option_btn.clicked.connect(self.open_search_options)
        search_layout.addWidget(search_option_btn)

        # 검색 버튼
        search_btn = QPushButton("🔎")
        search_btn.clicked.connect(self.run_scan)
        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        # -------------------------
        # 결과 탭
        # -------------------------
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
            border: 1px solid #c0d4ff;
            border-bottom: none;
        }

        QTabBar::tab:hover {
            background: #f5f5f5;
        }
        """)

        layout.addWidget(self.tabs)
        self.setLayout(layout)

        # 기본 key
        self.default_keys = [
            "version", "timestamp", "episode_name", "domain",
            "collect_place", "collect_place_description",
            "collect_device", "zed_serial", "scenario",
            "task", "name", "prompt", "hand_visible",
            "tags", "worker"
        ]

        self.default_key_set = set(self.default_keys)

    # ==================================================
    # 옵션 저장
    # ==================================================
    def save_options(self):
        try:
            with open(self.options_file, "w", encoding="utf-8") as f:
                json.dump(self.last_search_options, f, indent=4)
        except Exception as e:
            print("옵션 저장 실패:", e)

    # ==================================================
    # 옵션 로드
    # ==================================================
    def load_options(self):
        try:
            if os.path.exists(self.options_file):
                with open(self.options_file, "r", encoding="utf-8") as f:
                    loaded_options = json.load(f)

                    self.last_search_options["depth"] = loaded_options.get("depth", 3)
                    self.last_search_options["use_regex"] = loaded_options.get("use_regex", False)
        except Exception as e:
            print("옵션 로드 실패:", e)

    # ==================================================
    # 옵션창
    # ==================================================
    def open_search_options(self):
        dialog = SearchOptionsDialog(self, self.last_search_options)

        if dialog.exec() == QDialog.Accepted:
            self.last_search_options = dialog.get_options()
            self.save_options()
            self.run_scan(self.last_search_options)

    # ==================================================
    # 폴더 선택
    # ==================================================
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self)
        if folder:
            self.path_input.setText(folder)

    # ==================================================
    # 스캔
    # ==================================================
    def run_scan(self, options=None):
        root = self.path_input.text().strip()
        if not os.path.isdir(root):
            return

        options = options or self.last_search_options
        use_regex = options.get("use_regex", False)

        self.tabs.clear()
        self.line_maps.clear()

        user_queries = parse_user_queries(self.key_input.text().strip())
        queries = user_queries + [k for k in self.default_keys if k not in user_queries]

        if not queries:
            return

        matchers = {}

        for q in queries:
            if use_regex:
                try:
                    regex = re.compile(q, re.IGNORECASE)
                    matchers[q] = lambda k, v, r=regex: bool(r.search(str(k)) or r.search(str(v)))
                except Exception:
                    matchers[q] = lambda k, v: False
            else:
                matchers[q] = build_match_function(q)

        results = {q: [] for q in queries}

        for r, _, files in os.walk(root):
            for f in files:
                if not f.endswith(".yaml"):
                    continue

                full = os.path.join(r, f)
                data, err = load_yaml(full)

                if err or not isinstance(data, dict):
                    continue

                for data_key, value in data.items():
                    for q in queries:
                        if matchers[q](data_key, value):
                            entry = (full, data_key, value)

                            if entry not in results[q]:
                                results[q].append(entry)

        for q in queries:
            self.add_tab(q, [q], results, current_query=q)

    # ==================================================
    # 탭 생성
    # ==================================================
    def add_tab(self, title, queries, results, current_query=""):
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 11))
        text.setStyleSheet("""
        QPlainTextEdit {
            padding: 6px;
        }
        """)

        self.tabs.addTab(text, title)

        # 라인 → 파일 경로 매핑
        self.line_maps[text] = {}

        lines = []
        line_index = 0

        root = self.path_input.text().strip()
        depth = self.last_search_options.get("depth", 3)

        for q in queries:
            for path, real_key, value in results[q]:

                if value is None:
                    display = f"{real_key}:"
                elif isinstance(value, str) and value.strip() == "":
                    display = f"{real_key}: ''"
                else:
                    display = f"{real_key}: {value}"

                short_path = shorten_path(path, root=root, depth=depth)

                line = f"{short_path} {display}"
                lines.append(line)

                self.line_maps[text][line_index] = path
                line_index += 1

        text.setPlainText("\n".join(lines))

        # 현재 탭 query 전달
        highlighter = ResultHighlighter(
            text.document(),
            self,
            current_query=current_query
        )
        text._highlighter = highlighter

        # 더블클릭 이벤트 연결
        text.mouseDoubleClickEvent = lambda e, t=text: self.open_from_click(e, t)

    # ==================================================
    # 더블클릭 시 파일 열기
    # ==================================================
    def open_from_click(self, event, text):
        cursor = text.cursorForPosition(event.position().toPoint())
        line = cursor.blockNumber()

        if line in self.line_maps[text]:
            open_file(self.line_maps[text][line])

    # ==================================================
    # 스타일 정의
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
# 메인
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