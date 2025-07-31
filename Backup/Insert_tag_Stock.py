import re
import json
import pyperclip
import sys
import subprocess
from PyQt5.QtWidgets import QApplication, QMainWindow, QLineEdit, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

def load_data(file_path):
    with open(file_path, encoding="utf-8") as file:
        return json.load(file)

def save_data(data, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def add_stock(name, new_tags, data):
    for stock in data["stocks"]:
        if stock["symbol"] == name:
            stock["tag"].extend(tag for tag in new_tags if tag not in stock["tag"])
            break

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    subprocess.run(['osascript', '-e', script])

def show_error_dialog():
    applescript_code = 'display dialog "不是有效的股票代码或股票代码不存在！" buttons {"OK"} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def validate_stock(name, data):
    return re.match("^[A-Z\-]+$", name) and any(stock['symbol'] == name for stock in data['stocks'])

class TagInputWindow(QMainWindow):
    def __init__(self, stock_name, data, json_file):
        super().__init__()
        self.stock_name = stock_name
        self.data = data
        self.json_file = json_file
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Add Tags')
        self.setGeometry(300, 300, 300, 100)

        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 创建输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入标签，用空格分隔")
        layout.addWidget(self.input_field)

        # 创建按钮
        submit_button = QPushButton('添加tag')
        submit_button.clicked.connect(self.on_submit)
        layout.addWidget(submit_button)

        # 设置快捷键
        self.input_field.returnPressed.connect(self.on_submit)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def on_submit(self):
        input_tags = self.input_field.text().split()
        add_stock(self.stock_name, input_tags, self.data)
        save_data(self.data, self.json_file)
        self.close()

def main():
    json_file = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"
    data = load_data(json_file)

    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        new_name = sys.argv[1].replace('"', '').replace("'", "")
    else:
        Copy_Command_C()
        new_name = pyperclip.paste().replace('"', '').replace("'", "")

    if not validate_stock(new_name, data):
        show_error_dialog()
        sys.exit(1)

    # 创建 PyQt 应用
    app = QApplication(sys.argv)
    window = TagInputWindow(new_name, data, json_file)
    window.show()
    window.activateWindow()
    window.raise_()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()