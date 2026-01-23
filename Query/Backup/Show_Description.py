import sys
import json
import pyperclip
import subprocess
from functools import lru_cache

# PyQt5 界面
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QTextEdit, QLineEdit, QLabel,
    QPushButton, QHBoxLayout
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

# --- Nord 主题（与 a.py 保持一致） ---
NORD_THEME = {
    'background': '#2E3440',
    'widget_bg': '#3B4252',
    'border': '#4C566A',
    'text_light': '#88C0D0',
    'text_bright': '#88C0D0',
    'accent_blue': '#5E81AC',
    'accent_cyan': '#88C0D0',
    'accent_red': '#BF616A',
    'accent_orange': '#D08770',
    'accent_yellow': '#EBCB8B',
    'pure_yellow': 'yellow',
    'accent_green': '#A3BE8C',
    'accent_deepgreen': '#607254',
    'accent_purple': '#B48EAD',
}

# ---------------- 公共函数 ----------------
def load_json_data(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)

def find_in_json(symbol, data):
    """在JSON数据中查找名称为symbol的股票或ETF"""
    # 若想更健壮：大小写无关匹配
    sym_upper = symbol.upper() if symbol else ""
    for item in data:
        if item.get('symbol', '').upper() == sym_upper:
            return item
    return None

def show_macos_dialog(message):
    try:
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except Exception:
        pass

# ---------------- PyQt5 对话框 ----------------
class InfoDialog(QDialog):
    def __init__(self, title, content, font_family='Arial Unicode MS', font_size=16, width=600, height=750, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)
        self._center_on_screen()
        layout = QVBoxLayout(self)

        text_box = QTextEdit(self)
        text_box.setReadOnly(True)
        text_box.setFont(QFont(font_family))
        text_box.setText(content)

        layout.addWidget(text_box)
        self.setLayout(layout)
        self._apply_nord_style(font_size)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _center_on_screen(self):
        # 兼容老 API：使用 availableGeometry
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            x = rect.x() + (rect.width() - self.width()) // 2
            y = rect.y() + (rect.height() - self.height()) // 2
            self.move(x, y)

    def _apply_nord_style(self, font_size):
        qss = f"""
        QDialog {{
            background-color: {NORD_THEME['background']};
        }}
        QTextEdit {{
            background-color: {NORD_THEME['widget_bg']};
            color: {NORD_THEME['text_bright']};
            border: 1px solid {NORD_THEME['border']};
            border-radius: 6px;
            font-size: {font_size}px;
            padding: 8px;
        }}
        QScrollBar:vertical {{
            border: none;
            background: {NORD_THEME['widget_bg']};
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {NORD_THEME['accent_blue']};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        """
        self.setStyleSheet(qss)

class InputDialog(QDialog):
    def __init__(self, prompt="请输入关键字查询数据库:", width=320, height=120, parent=None):
        super().__init__(parent)
        self.setWindowTitle(prompt)
        self.resize(width, height)
        self._center_on_screen()

        self.user_input = None

        # UI
        root_layout = QVBoxLayout(self)
        label = QLabel(prompt, self)
        label.setStyleSheet(f"color: {NORD_THEME['text_light']};")
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.entry = QLineEdit(self)
        self.entry.setPlaceholderText("输入股票/ETF 代码，例如: AAPL")
        self.entry.setFont(QFont('Helvetica', 16))
        self.entry.setMaxLength(40)

        # 从剪贴板填充
        try:
            clip = pyperclip.paste()
            if isinstance(clip, str):
                clip = clip.replace('"', '').replace("'", "")
                self.entry.setText(clip)
                self.entry.selectAll()
        except Exception:
            pass

        # Buttons
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("确定", self)
        cancel_btn = QPushButton("取消", self)

        ok_btn.clicked.connect(self._on_submit)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)

        root_layout.addWidget(label)
        root_layout.addWidget(self.entry)
        root_layout.addLayout(btn_row)
        self.setLayout(root_layout)

        self._apply_nord_style()

        # 交互
        self.entry.returnPressed.connect(self._on_submit)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def _on_submit(self):
        text = self.entry.text().strip().upper()
        self.user_input = text if text else None
        self.accept()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            x = rect.x() + (rect.width() - self.width()) // 2
            y = rect.y() + (rect.height() - self.height()) // 3  # 略靠上
            self.move(x, y)

    def _apply_nord_style(self):
        qss = f"""
        QDialog {{
            background-color: {NORD_THEME['background']};
        }}
        QLabel {{
            color: {NORD_THEME['text_bright']};
            font-size: 16px;
        }}
        QLineEdit {{
            background-color: {NORD_THEME['widget_bg']};
            color: {NORD_THEME['text_bright']};
            border: 1px solid {NORD_THEME['border']};
            border-radius: 6px;
            padding: 6px 10px;
        }}
        QPushButton {{
            background-color: {NORD_THEME['accent_blue']};
            color: {NORD_THEME['text_bright']};
            border: none;
            border-radius: 6px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background-color: {NORD_THEME['accent_cyan']};
        }}
        QPushButton:pressed {{
            background-color: {NORD_THEME['accent_purple']};
        }}
        """
        self.setStyleSheet(qss)

# ---------------- 业务函数 ----------------
def format_info_text(symbol, descriptions):
    name = descriptions.get('name', '')
    tag = descriptions.get('tag', '')
    desc1 = descriptions.get('description1', '')
    desc2 = descriptions.get('description2', '')
    info = f"{symbol}\n{name}\n\n{tag}\n\n{desc1}\n\n{desc2}"
    return info

@lru_cache(maxsize=1)
def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        # 统一默认字体
        app.setFont(QFont('Arial Unicode MS', 12))
    return app

def show_description_qt(symbol, descriptions):
    app = get_app()
    info_text = format_info_text(symbol, descriptions)
    dlg = InfoDialog("Descriptions", info_text, font_family='Arial Unicode MS', font_size=22, width=600, height=750)
    dlg.exec_()

def get_user_input_custom_qt(prompt):
    app = get_app()
    dlg = InputDialog(prompt=prompt, width=360, height=140)
    result = dlg.exec_()
    return dlg.user_input if result == QDialog.Accepted else None

# ---------------- 主入口 ----------------
if __name__ == '__main__':
    # 路径保持与原脚本一致
    json_path = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
    json_data = load_json_data(json_path)

    # 支持命令行参数：paste 或 input
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()

        if arg == "paste":
            # 从剪贴板读取、清洗并转大写
            symbol = pyperclip.paste()
            symbol = (symbol or "").replace('"', '').replace("'", "").upper()

            result = find_in_json(symbol, json_data.get('stocks', []))
            # 如果在stocks中没有找到，再在etfs中查找
            if not result:
                result = find_in_json(symbol, json_data.get('etfs', []))
            # 如果找到结果，显示信息
            if result:
                show_description_qt(symbol, result)
                sys.exit(0)  # 找到并显示
            else:
                sys.exit(1)  # 没找到，退出代码1

        elif arg == "input":
            prompt = "请输入关键字查询数据库:"
            user_input = get_user_input_custom_qt(prompt)
            if not user_input:
                sys.exit(0)

            result = find_in_json(user_input, json_data.get('stocks', []))
            # 如果在stocks中没有找到，再在etfs中查找
            if not result:
                result = find_in_json(user_input, json_data.get('etfs', []))
            # 如果找到结果，显示信息
            if result:
                show_description_qt(user_input, result)
                sys.exit(0)
            else:
                show_macos_dialog("未找到股票或ETF！")
                sys.exit(1)
        else:
            print("请提供参数 input 或 paste")
            sys.exit(1)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)