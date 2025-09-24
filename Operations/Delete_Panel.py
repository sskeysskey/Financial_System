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

# --- 以下函数未做修改 ---

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
    # 增加一个 try-except 块以防止 osascript 出错时程序崩溃
    try:
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"执行 AppleScript 失败: {e}")
        # 在GUI程序中，最好用弹窗提示
        # QMessageBox.warning(None, "剪贴板操作失败", "无法自动复制内容，请手动输入。")


class SymbolInputDialog(QDialog):
    """
    第一个界面：用于输入 Symbol 的对话框。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("第一步：输入要删除的 Symbol") # 修改了标题以符合新功能
        self.setMinimumWidth(300)

        # 布局
        layout = QVBoxLayout(self)

        # 提示标签和输入框
        self.label = QLabel("请输入要删除的 Symbol:", self)
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
    第二个界面：用于选择分组的对话框。(大部分结构复用，但用途改变)
    """
    # --- 修改：调整了标题和提示信息以符合删除操作 ---
    def __init__(self, symbol, categories_found, parent=None):
        super().__init__(parent)
        self.setWindowTitle("第二步：选择要删除的分组")
        self.setMinimumWidth(300)

        # 布局
        layout = QVBoxLayout(self)
        # 修改提示语，使用红色突出显示要删除的 Symbol
        self.label = QLabel(f"Symbol <b style='color:red;'>{symbol}</b> 存在于以下分组，<br>请选择要将其删除的位置:", self)
        layout.addWidget(self.label)

        # 复选框
        self.checkboxes = []
        for category in categories_found:
            checkbox = QCheckBox(category, self)
            checkbox.setChecked(True)  # 设置复选框默认为选中状态
            self.checkboxes.append(checkbox)
            layout.addWidget(checkbox)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        button_box.button(QDialogButtonBox.Ok).setText("确认删除") # 修改按钮文本
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

    # 2. 确定 Symbol (逻辑不变，但对话框标题已修改)
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

    # --- 核心修改点 ---
    # 3. 读取 JSON 数据并搜索 Symbol 所在的分组
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)
    except json.JSONDecodeError:
        QMessageBox.critical(None, "文件错误", f"无法解析 JSON 文件，请检查文件格式：\n{JSON_FILE_PATH}")
        sys.exit(1)
    except Exception as e:
        QMessageBox.critical(None, "文件读取错误", f"读取文件时发生意外错误：\n{e}")
        sys.exit(1)

    # 查找包含该 symbol 的所有分组
    found_in_categories = []
    for category, symbols_dict in panel_data.items():
        # 确保分组的值是一个字典
        if isinstance(symbols_dict, dict) and symbol in symbols_dict:
            found_in_categories.append(category)

    # 如果任何分组中都未找到该 symbol，则提示并退出
    if not found_in_categories:
        QMessageBox.information(None, "未找到", f"在所有分组中均未找到 Symbol <b style='color:blue;'>{symbol}</b>，程序已终止。")
        sys.exit(0)

    # 4. 弹出选择对话框，让用户选择要从哪些分组中删除
    category_dialog = CategorySelectionDialog(symbol, found_in_categories)
    category_dialog.show()
    category_dialog.activateWindow()
    category_dialog.raise_()
    
    categories_to_delete_from = []
    if category_dialog.exec_() == QDialog.Accepted:
        categories_to_delete_from = category_dialog.get_selected_categories()
        if not categories_to_delete_from:
            QMessageBox.warning(None, "选择无效", "您没有选择任何分组进行删除，程序已终止。")
            sys.exit(1)
    else:
        # 用户点击了取消或按了 ESC
        print("用户取消了操作。程序退出。")
        sys.exit(0)

    # 5. 执行删除操作并更新 JSON 文件
    try:
        delete_count = 0
        for category in categories_to_delete_from:
            # 再次确认分组和 symbol 存在，然后删除
            if category in panel_data and symbol in panel_data[category]:
                del panel_data[category][symbol]
                delete_count += 1

        # 如果有任何成功的删除，则写回文件
        if delete_count > 0:
            with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(panel_data, f, ensure_ascii=False, indent=4)
            
            # 使用 print 替代 QMessageBox 以快速退出
            print(f"成功从分组 {categories_to_delete_from} 中删除了 '{symbol}'。")
        else:
            # 这个分支理论上不会进入，因为前面的逻辑保证了至少有一个可选项
            QMessageBox.warning(None, "无任何更改", "未能执行任何删除操作。")

    except Exception as e:
        QMessageBox.critical(None, "未知错误", f"写入文件或删除数据时发生意外错误：\n{e}")
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()