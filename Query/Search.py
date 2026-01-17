import os
import re
import sys
import json
import pyperclip
import subprocess
import sqlite3
import pickle
import platform # <--- 新增
from datetime import datetime, date
from enum import Enum

# --- 1. 迁移到 PyQt6 ---
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QMainWindow, QScrollArea, QToolButton, QSizePolicy,
    QListWidget, QListWidgetItem, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QAction

# ================= 配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

# 3. 具体业务文件路径
JSON_DESCRIPTION_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
SEARCH_HISTORY_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "search_history.pkl")
COMPARE_ALL_PATH = os.path.join(NEWS_BACKUP_DIR, "Compare_All.txt")
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
STOCK_CHART_SCRIPT = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Stock_Chart.py")

# ========================================================

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
        self.item_type = item_type 

class SearchHistory:
    def __init__(self, max_size=20):
        self.max_size = max_size
        self.history_file = SEARCH_HISTORY_PATH
        self.history = self.load_history()

    def add(self, query):
        if query in self.history: self.history.remove(query)
        self.history.insert(0, query)
        if len(self.history) > self.max_size: self.history = self.history[:self.max_size]
        self.save_history()

    def get_history(self): return self.history

    def load_history(self):
        try:
            if not os.path.exists(self.history_file): return []
            with open(self.history_file, 'rb') as f: return pickle.load(f)
        except: return []

    def save_history(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'wb') as f: pickle.dump(self.history, f)
        except Exception as e: print(f"保存搜索历史失败: {e}")

class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        # PyQt6: 枚举更新
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._mouse_pressed_pos = None

    def mousePressEvent(self, event):
        self._mouse_pressed_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed_pos and (event.pos() - self._mouse_pressed_pos).manhattanLength() < 5:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

