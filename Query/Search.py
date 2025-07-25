import os
import re
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
from enum import Enum

json_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"

# --- 1. 引入 MatchCategory 枚举 (模仿 Swift) ---
class MatchCategory(Enum):
    STOCK_SYMBOL = ("Stock Symbol", 1000, 'stock')
    ETF_SYMBOL = ("ETF Symbol", 1000, 'etf')
    STOCK_TAG = ("Stock Tag", 800, 'stock')
    ETF_TAG = ("ETF Tag", 800, 'etf')
    STOCK_NAME = ("Stock Name", 500, 'stock')
    ETF_NAME = ("ETF Name", 500, 'etf')
    STOCK_DESCRIPTION = ("Stock Description", 300, 'stock')
    ETF_DESCRIPTION = ("ETF Description", 300, 'etf')

    def __init__(self, display_name, priority, item_type):
        self.display_name = display_name
        self.priority = priority
        self.item_type = item_type # 'stock' or 'etf'


# 添加新的SearchHistory类来管理搜索历史 (代码无变化)
class SearchHistory:
    def __init__(self, max_size=20):
        self.max_size = max_size
        self.history_file = "/Users/yanzhang/Documents/Financial_System/Modules/search_history.pkl"
        self.history = self.load_history()

    def add(self, query):
        if query in self.history: self.history.remove(query)
        self.history.insert(0, query)
        if len(self.history) > self.max_size: self.history = self.history[:self.max_size]
        self.save_history()

    def get_history(self): return self.history
    def load_history(self):
        try:
            with open(self.history_file, 'rb') as f: return pickle.load(f)
        except: return []
    def save_history(self):
        try:
            with open(self.history_file, 'wb') as f: pickle.dump(self.history, f)
        except Exception as e: print(f"保存搜索历史失败: {e}")

