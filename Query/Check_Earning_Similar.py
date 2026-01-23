import sys
import json
import sqlite3
import os
from collections import OrderedDict
import subprocess
from decimal import Decimal
from datetime import datetime, date

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 修改 1: 导入调整 ---
# QAction 移动到了 QtGui
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QMenu,
    QGridLayout, QLineEdit, QMessageBox
)
from PyQt6.QtGui import QCursor, QAction
from PyQt6.QtCore import Qt, QTimer

sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
from Chart_input import plot_financial_data

DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
EARNINGS_FILE_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_new.txt")
EARNINGS_FILE_NEXT_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_next.txt")
EARNINGS_FILE_THIRD_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_third.txt")
EARNINGS_FILE_FOURTH_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_fourth.txt")
EARNINGS_FILE_FIFTH_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_fifth.txt")
TAGS_WEIGHT_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "tags_weight.json")

RELATED_SYMBOLS_LIMIT = 10
MAX_PER_COLUMN = 20

symbol_manager = None
compare_data = {}
sector_data = {}
json_data = {}
tags_weight_config = {}
DEFAULT_WEIGHT = Decimal('1')

# 新增：SymbolButton 子类
class SymbolButton(QPushButton):
    def mousePressEvent(self, event):
        # --- 修改 2: 枚举使用全名 (Qt.MouseButton.LeftButton) ---
        if event.button() == Qt.MouseButton.LeftButton:
            mods = event.modifiers()
            # --- 修改 3: 修饰键枚举 (Qt.KeyboardModifier) ---
            if mods & Qt.KeyboardModifier.AltModifier:
                execute_external_script('similar', self.text())
                return
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                execute_external_script('futu', self.text())
                return
        # 其他情况走原有行为（例如普通左键点击会触发 on_symbol_button_clicked）
        super().mousePressEvent(event)

class SymbolManager:
    def __init__(self, symbols_list):
        self.symbols = symbols_list
        self.current_index = -1
        if not self.symbols:
            print("Warning: No symbols loaded into SymbolManager.")

    def next_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index - 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        if symbol in self.symbols:
            self.current_index = self.symbols.index(symbol)
        else:
            print(f"Warning: Symbol {symbol} not found in the list.")

    def reset(self):
        self.current_index = -1

def parse_multiple_earnings_files(paths):
    merged = OrderedDict()
    all_symbols = []
    
    for p in paths:
        sched, syms = parse_earnings_file(p)
        for date_str, times in sched.items():
            merged.setdefault(date_str, OrderedDict())
            for tc, slist in times.items():
                merged[date_str].setdefault(tc, [])
                for s in slist:
                    if s not in merged[date_str][tc]:
                        merged[date_str][tc].append(s)
        for s in syms:
            if s not in all_symbols:
                all_symbols.append(s)
                
    for date_str, times in merged.items():
        ordered = OrderedDict()
        if 'BMO' in times: ordered['BMO'] = times['BMO']
        if 'AMC' in times: ordered['AMC'] = times['AMC']
        for tc, slist in times.items():
            if tc not in ordered:
                ordered[tc] = slist
        merged[date_str] = ordered
        
    merged = OrderedDict(sorted(merged.items()))
    return merged, all_symbols

def parse_earnings_file(path):
    earnings_schedule = OrderedDict()
    all_symbols = []
    try:
        with open(path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line: continue
                parts = [p.strip() for p in line.split(':')]
                if len(parts) == 3:
                    symbol, time_code, date_str = parts
                    tc = time_code.upper()
                    earnings_schedule.setdefault(date_str, OrderedDict())
                    earnings_schedule[date_str].setdefault(tc, [])
                    earnings_schedule[date_str][tc].append(symbol)
                    if symbol not in all_symbols:
                        all_symbols.append(symbol)
    except FileNotFoundError:
        print(f"Error: Earnings file not found at {path}")

    for date_str, times in earnings_schedule.items():
        sorted_times = OrderedDict()
        if 'BMO' in times: sorted_times['BMO'] = times['BMO']
        if 'AMC' in times: sorted_times['AMC'] = times['AMC']
        for tc, slist in times.items():
            if tc not in sorted_times:
                sorted_times[tc] = slist
        earnings_schedule[date_str] = sorted_times

    return OrderedDict(sorted(earnings_schedule.items())), all_symbols


def get_symbol_type(symbol):
    for item in json_data.get('stocks', []):
        if item.get('symbol') == symbol:
            return 'stock'
    for item in json_data.get('etfs', []):
        if item.get('symbol') == symbol:
            return 'etf'
    return None


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file, object_pairs_hook=OrderedDict)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading JSON from {path}: {e}")
        return {}


