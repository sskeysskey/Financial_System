import sys
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLineEdit, QPushButton, QListWidget, QLabel, 
                             QMessageBox, QFrame)
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, QSize

class EarningsSearchApp(QWidget):
    def __init__(self):
        super().__init__()
        
        # 存放从文件中读取的数据
        # 结构: {'SYMBOL': ['date1', 'date2', ...]}
        self.earnings_data = {}
        
        # 加载数据
        self.load_data()
        
        # 初始化用户界面
        self.initUI()

    def load_data(self):
        """
        从文本文件中加载数据到字典中。
        一个 symbol 可能对应多个日期。
        """
        # --- !!! 重要 !!! ---
        # --- 请将这里的路径修改为你文件的实际路径 ---
        file_path = "/Users/yanzhang/Coding/News/backup/Earnings_Release.txt"
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            # 如果文件不存在，显示一个错误弹窗并准备退出
            error_box = QMessageBox()
            error_box.setIcon(QMessageBox.Critical)
            error_box.setText(f"错误：找不到文件\n{file_path}\n\n请检查文件路径是否正确。")
            error_box.setWindowTitle("文件未找到")
            error_box.exec_()
            # 设置一个标志，以便在显示窗口后立即关闭
            self.file_not_found = True
            return
        else:
            self.file_not_found = False

        # 使用 with 语句安全地打开文件
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # 忽略空行
                if ':' not in line:
                    continue
                
                # 分割 symbol 和日期
                parts = line.strip().split(':', 1)
                symbol = parts[0].strip().upper() # 转为大写以方便不区分大小写搜索
                date = parts[1].strip()
                
                # 如果 symbol 已存在，则追加日期；否则，创建新列表
                if symbol in self.earnings_data:
                    self.earnings_data[symbol].append(date)
                else:
                    self.earnings_data[symbol] = [date]

    def initUI(self):
        """
        初始化和设置用户界面。
        """
        # --- 整体布局 ---
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20) # 设置外边距
        main_layout.setSpacing(15) # 设置控件间距

        # --- 标题 ---
        title_label = QLabel("财报日期搜索")
        title_label.setFont(QFont("Arial", 24, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # --- 搜索框和按钮的水平布局 ---
        search_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("请输入 Symbol (例如: BNS)")
        self.search_input.setFont(QFont("Arial", 14))
        # 当在输入框中按回车时，触发搜索
        self.search_input.returnPressed.connect(self.perform_search)
        
        self.search_button = QPushButton("搜索")
        self.search_button.setFont(QFont("Arial", 14))
        # 点击按钮时，触发搜索
        self.search_button.clicked.connect(self.perform_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        
        main_layout.addLayout(search_layout)

        # --- 分隔线 ---
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # --- 结果显示列表 ---
        self.results_list = QListWidget()
        self.results_list.setFont(QFont("Arial", 14))
        main_layout.addWidget(self.results_list)

        # --- 设置窗口属性 ---
        self.setLayout(main_layout)
        self.setWindowTitle('财报日期快速搜索工具')
        self.setGeometry(300, 300, 500, 400) # x, y, width, height
        
        # 设置窗口图标 (可选，需要一个图标文件)
        # self.setWindowIcon(QIcon('path/to/your/icon.png'))

    def perform_search(self):
        """
        执行搜索操作并更新结果列表。
        """
        # 获取输入框的文本，去除首尾空格并转为大写
        query = self.search_input.text().strip().upper()
        
        # 清空上一次的搜索结果
        self.results_list.clear()
        
        if not query:
            self.results_list.addItem("请输入一个Symbol进行搜索。")
            return
            
        # 在数据中查找
        if query in self.earnings_data:
            dates = self.earnings_data[query]
            # 对日期进行排序，让显示更有条理
            dates.sort()
            for date in dates:
                self.results_list.addItem(date)
        else:
            self.results_list.addItem(f"未找到 '{query}' 的相关日期。")

    # --- 新增的功能 ---
    def keyPressEvent(self, event):
        """
        重写 keyPressEvent 事件处理器，用于捕捉键盘按键。
        """
        # 检查按下的键是否是 ESC 键
        # Qt.Key_Escape 是 PyQt5 中对 ESC 键的内置常量
        if event.key() == Qt.Key_Escape:
            self.close() # 如果是，则调用 close() 方法关闭窗口

def main():
    # 创建 QApplication 实例
    app = QApplication(sys.argv)
    
    # --- 设置漂亮的深色主题样式 (QSS, 类似于 CSS) ---
    app.setStyle("Fusion") # Fusion 风格更现代
    dark_stylesheet = """
        QWidget {
            background-color: #2E2E2E;
            color: #F0F0F0;
            font-family: Arial, sans-serif;
        }
        QLabel {
            color: #FFFFFF;
        }
        QLineEdit {
            background-color: #424242;
            border: 1px solid #5A5A5A;
            border-radius: 5px;
            padding: 8px;
        }
        QLineEdit:focus {
            border: 1px solid #007ACC;
        }
        QPushButton {
            background-color: #007ACC;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 16px;
        }
        QPushButton:hover {
            background-color: #005C99;
        }
        QPushButton:pressed {
            background-color: #004C80;
        }
        QListWidget {
            background-color: #424242;
            border: 1px solid #5A5A5A;
            border-radius: 5px;
            padding: 5px;
        }
        QListWidget::item {
            padding: 8px;
        }
        QListWidget::item:selected {
            background-color: #007ACC;
            color: white;
        }
        QMessageBox {
            background-color: #424242;
        }
        QFrame[frameShape="HLine"] {
            color: #5A5A5A;
        }
    """
    app.setStyleSheet(dark_stylesheet)
    
    # 创建主窗口实例
    ex = EarningsSearchApp()
    
    # 如果文件未找到，则在显示窗口后立即退出
    if hasattr(ex, 'file_not_found') and ex.file_not_found:
        # 不调用 ex.show()，直接退出
        sys.exit(1) # 返回一个非零值表示错误
    
    # 显示窗口
    ex.show()
    
    # 进入应用主循环
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()