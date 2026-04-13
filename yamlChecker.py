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
    QDialog, QCheckBox, QFrame, QMessageBox
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

        btn_ok = QPushButton("적용")
        btn_ok.clicked.connect(self.accept)

        btn_cancel = QPushButton("취소")
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
def is_problem_line(line: str, key: str) -> bool:

    # 태그 탭은 따로 검사하지 않음
    if key == "tags":
        return False

    # ':' 기준 분리
    parts = line.split(":", 1)

    # ':' 이후 공백이면 문제로 판단
    if len(parts) < 2:
        return True

    # 공백제거 (첫 줄 value)
    value_part = parts[1].strip()

    # ---------------------------
    # 🔥 멀티라인 대응 추가
    # ---------------------------
    # prompt 등 여러 줄일 경우 전체 value로 재구성
    if "\n" in line:
        lines = line.split("\n")

        # 첫 줄 이후 내용 붙이기
        value_part = lines[0].split(":", 1)[1].strip() + "\n" + "\n".join(lines[1:])
        value_part = value_part.strip()

    # ':' 가 없는 라인인제 체크
    if not value_part:
        return True

    # ---------------------------
    # 공통 검사
    # ---------------------------

    # 첫번째 글자만 가져와서
    first_char = value_part[0]

    # 영어/숫자/한글 시작인지 검사
    if not re.match(r'[a-zA-Z0-9가-힣]', first_char):
        return True

    # ---------------------------
    # key별 추가 검사
    # ---------------------------
    # 버전은 무조건 0.2
    if key == "version":
        if value_part != "0.2":
            return True
    
    # 타임스탬프는 숫자만 허용
    elif key == "timestamp":
        if not value_part.isdigit():
            return True

        # 정확히 13자리만 허용
        if len(value_part) != 13:
            return True

    elif key == "prompt":
        # 손 포함 여부 검사 (멀티라인 전체 기준)
        if not any(hand in value_part for hand in ["왼손", "오른손", "양손"]):
            return True
        
        # 🔥 마지막 줄 기준으로 온점 검사
        lines = [l.strip() for l in value_part.split("\n") if l.strip()]

        if not lines:
            return True

        last_line = lines[-1]

        # 문장 끝 온점 검사
        if not last_line.endswith("."):
            return True
    
    # ID는 worker_숫자3자리만 허용
    elif key == "id":
        if not re.match(r'^worker_\d{3}$', value_part):
            return True

    # 설명은 male, female
    elif key == "gender":
        if value_part not in ("male", "female"):
            return True

    # 키는 1200 ~ 2200
    elif key == "height":
        if not value_part.isdigit():
            return True

        height = int(value_part)

        if height < 1200 or height > 2200:
            return True

    # 손은 left / right
    elif key == "main_hand":
        if value_part not in ("left", "right"):
            return True

    # 정상 문장
    return False