class SearchWorker(QThread):
    results_ready = pyqtSignal(object)

    def __init__(self, keywords, json_path, use_or=False):
        super().__init__()
        self.keywords_str = keywords
        self.json_path = json_path
        self.use_or = use_or

    def run(self):
        grouped_results = self.unified_search()
        sorted_grouped_results = sorted(
            grouped_results,
            key=lambda g: (g['highest_score'], g['priority']),
            reverse=True
        )
        self.results_ready.emit(sorted_grouped_results)

    def unified_search(self):
        try:
            if not os.path.exists(self.json_path): return []
            with open(self.json_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
        except Exception as e:
            print(f"Error reading JSON file: {e}")
            return []

        keywords = [k for k in self.keywords_str.lower().split() if k]
        if not keywords: return []

        raw_results = {cat: [] for cat in MatchCategory}
        all_items = [('stock', item) for item in data.get('stocks', [])] + \
                    [('etf', item) for item in data.get('etfs', [])]

        for item_type, item in all_items:
            for category in MatchCategory:
                if category.item_type != item_type: continue
                
                if self.use_or:
                    total_score = 0
                    for kw in keywords:
                        s = self.score_of_single_match(item, kw, category)
                        if s > 0: total_score += s
                    if total_score > 0: raw_results[category].append((item, total_score))
                else:
                    total_score = 0
                    all_match = True
                    for kw in keywords:
                        s = self.score_of_single_match(item, kw, category)
                        if s <= 0:
                            all_match = False
                            break
                        total_score += s
                    if all_match: raw_results[category].append((item, total_score))

        final_groups = []
        for category, results_list in raw_results.items():
            if results_list:
                sorted_results = sorted(results_list, key=lambda x: x[1], reverse=True)
                highest_score = sorted_results[0][1]
                group = {
                    'category_name': category.display_name,
                    'priority': category.priority,
                    'highest_score': highest_score,
                    'results': sorted_results 
                }
                final_groups.append(group)
        return final_groups

    def score_of_single_match(self, item, keyword, category):
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
        name_words = name.split()
        if keyword in name_words: return 3
        if keyword in name: return 2
        for word in name_words:
            if self.levenshtein_distance(word, keyword) <= 1: return 1
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

class CollapsibleWidget(QWidget):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet("QToolButton { border: none; font: bold 16px; }")
        # PyQt6: 枚举更新
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle_button.clicked.connect(self.on_toggle)
        self.content_area = QWidget()
        self.content_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def addContentWidget(self, widget: QWidget):
        self.content_layout.addWidget(widget)
        self.content_area.adjustSize()

def get_latest_etf_volume(etf_name):
    if not os.path.exists(DB_PATH): return "N/A"
    try:
        conn = sqlite3.connect(DB_PATH, timeout=60.0)
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
        if os.path.exists(COMPARE_ALL_PATH):
            with open(COMPARE_ALL_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        symbol, value = line.strip().split(":", 1)
                        compare_data[symbol.strip()] = value.strip()
    except Exception as e:
        print(f"读取Compare_All.txt出错: {e}")
    return compare_data

def load_sectors_data():
    try:
        if os.path.exists(SECTORS_ALL_PATH):
            with open(SECTORS_ALL_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"读取 {SECTORS_ALL_PATH} 出错: {e}")
    return {}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("公司、股票和ETF搜索")
        self.setGeometry(300, 100, 1000, 800)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        self.input_layout = QHBoxLayout()
        # 搜索输入框
        self.input_field = QLineEdit()
        self.input_field.textChanged.connect(self.on_text_changed)
        self.input_field.setFixedHeight(40)
        # 跨平台字体
        self.input_field.setFont(QFont("Segoe UI" if os.name == 'nt' else "Arial", 18))
        self.input_layout.addWidget(self.input_field)
        
        # OR/AND 勾选框
        self.mode_checkbox = QCheckBox("OR")
        self.mode_checkbox.setToolTip("勾选后关键字空格为 OR，未勾选为 AND")
        self.input_layout.addWidget(self.mode_checkbox)
        
        # 搜索按钮
        self.search_button = QPushButton("搜索")
        self.search_button.setFixedHeight(45)
        self.search_button.setFixedWidth(80)
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
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setFont(QFont("Arial", 14))
        self.loading_label.hide()
        self.layout.addWidget(self.loading_label)

        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_container = QWidget()
        self.results_layout = QVBoxLayout(self.result_container)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.result_container.setLayout(self.results_layout)
        self.result_scroll.setWidget(self.result_container)
        self.layout.addWidget(self.result_scroll)

        self.search_button.clicked.connect(self.start_search)
        self.input_field.returnPressed.connect(self.start_search)

        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(QKeySequence("Esc"))
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)

        self.focus_search_action = QAction("Focus Search", self)
        self.focus_search_action.setShortcut(QKeySequence("/"))
        self.focus_search_action.triggered.connect(self.focus_search_input)
        self.addAction(self.focus_search_action)

        self._mnspp_cache = {}
        self._finance_db = DB_PATH
        self.compare_data = {}
        self.sector_data = load_sectors_data()

    def focus_search_input(self):
        self.input_field.setFocus()

    def start_search(self):
        keywords = self.input_field.text().strip()
        if not keywords:
            self.clear_results()
            return
        self.search_history.add(keywords)
        self.hide_history()
        self.compare_data = load_compare_data()
        self.loading_label.show()
        self.clear_results()
        self.search_button.setEnabled(False)
        self.input_field.setEnabled(False)
        use_or = self.mode_checkbox.isChecked()
        self.worker = SearchWorker(keywords, JSON_DESCRIPTION_PATH, use_or)
        self.worker.results_ready.connect(self.show_results)
        self.worker.finished.connect(self.on_search_finished)
        self.worker.start()

    def on_text_changed(self, text: str):
         if not text.strip():
             self.display_history()
         else:
             self.hide_history()

    def on_search_finished(self):
        self.loading_label.hide()
        self.search_button.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        if getattr(self, "suppress_history", False):
            self.input_field.selectAll()
            self.suppress_history = False

    def clear_results(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def get_color_decision_data(self, symbol: str) -> tuple[float | None, str | None, date | None]:
        try:
            if not os.path.exists(self._finance_db): return None, None, None
            with sqlite3.connect(self._finance_db, timeout=60.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT date, price FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 2",
                    (symbol,)
                )
                earning_rows = cursor.fetchall()
            if not earning_rows:
                return None, None, None
            latest_earning_date_str, latest_earning_price_str = earning_rows[0]
            latest_earning_date = datetime.strptime(latest_earning_date_str, "%Y-%m-%d").date()
            latest_earning_price = float(latest_earning_price_str) if latest_earning_price_str is not None else 0.0
            
            days_diff = (date.today() - latest_earning_date).days
            if days_diff > 75:
                return latest_earning_price, None, latest_earning_date
            
            if len(earning_rows) < 2:
                return latest_earning_price, None, latest_earning_date
            
            previous_earning_date_str, _ = earning_rows[1]
            previous_earning_date = datetime.strptime(previous_earning_date_str, "%Y-%m-%d").date()
            
            sector_table = next((s for s, names in self.sector_data.items() if symbol in names), None)
            if not sector_table:
                return latest_earning_price, None, latest_earning_date
            
            with sqlite3.connect(self._finance_db, timeout=60.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'SELECT price FROM "{sector_table}" WHERE name = ? AND date = ?',
                    (symbol, latest_earning_date.isoformat())
                )
                latest_stock_price_row = cursor.fetchone()
                cursor.execute(
                    f'SELECT price FROM "{sector_table}" WHERE name = ? AND date = ?',
                    (symbol, previous_earning_date.isoformat())
                )
                previous_stock_price_row = cursor.fetchone()
            
            if not latest_stock_price_row or not previous_stock_price_row:
                return latest_earning_price, None, latest_earning_date
            
            latest_stock_price = float(latest_stock_price_row[0])
            previous_stock_price = float(previous_stock_price_row[0])
            
            trend = 'rising' if latest_stock_price > previous_stock_price else 'falling'
            return latest_earning_price, trend, latest_earning_date
        except Exception as e:
            print(f"[颜色决策数据获取错误] {symbol}: {e}")
            return None, None, None

    def get_mnspp_marketcap(self, symbol: str) -> float:
        if not symbol: return 0.0
        if symbol in self._mnspp_cache: return self._mnspp_cache[symbol]
        mcap = 0.0
        try:
            if os.path.exists(self._finance_db):
                conn = sqlite3.connect(self._finance_db, timeout=60.0)
                cursor = conn.cursor()
                cursor.execute("SELECT marketcap FROM MNSPP WHERE symbol = ?", (symbol,))
                row = cursor.fetchone()
                conn.close()
                if row and row[0] is not None:
                    mcap = float(row[0])
        except Exception as e:
            print(f"[MNSPP 查询错误] {symbol}: {e}")
        self._mnspp_cache[symbol] = mcap
        return mcap
    
    def show_results(self, sorted_groups):
        search_term = self.input_field.text().strip().upper()
        if sorted_groups:
            first_group = sorted_groups[0]
            if "Symbol" in first_group['category_name']:
                first_item, _ = first_group['results'][0]
                if first_item.get('symbol', '').upper() == search_term:
                    self.open_symbol(first_item['symbol'])

        for group_data in sorted_groups:
            category_name = group_data['category_name']
            results = group_data['results']
            results = sorted(
                results,
                key=lambda x: (
                    x[1],
                    self.get_mnspp_marketcap(x[0].get("symbol", ""))
                ),
                reverse=True
            )
            
            group_widget = CollapsibleWidget(title=category_name)
            
            for item, score in results:
                symbol = item.get('symbol', '')
                name = item.get('name', '')
                tags = ' '.join(item.get('tag', []))
                compare_info = self.compare_data.get(symbol, "")
                
                earning_price, price_trend, _ = self.get_color_decision_data(symbol)
                
                sym_color = 'white'
                if earning_price is not None and price_trend is not None:
                    is_price_positive = earning_price > 0
                    is_trend_rising = price_trend == 'rising'
                    if is_trend_rising and is_price_positive:
                        sym_color = 'red'
                    elif not is_trend_rising and is_price_positive:
                        sym_color = '#008B8B'
                    elif is_trend_rising and not is_price_positive:
                        sym_color = '#912F2F'
                    elif not is_trend_rising and not is_price_positive:
                        sym_color = 'green'
                
                if 'Stock' in category_name:
                    display_parts = [symbol]
                    if compare_info: display_parts.append(compare_info)
                    if name: display_parts.append(name)
                    if tags: display_parts.append(tags)
                    display_text = "  ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, sym_color, 20)
                else: # ETF
                    latest_volume = get_latest_etf_volume(symbol)
                    display_parts = [symbol]
                    if compare_info: display_parts.append(compare_info)
                    if name: display_parts.append(name)
                    if tags: display_parts.append(tags)
                    if latest_volume and latest_volume != "N/A": display_parts.append(latest_volume)
                    display_text = "  ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, sym_color, 20)
                
                group_widget.addContentWidget(lbl)
            
            self.results_layout.addWidget(group_widget)

    def create_result_label(self, display_text, symbol, color, font_size):
        lbl = ClickableLabel()
        # PyQt6: 枚举更新
        lbl.setTextFormat(Qt.TextFormat.RichText)
        remainder = display_text[len(symbol):] if display_text.startswith(symbol) else display_text
        pattern = r"(\d+(?:前|后))"
        remainder = re.sub(pattern,
                            r"<span style='color:#FFFF99'>\1</span>",
                            remainder)
        label_html = (
            f"<span style='line-height: 2.2; letter-spacing: 1px;'>"
            f"<span style='color: {color}; font-size: {font_size}px;'>{symbol}</span>"
            f"<span style='color: #A9A9A9; font-size: {font_size}px;'>{remainder}</span>"
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
            try:
                # 使用 sys.executable 调用 Python
                subprocess.Popen([sys.executable, STOCK_CHART_SCRIPT, 'paste'])
            except Exception as e:
                print(f"无法打开图表脚本 {STOCK_CHART_SCRIPT}: {e}")

    def display_history(self):
        if getattr(self, "suppress_history", False): return
        self.history_list.clear()
        history_items = self.search_history.get_history()
        if history_items:
            for item in history_items: self.history_list.addItem(QListWidgetItem(item))
            self.history_list.setVisible(True)
            self.history_list.setFixedWidth(self.input_field.width())
            self.history_list.setCurrentRow(-1)
        else:
            self.history_list.setVisible(False)

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
            if key == Qt.Key.Key_Down:
                next_row = min(current_row + 1, num_items - 1) if current_row != -1 else 0
                self.history_list.setCurrentRow(next_row)
                event.accept(); return
            elif key == Qt.Key.Key_Up:
                next_row = max(current_row - 1, 0) if current_row != -1 else num_items - 1
                self.history_list.setCurrentRow(next_row)
                event.accept(); return
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if current_row != -1 and self.history_list.item(current_row):
                    self.input_field.setText(self.history_list.item(current_row).text())
                    self.hide_history(); self.start_search()
                    event.accept(); return
                else:
                    self.hide_history(); self.start_search()
                    event.accept(); return
            elif key == Qt.Key.Key_Escape:
                 self.hide_history(); event.accept(); return
        self._orig_key_press(event)

    def hide_history(self):
        self.history_list.setVisible(False)

    def use_history_item(self, item):
        self.input_field.setText(item.text())
        self.hide_history()
        self.start_search()

if __name__ == "__main__":
    # PyQt6 中不再需要 AA_EnableHighDpiScaling
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and sys.argv[1] == "paste":
        clipboard_content = pyperclip.paste()
        if clipboard_content:
            window.input_field.setText(clipboard_content)
            window.start_search()
    # PyQt6: 使用 exec()
    sys.exit(app.exec())