def load_text_data(path):
    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                key, value = map(str.strip, line.split(':', 1))
                cleaned_key = key.split()[-1]
                data[cleaned_key] = tuple(p.strip() for p in value.split(',')) if ',' in value else value
    except FileNotFoundError:
        print(f"Error: Text data file not found at {path}")
    return data


def fetch_mnspp_data_from_db(db_path, symbol):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?", (symbol,))
        result = cursor.fetchone()
    return result if result else ("N/A", None, "N/A", "--")


def get_tags_for_symbol(symbol):
    for category in ["stocks", "etfs"]:
        for item in json_data.get(category, []):
            if item.get("symbol") == symbol:
                return item.get("tag", "无标签")
    return "无标签"


def execute_external_script(script_type, keyword):
    script_configs = {
        'blacklist': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Blacklist.py'),
        'similar':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Search_Similar_Tag.py'),
        'tags':     os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'editor_earning': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Earning_DB.py'),
        'earning':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Earning.py'),
        'futu':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'kimi':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Check_Earning.scpt')
    }
    try:
        if script_type in ['futu', 'kimi']:
            subprocess.Popen(['osascript', script_configs[script_type], keyword])
        else:
            python_path = sys.executable
            subprocess.Popen([python_path, script_configs[script_type], keyword])
    except Exception as e:
        print(f"执行脚本时出错: {e}")


def load_weight_groups():
    try:
        with open(TAGS_WEIGHT_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            return {Decimal(k): v for k, v in raw_data.items()}
    except Exception as e:
        print(f"加载权重配置文件时出错: {e}")
        return {}


def find_tags_by_symbol_b(symbol, data):
    tags_with_weight = []
    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            if item.get('symbol') == symbol:
                for tag in item.get('tag', []):
                    weight = tags_weight_config.get(tag, DEFAULT_WEIGHT)
                    tags_with_weight.append((tag, weight))
                return tags_with_weight
    return []


def find_symbols_by_tags_b(target_tags_with_weight, data, original_symbol):
    related = {'stocks': [], 'etfs': []}
    target_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}

    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            sym = item.get('symbol')
            if sym == original_symbol:
                continue
            tags = item.get('tag', [])
            matched = []
            used = set()

            for tag in tags:
                tl = tag.lower()
                if tl in target_dict and tl not in used:
                    matched.append((tag, target_dict[tl]))
                    used.add(tl)

            for tag in tags:
                tl = tag.lower()
                if tl in used:
                    continue
                for tgt, w in target_dict.items():
                    if tgt in tl or tl in tgt:
                        if tl != tgt and tgt not in used:
                            weight_to_use = Decimal('1.0') if w > Decimal('1.0') else w
                            matched.append((tag, weight_to_use))
                            used.add(tgt)
                        break

            if matched:
                total = sum(w for _, w in matched)
                related[category].append((sym, total))

    for cat in related:
        related[cat].sort(key=lambda x: x[1], reverse=True)

    stype = get_symbol_type(original_symbol)
    order = ['etfs', 'stocks'] if stype == 'etf' else ['stocks', 'etfs']
    combined = []
    for cat in order:
        combined.extend(related[cat])
    return combined