# ==================================================
# 하이라이터
# ==================================================
class ResultHighlighter(QSyntaxHighlighter):
    def __init__(self, document, app_instance, current_query="", current_key=""):
        super().__init__(document)
        self.app = app_instance
        self.current_query = current_query.strip()
        self.current_key = current_key

    def highlightBlock(self, text):
        if not text:
            return

        first_space = text.find(" ")

        if first_space > 0:
            self.setFormat(0, first_space, self.app.format_path())
            self.setFormat(first_space + 1, len(text), self.app.format_value())

        # 문제 라인 검사 (우선 적용)
        content = text[first_space + 1:] if first_space > 0 else text

        if is_problem_line(content, self.current_key):
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
            "hide_filename": True,
            "use_regex": False
        }

        self.load_options()

        # 루트 레이아웃
        root_layout = QVBoxLayout()

        # 메인 UI 컨테이너
        self.content_widget = QWidget()

        # 기존 layout
        layout = QVBoxLayout()

        # 경로
        top = QHBoxLayout()
        self.path_input = QLineEdit()

        btn_select_folder  = QPushButton("📁")
        btn_select_folder.setToolTip("루트 폴더를 선택합니다.")
        btn_select_folder .clicked.connect(self.select_folder)

        top.addWidget(QLabel("루트 경로"))
        top.addWidget(self.path_input)
        top.addWidget(btn_select_folder)

        layout.addLayout(top)

        # 검색
        search = QHBoxLayout()
        self.key_input = QLineEdit()

        btn_option = QPushButton("⚙️")
        btn_option.setToolTip("검색 옵션을 설정합니다.")  
        btn_option.clicked.connect(self.open_search_options)

        btn_search = QPushButton("🔎")
        btn_search.setToolTip("현재 경로에서 YAML 파일을 검색합니다.")
        btn_search.clicked.connect(self.run_scan)

        search.addWidget(QLabel("검색"))
        search.addWidget(self.key_input)
        search.addWidget(btn_search)
        search.addWidget(btn_option)

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
        self.content_widget.setLayout(layout)
        root_layout.addWidget(self.content_widget)
        self.setLayout(root_layout)

        self.default_keys = [
            "version", "timestamp", "episode_name", "domain",
            "collect_place", "collect_place_description",
            "collect_device", "zed_serial", "scenario",
            "task", "name", "prompt", "hand_visible",
            "tags", "id", "gender", "height", "main_hand"
        ]

        self._original_style = ""

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
        self.apply_dim_style() 

        dialog = SearchOptionsDialog(self, self.last_search_options)

        try:
            if dialog.exec():
                self.last_search_options = dialog.get_options()
                self.save_options()
                # self.run_scan()
        finally:
            self.clear_dim_style()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self)
        if folder:
            self.path_input.setText(folder)

    # ==================================================
    # grep 검색 유지
    # ==================================================
    def run_scan(self):
        root = self.path_input.text().strip()
        if not root:
            QMessageBox.warning(
                self,
                "경로 없음",
                "먼저 루트 경로를 선택해주세요."
            )
            return

        if not os.path.isdir(root):
            QMessageBox.warning(
                self,
                "잘못된 경로",
                "유효한 폴더 경로를 선택해주세요."
            )
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
                        collecting_tags = False
                        tag_block = []
                        
                        collecting_prompt = False
                        prompt_block = []

                        for line in file:
                            line = line.rstrip("\n")

                            # --------------------------
                            # prompt 블록 처리 시작
                            # --------------------------
                            if re.match(r'^\s*prompt\s*:', line):
                                collecting_prompt = True
                                prompt_block = [line]
                                continue

                            if collecting_prompt:
                                # 다음 key 나오면 종료
                                if re.match(r'^\s*\w+\s*:', line):
                                    results_default["prompt"].append((path, "\n".join(prompt_block)))
                                    collecting_prompt = False
                                    prompt_block = []
                                    # 여기서 continue 안 하면 현재 라인도 다시 처리됨
                                    # continue 하면 더 안전
                                    continue

                                prompt_block.append(line)
                                continue

                            # --------------------------
                            # tags
                            # --------------------------
                            # tag 블록 시작
                            if re.match(r'^\s*tags\s*:', line):
                                collecting_tags = True
                                tag_block = [line]
                                continue
                            
                            # tag 수집
                            if collecting_tags:
                                # 다음 key 나오면 종료
                                if re.match(r'^\s*\w+\s*:', line):
                                    results_default["tags"].append((path, "\n".join(tag_block)))
                                    collecting_tags = False
                                    tag_block = []
                                    continue

                                # 계속 수집
                                tag_block.append(line)
                                continue

                            # --------------------------
                            # 기존 key 처리
                            # --------------------------
                            for key in self.default_keys:
                                if key == "tags":
                                    continue  # tags는 따로 처리

                                if key == "task":
                                    if re.match(r'^\s*task\s*:', line):
                                        results_default[key].append((path, line))
                                        break
                                else:
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


                        if collecting_prompt:
                            results_default["prompt"].append((path, "\n".join(prompt_block)))
                            collecting_prompt = False
                            prompt_block = []

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
        # 결과 출력용 텍스트 위젯 생성
        text = QPlainTextEdit()
        text.setReadOnly(True)  # 읽기 전용
        text.setFont(QFont("Consolas", 11))  # 고정폭 폰트

        # 탭 추가
        self.tabs.addTab(text, title)

        # 라인 매핑 초기화
        self.line_maps[text] = {}

        lines = []  # 실제 UI에 출력할 문자열 리스트

        root = self.path_input.text().strip()
        depth = self.last_search_options["depth"]

        # --------------------------
        # 멀티라인 대응 라인 매핑
        # --------------------------
        display_line_index = 0  # 실제 화면 기준 라인 인덱스

        for path, line in data:
            hide_filename = self.last_search_options.get("hide_filename", False)

            # 경로 축약 처리
            short = process_path_display(path, root, depth, hide_filename)

            # 멀티라인 분리
            split_lines = line.split("\n")

            for j, sub_line in enumerate(split_lines):

                # 첫 줄은 경로 포함
                if j == 0:
                    full_line = f"{short} {sub_line}"
                else:
                    full_line = f"{sub_line}"
                    # path 길이 + 공백 1칸까지 포함해서 정렬
                    # indent = len(short) + 1
                    # full_line = f"{' ' * indent}{sub_line}"

                # 실제 출력 리스트에 추가
                lines.append(full_line)

                # 실제 표시되는 모든 라인에 path 매핑
                self.line_maps[text][display_line_index] = path
                display_line_index += 1  # 다음 라인으로 증가

        # 텍스트 한번에 출력
        text.setPlainText("\n".join(lines))

        # 하이라이터 적용
        text._highlighter = ResultHighlighter(
            text.document(),
            self,
            current_query=current_query,
            current_key=title
        )

        # 더블 클릭 이벤트 연결
        text.mouseDoubleClickEvent = lambda e, t=text: self.open_from_click(e, t)

    def open_from_click(self, event, text):
        cursor = text.cursorForPosition(event.position().toPoint())
        line = cursor.blockNumber()

        if line in self.line_maps[text]:
            open_file(self.line_maps[text][line])

    # ==================================================
    # 스타일
    # ==================================================
    def apply_dim_style(self):
        # 기존 스타일 저장
        if not self._original_style: #한번만 저장하기
            self._original_style = self.content_widget.styleSheet()

        # 메인창 어둡게
        self.content_widget.setStyleSheet("background-color: #d0d0d0;")


    def clear_dim_style(self):
        # 원래 스타일 복구
        self.content_widget.setStyleSheet(self._original_style)

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

     # Tooltip 스타일
    app.setStyleSheet("""
        QToolTip {
            background-color: #FFFFFF;
            color: #1A1A1A;
            border: 1px solid #A8D0F0;
            border-radius: 6px;
            padding: 3px 5px;
            font-size: 12px;
        }
    """)

    w = App()
    w.show()

    sys.exit(app.exec())