import os
import sys
import json
import pyperclip
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QMainWindow, QAction, QScrollArea, QToolButton, QSizePolicy, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QKeySequence
import sqlite3
import pickle

# JSON 文件路径
json_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"


# 添加新的SearchHistory类来管理搜索历史
class SearchHistory:
    def __init__(self, max_size=20):
        self.max_size = max_size
        self.history_file = "/Users/yanzhang/Documents/Financial_System/Modules/search_history.pkl"
        self.history = self.load_history()

    def add(self, query):
        # 确保添加前移除已存在的重复项
        if query in self.history:
            self.history.remove(query)
        # 插入到最前面
        self.history.insert(0, query)
        # 限制历史记录大小
        if len(self.history) > self.max_size:
            self.history = self.history[:self.max_size]
        self.save_history()

    def get_history(self):
        return self.history

    def load_history(self):
        try:
            with open(self.history_file, 'rb') as f:
                return pickle.load(f)
        except:
            return []

    def save_history(self):
        try:
            with open(self.history_file, 'wb') as f:
                pickle.dump(self.history, f)
        except Exception as e:
            print(f"保存搜索历史失败: {e}")

class ClickableLabel(QLabel):
    """
    自定义的可点击标签，同时允许鼠标选择文本
    """
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        # 允许选择文本
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 修改鼠标悬停的指针样式为输入箭头（IBeam）
        self.setCursor(Qt.IBeamCursor)
        # 设置左对齐
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._mouse_pressed_pos = None

    def mousePressEvent(self, event):
        self._mouse_pressed_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed_pos is not None:
            # 如果鼠标移动距离较短，则认为是点击
            if (event.pos() - self._mouse_pressed_pos).manhattanLength() < 5:
                self.clicked.emit()
        super().mouseReleaseEvent(event)


class SearchWorker(QThread):
    results_ready = pyqtSignal(object)

    def __init__(self, keywords, json_path):
        super().__init__()
        self.keywords = keywords
        self.json_path = json_path
        # 注意：load_compare_data 现在在主线程调用，确保UI不卡顿
        # self.compare_data = load_compare_data() # 不再在worker中加载

    def run(self):
        # 耗时搜索操作
        matched_names_stocks, matched_names_etfs = search_json_for_keywords(self.json_path, self.keywords)
        (matched_names_stocks_tag, matched_names_etfs_tag, 
         matched_names_stocks_name, matched_names_etfs_name,
         matched_names_stocks_symbol, matched_names_etfs_symbol) = search_tag_for_keywords(self.json_path, self.keywords)

        self.results = {
            'matched_names_stocks': matched_names_stocks,
            'matched_names_etfs': matched_names_etfs,
            'matched_names_stocks_tag': matched_names_stocks_tag,
            'matched_names_etfs_tag': matched_names_etfs_tag,
            'matched_names_stocks_name': matched_names_stocks_name,
            'matched_names_etfs_name': matched_names_etfs_name,
            'matched_names_stocks_symbol': matched_names_stocks_symbol,
            'matched_names_etfs_symbol': matched_names_etfs_symbol
        }

        # 发射搜索结果信号
        self.results_ready.emit(self.results)


