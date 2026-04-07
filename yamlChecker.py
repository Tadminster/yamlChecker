import os
import sys
import yaml
import platform
import subprocess
import re

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLineEdit, QLabel,
    QFileDialog, QTabWidget
)
from PySide6.QtGui import (
    QColor, QTextCharFormat, QFont, QPalette, QSyntaxHighlighter
)
from PySide6.QtCore import Qt


# ==================================================
# 파일 열기
# ==================================================
def open_file(path):
    """
    더블 클릭 시 해당 파일을 OS 기본 프로그램으로 열기
    """
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
    """
    YAML 파일을 읽어 dict 로 변환
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), None
    # 실패하면 (None, 에러문자열) 반환
    except Exception as e:
        return None, str(e)


# ==================================================
# 검색 조건 생성기
# ==================================================
def build_match_function(query: str):
    """
    query 전체를 key + value 대상으로 검사하는 matcher 반환
    """

    query = query.strip()

    # 정규식 검색
    if query.startswith("re:"):
        pattern = query[3:]
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except Exception as e:
            print(f"Regex error: {e}")
            return lambda k, v: False

        return lambda k, v: bool(regex.search(str(k)) or regex.search(str(v)))

    # OR 검색
    if " OR " in query:
        tokens = [t.strip().lower() for t in query.split(" OR ") if t.strip()]

        return lambda k, v: any(
            token in str(k).lower() or token in str(v).lower()
            for token in tokens
        )

    # 기본 AND 검색
    tokens = [t.strip().lower() for t in query.split() if t.strip()]

    return lambda k, v: all(
        token in str(k).lower() or token in str(v).lower()
        for token in tokens
    )


def build_key_highlight_function(query: str):
    """
    query를 key 기준으로 다시 검사하는 함수 반환 (파란색 강조)
    """

    query = query.strip()

    # 빈 query
    if not query:
        return lambda key_text: False

    # 정규식
    if query.startswith("re:"):
        pattern = query[3:]
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except Exception as e:
            print(f"Regex error in key highlighter: {e}")
            return lambda key_text: False

        return lambda key_text: bool(regex.search(str(key_text)))

    # OR
    if " OR " in query:
        tokens = [t.strip().lower() for t in query.split(" OR ") if t.strip()]

        return lambda key_text: any(
            token in str(key_text).lower()
            for token in tokens
        )

    # AND
    tokens = [t.strip().lower() for t in query.split() if t.strip()]

    return lambda key_text: all(
        token in str(key_text).lower()
        for token in tokens
    )


# ==================================================
# 결과 하이라이터
# ==================================================
class ResultHighlighter(QSyntaxHighlighter):
    """
    각 줄을 파싱해서 스타일 적용
    초록: folder
    빨강: 잘못된 라인(빈값, '')
    파랑: 탭 query와 매칭
    """

    def __init__(self, document, app_instance, current_query=""):
        super().__init__(document)

        # App 인스턴스 접근용
        self.app = app_instance

        # 현재 탭 query
        self.current_query = current_query.strip()

        # key 영역만 대상으로 파란색 판정하는 함수
        self.key_matcher = build_key_highlight_function(self.current_query)

    def highlightBlock(self, text):
        if not text:
            return

        # --------------------------------------
        # folder 분리
        # --------------------------------------
        first_space = text.find(" ")

        if first_space > 0:
            folder_end = first_space
            content_start = first_space + 1

            self.setFormat(0, folder_end, self.app.format_path())
            self.setFormat(content_start, len(text) - content_start, self.app.format_value())
        else:
            content_start = 0
            self.setFormat(0, len(text), self.app.format_value())

        # --------------------------------------
        # 기본 key인지 확인
        # --------------------------------------
        is_default_key_line = False

        if first_space > 0 and ":" in text:
            remain = text[content_start:]
            colon_index = remain.find(":")

            if colon_index >= 0:
                key = remain[:colon_index].strip()

                if key in self.app.default_keys:
                    is_default_key_line = True

                    value = remain[colon_index + 1:].strip()

                    # --------------------------------------
                    # 빈값 검사 (기본 key만)
                    # --------------------------------------
                    if value == "" or value == "''":
                        self.setFormat(
                            content_start,
                            len(text) - content_start,
                            self.app.format_empty()
                        )
                        return

        # --------------------------------------
        # query highlight
        # --------------------------------------
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
# 메인 UI
# ==================================================
class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("YAML Checker")
        self.resize(1000, 700)

        # 라인 번호 → 파일 경로 매핑
        self.line_maps = {}

        layout = QVBoxLayout()

        # -------------------------
        # 경로 입력 영역
        # -------------------------
        top = QHBoxLayout()
        self.path_input = QLineEdit()

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.select_folder)

        top.addWidget(QLabel("Root Path"))
        top.addWidget(self.path_input)
        top.addWidget(browse_btn)

        layout.addLayout(top)


        # -------------------------
        # 기본 key (단일 소스)
        # -------------------------
        self.default_keys = [
            "collect_place",
            "episode",
            "name",
            "sub_task",
            "prompt"
        ]

        # 빠른 lookup용 set
        self.default_key_set = set(self.default_keys)

        # -------------------------
        # 검색 쿼리 입력 영역
        # -------------------------
        self.key_input = QPlainTextEdit()

        # default_keys를 그대로 UI에 표시
        self.key_input.setPlainText("\n".join(self.default_keys))

        layout.addWidget(QLabel("Search Queries"))
        layout.addWidget(self.key_input)

        # -------------------------
        # Scan 버튼
        # -------------------------
        scan_btn = QPushButton("Scan")
        scan_btn.clicked.connect(self.run_scan)
        layout.addWidget(scan_btn)

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
    def run_scan(self):
        root = self.path_input.text().strip()
        if not os.path.isdir(root):
            return

        # 기존 결과 초기화
        self.tabs.clear()
        self.line_maps.clear()

        # 사용자가 입력한 query 목록
        queries = [
            q.strip()
            for q in self.key_input.toPlainText().splitlines()
            if q.strip()
        ]

        if not queries:
            return

        # query별 matcher 생성
        matchers = {q: build_match_function(q) for q in queries}

        # 결과 구조
        # results["text"] = [(path, real_key, value), ...]
        results = {q: [] for q in queries}

        # 폴더 재귀 탐색
        for r, _, files in os.walk(root):
            for f in files:
                if not f.endswith(".yaml"):
                    continue

                full = os.path.join(r, f)

                data, err = load_yaml(full)

                # dict 구조 아니면 스킵
                if err or not isinstance(data, dict):
                    continue

                # YAML 최상위 key/value 순회
                for data_key, value in data.items():
                    for q in queries:
                        if matchers[q](data_key, value):
                            entry = (full, data_key, value)

                            # 중복 제거
                            if entry not in results[q]:
                                results[q].append(entry)

        # All 탭
        self.add_tab("All", queries, results, current_query="")

        # 개별 탭
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

        # 탭 내부 텍스트 구성
        for q in queries:
            # 탭 제목 라인
            lines.append(q)
            line_index += 1

            # 결과 라인
            for path, real_key, value in results[q]:
                folder = os.path.basename(os.path.dirname(path))

                if value is None:
                    display = f"{real_key}:"
                elif isinstance(value, str) and value.strip() == "":
                    display = f"{real_key}: ''"
                else:
                    display = f"{real_key}: {value}"

                line = f"{folder} {display}"
                lines.append(line)

                # 더블클릭용 라인 매핑
                self.line_maps[text][line_index] = path
                line_index += 1

            # 구분용 빈 줄
            lines.append("")
            line_index += 1

        text.setPlainText("\n".join(lines))

        # 현재 탭 query 전달
        highlighter = ResultHighlighter(
            text.document(),
            self,
            current_query=current_query
        )
        text._highlighter = highlighter  # GC 방지

        # 더블클릭 이벤트 연결
        text.mouseDoubleClickEvent = lambda e, t=text: self.open_from_click(e, t)

    # ==================================================
    # 더블클릭 시 파일 열기
    # ==================================================
    def open_from_click(self, event, text):
        cursor = text.cursorForPosition(event.pos())
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
# 메인 진입점
# ==================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#ffffff"))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Text, Qt.black)
    palette.setColor(QPalette.Button, QColor("#f0f0f0"))
    palette.setColor(QPalette.ButtonText, Qt.black)
    palette.setColor(QPalette.Highlight, QColor("#0078d7"))
    palette.setColor(QPalette.HighlightedText, Qt.white)

    app.setPalette(palette)

    w = App()
    w.show()
    sys.exit(app.exec())