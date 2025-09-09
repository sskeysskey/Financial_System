import sys
import json
import os
import re
import pyperclip
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout,
    QLineEdit, QLabel, QCheckBox,
    QMessageBox, QDialogButtonBox
)
from PyQt5.QtCore import Qt
import subprocess

# --- 配置区 ---

# 请将这里替换为您 JSON 文件的实际路径
JSON_FILE_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json"

# 您指定要显示在第二个界面中的分组
TARGET_CATEGORIES = [
    "Today",
    "Watching",
    "Next Week",
    "2 Weeks",
    "3 Weeks"
]

def is_uppercase_letters(text: str) -> bool:
    return bool(re.match(r'^[A-Z]+$', text))

def copy2clipboard():
    script = '''
    set the clipboard to ""
    delay 0.3
    tell application "System Events"
        keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

class SymbolInputDialog(QDialog):
    """
    第一个界面：用于输入 Symbol 的对话框。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("第一步：输入 Symbol")
        self.setMinimumWidth(300)

        # 布局
        layout = QVBoxLayout(self)

        # 提示标签和输入框
        self.label = QLabel("请输入 Symbol:", self)
        self.symbol_input = QLineEdit(self)
        self.symbol_input.setPlaceholderText("例如：AAPL")

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        button_box.button(QDialogButtonBox.Ok).setText("确认")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")

        # 添加到布局
        layout.addWidget(self.label)
        layout.addWidget(self.symbol_input)
        layout.addWidget(button_box)

        # --- 信号与槽连接 ---
        # 1. 点击 "确认" 或 "取消" 按钮
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        # 2. 在输入框中按回车键
        self.symbol_input.returnPressed.connect(self.accept)

    def get_symbol(self):
        """获取输入框中的文本"""
        return self.symbol_input.text().strip()

    def keyPressEvent(self, event):
        """处理按键事件，实现 ESC 关闭"""
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class CategorySelectionDialog(QDialog):
    """
    第二个界面：用于选择分组的对话框。
    """
    def __init__(self, symbol, categories, parent=None):
        super().__init__(parent)
        self.setWindowTitle("第二步：选择分组")
        self.setMinimumWidth(300)

        # 布局
        layout = QVBoxLayout(self)

        # 提示标签
        self.label = QLabel(f"为 Symbol <b style='color:blue;'>{symbol}</b> 选择一个或多个分组:", self)
        layout.addWidget(self.label)

        # 复选框
        self.checkboxes = []
        for category in categories:
            checkbox = QCheckBox(category, self)
            self.checkboxes.append(checkbox)
            layout.addWidget(checkbox)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        button_box.button(QDialogButtonBox.Ok).setText("确认")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addWidget(button_box)

        # --- 信号与槽连接 ---
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def get_selected_categories(self):
        """获取所有被选中的复选框的文本"""
        return [cb.text() for cb in self.checkboxes if cb.isChecked()]

    def keyPressEvent(self, event):
        """处理按键事件，实现 ESC 关闭"""
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

def main():
    app = QApplication(sys.argv)

    # 1. 检查 JSON 文件是否存在
    if not os.path.exists(JSON_FILE_PATH):
        QMessageBox.critical(None, "错误", f"关键文件未找到，请检查路径：\n{JSON_FILE_PATH}")
        sys.exit(1)

    # 2. 确定 Symbol (来自命令行参数或弹窗)
    symbol = None
    # 检查是否有命令行参数 (sys.argv[0] 是脚本名, sys.argv[1] 是第一个参数)
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
        print(f"从命令行参数获取 Symbol: {symbol}")
    else:
        copy2clipboard()
        clipboard_content = pyperclip.paste().strip()

        if not clipboard_content or not is_uppercase_letters(clipboard_content):
            # 如果剪贴内容不合格或为空，弹出第一个对话框
            symbol_dialog = SymbolInputDialog()
            symbol_dialog.show()  # 先显示
            symbol_dialog.activateWindow()  # 然后激活
            symbol_dialog.raise_()  # 提升到前台
            # .exec_() 会阻塞程序，直到对话框关闭
            if symbol_dialog.exec_() == QDialog.Accepted:
                symbol = symbol_dialog.get_symbol()
                if not symbol:
                    QMessageBox.warning(None, "输入无效", "Symbol 不能为空，程序已终止。")
                    sys.exit(1)
            else:
                # 用户点击了取消或按了 ESC
                print("用户取消了操作。程序退出。")
                sys.exit(0)
        else:
            symbol = clipboard_content

    # 统一将 Symbol 转为大写
    symbol = symbol.upper()

    # 3. 选择分组
    category_dialog = CategorySelectionDialog(symbol, TARGET_CATEGORIES)
    category_dialog.show()
    category_dialog.activateWindow()
    category_dialog.raise_()
    selected_categories = []
    if category_dialog.exec_() == QDialog.Accepted:
        selected_categories = category_dialog.get_selected_categories()
        if not selected_categories:
            QMessageBox.warning(None, "选择无效", "您没有选择任何分组，程序已终止。")
            sys.exit(1)
    else:
        # 用户点击了取消或按了 ESC
        print("用户取消了操作。程序退出。")
        sys.exit(0)

    # 4. 更新 JSON 文件
    try:
        # 读取现有数据
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)

        # 更新数据
        update_count = 0
        for category in selected_categories:
            # 确保分组存在于 JSON 数据中
            if category in panel_data:
                # --- 这是修改的核心 ---
                # 创建一个新字典，将新 symbol 放在最前面，然后解包（**）旧的字典内容
                panel_data[category] = {symbol: "", **panel_data[category]}
                update_count += 1
            else:
                # 如果分组不存在，可以选择创建它或发出警告
                print(f"警告：分组 '{category}' 在 JSON 文件中不存在，已跳过。")

        # 如果有任何成功的更新，则写回文件
        if update_count > 0:
            with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
                # ensure_ascii=False 保证中文正常显示
                # indent=4 保持漂亮的格式
                json.dump(panel_data, f, ensure_ascii=False, indent=4)
            
            # 显示成功信息
            # QMessageBox.information(None, "操作成功",
            #     f"Symbol <b style='color:green;'>{symbol}</b> 已成功添加到以下分组：\n\n"
            #     f"<b>{', '.join(selected_categories)}</b>"
            # )
            print(f"成功将 '{symbol}' 添加到 {selected_categories}。")
        else:
            QMessageBox.warning(None, "无任何更改", "所有选定的分组在JSON文件中均不存在，文件未被修改。")


    except json.JSONDecodeError:
        QMessageBox.critical(None, "文件错误", f"无法解析 JSON 文件，请检查文件格式：\n{JSON_FILE_PATH}")
        sys.exit(1)
    except Exception as e:
        QMessageBox.critical(None, "未知错误", f"发生了一个意外错误：\n{e}")
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()