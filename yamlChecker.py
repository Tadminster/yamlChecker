import os
import sys
import platform
import subprocess
import re
import json

from pathlib import Path 
from datetime import datetime, timezone, timedelta

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLineEdit, QLabel,
    QFileDialog, QTabWidget, QSpinBox, QTextEdit,
    QDialog, QCheckBox, QFrame, QMessageBox
)

from PySide6.QtGui import (
    QColor, QTextCharFormat, QFont, QPalette, QSyntaxHighlighter,
    QTextCursor, QKeySequence, QAction,

)

from PySide6.QtCore import Qt, QEvent


class SearchableResultView(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)

        self.app = app
        # ---------------------------
        # 루트
        # ---------------------------
        # 검색 결과 뷰어
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)    # 읽기 전용

        # 탭 내 검색 바
        self.search_bar_widget = QWidget()

        # 검색 바용 가로 레이아웃 생성
        self.search_bar_layout = QHBoxLayout(self.search_bar_widget)

        # 검색 바 여백 제거
        self.search_bar_layout.setContentsMargins(0, 0, 0, 0)

        # ---------------------------
        # 탭 내 검색
        # ---------------------------
        self.search_label = QLabel("탭 내 찾기")
        self.search_label.setAlignment(Qt.AlignCenter)

        # 검색어 입력창
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("탭 내 검색 (Enter: 검색/다음, Shift+Enter: 이전, Esc: 닫기)")

        # current index/total index
        self.result_label = QLabel("0 / 0")

        # 이전 버튼 (prev)
        self.prev_button = QPushButton("◀")
        self.prev_button.setFixedWidth(60)
        self.prev_button.setToolTip("이전 검색 (Shift+Enter)")

        # 다음 버튼 (next)
        self.next_button = QPushButton("▶")
        self.next_button.setFixedWidth(60)
        self.next_button.setToolTip("다음 검색 (Enter)")

        self.prev_button.clicked.connect(self.find_previous)
        self.next_button.clicked.connect(self.find_next)

        # 검색 바 닫기 버튼
        self.close_button = QPushButton("X")
        self.close_button.setFixedWidth(28)
        self.close_button.setToolTip("탭 내 검색 닫기 (ESC)")

        btn_style = """
        QPushButton {
            background-color: #E6ECF5;
            border: 1px solid #BFC9DA;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #D6E4F5;
        }
        """

        self.prev_button.setStyleSheet(btn_style)
        self.next_button.setStyleSheet(btn_style)
        self.close_button.setStyleSheet(btn_style)

        # 검색 바 레이아웃에 위젯 추가
        self.search_bar_layout.addWidget(self.search_label)
        self.search_bar_layout.addWidget(self.search_input)
        self.search_bar_layout.addWidget(self.prev_button)
        self.search_bar_layout.addWidget(self.next_button)
        self.search_bar_layout.addWidget(self.result_label)
        self.search_bar_layout.addWidget(self.close_button)

        # 처음에는 검색 바를 숨김
        self.search_bar_widget.hide()

        # Ctrl+F 액션
        self.action_find = QAction(self)
        self.action_find.setShortcut(QKeySequence.Find)
        self.action_find.triggered.connect(self.show_search_bar)
        self.addAction(self.action_find)

        # ---------------------------
        # 메인 레이아웃
        # ---------------------------
        self.main_layout = QVBoxLayout(self)

        # 메인 레이아웃 여백 제거
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_layout.addWidget(self.text_edit)              # 검색 결과 뷰어
        self.main_layout.addWidget(self.search_bar_widget)      # 탭내 검색 바

        # 검색 결과 위치 목록 저장용 리스트
        self.match_positions = []

        # 현재 선택된 검색 결과 인덱스
        self.current_match_index = -1

        # 마지막으로 실제 검색에 사용된 검색어
        self.current_query = ""

        # 닫기 버튼 클릭 시 검색 바 숨김
        self.close_button.clicked.connect(self.hide_search_bar)

        # 검색 입력창 키 이벤트 처리를 위해 이벤트 필터 설치
        self.search_input.installEventFilter(self)

    def setPlainText(self, text: str):
        # 외부에서 결과 문자열을 설정하는 함수
        self.text_edit.setPlainText(text)

        # 텍스트가 바뀌면 검색 상태 초기화
        self.clear_search_state()

    def toPlainText(self) -> str:
        # 현재 텍스트 내용을 반환하는 함수
        return self.text_edit.toPlainText()

    def show_search_bar(self):
        # 검색 바를 표시
        self.search_bar_widget.show()

        # 검색 입력창에 포커스 이동
        self.search_input.setFocus()

        # 기존 입력값이 있다면 전체 선택
        self.search_input.selectAll()

    def hide_search_bar(self):
        # 검색 바 숨김
        self.search_bar_widget.hide()

        # 전체 하이라이트 제거
        self.text_edit.setExtraSelections([])

        # 현재 선택 영역 제거
        cursor = self.text_edit.textCursor()
        cursor.clearSelection()
        self.text_edit.setTextCursor(cursor)

        # 결과 텍스트 쪽으로 포커스 복귀
        self.text_edit.setFocus()
        self.text_edit.activateWindow()

    def clear_search_state(self):
        # 검색 결과 위치 목록 초기화
        self.match_positions = []

        # 현재 검색 결과 인덱스 초기화
        self.current_match_index = -1

        # 현재 검색어 초기화
        self.current_query = ""

        # 결과 라벨 초기화
        self.result_label.setText("0 / 0")

        # 전체 하이라이트 제거
        self.text_edit.setExtraSelections([])

    def rebuild_matches(self, query: str):
        # 기존 검색 결과 목록 초기화
        self.match_positions = []

        # 검색어가 비어 있으면 상태만 갱신 후 종료
        if not query:
            self.current_query = ""
            self.current_match_index = -1
            self.result_label.setText("0 / 0")
            self.text_edit.setExtraSelections([])
            return

        # 전체 텍스트 가져오기
        full_text = self.text_edit.toPlainText()

        # 대소문자 무시 검색을 위해 소문자로 변환한 전체 텍스트
        lower_text = full_text.lower()

        # 대소문자 무시 검색을 위해 소문자로 변환한 검색어
        lower_query = query.lower()

        # 검색 시작 위치
        start = 0

        # 실제 선택 범위 계산을 위한 검색어 길이
        query_len = len(query)

        # 전체 문서에서 검색어를 모두 찾을 때까지 반복
        while True:
            # 현재 시작 위치 이후에서 검색어 위치 찾기
            index = lower_text.find(lower_query, start)

            # 더 이상 검색 결과가 없으면 반복 종료
            if index == -1:
                break

            # 검색 결과 시작/끝 위치 저장
            self.match_positions.append((index, index + query_len))

            # 다음 검색 시작 위치 갱신
            start = index + query_len

        # 실제 검색에 사용된 검색어 저장
        self.current_query = query

        # 검색 결과가 있으면 첫 번째 결과 인덱스로 준비
        if self.match_positions:
            self.current_match_index = 0
            self.result_label.setText(f"1 / {len(self.match_positions)}")
        else:
            self.current_match_index = -1
            self.result_label.setText("0 / 0")

        # 전체 하이라이트 갱신
        self.update_highlight_selections()

    def move_to_match(self, match_index: int):
        # 검색 결과가 없으면 종료
        if not self.match_positions:
            self.result_label.setText("0 / 0")
            return

        # 현재 인덱스의 검색 결과 범위 가져오기
        start, end = self.match_positions[match_index]

        # 현재 커서 가져오기
        cursor = self.text_edit.textCursor()

        # 검색 결과 시작 위치로 이동
        cursor.setPosition(start)

        # 검색 결과 끝까지 선택
        cursor.setPosition(end, QTextCursor.KeepAnchor)

        # 에디터에 커서 반영
        self.text_edit.setTextCursor(cursor)

        # 현재 결과가 화면 중앙에 오도록 스크롤 이동
        self.text_edit.centerCursor()

        # 결과 라벨 갱신
        self.result_label.setText(f"{match_index + 1} / {len(self.match_positions)}")

        # 전체 하이라이트 갱신
        self.update_highlight_selections()

    def update_highlight_selections(self):
        # 하이라이트 목록 저장용 리스트
        selections = []

        # 검색 결과가 없으면 하이라이트 제거 후 종료
        if not self.match_positions:
            self.text_edit.setExtraSelections([])
            return

        # 모든 검색 결과에 대해 하이라이트 생성
        for i, (start, end) in enumerate(self.match_positions):
            # 각 검색 결과 범위용 커서 생성
            cursor = self.text_edit.textCursor()

            # 검색 결과 시작 위치로 이동
            cursor.setPosition(start)

            # 검색 결과 끝 위치까지 선택
            cursor.setPosition(end, QTextCursor.KeepAnchor)

            # 추가 선택 영역 객체 생성
            selection = QTextEdit.ExtraSelection()

            # 선택 영역 커서 지정
            selection.cursor = cursor

            # 하이라이트 포맷 생성
            fmt = QTextCharFormat()

            # 현재 선택된 결과는 더 진한 색
            if i == self.current_match_index:
                fmt.setBackground(QColor("#FFD54F"))

            # 나머지 결과는 더 연한 색
            else:
                fmt.setBackground(QColor("#FFF59D"))

            # 포맷 적용
            selection.format = fmt

            # 선택 목록에 추가
            selections.append(selection)

        # 전체 하이라이트 반영
        self.text_edit.setExtraSelections(selections)

    def execute_search_or_next(self):
        # 입력창의 현재 검색어를 앞뒤 공백 제거해서 가져오기
        query = self.search_input.text().strip()

        # 비어 있으면 검색 안 함
        if not query:
            self.clear_search_state()
            return

        # 아직 검색한 적이 없거나 검색어가 이전과 달라졌으면 새 검색 수행
        if query != self.current_query:
            self.rebuild_matches(query)

            # 검색 결과가 있으면 첫 번째 결과로 이동
            if self.match_positions:
                self.move_to_match(self.current_match_index)

            return

        # 검색어가 같으면 다음 결과로 이동
        self.find_next()

    def execute_search_or_previous(self):
        # 입력창의 현재 검색어를 앞뒤 공백 제거해서 가져오기
        query = self.search_input.text().strip()

        # 비어 있으면 검색 안 함
        if not query:
            self.clear_search_state()
            return

        # 아직 검색한 적이 없거나 검색어가 이전과 달라졌으면 새 검색 수행
        if query != self.current_query:
            self.rebuild_matches(query)

            # 검색 결과가 있으면 마지막 결과로 이동하고 싶다면 여기서 마지막으로 변경 가능
            # 현재는 첫 번째 결과로 맞춤
            if self.match_positions:
                self.move_to_match(self.current_match_index)

            return

        # 검색어가 같으면 이전 결과로 이동
        self.find_previous()

    def find_next(self):
        # 검색 결과가 없으면 종료
        if not self.match_positions:
            self.result_label.setText("0 / 0")
            return

        # 아직 선택된 결과가 없으면 첫 번째 결과 선택
        if self.current_match_index == -1:
            self.current_match_index = 0
        else:
            # 다음 결과로 이동, 끝이면 처음으로 순환
            self.current_match_index = (self.current_match_index + 1) % len(self.match_positions)

        # 해당 결과 위치로 이동
        self.move_to_match(self.current_match_index)

    def find_previous(self):
        # 검색 결과가 없으면 종료
        if not self.match_positions:
            self.result_label.setText("0 / 0")
            return

        # 아직 선택된 결과가 없으면 마지막 결과 선택
        if self.current_match_index == -1:
            self.current_match_index = len(self.match_positions) - 1
        else:
            # 이전 결과로 이동, 처음보다 앞이면 마지막으로 순환
            self.current_match_index = (self.current_match_index - 1) % len(self.match_positions)

        # 해당 결과 위치로 이동
        self.move_to_match(self.current_match_index)

    def eventFilter(self, obj, event):
        # 검색 입력창에서 발생한 키 이벤트만 처리
        if obj == self.search_input and event.type() == QEvent.KeyPress:
            # 눌린 키 코드 가져오기
            key = event.key()

            focus_widget = QApplication.focusWidget()
            # print(f"[KEY] key={key}, focus={type(focus_widget)}")

            # 현재 보조키 상태 가져오기
            modifiers = event.modifiers()

            # Shift + Enter면 이전 검색 결과 또는 검색 실행
            if key in (Qt.Key_Return, Qt.Key_Enter) and (modifiers & Qt.ShiftModifier):
                self.execute_search_or_previous()
                return True

            # Enter면 검색 실행 또는 다음 검색 결과 이동
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.execute_search_or_next()
                return True

            # Esc면 검색 바 닫기
            if key == Qt.Key_Escape:
                self.hide_search_bar()
                return True
            

        # 나머지 이벤트는 기본 처리로 넘김
        return super().eventFilter(obj, event)


    # 컨트롤 클릭 이벤트
    def ctrl_click_debug(self, event):
        if not (event.modifiers() & Qt.ControlModifier):
            return False

        cursor = self.text_edit.cursorForPosition(event.position().toPoint())
        
        block = cursor.block()
        line_text = block.text()

        # timestamp만 처리
        if "timestamp:" not in line_text:
            return False

        self.print_timestamp_debug(block, line_text)

        return True

    def print_timestamp_debug(self, block, line_text):
        try:
            match = re.search(r'timestamp:\s*(\d+)', line_text)
            if not match:
                print("[DEBUG] timestamp 파싱 실패")
                return

            ts = int(match.group(1))

            # 현재 라인의 파일 경로
            block_number = block.blockNumber()
            path = self.app.line_maps.get(self.text_edit, {}).get(block_number)

            if not path or not os.path.exists(path):
                print("[DEBUG] 파일 경로 없음:", path)
                return

            # -----------------------------
            # YAML 파일 읽기
            # -----------------------------
            episode_time_str = extract_episode_time_from_yaml(path)

            if not episode_time_str:
                print("[DEBUG] episode_name에서 시간 추출 실패")
                return

            # -----------------------------
            # timestamp 계산
            # -----------------------------
            expected = kst_to_timestamp_ms(episode_time_str)
            diff = ts - expected

            minutes = abs(diff) // 60000
            seconds = (abs(diff) % 60000) / 1000
            sign = "+" if diff >= 0 else "-"


            label_width = 8

            print(f"""
            [Timestamp Debug]
            ----------------------------------------
            {"파일":<{label_width}} : {path}
            {"촬영시작":<{label_width-2}} : {episode_time_str}

            {"기준(ms)":<{label_width}} : {expected}
            {"현재(ms)":<{label_width}} : {ts}

            {"차이":<{label_width}} : {diff} ms ({sign} {int(minutes)}분 {seconds:.3f}초)
            ----------------------------------------
            """)

        except Exception as e:
            print(f"[DEBUG ERROR] {e}")