class CollapsibleWidget(QWidget):
    """
    可折叠控件：上方显示标题与折叠按钮，点击后可隐藏或显示下方的内容区域
    """
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        # 创建标题按钮，显示组名与箭头
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet("QToolButton { border: none; font: bold 16px; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self.on_toggle)

        # 内容区域（存放组内搜索结果项）
        self.content_area = QWidget()
        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(20, 0, 0, 0)
        self.content_area.setLayout(self.content_layout)

        # 主布局：标题按钮 + 内容区域
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

    def on_toggle(self):
        """点击标题按钮时切换内容显示/隐藏，并更新箭头方向"""
        checked = self.toggle_button.isChecked()
        self.content_area.setVisible(checked)
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def addContentWidget(self, widget: QWidget):
        """向内容区域添加控件"""
        self.content_layout.addWidget(widget)
        # 调整内容区域大小以适应新添加的控件
        self.content_area.adjustSize()


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def search_json_for_keywords(json_path, keywords):
    with open(json_path, 'r') as file:
        data = json.load(file)
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    def search_category(category):
        if category == 'stocks':
            return [
                (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) 
                for item in data.get(category, [])
                if all(keyword in ' '.join([item['description1'], item['description2']]).lower() for keyword in keywords_lower)
            ]
        else:  # ETFs
            return [
                (item['symbol'], ' '.join(item.get('tag', []))) 
                for item in data.get(category, [])
                if all(keyword in ' '.join([item['description1'], item['description2']]).lower() for keyword in keywords_lower)
            ]

    return search_category('stocks'), search_category('etfs')


def search_tag_for_keywords(json_path, keywords, max_distance=1):
    with open(json_path, 'r') as file:
        data = json.load(file)
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    def fuzzy_match(text, keyword):
        if len(keyword) <= 1:
            return keyword in text.lower()
        words = text.lower().split()
        return any(levenshtein_distance(word, keyword) <= max_distance for word in words)

    def two_step_search(category, search_field):
        search_term = keywords.strip().lower()
        search_term_lower = search_term

        def exact_match(item):
            if search_field == 'name':
                return item.get('name', '').lower() == search_term_lower
            elif search_field == 'symbol':
                return item.get('symbol', '').lower() == search_term_lower
            return False

        def partial_match(item):
            if search_field == 'name':
                return all(keyword in item.get('name', '').lower() for keyword in keywords_lower)
            elif search_field == 'symbol':
                return all(keyword in item.get('symbol', '').lower() for keyword in keywords_lower)
            return False

        def fuzzy_match_item(item):
            if search_field == 'name':
                return all(fuzzy_match(item.get('name', ''), keyword) for keyword in keywords_lower)
            elif search_field == 'symbol':
                return all(fuzzy_match(item.get('symbol', ''), keyword) for keyword in keywords_lower)
            return False

        exact_matches = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) 
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if exact_match(item)
        ]

        partial_matches = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if not exact_match(item) and partial_match(item)
        ]

        fuzzy_matches = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if not exact_match(item) and not partial_match(item) and fuzzy_match_item(item)
        ]

        return exact_matches + partial_matches + fuzzy_matches

    def search_category_for_tag(category):
        def match_score(item):
            tags = item[2].lower() if category == 'stocks' else item[1].lower()
            exact_matches = sum(keyword in tags for keyword in keywords_lower)
            fuzzy_matches = sum(any(fuzzy_match(tag.lower(), keyword) for tag in tags.split()) for keyword in keywords_lower)
            return (exact_matches, fuzzy_matches)

        exact_results = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(keyword in ' '.join(item.get('tag', [])).lower() for keyword in keywords_lower)
        ]
        if exact_results:
            return sorted(exact_results, key=match_score, reverse=True)

        return [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(any(fuzzy_match(tag, keyword) for tag in item.get('tag', [])) for keyword in keywords_lower)
        ]

    return (
        search_category_for_tag('stocks'),
        search_category_for_tag('etfs'),
        two_step_search('stocks', 'name'),
        two_step_search('etfs', 'name'),
        two_step_search('stocks', 'symbol'),
        two_step_search('etfs', 'symbol')
    )


def get_latest_etf_volume(etf_name):
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 查询最新的 volume
    cursor.execute("SELECT volume FROM ETFs WHERE name = ? ORDER BY date DESC LIMIT 1", (etf_name,))
    result = cursor.fetchone()

    conn.close()

    if result and result[0] is not None:
        volume = result[0]
        # 将 volume 转换为 K 单位返回
        return f"{int(volume / 1000)}K"
    else:
        return "N/A"


