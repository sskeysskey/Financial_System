import json
import sys
import time
import subprocess
import pyperclip
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QTextEdit, QPushButton, 
                            QListWidget, QMessageBox, QInputDialog, QAction,
                            QLineEdit) # 导入 QLineEdit
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QKeySequence

def get_clipboard_content():
    """获取剪贴板内容，包含错误处理"""
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception:
        return ""

def copy2clipboard():
    """执行复制操作并等待复制完成"""
    try:
        # 此脚本适用于macOS
        script = '''
        tell application "System Events"
            keystroke "c" using {command down}
        end tell
        '''
        subprocess.run(['osascript', '-e', script], check=True)
        # 给系统一点时间来完成复制操作
        time.sleep(0.5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # FileNotFoundError on non-macOS systems
        return False

def get_stock_symbol(default_symbol=""):
    """获取股票代码，如果用户取消则返回None"""
    # 确保QApplication实例存在
    app = QApplication.instance() or QApplication(sys.argv)
    
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    
    # 设置窗口标志，确保窗口始终在最前面
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
    
    # 应用一些基本样式以匹配主窗口
    input_dialog.setStyleSheet("""
        QInputDialog {
            background-color: #2E3440;
            color: #D8DEE9;
        }
        QLineEdit, QLabel, QPushButton {
            color: #D8DEE9;
            background-color: #434C5E;
            border: 1px solid #4C566A;
        }
        QPushButton:hover {
            background-color: #5E81AC;
        }
    """)
    
    if input_dialog.exec_() == QInputDialog.Accepted:
        return input_dialog.textValue().strip()
    return None # 用户点击了取消或关闭按钮

class TagEditor(QMainWindow):
    def __init__(self, init_symbol=None):
        super().__init__()        
        self.json_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"
        self.load_json_data()
        
        self.setWindowTitle("标签编辑器 (支持拖拽排序)")
        self.setGeometry(100, 100, 600, 700)
        
        # 创建主窗口部件和布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # 添加 ESC 键关闭窗口的功能
        self.shortcut_close = QKeySequence("Esc")
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(self.shortcut_close)
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)
        
        self.init_ui()
        self.apply_stylesheet() # ★ 新增：应用美化样式
        
        # 处理初始化数据
        # 如果init_symbol是None或空，process_symbol会处理并可能关闭窗口
        self.process_symbol(init_symbol)
            
        # 设置焦点到输入框
        self.new_tag_input.setFocus()

        # 确保tags_list可以接收键盘焦点
        self.tags_list.setFocusPolicy(Qt.StrongFocus)
    
    # ★★★ BUG修复点 ★★★
    # 使用 QTimer.singleShot 来安全地调用 add_tag，避免崩溃
    def eventFilter(self, source, event):
        if source is self.new_tag_input and event.type() == QEvent.KeyPress:
            # 如果按下的是回车键 (且没有按下Shift键)
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
                # 不直接调用 self.add_tag()
                # 而是安排它在当前事件处理完成后立即执行
                QTimer.singleShot(0, self.add_tag)
                return True # 告诉Qt事件已处理，防止输入框换行
        return super().eventFilter(source, event)

    # ★ 修改点: 简化UI初始化，移除按钮，开启拖拽
    def init_ui(self):
        self.symbol_label = QLabel("Symbol: ")
        self.layout.addWidget(self.symbol_label)
        
        self.tags_list = QListWidget()
        self.tags_list.itemDoubleClicked.connect(self.on_double_click)
        
        # --- 开启拖拽排序功能 ---
        self.tags_list.setSelectionMode(QListWidget.SingleSelection)
        self.tags_list.setDragDropMode(QListWidget.InternalMove)
        self.tags_list.setDefaultDropAction(Qt.MoveAction)
        
        # ★ 删除: 上下移动按钮和相关布局已被移除
        # 直接将列表添加到主布局
        self.layout.addWidget(self.tags_list)
        
        # --- 输入区域 ---
        input_layout = QHBoxLayout()
        
        # ★ 修改：使用QTextEdit代替QLineEdit，并设置固定高度
        self.new_tag_input = QTextEdit()
        self.new_tag_input.setPlaceholderText("在此输入新标签，按 Enter 添加...")
        self.new_tag_input.setFixedHeight(80) # 设置一个更舒适的高度
        # ★ 新增：安装事件过滤器来捕获回车键
        self.new_tag_input.installEventFilter(self)

        add_button = QPushButton("添加标签")
        add_button.clicked.connect(self.add_tag)
        
        input_layout.addWidget(self.new_tag_input)
        input_layout.addWidget(add_button)
        
        self.layout.addLayout(input_layout)
        
        # --- 底部按钮 ---
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        delete_button = QPushButton("删除选中")
        save_button = QPushButton("保存并退出")
        
        # 给功能性按钮添加objectName，以便在QSS中单独设置样式
        delete_button.setObjectName("deleteButton")
        save_button.setObjectName("saveButton")

        delete_button.clicked.connect(self.delete_tag)
        save_button.clicked.connect(self.save_changes)
        
        buttons_layout.addWidget(delete_button)
        buttons_layout.addWidget(save_button)
        
        self.layout.addLayout(buttons_layout)

    # ★ 新增：应用QSS样式表的方法
    def apply_stylesheet(self):
        """应用全局QSS样式，美化界面"""
        qss = """
        QMainWindow, QWidget {
            background-color: #2E3440; /* Nord-like dark background */
        }
        
        QLabel {
            color: #D8DEE9; /* Light text color */
            font-size: 16px;
            font-weight: bold;
            padding: 5px;
        }
        
        QListWidget {
            background-color: #3B4252;
            color: #ECEFF4;
            border: 1px solid #4C566A;
            border-radius: 5px;
            font-size: 14px;
            outline: 0px; /* 移除选中时的虚线框 */
        }
        
        QListWidget::item {
            padding: 8px;
        }
        
        QListWidget::item:hover {
            background-color: #434C5E;
        }
        
        QListWidget::item:selected {
            background-color: #5E81AC; /* A nice blue for selection */
            color: #ECEFF4;
        }
        
        /* 添加一个指示器，显示可以拖拽的目标位置 */
        QListWidget::drop-indicator { border: 2px dashed #A3BE8C; }
        QTextEdit {
            background-color: #3B4252;
            color: #ECEFF4;
            border: 1px solid #4C566A;
            border-radius: 5px;
            font-size: 14px;
            padding: 5px;
        }
        
        QTextEdit:focus {
            border: 1px solid #5E81AC; /* Highlight when focused */
        }
        
        QPushButton {
            background-color: #4C566A;
            color: #ECEFF4;
            border: none;
            padding: 10px 15px;
            font-size: 14px;
            border-radius: 5px;
        }
        
        QPushButton:hover {
            background-color: #5E81AC;
        }
        
        QPushButton:pressed {
            background-color: #81A1C1;
        }
        
        /* 为特定按钮设置不同样式 */
        QPushButton#saveButton {
            background-color: #A3BE8C; /* Green for save/confirm */
            font-weight: bold;
        }
        
        QPushButton#saveButton:hover {
            background-color: #B4D39C;
        }
        
        QPushButton#deleteButton {
            background-color: #BF616A; /* Red for delete/warning */
        }
        
        QPushButton#deleteButton:hover {
            background-color: #D08770;
        }
        
        /* 美化滚动条 */
        QScrollBar:vertical {
            border: none;
            background: #3B4252;
            width: 10px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #5E81AC;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        """
        self.setStyleSheet(qss)

    # ★ 修改点: 在保存前同步拖拽后的顺序
    def save_json_data(self):
        """保存数据到JSON文件。在保存前会先同步UI中的标签顺序。"""
        # --- 数据同步逻辑 ---
        # 检查当前是否有项目被加载
        if hasattr(self, 'current_item') and self.current_item:
            # 从 QListWidget 的当前可视顺序，重新构建 tag 列表
            updated_tags = [self.tags_list.item(i).text() for i in range(self.tags_list.count())]
            self.current_item['tag'] = updated_tags
        
        # --- 原有的保存逻辑 ---
        try:
            with open(self.json_file_path, 'w', encoding='utf-8') as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"保存失败: {str(e)}")
            return False

    # ★ 删除: 这两个方法不再需要
    # def move_tag_up(self): ...
    # def move_tag_down(self): ...

    # --- 其他方法保持不变 ---
    def add_tag(self):
        if not hasattr(self, 'current_item'):
            QMessageBox.warning(self, "警告", "没有加载任何项目，无法添加标签。")
            return
        
        # ★ 修改：从QTextEdit获取文本
        new_tag = self.new_tag_input.toPlainText().strip()
        
        if new_tag:
            if new_tag not in self.current_item['tag']:
                self.current_item['tag'].append(new_tag)
                self.tags_list.addItem(new_tag)
                self.new_tag_input.clear()
            else:
                QMessageBox.information(self, "提示", "该标签已存在。")
        self.new_tag_input.setFocus()
        
    # --- 其他方法保持不变 ---
    def edit_current_tag(self):
        """编辑当前选中的标签"""
        current_item = self.tags_list.currentItem()
        if not current_item:
            return
            
        row = self.tags_list.row(current_item)
        old_tag = current_item.text()
        
        # ★★★ BUG修复点 ★★★
        # 使用正确的 QLineEdit.Normal
        new_tag, ok = QInputDialog.getText(
            self, "编辑标签", "请输入新标签:", QLineEdit.Normal, old_tag
        )
        
        if ok and new_tag.strip() and new_tag != old_tag:
            self.current_item['tag'][row] = new_tag.strip()
            current_item.setText(new_tag.strip())

    def delete_current_tag(self):
        """删除当前选中的标签"""
        current_item = self.tags_list.currentItem()
        if current_item and hasattr(self, 'current_item'):
            row = self.tags_list.row(current_item)
            self.tags_list.takeItem(row)
            # 注意：因为保存时会整个重新同步，所以这里不操作 self.current_item['tag'] 也可以。
            # 但为了逻辑严谨性，最好还是删除。
            del self.current_item['tag'][row]

    def keyPressEvent(self, event):
        """处理键盘事件"""
        if self.tags_list.hasFocus() and self.tags_list.currentItem():
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.edit_current_tag()
                event.accept()
                return
            elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.delete_current_tag()
                event.accept()
                return
        
        super().keyPressEvent(event)

    def show(self):
        """重写 show 方法，确保窗口显示时properly激活"""
        super().show()
        self.activateWindow()
        self.raise_()
        self.new_tag_input.setFocus(Qt.OtherFocusReason)

    def showEvent(self, event):
        """重写showEvent以确保窗口显示后输入框获得焦点"""
        super().showEvent(event)
        QTimer.singleShot(100, self.new_tag_input.setFocus)
        
    def process_symbol(self, symbol):
        """
        处理指定的symbol。如果找不到，则提示用户输入。如果用户取消，则关闭窗口。
        """
        # 如果传入的symbol是None或空字符串，直接弹窗
        if not symbol:
            new_symbol = get_stock_symbol()
            if new_symbol:
                self.process_symbol(new_symbol)
            else:
                # 用户在第一次输入时就取消了，关闭窗口
                QTimer.singleShot(0, self.close)
            return
            
        original_symbol = symbol
        category, item = self.find_symbol(original_symbol)
        
        # 如果没找到，尝试大写形式
        if not item:
            uppercase_symbol = original_symbol.upper()
            if uppercase_symbol != original_symbol:
                category, item = self.find_symbol(uppercase_symbol)

        # 找到了就更新 UI
        if item:
            self.current_category = category
            self.current_item = item
            self.update_ui(item)
        else:
            # ★★★ BUG修复点 ★★★
            # 没找到，弹输入框让用户重新输入
            new_symbol = get_stock_symbol(default_symbol=original_symbol)
            if new_symbol:
                # 用户输入了新的symbol，递归处理
                self.process_symbol(new_symbol)
            else:
                # 用户在二次输入时点击了取消或关闭(ESC)，此时必须关闭窗口
                # 因为窗口已经创建但无法正确初始化数据
                QTimer.singleShot(0, self.close)

    def load_json_data(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                self.data = json.load(file)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"加载JSON文件失败: {str(e)}")
            self.data = {"stocks": [], "etfs": []}
            # 如果JSON加载失败，可能需要直接退出
            QTimer.singleShot(0, self.close)

    def on_double_click(self, item):
        """处理双击编辑事件"""
        self.edit_current_tag()

    def find_symbol(self, symbol):
        """在 'stocks' 和 'etfs' 中查找symbol对应的数据"""
        for category in ['stocks', 'etfs']:
            for item in self.data.get(category, []):
                if item.get('symbol') == symbol:
                    return category, item
        return None, None

    def update_ui(self, item):
        self.symbol_label.setText(f"Symbol: <b>{item['symbol']}</b>")
        self.tags_list.clear()
        if 'tag' in item and item['tag']:
            self.tags_list.addItems(item['tag'])

    def delete_tag(self):
        self.delete_current_tag()

    def save_changes(self):
        if hasattr(self, 'current_item'):
            if self.save_json_data():
                self.close() # 保存成功后关闭
        else:
            QMessageBox.information(self, "提示", "没有可保存的更改。")
            self.close() # 没有更改也直接关闭

    def closeEvent(self, event):
        # 这里的逻辑现在变得更健壮，因为它调用的save_json_data()会自动同步顺序
        if hasattr(self, 'current_item'):
            # 可以在这里比较当前状态和初始状态，判断是否有未保存的更改
            # 为简化，我们总是询问或自动保存
            if self.save_json_data():
                event.accept()
            else:
                reply = QMessageBox.question(
                    self, '保存失败', "数据保存失败，是否仍要关闭程序？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    event.accept()
                else:
                    event.ignore()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    
    init_symbol = None
    if len(sys.argv) > 1:
        init_symbol = sys.argv[1]
    
    if not init_symbol:
        pyperclip.copy('')
        if not copy2clipboard():
            # 在非macOS或有权限问题时，直接弹出输入框
            init_symbol = get_stock_symbol()
        else:
            time.sleep(0.1) # 等待剪贴板更新
            new_content = get_clipboard_content()
            if not new_content:
                init_symbol = get_stock_symbol()
            else:
                init_symbol = new_content

    # 如果在所有尝试后，init_symbol仍然是None或空字符串，则退出
    if not init_symbol:
        return # 优雅退出

    editor = TagEditor(init_symbol)
    # 如果窗口在初始化过程中被关闭（例如，用户取消输入），exec_会立即返回
    if not editor.isVisible():
        editor.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()