# --- 新增的辅助函数 ---
def calculate_earnings_price_change(symbol, db_path, sector_data):
    """
    计算自上次财报日以来的股价变化百分比。
    """
    fallback_text = "..."
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()

            # 1. 获取最新财报日期
            cursor.execute("SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1", (symbol,))
            result = cursor.fetchone()
            if not result:
                return fallback_text
            earnings_date = result[0]

            # 2. 获取symbol所属的表名 (sector)
            table_name = None
            for sector, symbols_list in sector_data.items():
                if symbol in symbols_list:
                    table_name = sector
                    break
            if not table_name:
                return fallback_text
            
            # 3. 获取财报日收盘价
            # 注意：表名不能用 '?' 参数化，但由于表名来自受控的json文件，这里是安全的
            query_earnings_price = f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?'
            cursor.execute(query_earnings_price, (symbol, earnings_date))
            result = cursor.fetchone()
            if not result:
                return fallback_text
            earnings_price = result[0]

            # 4. 获取最新收盘价
            query_latest_price = f'SELECT price FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1'
            cursor.execute(query_latest_price, (symbol,))
            result = cursor.fetchone()
            if not result:
                return fallback_text
            latest_price = result[0]

            # 5. 计算百分比
            if earnings_price is None or latest_price is None or earnings_price == 0:
                return fallback_text
            
            percentage_change = ((latest_price - earnings_price) / earnings_price) * 100
            
            return f"{percentage_change:+.1f}%"

    except Exception as e:
        print(f"Error calculating price change for {symbol}: {e}")
        return fallback_text

# --- 新增：从 b.py 移植的核心颜色决策函数 ---
def get_color_decision_data(symbol: str, db_path: str, sector_data: dict) -> tuple[float | None, str | None, date | None]:
    """
    获取决定按钮颜色所需的所有数据。
    返回: (latest_earning_price, stock_price_trend, latest_earning_date)
          - stock_price_trend: 'rising', 'falling', 'single', 或 None
    """
    try:
        # 步骤 1: 获取最近两次财报信息
        with sqlite3.connect(db_path, timeout=60.0) as conn:
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
            return latest_earning_price, 'single', latest_earning_date

        previous_earning_date_str, _ = earning_rows[1]
        previous_earning_date = datetime.strptime(previous_earning_date_str, "%Y-%m-%d").date()

        # 步骤 2: 查找 sector 表名
        sector_table = next((s for s, names in sector_data.items() if symbol in names), None)
        if not sector_table:
            return latest_earning_price, None, latest_earning_date

        # 步骤 3: 获取两个日期的收盘价
        with sqlite3.connect(db_path, timeout=60.0) as conn:
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
        
        # 步骤 4: 判断趋势
        trend = 'rising' if latest_stock_price > previous_stock_price else 'falling'
        
        return latest_earning_price, trend, latest_earning_date

    except Exception as e:
        print(f"[颜色决策数据获取错误] {symbol}: {e}")
        return None, None, None

# --- 新增：将颜色决策逻辑封装为独立函数 ---
def determine_button_colors(symbol):
    """
    根据复杂的财报和股价逻辑，决定按钮的背景色和前景色。
    返回 (background_color, text_color) 元组。
    """
    earning_price, price_trend, _ = get_color_decision_data(symbol, DB_PATH, sector_data)

    # 定义颜色映射 (背景色, 前景色)
    color_map = {
        'red': ('red', 'white'),
        'dark_cyan': ('#008B8B', 'white'),
        'purple': ('#912F2F', 'white'),
        'green': ('green', 'white'),
        'white': ('white', 'black'),
        'default': ('#ddd', 'black')
    }

    if earning_price is None or price_trend is None:
        return color_map['default']

    if price_trend == 'single':
        if earning_price > 0:
            return color_map['red']
        elif earning_price < 0:
            return color_map['green']
        else:
            return color_map['white']
    else:
        is_price_positive = earning_price > 0
        is_trend_rising = price_trend == 'rising'

        if is_trend_rising and is_price_positive:
            return color_map['red']
        elif not is_trend_rising and is_price_positive:
            return color_map['dark_cyan']
        elif is_trend_rising and not is_price_positive:
            return color_map['purple']
        elif not is_trend_rising and not is_price_positive:
            return color_map['green']
    
    return color_map['default'] # 备用


class EarningsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.button_mapping = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("财报日历查看器 (新颜色方案)")
        # --- 修改 4: FocusPolicy 枚举 ---
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 搜索栏
        top_widget = QWidget()
        top_lay = QHBoxLayout(top_widget)
        self.search_line = QLineEdit()
        self.search_button = QPushButton("搜索 Symbol")
        self.search_button.setObjectName("SearchButton")  # 新增：为搜索按钮设置独立的对象名
        top_lay.addWidget(self.search_line)
        top_lay.addWidget(self.search_button)
        self.search_line.setPlaceholderText("输入要搜索的 Symbol，然后按回车或点击“搜索 Symbol”")
        self.search_line.returnPressed.connect(self.on_search)
        self.search_button.clicked.connect(self.on_search)

        # 主滚动区
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout = QHBoxLayout(self.scroll_content)
        # --- 修改 5: AlignmentFlag 枚举 ---
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        container = QWidget()
        container_l = QVBoxLayout(container)
        container_l.setContentsMargins(0, 0, 0, 0)
        container_l.addWidget(top_widget)
        container_l.addWidget(self.scroll_area)
        self.setCentralWidget(container)

        self.apply_stylesheet()
        self.populate_ui()

    def apply_stylesheet(self):
        # --- 修改：移除旧的基于ID的颜色样式，改为通用的按钮样式 ---
        qss = """
        SymbolButton {
            font-size: 16px;
            padding: 5px;
            border: 1px solid #333;
            border-radius: 4px;
        }
        SymbolButton:hover {
            border: 1px solid #0078d7;
        }
        QGroupBox { 
            font-size: 16px; 
            font-weight: bold; 
            margin-top: 10px; 
        }
        QPushButton { 
            font-size: 14px; 
            padding: 5px; 
            border: 1px solid #aaa; 
            border-radius: 4px;
            background-color: #f0f0f0;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        QPushButton#PercentBadge {
            background-color: #333333;
            color: #FFFFFF;
            font-weight: 600;
            border: 1px solid #000;
            border-radius: 4px;
            padding: 4px 6px;
        }
        QPushButton#PercentBadge:hover {
            background-color: #3d3d3d;
        }
        /* 新增：搜索按钮使用深色主题 */
        QPushButton#SearchButton {
            background-color: #222831;      /* 深色背景 */
            color: #FFFFFF;                  /* 字体白色 */
            border: 1px solid #0E1116;       /* 深色边框 */
        }
        QPushButton#SearchButton:hover {
            background-color: #31363F;       /* 悬停时稍亮 */
        }
        """
        self.setStyleSheet(qss)

    # --- 移除了 lighten_color 和 get_button_style_name 函数 ---

    def on_search(self):
        key = self.search_line.text().strip().upper()
        if not key:
            return
        
        if key not in self.button_mapping:
            QMessageBox.information(self, "未找到", f"Symbol “{key}” 不在当前列表中。")
            return
        
        # 解包获取两个按钮
        btn, _, _, related_btn = self.button_mapping[key]
        
        # 确保可见
        QTimer.singleShot(100, lambda: self.scroll_area.ensureWidgetVisible(btn))
        
        # 2. 聚焦
        btn.setFocus()

        # === 高亮效果 ===
        # 使用亮青色(Cyan)或金色(Gold)边框模拟发光
        glow_border = "border: 3px solid #00FFFF; border-radius: 4px;" 

        old_btn_style = btn.styleSheet()
        old_rel_style = related_btn.styleSheet()

        # 叠加样式
        btn.setStyleSheet(old_btn_style + glow_border)
        related_btn.setStyleSheet(old_rel_style + glow_border)

        # 1.5秒后自动还原
        QTimer.singleShot(15000, lambda: self._restore_search_style(btn, related_btn, old_btn_style, old_rel_style))

    # 辅助函数，用于还原样式，避免lambda过长
    def _restore_search_style(self, btn, related_btn, old_btn_style, old_rel_style):
        try:
            btn.setStyleSheet(old_btn_style)
            related_btn.setStyleSheet(old_rel_style)
        except RuntimeError:
            pass

    def populate_ui(self):
        earnings_schedule, _ = parse_multiple_earnings_files([
            EARNINGS_FILE_PATH,
            EARNINGS_FILE_NEXT_PATH,
            EARNINGS_FILE_THIRD_PATH,
            EARNINGS_FILE_FOURTH_PATH,
            EARNINGS_FILE_FIFTH_PATH
        ])

        valid_symbols = set()
        for names in sector_data.values():
            valid_symbols.update(names)

        known_time_labels = {"BMO": "盘前 (BMO)", "AMC": "盘后 (AMC)", "TNS": "待定 (TNS)"}

        for date_str, times in earnings_schedule.items():
            # 日期分组
            date_group = QGroupBox(date_str)
            date_layout = QVBoxLayout()
            date_layout.setContentsMargins(10, 25, 10, 10)   # ← 留出标题高度
            date_layout.setSpacing(10)
            date_group.setLayout(date_layout)
            
            # --- 修改 6: AlignmentFlag 枚举 ---
            self.main_layout.addWidget(date_group, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            for tc, symbols in times.items():
                if not symbols:
                    continue
                time_group = QGroupBox(known_time_labels.get(tc, tc))
                time_layout = QGridLayout()
                time_layout.setContentsMargins(10, 20, 10, 10)  # ← 同样留出标题高度
                time_layout.setHorizontalSpacing(5)
                time_layout.setVerticalSpacing(5)
                time_group.setLayout(time_layout)
                date_layout.addWidget(time_group)

                for idx, sym in enumerate(symbols):
                    row = idx % MAX_PER_COLUMN
                    col_block = idx // MAX_PER_COLUMN
                    base_col = col_block * 3

                    txt = f"{sym}"
                    btn = SymbolButton(txt)
                    
                    # --- 修改部分：应用新的颜色逻辑 ---
                    bg_color, fg_color = determine_button_colors(sym)
                    btn.setStyleSheet(f"background-color: {bg_color}; color: {fg_color};")
                    # --- 修改结束 ---
                    
                    btn.clicked.connect(lambda _, s=sym: self.on_keyword_selected_chart(s))

                    # --- 修改部分开始 ---
                    # 调用新函数计算百分比
                    price_change_text = calculate_earnings_price_change(sym, DB_PATH, sector_data)
                    # 使用计算结果创建按钮
                    related = QPushButton(price_change_text)
                    related.setObjectName("PercentBadge")
                    related.setFixedWidth(80) # 适当加宽以容纳百分比文本
                    # --- 修改部分结束 ---

                    tags = get_tags_for_symbol(sym)
                    tags_str = ", ".join(tags) if isinstance(tags, list) else tags

                    self.button_mapping[sym] = (btn, date_group, time_group, related)
                    
                    btn.setToolTip(
                        f"<div style='font-size:20px;background-color:lightyellow;color:black;'>{tags_str}</div>")
                    
                    # --- 修改 7: ContextMenuPolicy 枚举 ---
                    btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    btn.customContextMenuRequested.connect(lambda pos, s=sym: self.show_context_menu(s))

                    # 相关容器
                    container = QWidget()
                    hl = QHBoxLayout(container)
                    hl.setContentsMargins(2, 2, 2, 2)
                    hl.setSpacing(5)
                    # --- 修改 8: AlignmentFlag 枚举 ---
                    hl.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    container.setVisible(False)

                    # 点击“相关”才动态计算并展开
                    related.clicked.connect(
                        lambda _, s=sym, c=container, vs=valid_symbols: self.toggle_related(s, c, vs)
                    )

                    time_layout.addWidget(btn, row, base_col)
                    time_layout.addWidget(related, row, base_col + 1)
                    time_layout.addWidget(container, row, base_col + 2)

    def toggle_related(self, sym, container, valid_symbols):
        # 如果还没有计算过，就动态计算并添加按钮
        layout = container.layout()
        if layout.count() == 0:
            tg = find_tags_by_symbol_b(sym, json_data)
            if tg:
                rels = find_symbols_by_tags_b(tg, json_data, sym)
                cnt = 0
                for r_sym, _ in rels:
                    if r_sym not in valid_symbols or cnt >= RELATED_SYMBOLS_LIMIT:
                        continue
                    rb = SymbolButton(f"{r_sym}")
                    
                    # --- 修改部分：为相关Symbol按钮也应用新的颜色逻辑 ---
                    bg_color, fg_color = determine_button_colors(r_sym)
                    rb.setStyleSheet(f"background-color: {bg_color}; color: {fg_color};")
                    # --- 修改结束 ---
                    
                    rb.clicked.connect(lambda _, s=r_sym: self.on_keyword_selected_chart(s))
                    rt = get_tags_for_symbol(r_sym)
                    rt_str = ", ".join(rt) if isinstance(rt, list) else rt
                    rb.setToolTip(
                        f"<div style='font-size:20px;background-color:lightyellow;color:black;'>{rt_str}</div>")
                    
                    # --- 修改 9: ContextMenuPolicy 枚举 ---
                    rb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    rb.customContextMenuRequested.connect(lambda pos, s=r_sym: self.show_context_menu(s))
                    layout.addWidget(rb)
                    cnt += 1
        # 切换显示/隐藏
        container.setVisible(not container.isVisible())

    def show_context_menu(self, keyword):
        menu = QMenu(self)
        acts = [
            ("在富途中搜索", lambda: execute_external_script('futu', keyword)),
            None,
            ("找相似", lambda: execute_external_script('similar', keyword)),
            None,
            ("编辑 Tags", lambda: execute_external_script('tags', keyword)),
            None,
            ("添加到 Earning", lambda: execute_external_script('earning', keyword)),
            ("编辑 Earing DB", lambda: execute_external_script('editor_earning', keyword)),
            ("Kimi检索财报", lambda: execute_external_script('kimi', keyword)),
            None,
            ("加入黑名单", lambda: execute_external_script('blacklist', keyword)),
        ]
        for item in acts:
            if item is None:
                menu.addSeparator()
            else:
                text, cb = item
                menu.addAction(QAction(text, self, triggered=cb))
        
        # --- 修改 10: exec_() -> exec() ---
        menu.exec(QCursor.pos())

    def on_keyword_selected_chart(self, sym):
        global symbol_manager
        sector = next((s for s, lst in sector_data.items() if sym in lst), None)
        if sector:
            symbol_manager.set_current_symbol(sym)
            cmp = compare_data.get(sym, "N/A")
            shares, mcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, sym)
            plot_financial_data(DB_PATH, sector, sym, cmp, (shares, pb), mcap, pe, json_data, '1Y', False)
            self.setFocus()

    def keyPressEvent(self, ev):
        k = ev.key()
        
        # 退出
        if k == Qt.Key.Key_Escape:
            self.close()
            
        # 向下切换 Symbol
        elif k == Qt.Key.Key_Down:
            self.on_arrow('down')
            
        # 向上切换 Symbol
        elif k == Qt.Key.Key_Up:
            self.on_arrow('up')
            
        # --- 新增功能：按 "/" 键聚焦搜索框 ---
        elif k == Qt.Key.Key_Slash:
            self.search_line.setFocus()   # 让光标跳到输入框
            self.search_line.selectAll()  # (可选) 选中框内已有文字，方便直接打字覆盖
            
        else:
            super().keyPressEvent(ev)

    def on_arrow(self, dir_):
        global symbol_manager
        sym = symbol_manager.next_symbol() if dir_ == 'down' else symbol_manager.previous_symbol()
        if sym:
            self.on_keyword_selected_chart(sym)

    def closeEvent(self, ev):
        global symbol_manager
        symbol_manager.reset()
        QApplication.quit()


if __name__ == '__main__':
    # --- 移除了 keyword_colors 的加载 ---
    json_data = load_json(DESCRIPTION_PATH)
    sector_data = load_json(SECTORS_ALL_PATH)
    compare_data = load_text_data(COMPARE_DATA_PATH)
    wg = load_weight_groups()
    tags_weight_config = {tag: w for w, tags in wg.items() for tag in tags}
    _, syms = parse_multiple_earnings_files([EARNINGS_FILE_PATH, EARNINGS_FILE_NEXT_PATH, EARNINGS_FILE_THIRD_PATH, EARNINGS_FILE_FOURTH_PATH, EARNINGS_FILE_FIFTH_PATH])
    symbol_manager = SymbolManager(syms)

    app = QApplication(sys.argv)
    win = EarningsWindow()
    win.showMaximized()
    # --- 修改 12: exec_() -> exec() ---
    sys.exit(app.exec())