def load_compare_data():
    compare_data = {}
    try:
        with open("/Users/yanzhang/Documents/News/backup/Compare_All.txt", "r") as f:
            for line in f:
                if ":" in line:
                    symbol, value = line.strip().split(":", 1)
                    compare_data[symbol.strip()] = value.strip()
    except Exception as e:
        print(f"读取Compare_All.txt出错: {e}")
        return {}
    return compare_data


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("公司、股票和ETF搜索")
        # 前面两个是配置整个窗口界面的位置，后面是界面的宽度和高度
        self.setGeometry(300, 200, 1000, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # 搜索输入区域
        self.input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setFixedHeight(40)
        self.input_field.setFont(QFont("Arial", 18))
        self.search_button = QPushButton("搜索")
        # --- 调整按钮高度以匹配输入框 ---
        self.search_button.setFixedHeight(45) # 使按钮高度与输入框一致
        self.search_button.setFixedWidth(80) # 可以适当增加宽度
        self.input_layout.addWidget(self.input_field) # 默认拉伸
        self.input_layout.addWidget(self.search_button) # 不拉伸
        self.layout.addLayout(self.input_layout)

        # 只有当第一个参数是 'paste' 时，我们才 suppress history
        self.suppress_history = len(sys.argv) > 1 and sys.argv[1] == "paste"

        # 搜索历史管理器
        self.search_history = SearchHistory()
        
        # 修改搜索历史列表的样式
        self.history_list = QListWidget(self)
        self.history_list.setMaximumHeight(200) # 限制最大高度
        self.history_list.setVisible(False) # 初始隐藏
        self.history_list.itemClicked.connect(self.use_history_item)
        # 设置样式
        self.history_list.setStyleSheet("""
            QListWidget {
                font-size: 16px; /* 字体稍大 */
                border: 1px solid #555; /* 边框 */
                background-color: #2d2d2d; /* 深色背景 */
                color: #ccc; /* 浅色文字 */
                outline: 0; /* 移除焦点时的虚线框 */
            }
            QListWidget::item {
                padding: 8px 12px; /* 增加内边距 */
                border-bottom: 1px solid #444; /* 项目间分隔线 */
            }
            QListWidget::item:hover {
                background-color: #3a3a3a; /* 悬停背景色 */
            }
            QListWidget::item:selected {
                background-color: #0078d7; /* 选中背景色 (蓝色) */
                color: white; /* 选中文字颜色 */
            }
        """)
        # 将历史列表插入到输入框下方
        self.layout.insertWidget(1, self.history_list) # 插入到索引1的位置

        # 输入框焦点事件连接 - 保存原始事件处理器
        self._orig_focus_in = self.input_field.focusInEvent
        self._orig_focus_out = self.input_field.focusOutEvent
        self._orig_key_press = self.input_field.keyPressEvent # <-- 新增：保存原始按键事件

        # 保存并重载 mousePressEvent
        self._orig_mouse_press = self.input_field.mousePressEvent
        self.input_field.mousePressEvent = self._input_mouse_press

        # 绑定新的事件处理器
        self.input_field.focusInEvent = self._input_focus_in
        self.input_field.focusOutEvent = self._input_focus_out
        self.input_field.keyPressEvent = self._input_key_press # <-- 新增：绑定新的按键事件

        # 添加计时器用于延迟隐藏历史记录列表
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_history)

        # 搜索中提示
        self.loading_label = QLabel("正在搜索...", self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Arial", 14))
        self.loading_label.hide()
        self.layout.addWidget(self.loading_label)

        # 结果展示区域：使用 QScrollArea 存放折叠分组
        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_container = QWidget()
        self.results_layout = QVBoxLayout(self.result_container)
        self.results_layout.setAlignment(Qt.AlignTop) # 结果从顶部开始排列
        self.result_container.setLayout(self.results_layout)
        self.result_scroll.setWidget(self.result_container)
        self.layout.addWidget(self.result_scroll)

        self.search_button.clicked.connect(self.start_search)
        self.input_field.returnPressed.connect(self.start_search) # 保留回车直接搜索

        # 添加 ESC 键快捷关闭功能
        self.shortcut_close = QKeySequence("Esc")
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(self.shortcut_close)
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)

        self.compare_data = {} # 初始化 compare_data

    def display_history(self):
        """加载并显示搜索历史列表"""
        # 如果被 suppress 了，就直接返回
        if getattr(self, "suppress_history", False):
            return

        self.history_list.clear()
        history_items = self.search_history.get_history()
        if history_items:
            for item in history_items:
                self.history_list.addItem(QListWidgetItem(item))
            self.history_list.setVisible(True)
            self.history_list.setFixedWidth(self.input_field.width())
            self.history_list.setCurrentRow(-1)
        else:
            self.history_list.setVisible(False)
    
    def _input_focus_in(self, event):
        # 1) 原始处理
        self._orig_focus_in(event)
        
        # 如果 suppress 了，就不弹
        if getattr(self, "suppress_history", False):
            return
        # 2) 否则显示历史并全选
        self.display_history()
        QTimer.singleShot(0, self.input_field.selectAll)

    def _input_mouse_press(self, event):
        """
        当已经有焦点时，再次点击输入框也要弹出历史列表
        """
        # 1) 先调用原始的 mousePressEvent，让光标定位
        self._orig_mouse_press(event)
        # 2) 再显示历史列表（但不 selectAll），除非 suppress
        if not getattr(self, "suppress_history", False):
            self.display_history()

    def _input_focus_out(self, event):
        """
        失去焦点时：先调用原始 focusOutEvent，再延时隐藏历史列表
        """
        # 检查新的焦点是否在历史列表内，如果是，则不隐藏
        new_focus_widget = QApplication.focusWidget()
        if new_focus_widget == self.history_list:
            # 如果焦点转移到列表本身（例如通过Tab键），不立即隐藏
            # 但我们主要关心鼠标点击，所以延时隐藏通常是好的
            pass # 可以选择在这里直接返回，避免启动计时器

        self._orig_focus_out(event)
        # 延时隐藏，给点击历史项留出时间
        self.hide_timer.start(200) # 200ms 延迟

    def _input_key_press(self, event):
        """
        处理输入框中的按键事件，特别是方向键和回车键，
        用于导航和选择搜索历史列表。
        """
        # 检查历史列表是否可见且有内容
        if self.history_list.isVisible() and self.history_list.count() > 0:
            key = event.key()
            current_row = self.history_list.currentRow()
            num_items = self.history_list.count()

            if key == Qt.Key_Down:
                next_row = min(current_row + 1, num_items - 1)
                # 如果当前没有选中项（-1），按向下键选中第一个
                if current_row == -1:
                    next_row = 0
                self.history_list.setCurrentRow(next_row)
                event.accept() # 阻止光标在输入框中移动
                return # 处理完毕

            elif key == Qt.Key_Up:
                next_row = max(current_row - 1, 0)
                 # 如果当前没有选中项（-1），按向上键选中最后一个
                if current_row == -1:
                     next_row = num_items - 1 # 选中最后一个
                self.history_list.setCurrentRow(next_row)
                event.accept() # 阻止光标在输入框中移动
                return # 处理完毕

            elif key in (Qt.Key_Return, Qt.Key_Enter):
                # 如果有选中的历史项，使用该项进行搜索
                if current_row != -1:
                    selected_item = self.history_list.item(current_row)
                    if selected_item:
                        self.input_field.setText(selected_item.text())
                        self.hide_history() # 隐藏历史列表
                        self.start_search() # 开始搜索
                        event.accept() # 阻止默认的回车事件（如触发行编辑器的returnPressed信号）
                        return # 处理完毕
                else:
                    # 如果没有选中项，但列表可见，按回车则直接搜索当前输入框内容
                    # 并且隐藏列表
                    self.hide_history()
                    # 让原始的回车处理（连接到start_search）执行
                    # 但这里我们还是调用 start_search 并阻止事件，避免潜在的双重调用
                    self.start_search()
                    event.accept()
                    return

            elif key == Qt.Key_Escape:
                 # 按 ESC 时，如果历史列表可见，则隐藏它，否则让主窗口处理关闭
                 self.hide_history()
                 event.accept()
                 return # 阻止 ESC 关闭窗口（如果列表可见）

        # 对于其他所有按键（包括字母、数字、退格等）或历史列表不可见时
        # 调用原始的 keyPressEvent 处理函数
        self._orig_key_press(event)


    def hide_history(self):
        """隐藏搜索历史记录"""
        self.history_list.setVisible(False)

    def use_history_item(self, item):
        """点击历史记录项时触发"""
        self.input_field.setText(item.text())
        self.hide_history() # 隐藏列表
        self.start_search() # 开始搜索

    # 修改start_search方法，添加历史记录保存功能
    def start_search(self):
        keywords = self.input_field.text()
        if not keywords.strip():
            # 如果输入为空，可以选择清除结果或不执行任何操作
            self.clear_results()
            return

        # 保存到搜索历史 (确保在搜索前保存)
        self.search_history.add(keywords.strip())

        # 确保历史列表此时是隐藏的
        self.hide_history()

        # 加载 compare_data 放在主线程，避免阻塞 worker
        self.compare_data = load_compare_data()

        self.loading_label.show()
        self.clear_results() # 清除旧结果
        self.search_button.setEnabled(False)
        self.input_field.setEnabled(False) # 禁用输入直到搜索完成

        # 创建并启动后台搜索线程
        self.worker = SearchWorker(keywords, json_path)
        self.worker.results_ready.connect(self.show_results)
        # 线程结束后重新启用UI
        self.worker.finished.connect(lambda: (
            self.loading_label.hide(),
            self.search_button.setEnabled(True),
            self.input_field.setEnabled(True),
            self.input_field.setFocus() # 搜索结束后重新聚焦输入框
        ))
        self.worker.start()

    def clear_results(self):
        # 清除结果区域中所有子控件
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater() # 安全删除控件

    def show_results(self, results):
        # 注意：此方法现在由 results_ready 信号触发，在主线程执行

        # 解包搜索结果
        matched_names_stocks = results['matched_names_stocks']
        matched_names_etfs = results['matched_names_etfs']
        matched_names_stocks_tag = results['matched_names_stocks_tag']
        matched_names_etfs_tag = results['matched_names_etfs_tag']
        matched_names_stocks_name = results['matched_names_stocks_name']
        matched_names_etfs_name = results['matched_names_etfs_name'] # 注意ETF可能没有name字段
        matched_names_stocks_symbol = results['matched_names_stocks_symbol']
        matched_names_etfs_symbol = results['matched_names_etfs_symbol']

        search_term = self.input_field.text().strip().upper() # 获取当前搜索词用于排序

        # 排序函数：将与搜索词完全匹配的 symbol 放到最前面
        def sort_by_exact_match(items, search_term):
            exact_matches = []
            partial_matches = []
            for item in items:
                symbol = item[0]
                if symbol == search_term:
                    exact_matches.append(item)
                else:
                    partial_matches.append(item)
            return exact_matches + partial_matches

        # 对 symbol 结果排序
        matched_names_stocks_symbol = sort_by_exact_match(matched_names_stocks_symbol, search_term)
        matched_names_etfs_symbol = sort_by_exact_match(matched_names_etfs_symbol, search_term)

        # 定义各结果组的显示顺序、名称及颜色
        display_order = [
            ("Stock_symbol", matched_names_stocks_symbol, 'white'),
            ("ETF_symbol", matched_names_etfs_symbol, 'white'),
            ("Stock_name", matched_names_stocks_name, 'white'),
            ("ETF_name", matched_names_etfs_name, 'white'),
            ("Stock_tag", matched_names_stocks_tag, 'white'),
            ("ETF_tag", matched_names_etfs_tag, 'white')
        ]

        # 添加每个分组到结果区域
        for category, result_list, color in display_order:
            if result_list:
                group = CollapsibleWidget(title=category)
                for result in result_list:
                    if len(result) == 3:  # 股票结果： (symbol, name, tags)
                        symbol, name, tags = result
                        compare_info = self.compare_data.get(symbol, "")
                        if compare_info:
                            display_text = f"{symbol}  {compare_info}  {name}  {tags}"
                        else:
                            display_text = f"{symbol}  {name}  {tags}"
                    else:  # ETF 结果： (symbol, tags)
                        symbol, tags = result
                        latest_volume = get_latest_etf_volume(symbol)
                        compare_info = self.compare_data.get(symbol, "")
                        display_parts = [symbol]
                        if compare_info:
                            display_parts.append(compare_info)
                        display_parts.append(tags)
                        if latest_volume and latest_volume != "N/A":
                            display_parts.append(latest_volume)
                        display_text = " ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, color, 20)
                    group.addContentWidget(lbl)
                self.results_layout.addWidget(group)

        # 固定分组： Stock_Description 与 ETFs_Description
        if matched_names_stocks:
            group = CollapsibleWidget(title="Stock_Description")
            for result in matched_names_stocks:
                if len(result) == 3:
                    symbol, name, tags = result
                    compare_info = self.compare_data.get(symbol, "")
                    if compare_info:
                        display_text = f"{symbol}  {compare_info}  {name}  {tags}"
                    else:
                        display_text = f"{symbol}  {name}  {tags}"
                    lbl = self.create_result_label(display_text, symbol, 'gray', 20)
                    group.addContentWidget(lbl)
            self.results_layout.addWidget(group)

        if matched_names_etfs:
            group = CollapsibleWidget(title="ETFs_Description")
            for result in matched_names_etfs:
                if len(result) == 2:
                    symbol, tags = result
                    latest_volume = get_latest_etf_volume(symbol)
                    compare_info = self.compare_data.get(symbol, "")
                    display_parts = [symbol]
                    if compare_info:
                        display_parts.append(compare_info)
                    display_parts.append(tags)
                    if latest_volume and latest_volume != "N/A":
                        display_parts.append(latest_volume)
                    display_text = " ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, 'gray', 20)
                    group.addContentWidget(lbl)
            self.results_layout.addWidget(group)

    def create_result_label(self, display_text, symbol, color, font_size):
        """
        创建一个结果项标签，设置左对齐、允许文本选择，并通过富文本格式将 symbol 部分设为蓝色，
        其余部分则保持原来的颜色（通过参数 color 传入）
        - 同时设置行间距和字间距加大
        """
        lbl = ClickableLabel()
        lbl.setTextFormat(Qt.RichText)
        # 如果 display_text 以 symbol 开头，则分割 symbol 和剩余文本
        if display_text.startswith(symbol):
            remainder = display_text[len(symbol):]
        else:
            remainder = display_text
        # 使用富文本 HTML 设定 symbol 为蓝色，其余部分使用传入的 color
        # 在外层添加统一的样式：增大行间距(line-height)和字间距(letter-spacing)
        label_html = (
            f"<span style='line-height: 2.2; letter-spacing: 1px;'>"
            f"<span style='color: cyan; font-size: {font_size}px;'>{symbol}</span>"
            f"<span style='color: {color}; font-size: {font_size}px;'>{remainder}</span>"
            f"</span>"
        )
        lbl.setText(label_html)
        # 修改点击信号连接：传入标签本身和 symbol 信息
        lbl.clicked.connect(lambda: self.handle_label_click(lbl, symbol))
        return lbl

    def handle_label_click(self, label, symbol):
        """
        处理点击标签时的反馈效果：
        1. 先改变标签的背景色（例如设置为黄色高亮）
        2. 使用 QTimer 在短暂延时后恢复原来的样式
        3. 调用 open_symbol() 打开图表
        """
        original_style = label.styleSheet()
        # 设置一个临时背景色，例如黄色
        label.setStyleSheet(original_style + " background-color: white;")
        # 300 毫秒后恢复原有样式
        QTimer.singleShot(300, lambda: label.setStyleSheet(original_style))
        # 调用原有的打开图表函数
        self.open_symbol(symbol)

    def open_symbol(self, symbol):
        """
        当用户点击结果项时，将 symbol 复制到剪贴板，
        并调用 Stock_Chart.py 传入 'paste' 参数
        """
        if symbol:
            pyperclip.copy(symbol)
            stock_chart_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '/Users/yanzhang/Documents/Financial_System/Query/Stock_Chart.py'
            )
            try:
                subprocess.Popen([sys.executable, stock_chart_path, 'paste'])
            except Exception as e:
                print(f"无法打开图表脚本 {stock_chart_path}: {e}")


if __name__ == "__main__":
    # 开启高 DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "input":
            # 显示窗口供用户输入
            pass
        elif arg == "paste":
            # 从剪贴板中复制文本进行搜索
            clipboard_content = pyperclip.paste()
            if clipboard_content:
                window.input_field.setText(clipboard_content)
                window.start_search()
            else:
                print("剪贴板为空，请复制一些文本后再试。")
    else:
        # 没有传入参数时由用户手动输入
        pass

    sys.exit(app.exec_())