def extract_episode_time_from_yaml(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line.startswith("episode_name:"):
                    continue

                value = line.split(":", 1)[1].strip()

                # episode_name 안에서 YYMMDD_HHMMSS 패턴 직접 찾기
                match = re.search(r'(\d{6})_(\d{6})', value)
                if not match:
                    return None

                date_part = match.group(1)
                time_part = match.group(2)

                return f"{date_part}_{time_part}"

    except Exception as e:
        print(f"[DEBUG ERROR] episode_name 읽기 실패: {e}")

    return None



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
# 시간 문자열 -> KST Unix Timestamp(ms)
# ==================================================
def kst_to_timestamp_ms(date_str: str) -> int:
    # "260112_135500" 형식 문자열을 datetime으로 변환
    dt = datetime.strptime(date_str, "%y%m%d_%H%M%S")

    # KST 시간대 객체 생성 (UTC+9)
    kst = timezone(timedelta(hours=9))

    # 파싱한 datetime에 KST 시간대 지정
    dt = dt.replace(tzinfo=kst)

    # Unix Timestamp를 초 단위로 구한 뒤 밀리초로 변환
    return int(dt.timestamp() * 1000)


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
        self.depth_spin.setMinimum(3)
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
        # Timestamp 범위 옵션
        # -----------------------------
        ts_layout = QHBoxLayout()

        ts_label = QLabel("Timestamp 허용 범위(분)")

        self.ts_range_spin = QSpinBox()
        self.ts_range_spin.setMinimum(1)
        self.ts_range_spin.setMaximum(60)  # 최대 10시간 정도
        self.ts_range_spin.setValue(
            init_options.get("timestamp_range_ms", 3600000) // 60000
        )

        ts_layout.addWidget(ts_label)
        ts_layout.addStretch()
        ts_layout.addWidget(self.ts_range_spin)

        layout.addLayout(ts_layout)


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
            "use_regex": self.regex_checkbox.isChecked(),
            "timestamp_range_ms": self.ts_range_spin.value() * 60000
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
def is_problem_line(line: str, key: str, path: str = None, app=None) -> bool:
    """
    @return True: 문제 있는 라인
    @return False: 정상 라인
    """

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
    # 멀티라인 대응
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
        
        # ---------------------------
        # 폴더명 기반 검증
        # ---------------------------
        if path:
            try:
                # 전체 경로에서 시간 패턴 찾기
                match = re.search(r'(\d{6})_(\d{6})', path)

                if match:
                    date_part = match.group(1)
                    time_part = match.group(2)

                    time_str = f"{date_part}_{time_part}"


                    ts = int(value_part)
                    expected = kst_to_timestamp_ms(time_str)

                        
                    # ---------------------------
                    # 디버그 로그
                    # ---------------------------

                    # diff = ts - expected
                    # # ms → 분/초 변환
                    # minutes = abs(diff) // 60000
                    # seconds = (abs(diff) % 60000) / 1000

                    # print(
                    #     f"""
                    # [Timestamp Debug]
                    # ----------------------------------------
                    # 폴더명     : {folder}
                    # 촬영 시작  : {time_str}

                    # 기준(ms)   : {expected}
                    # 현재(ms)   : {ts}

                    # 차이       : {diff} ms (약 {int(minutes)}분 {seconds:.3f}초)
                    # ----------------------------------------
                    # """
                    # )

                    # 타임 스탬프 허용범위 get
                    max_range = 3600000

                    if app:
                        max_range = app.last_search_options.get("timestamp_range_ms", 3600000)

                    # ---------------------------
                    # 범위 기반 검증
                    # ---------------------------
                    # 시작 시간보다 과거면 오류
                    if ts < expected:
                        return True

                    # 너무 미래면 오류 (1시간 이상)
                    if ts > expected + max_range:
                        return True

            except:
                return True
        
    elif key == "episode_name":
        # _를 기준으로 문자열 분리
        episode_parts  = value_part.split('_')

        # 분리된 문자열이 5개인지 확인
        if len(episode_parts) != 5:
            return True  # 개수 틀리면 실패

        # 마지막 요소 (timestamp)
        last_part = episode_parts[-1]  
        # 17자리 숫자인지 확인
        if not (last_part.isdigit() and len(last_part) == 13):
            return True  # 숫자 아니거나 길이 다르면 실패

    elif key == "prompt":
        # 손 포함 여부 검사 (멀티라인 전체 기준)
        if not any(hand in value_part for hand in ["왼손", "오른손", "양손"]):
            return True
        
        # 마지막 줄 기준으로 온점 검사
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


# def get_problem_reason(line: str, key: str, path: str = None) -> str:
#     parts = line.split(":", 1)

#     if len(parts) < 2:
#         return "':' 구분자가 없습니다."

#     value_part = parts[1].strip()

#     if not value_part:
#         return "값이 비어있습니다."

#     first_char = value_part[0]
#     if not re.match(r'[a-zA-Z0-9가-힣]', first_char):
#         return "값이 잘못된 문자로 시작합니다."

#     # ---------------------------
#     # key별 검사
#     # ---------------------------

#     if key == "version":
#         if value_part != "0.2":
#             return "version은 반드시 0.2여야 합니다."

#     elif key == "timestamp":
#         if not value_part.isdigit():
#             return "timestamp는 숫자만 가능합니다."

#         if len(value_part) != 13:
#             return "timestamp는 13자리(ms)여야 합니다."

#         if path:
#             try:
#                 folder = path.replace("\\", "/").split("/")[-2]
#                 parts = folder.split("_")

#                 if len(parts) >= 2:
#                     date_part = parts[-2]
#                     time_part = parts[-1]

#                     time_str = f"{date_part}_{time_part}"

#                     ts = int(value_part)
#                     expected = kst_to_timestamp_ms(time_str)

#                     diff = ts - expected

#                     if ts < expected:
#                         return "촬영 시작 시간보다 이전입니다."

#                     if ts > expected + 3600000:
#                         return "촬영 시작 기준 1시간을 초과했습니다."

#                     # 정상인데도 tooltip 띄우고 싶으면
#                     return None

#             except:
#                 return "timestamp 파싱 실패"

#     elif key == "id":
#         if not re.match(r'^worker_\d{3}$', value_part):
#             return "id는 worker_000 형식이어야 합니다."

#     elif key == "gender":
#         if value_part not in ("male", "female"):
#             return "gender는 male 또는 female만 허용됩니다."

#     elif key == "height":
#         if not value_part.isdigit():
#             return "height는 숫자여야 합니다."

#         h = int(value_part)
#         if h < 1200 or h > 2200:
#             return "height는 1200~2200 범위여야 합니다."

#     elif key == "main_hand":
#         if value_part not in ("left", "right"):
#             return "main_hand는 left 또는 right만 허용됩니다."

#     return None

# ==================================================
# 하이라이터
# ==================================================
class ResultHighlighter(QSyntaxHighlighter):
    def __init__(self, document, app_instance, current_query="", current_key="", is_user_tab=False):
        super().__init__(document)
        self.app = app_instance                         # App 인스턴스 (format 함수 접근용)
        self.current_query = current_query.strip()      # 현재 검색어
        self.current_key = current_key                  # 현재 탭 key
        self.is_user_tab = is_user_tab                  # 유저탭 여부

    def highlightBlock(self, text):
        if not text:
            return

        # -----------------------------------
        # 사용자 입력 탭 전용 (검색어만 하이라이트)
        # -----------------------------------
        if self.is_user_tab:
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

            return


        # -----------------------------
        # 경로 / 값 분리
        # ----------------------------
        first_space = text.find(" ")

        # 경로 부분 스타일
        if first_space > 0:
            self.setFormat(0, first_space, self.app.format_path())
            self.setFormat(first_space + 1, len(text), self.app.format_value())

        # 실제 검사 대상 문자열
        content = text[first_space + 1:] if first_space > 0 else text

        # -----------------------------
        # hand_visible 처리
        # -----------------------------
        if self.current_key == "hand_visible":
            parts = content.split(":", 1)

            if len(parts) >= 2:
                key_name = parts[0].strip()
                raw_value = parts[1]
                value = raw_value.strip().lower()

                content_start = first_space + 1 if first_space > 0 else 0

                # 키 컬러 적용을 위한 텍스트
                target = "hand_visible"

                # key_name 안에서 "hand_visible" 위치 찾기
                hv_offset = key_name.find(target)

                if hv_offset != -1:
                    # content 기준 위치 계산
                    key_offset = content.find(key_name)

                    # 최종 위치 = key 시작 + hand_visible 위치
                    hv_pos = content_start + key_offset + hv_offset

                    self.setFormat(
                        hv_pos,
                        len(target),
                        self.app.format_key()
                    )
                
                # value 계산
                value_offset = content.find(raw_value) + raw_value.find(value)
                value_pos = content_start + value_offset

                # value 컬러 적용
                if value == "true":
                    self.setFormat(
                        value_pos, 
                        len(value), 
                        self.app.format_font("#2E8B57", True)
                    )
                elif value == "false":
                    self.setFormat(
                        value_pos, 
                        len(value), 
                        self.app.format_font("#E74C3C", True)
                    )

                return

        # -----------------------------
        # 문제 라인 검사
        # -----------------------------

        # path 추출
        path_part = text[:first_space] if first_space > 0 else None

        if is_problem_line(content, self.current_key, path_part, self.app):
            self.setFormat(
                first_space + 1 if first_space > 0 else 0,
                len(content),
                self.app.format_empty()
            )
            return

        # -----------------------------
        # 검색어 하이라이트
        # -----------------------------
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
            "use_regex": False,
            "timestamp_range_ms": 3600000
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

        # 전역 키 입력 감지
        # self.installEventFilter(self)


        self.default_keys = [
            "version", "timestamp", "episode_name", "domain",
            "collect_place", #"collect_place_description",
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

        results_user = []

        # 사용자 입력 검색어 처리
        if user_query:
            try:
                cmd = [
                    "grep",
                    "-rP" if use_regex else "-rF",
                    "--include=*.yaml",
                    user_query,
                    root
                ]

                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8"
                )

                grep_lines = result.stdout.splitlines()

                for line in grep_lines:
                    try:
                        path, content = line.split(":", 1)
                    except ValueError:
                        continue

                    results_user.append((path, content))

            except Exception as e:
                print(e)

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
                            # hand_visible
                            # --------------------------
                            if re.match(r'^\s*is_(left|right)_hand_visible\s*:', line):
                                results_default["hand_visible"].append((path, line))
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
                                if re.match(r'^\s*[a-zA-Z_]+\s*:', line):
                                    results_default["tags"].append((path, "\n".join(tag_block)))
                                    collecting_tags = False
                                    tag_block = []
                                    # continue
                                else:
                                # 계속 수집
                                    tag_block.append(line)
                                    continue

                            # --------------------------
                            # prompt
                            # --------------------------
                            if re.match(r'^\s*prompt\s*:', line):
                                collecting_prompt = True
                                prompt_block = [line]
                                continue

                            if collecting_prompt:
                                # 다음 key 나오면 종료
                                if re.match(r'^\s*(-\s*)?[a-zA-Z_]+\s*:', line):
                                    results_default["prompt"].append((path, "\n".join(prompt_block)))
                                    collecting_prompt = False
                                    prompt_block = []

                                    # 라인 다시 재처리 방지
                                    # continue
                                else:
                                    prompt_block.append(line)
                                    continue


                            # --------------------------
                            # 기존 key 처리
                            # --------------------------
                            for key in self.default_keys:
                                # tags, hand_visible은 따로 처리
                                if key in ["tags", "hand_visible"]:
                                     continue
                                
                                if key == "name":
                                    if re.match(r'^\s*(-\s*)?name\s*:', line):
                                        results_default[key].append((path, line))
                                    continue

                                if key == "id":
                                    if "id" in line:
                                        results_default[key].append((path, line))
                                    continue
                                
                                if key == "task":
                                    if re.match(r'^\s*task\s*:', line):
                                        results_default[key].append((path, line))
                                    continue

                                if key in line:
                                    results_default[key].append((path, line))

                        if collecting_prompt:
                            results_default["prompt"].append((path, "\n".join(prompt_block)))
                            collecting_prompt = False
                            prompt_block = []

                        if collecting_tags:
                            results_default["tags"].append((path, "\n".join(tag_block)))

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
        # 검색 가능한 결과 뷰 위젯 생성
        view = SearchableResultView(self)

        # 내부 텍스트 에디터에 폰트 적용
        view.text_edit.setFont(QFont("Consolas", 11))
        

        # 탭에 SearchableResultView 자체를 추가
        self.tabs.addTab(view, title)

        # 라인 매핑은 내부 text_edit 기준으로 관리
        self.line_maps[view.text_edit] = {}

        lines = []

        root = self.path_input.text().strip()
        depth = self.last_search_options["depth"]

        # 실제 화면 기준 라인 인덱스
        display_line_index = 0
        # 이전 파일명 기록용
        prev_path = None 


        # -----------------------------------
        # 사용자 입력 탭 분기
        # -----------------------------------
        user_query = self.key_input.text().strip()

        if title == user_query and user_query:
            for path, line in data:
                full_line = f"{path}:{line}"
                lines.append(full_line)

                self.line_maps[view.text_edit][display_line_index] = path
                display_line_index += 1

            view.setPlainText("\n".join(lines))

            view.text_edit._highlighter = ResultHighlighter(
                view.text_edit.document(),
                self,
                current_query=current_query,
                current_key="",
                is_user_tab=True
            )

            view.text_edit.mouseDoubleClickEvent = (
                lambda e, t=view.text_edit: self.open_from_click(e, t)
            )

            return


        # -----------------------------------
        # default key 분기
        # -----------------------------------
        for path, line in data:
            hide_filename = self.last_search_options.get("hide_filename", False)

            # 경로 축약 처리
            short = process_path_display(path, root, depth, hide_filename)

            # hand_visible
            if title == "hand_visible" and prev_path is not None and prev_path != path:
                # 파일 바뀔 때 구분용 빈 라인 한 줄 추가
                separator = ""
                lines.append(separator)

                # line_map 맞춰주기
                self.line_maps[view.text_edit][display_line_index] = path
                display_line_index += 1

            # 멀티라인 분리
            split_lines = line.split("\n")

            for j, sub_line in enumerate(split_lines):
                # 첫 줄은 경로 포함
                if j == 0:
                    full_line = f"{short} {sub_line}"
                else:
                    full_line = f"{sub_line}"

                # 실제 출력 리스트에 추가
                lines.append(full_line)

                # 내부 text_edit 기준으로 path 매핑
                self.line_maps[view.text_edit][display_line_index] = path
                display_line_index += 1


            prev_path = path

        # SearchableResultView의 setPlainText 사용
        view.setPlainText("\n".join(lines))

        user_query = self.key_input.text().strip()

        # 하이라이터는 내부 text_edit.document() 에 적용
        view.text_edit._highlighter = ResultHighlighter(
            view.text_edit.document(),
            self,
            current_query=current_query,
            current_key=title,
            is_user_tab=(title == user_query and user_query != "")
        )

        # 마우스 입력 핸들러
        def mouse_press_handler(e, t=view.text_edit, v=view):
            # Ctrl 클릭이면 tooltip
            if v.ctrl_click_debug(e):
                return

            # 일반 클릭은 기본 동작 유지
            QPlainTextEdit.mousePressEvent(t, e)

        view.text_edit.mousePressEvent = mouse_press_handler

        # 더블 클릭 이벤트 연결
        view.text_edit.mouseDoubleClickEvent = (
            lambda e, t=view.text_edit: self.open_from_click(e, t)
        )


    def open_from_click(self, event, text):
        cursor = text.cursorForPosition(event.position().toPoint())
        line = cursor.blockNumber()

        if line in self.line_maps[text]:
            open_file(self.line_maps[text][line])

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and isinstance(obj, QPlainTextEdit):

            key = event.key()
            focus_widget = QApplication.focusWidget()

            # print(f"[KEY] key={key}, focus={type(focus_widget)}")

            # ----------------------
            # 좌우 탭이동
            # ----------------------
            if key == Qt.Key_Left:
                current = self.tabs.currentIndex()
                if current > 0:
                    self.tabs.setCurrentIndex(current - 1)
                return True

            elif key == Qt.Key_Right:
                current = self.tabs.currentIndex()
                if current < self.tabs.count() - 1:
                    self.tabs.setCurrentIndex(current + 1)
                return True

            # ----------------------
            # 상하 스크롤
            # ----------------------
            elif key == Qt.Key_Up or key == Qt.Key_Down:

                scrollbar = obj.verticalScrollBar()

                # 한번에 스크롤 될 값 계산
                base = obj.fontMetrics().height()
                step = max(1, base // 4)

                if key == Qt.Key_Up:
                    scrollbar.setValue(scrollbar.value() - step)
                else:
                    scrollbar.setValue(scrollbar.value() + step)

                return True

        return super().eventFilter(obj, event)

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
    
    def format_font(self, color: str, bold: bool = False):
        f = QTextCharFormat()                 # 텍스트 스타일 객체
        
        # 색상 적용
        f.setForeground(QColor(color))        

        # bold 적용
        if bold:                              
            f.setFontWeight(QFont.Bold)

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