# ClickableLabel 类无变化
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setCursor(Qt.IBeamCursor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._mouse_pressed_pos = None
    def mousePressEvent(self, event):
        self._mouse_pressed_pos = event.pos()
        super().mousePressEvent(event)
    def mouseReleaseEvent(self, event):
        if self._mouse_pressed_pos and (event.pos() - self._mouse_pressed_pos).manhattanLength() < 5:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

# --- 2. 重构 SearchWorker 和搜索逻辑 ---
class SearchWorker(QThread):
    results_ready = pyqtSignal(object)

    def __init__(self, keywords, json_path):
        super().__init__()
        self.keywords_str = keywords
        self.json_path = json_path

    def run(self):
        # 耗时搜索操作
        grouped_results = self.unified_search()
        
        # 关键：在 Worker 线程中完成排序
        # 排序规则：1. 按组内最高分降序 2. 如果分数相同，按优先级降序
        sorted_grouped_results = sorted(
            grouped_results,
            key=lambda g: (g['highest_score'], g['priority']),
            reverse=True
        )
        
        # 发射已排序的搜索结果信号
        self.results_ready.emit(sorted_grouped_results)

    def unified_search(self):
        try:
            with open(self.json_path, 'r') as file:
                data = json.load(file)
        except Exception as e:
            print(f"Error reading JSON file: {e}")
            return []

        keywords = self.keywords_str.lower().split()
        if not keywords:
            return []

        # 初始化一个字典来存放每个类别的匹配结果
        # 格式: {MatchCategory: [(item, score), ...]}
        raw_results = {cat: [] for cat in MatchCategory}

        all_items = [('stock', item) for item in data.get('stocks', [])] + \
                    [('etf', item) for item in data.get('etfs', [])]

        for item_type, item in all_items:
            for category in MatchCategory:
                if category.item_type != item_type:
                    continue

                total_score = 0
                all_keywords_match = True
                for keyword in keywords:
                    # 计算单个关键词的分数
                    single_score = self.score_of_single_match(item, keyword, category)
                    if single_score <= 0:
                        all_keywords_match = False
                        break # 如果有一个关键词不匹配，则该项目在该类别下不匹配
                    total_score += single_score
                
                if all_keywords_match:
                    raw_results[category].append((item, total_score))

        # 将原始结果打包成 Swift 风格的分组结构
        final_groups = []
        for category, results_list in raw_results.items():
            if results_list:
                # 按分数对组内结果进行排序
                sorted_results = sorted(results_list, key=lambda x: x[1], reverse=True)
                highest_score = sorted_results[0][1] if sorted_results else 0
                
                group = {
                    'category_name': category.display_name,
                    'priority': category.priority,
                    'highest_score': highest_score,
                    'results': sorted_results # 包含 (item, score) 的元组列表
                }
                final_groups.append(group)
        
        return final_groups

    def score_of_single_match(self, item, keyword, category):
        """计算单个关键词在指定分类下的匹配分数 (模仿Swift)"""
        if category in (MatchCategory.STOCK_SYMBOL, MatchCategory.ETF_SYMBOL):
            return self.match_symbol(item.get('symbol', '').lower(), keyword)
        elif category in (MatchCategory.STOCK_NAME, MatchCategory.ETF_NAME):
            return self.match_name(item.get('name', '').lower(), keyword)
        elif category in (MatchCategory.STOCK_TAG, MatchCategory.ETF_TAG):
            return self.match_tags([t.lower() for t in item.get('tag', [])], keyword)
        elif category in (MatchCategory.STOCK_DESCRIPTION, MatchCategory.ETF_DESCRIPTION):
            desc1 = item.get('description1', '').lower()
            desc2 = item.get('description2', '').lower()
            return self.match_description(desc1, desc2, keyword)
        return 0

    def match_symbol(self, symbol, keyword):
        if symbol == keyword: return 3
        if keyword in symbol: return 2
        if self.levenshtein_distance(symbol, keyword) <= 1: return 1
        return 0

    def match_name(self, name, keyword):
        if name == keyword: return 4
        # 检查是否是完整的单词匹配
        if f" {keyword} " in f" {name} " or name.startswith(f"{keyword} ") or name.endswith(f" {keyword}"): return 3
        if keyword in name: return 2
        if self.levenshtein_distance(name, keyword) <= 1: return 1
        return 0

    def match_tags(self, tags, keyword):
        max_score = 0
        for tag in tags:
            score = 0
            if tag == keyword: score = 3
            elif keyword in tag: score = 2
            elif self.levenshtein_distance(tag, keyword) <= 1: score = 1
            max_score = max(max_score, score)
        return max_score

    def match_description(self, desc1, desc2, keyword):
        full_desc = desc1 + " " + desc2
        words = full_desc.split()
        if keyword in words: return 2
        if keyword in full_desc: return 1
        return 0

    def levenshtein_distance(self, s1, s2):
        if len(s1) < len(s2): return self.levenshtein_distance(s2, s1)
        if len(s2) == 0: return len(s1)
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


# CollapsibleWidget 类无变化
class CollapsibleWidget(QWidget):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet("QToolButton { border: none; font: bold 16px; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self.on_toggle)
        self.content_area = QWidget()
        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(20, 0, 0, 0)
        self.content_area.setLayout(self.content_layout)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
    def on_toggle(self):
        checked = self.toggle_button.isChecked()
        self.content_area.setVisible(checked)
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
    def addContentWidget(self, widget: QWidget):
        self.content_layout.addWidget(widget)
        self.content_area.adjustSize()

# 数据库和文件加载函数无变化
def get_latest_etf_volume(etf_name):
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    if not os.path.exists(db_path): return "N/A"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT volume FROM ETFs WHERE name = ? ORDER BY date DESC LIMIT 1", (etf_name,))
        result = cursor.fetchone()
        conn.close()
        if result and result[0] is not None:
            return f"{int(result[0] / 1000)}K"
        else:
            return "N/A"
    except Exception:
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
    return compare_data

# MainWindow 类大部分无变化，除了 show_results
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("公司、股票和ETF搜索")
        self.setGeometry(300, 200, 1000, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.textChanged.connect(self.on_text_changed)
        self.input_field.setFixedHeight(40)
        self.input_field.setFont(QFont("Arial", 18))
        self.search_button = QPushButton("搜索")
        self.search_button.setFixedHeight(45)
        self.search_button.setFixedWidth(80)
        self.input_layout.addWidget(self.input_field)
        self.input_layout.addWidget(self.search_button)
        self.layout.addLayout(self.input_layout)

        self.suppress_history = len(sys.argv) > 1 and sys.argv[1] == "paste"
        self.search_history = SearchHistory()
        self.history_list = QListWidget(self)
        self.history_list.setMaximumHeight(200)
        self.history_list.setVisible(False)
        self.history_list.itemClicked.connect(self.use_history_item)
        self.history_list.setStyleSheet("""
            QListWidget { font-size: 16px; border: 1px solid #555; background-color: #2d2d2d; color: #ccc; outline: 0; }
            QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #444; }
            QListWidget::item:hover { background-color: #3a3a3a; }
            QListWidget::item:selected { background-color: #0078d7; color: white; }
        """)
        self.layout.insertWidget(1, self.history_list)

        # 重写 input_field 的事件以显示/隐藏历史
        self._orig_focus_in = self.input_field.focusInEvent
        self._orig_focus_out = self.input_field.focusOutEvent
        self._orig_key_press = self.input_field.keyPressEvent
        self._orig_mouse_press = self.input_field.mousePressEvent
        self.input_field.mousePressEvent = self._input_mouse_press
        self.input_field.focusInEvent = self._input_focus_in
        self.input_field.focusOutEvent = self._input_focus_out
        self.input_field.keyPressEvent = self._input_key_press

        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_history)

        self.loading_label = QLabel("正在搜索...", self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Arial", 14))
        self.loading_label.hide()
        self.layout.addWidget(self.loading_label)

        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_container = QWidget()
        self.results_layout = QVBoxLayout(self.result_container)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.result_container.setLayout(self.results_layout)
        self.result_scroll.setWidget(self.result_container)
        self.layout.addWidget(self.result_scroll)

        self.search_button.clicked.connect(self.start_search)
        self.input_field.returnPressed.connect(self.start_search)

        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(QKeySequence("Esc"))
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)

        self.compare_data = {}

    def start_search(self):
        keywords = self.input_field.text()
        if not keywords.strip():
            self.clear_results()
            return
        self.search_history.add(keywords.strip())
        self.hide_history()
        self.compare_data = load_compare_data()
        self.loading_label.show()
        self.clear_results()
        self.search_button.setEnabled(False)
        self.input_field.setEnabled(False)

        # 创建并启动 Worker
        self.worker = SearchWorker(keywords, json_path)
        self.worker.results_ready.connect(self.show_results)
        # 改动：改为 on_search_finished
        self.worker.finished.connect(self.on_search_finished)
        self.worker.start()

    def on_text_changed(self, text: str):
         if not text.strip():
             self.display_history()
         else:
             self.hide_history()
             
    def on_search_finished(self):
        # 恢复按钮和输入框状态
        self.loading_label.hide()
        self.search_button.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()

        # 如果是 paste 启动，就全选输入框内容，然后只做一次
        if getattr(self, "suppress_history", False):
            self.input_field.selectAll()
            self.suppress_history = False

    def clear_results(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    # --- 3. 简化 show_results 方法 ---
    def show_results(self, sorted_groups):
        # 检查是否有完全匹配symbol的结果，并自动打开
        search_term = self.input_field.text().strip().upper()
        if sorted_groups:
            first_group = sorted_groups[0]
            # 检查第一个组的第一个结果是否是 symbol 的完全匹配
            if "Symbol" in first_group['category_name']:
                first_item, first_score = first_group['results'][0]
                if first_item.get('symbol', '').upper() == search_term:
                    self.open_symbol(first_item['symbol'])

        # 这个循环现在总会执行，无论是否自动打开了图表
        for group_data in sorted_groups:
            category_name = group_data['category_name']
            results = group_data['results']
            
            group_widget = CollapsibleWidget(title=category_name)
            
            for item, score in results:
                symbol = item.get('symbol', '')
                name = item.get('name', '')
                tags = ' '.join(item.get('tag', []))
                compare_info = self.compare_data.get(symbol, "")
                
                # 根据 item 类型（stock/etf）构建显示文本
                if 'Stock' in category_name:
                    display_parts = [symbol]
                    if compare_info: display_parts.append(compare_info)
                    if name: display_parts.append(name)
                    if tags: display_parts.append(tags)
                    display_text = "  ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, 'white', 20)
                else: # ETF
                    latest_volume = get_latest_etf_volume(symbol)
                    display_parts = [symbol]
                    if compare_info: display_parts.append(compare_info)
                    if name: display_parts.append(name) # ETF也可能有name
                    if tags: display_parts.append(tags)
                    if latest_volume and latest_volume != "N/A": display_parts.append(latest_volume)
                    display_text = "  ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, 'white', 20)
                
                group_widget.addContentWidget(lbl)
            
            self.results_layout.addWidget(group_widget)

    # 以下方法保持不变...
    def create_result_label(self, display_text, symbol, color, font_size):
        lbl = ClickableLabel()
        lbl.setTextFormat(Qt.RichText)
        # 把“数字+前/后”这类子串渲染成淡黄色
        remainder = display_text[len(symbol):] if display_text.startswith(symbol) else display_text
        # 高亮 “31前” “29后” 这类
        # 匹配：一段数字后面跟 “前” 或 “后”
        pattern = r"(\d+(?:前|后))"
        # 替换成 <span style='color:#FFFF99'>…</span>
        remainder = re.sub(pattern,
                           r"<span style='color:#FFFF99'>\1</span>",
                           remainder)
        label_html = (
            f"<span style='line-height: 2.2; letter-spacing: 1px;'>"
            f"<span style='color: cyan; font-size: {font_size}px;'>{symbol}</span>"
            f"<span style='color: {color}; font-size: {font_size}px;'>{remainder}</span>"
            f"</span>"
        )
        lbl.setText(label_html)
        lbl.clicked.connect(lambda: self.handle_label_click(lbl, symbol))
        return lbl

    def handle_label_click(self, label, symbol):
        original_style = label.styleSheet()
        label.setStyleSheet(original_style + " background-color: white;")
        QTimer.singleShot(300, lambda: label.setStyleSheet(original_style))
        self.open_symbol(symbol)

    def open_symbol(self, symbol):
        if symbol:
            pyperclip.copy(symbol)
            stock_chart_path = '/Users/yanzhang/Documents/Financial_System/Query/Stock_Chart.py'
            try:
                subprocess.Popen([sys.executable, stock_chart_path, 'paste'])
            except Exception as e:
                print(f"无法打开图表脚本 {stock_chart_path}: {e}")

    def display_history(self):
        if getattr(self, "suppress_history", False): return
        self.history_list.clear()
        history_items = self.search_history.get_history()
        if history_items:
            for item in history_items: self.history_list.addItem(QListWidgetItem(item))
            self.history_list.setVisible(True)
            self.history_list.setFixedWidth(self.input_field.width())
            self.history_list.setCurrentRow(-1)
        else: self.history_list.setVisible(False)
    
    def _input_focus_in(self, event):
        self._orig_focus_in(event)
        if getattr(self, "suppress_history", False): return
        self.display_history()
        QTimer.singleShot(0, self.input_field.selectAll)

    def _input_mouse_press(self, event):
        self._orig_mouse_press(event)
        if getattr(self, "suppress_history", False): self.suppress_history = False
        self.display_history()

    def _input_focus_out(self, event):
        new_focus_widget = QApplication.focusWidget()
        if new_focus_widget == self.history_list: pass
        self._orig_focus_out(event)
        self.hide_timer.start(200)

    def _input_key_press(self, event):
        if self.history_list.isVisible() and self.history_list.count() > 0:
            key, current_row, num_items = event.key(), self.history_list.currentRow(), self.history_list.count()
            if key == Qt.Key_Down:
                next_row = min(current_row + 1, num_items - 1) if current_row != -1 else 0
                self.history_list.setCurrentRow(next_row)
                event.accept(); return
            elif key == Qt.Key_Up:
                next_row = max(current_row - 1, 0) if current_row != -1 else num_items - 1
                self.history_list.setCurrentRow(next_row)
                event.accept(); return
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                if current_row != -1 and self.history_list.item(current_row):
                    self.input_field.setText(self.history_list.item(current_row).text())
                    self.hide_history(); self.start_search()
                    event.accept(); return
                else:
                    self.hide_history(); self.start_search()
                    event.accept(); return
            elif key == Qt.Key_Escape:
                 self.hide_history(); event.accept(); return
        self._orig_key_press(event)

    def hide_history(self): self.history_list.setVisible(False)
    def use_history_item(self, item):
        self.input_field.setText(item.text())
        self.hide_history(); self.start_search()

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
            clipboard_content = pyperclip.paste()
            if clipboard_content:
                window.input_field.setText(clipboard_content)
                window.start_search()
    sys.exit(app.exec_())