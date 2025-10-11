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
    "Short",
    "Next Week",
    "2 Weeks",
    "3 Weeks"
]

def is_uppercase_letters(text: str) -> bool:
    """检查字符串是否只包含大写字母"""
    return bool(re.match(r'^[A-Z]+$', text))

def copy2clipboard():
    """使用 AppleScript 模拟 Command+C 复制，并等待剪贴板更新"""
    script = '''
    set the clipboard to ""
    delay 0.5
    tell application "System Events"
        keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', script], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"执行 AppleScript 失败: {e}")
        # 在非 macOS 系统或 AppleScript 执行失败时，这是一个备用方案
        # 但通常我们期望它能工作。这里只是为了程序健壮性。
        pass

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
    # --- 修改点 1: __init__ 方法增加了一个参数 ---
    # 增加 pre_selected_categories 参数，用于接收一个包含应被预先勾选的分组名的集合
    def __init__(self, symbol, categories, pre_selected_categories=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("第二步：选择分组")
        self.setMinimumWidth(300)

        # 如果 pre_selected_categories 未提供，则初始化为空集合，防止出错
        if pre_selected_categories is None:
            pre_selected_categories = set()

        layout = QVBoxLayout(self)

        # 提示标签
        self.label = QLabel(f"为 Symbol <b style='color:blue;'>{symbol}</b> 选择一个或多个分组:", self)
        layout.addWidget(self.label)

        # 复选框
        self.checkboxes = []
        for category in categories:
            checkbox = QCheckBox(category, self)
            
            # --- 修改点 2: 设置复选框的初始状态 ---
            # 在创建复选框时，检查当前分组名是否在 pre_selected_categories 集合中
            # 如果在，就将这个复选框的初始状态设置为勾选 (Checked)
            if category in pre_selected_categories:
                checkbox.setChecked(True)
            
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

    # --- 修改点 3: 提前读取和解析 JSON 文件 ---
    # 为了检查 symbol 是否已存在，我们需要先加载 JSON 数据。
    # 将文件读取操作提前，并用 try-except 包裹以处理可能的错误。
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)
    except json.JSONDecodeError:
        QMessageBox.critical(None, "文件错误", f"无法解析 JSON 文件，请检查文件格式：\n{JSON_FILE_PATH}")
        sys.exit(1)
    except Exception as e:
        QMessageBox.critical(None, "文件读取错误", f"读取文件时发生错误：\n{e}")
        sys.exit(1)


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

    # --- 修改点 4: 查找 Symbol 已存在的分组 ---
    # 遍历所有目标分组，检查 symbol 是否已经是其中一员。
    # 使用集合 (set) 来存储结果，查询效率更高。
    existing_categories = set()
    for category in TARGET_CATEGORIES:
        # 确保分组在 JSON 数据中存在，并且 symbol 是该分组下的一个键
        if category in panel_data and symbol in panel_data[category]:
            existing_categories.add(category)

    # --- 修改点 5: 将预选中的分组传递给对话框 ---
    # 实例化 CategorySelectionDialog 时，将我们刚刚找到的 existing_categories 传递进去。
    category_dialog = CategorySelectionDialog(symbol, TARGET_CATEGORIES, existing_categories)
    category_dialog.show()
    category_dialog.activateWindow()
    category_dialog.raise_()
    
    selected_categories = []
    if category_dialog.exec_() == QDialog.Accepted:
        selected_categories = category_dialog.get_selected_categories()
        # 即使用户取消了所有勾选，也认为是有效操作（即从所有分组中移除），所以不再检查是否为空
    else:
        # 用户点击了取消或按了 ESC
        print("用户取消了操作。程序退出。")
        sys.exit(0)

    # --- 修改点 6: 优化 JSON 更新逻辑 ---
    # 新的逻辑会处理添加、移除和排序，使 JSON 文件状态与复选框的最终状态完全同步。
    try:
        something_changed = False
        # 遍历所有可能的分组
        for category in TARGET_CATEGORIES:
            # 检查分组是否在 JSON 数据中
            if category not in panel_data:
                print(f"警告：分组 '{category}' 在 JSON 文件中不存在，已跳过。")
                continue

            symbol_exists = symbol in panel_data[category]
            category_is_selected = category in selected_categories

            # 情况1: 复选框被勾选，但 symbol 不在分组里 -> 添加
            if category_is_selected and not symbol_exists:
                # 使用您原来的方法，将新 symbol 放在最前面
                panel_data[category] = {symbol: "", **panel_data[category]}
                print(f"已将 '{symbol}' 添加到分组 '{category}'。")
                something_changed = True
            
            # 情况2: 复选框被勾选，且 symbol 已经在分组里 -> 移动到最前
            elif category_is_selected and symbol_exists:
                # 先删除，再添加，即可实现移动到最前
                # 如果已经是第一个，这个操作也没影响
                del panel_data[category][symbol]
                panel_data[category] = {symbol: "", **panel_data[category]}
                # 这种情况也可以视为一种更改，但为了简化输出，我们只在添加/删除时打印
                something_changed = True # 即使只是顺序改变，也标记为已更改

            # 情况3: 复选框未被勾选，但 symbol 存在于分组里 -> 移除
            elif not category_is_selected and symbol_exists:
                del panel_data[category][symbol]
                print(f"已从分组 '{category}' 中移除 '{symbol}'。")
                something_changed = True

        # 只有在数据确实发生变动时，才写回文件
        if something_changed:
            with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(panel_data, f, ensure_ascii=False, indent=4)
            
            print(f"文件 '{JSON_FILE_PATH}' 已成功更新。")
            # 可以选择性地显示一个成功的消息框
            # QMessageBox.information(None, "操作成功", f"针对 Symbol '{symbol}' 的分组更新已完成。")
        else:
            print("数据未发生任何变化，无需更新文件。")

    except Exception as e:
        QMessageBox.critical(None, "未知错误", f"更新 JSON 文件时发生了一个意外错误：\n{e}")
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()