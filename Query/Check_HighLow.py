import sys
import json
import os
import sqlite3
import re
from collections import OrderedDict
import subprocess

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- PyQt6 引入 ---
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QLabel, QFrame,
    QMenu, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer 
from PyQt6.QtGui import QCursor, QColor, QFont, QShortcut, QKeySequence

# 外部绘图函数
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# 常量 / 全局配置
# ----------------------------------------------------------------------
MAX_ITEMS_PER_COLUMN = 9
SYMBOL_WIDGET_FIXED_WIDTH = 220

# 文件路径
HIGH_LOW_PATH = os.path.join(BASE_CODING_DIR, "News", "HighLow.txt")
CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")
COLORS_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Colors.json")
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
HIGH_LOW_5Y_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "HighLow.txt")
VOLUME_HIGH_PATH = os.path.join(BASE_CODING_DIR, "News", "0.5Y_volume_high.txt")
COMPARE_ETFS_PATH = os.path.join(BASE_CODING_DIR, "News", "CompareETFs.txt")
COMPARE_STOCK_PATH = os.path.join(BASE_CODING_DIR, "News", "CompareStock.txt")
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")

# 新增：10年新高数据路径
NEW_HIGH_10Y_PATH = os.path.join(BASE_CODING_DIR, "News", "10Y_newhigh_stock.txt")

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class SymbolManager:
    def __init__(self, symbol_list):
        self.update_symbols(symbol_list)

    def update_symbols(self, symbol_list):
        self.symbols = list(OrderedDict.fromkeys(symbol_list))
        self.current_index = -1

    def next_symbol(self):
        if not self.symbols: return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols: return None
        self.current_index = (self.current_index - 1 + len(self.symbols)) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        try:
            self.current_index = self.symbols.index(symbol)
        except ValueError:
            pass

    def reset(self):
        self.current_index = -1

# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------

def clean_ticker(symbol):
    """清洗 Symbol，去除中文后缀等，仅保留前面的字母和横杠"""
    match = re.search(r"^([A-Za-z-]+)", symbol)
    return match.group(1) if match else symbol

def calculate_frequency_data(history_data):
    """计算多组共振（次数统计）数据"""
    excluded_groups = {"season", "no_season", "_Tag_Blacklist"}
    support_level_groups = {"SupportLevel_Close", "SupportLevel_Over"}
    source_groups = {
        "Short", "Short_W", "Strategy12", "Strategy34", "OverSell_W",
        "PE_Deep", "PE_Deeper", "PE_W", "PE_valid", "PE_invalid",
        "PE_Volume", "PE_Volume_up", "PE_Hot", "PE_Volume_high"
    }
    
    # 新增：PE_Hot 的源头组
    pe_hot_sources = {
        "PE_Deep", "PE_Deeper", "PE_W", "OverSell_W", 
        "PE_valid", "PE_invalid", "season"
    }

    pe_chaodi_sources = {"PE_Null"}

    symbol_groups = {}
    # 记录哪些 Symbol 带有“抄底”后缀
    symbols_with_chaodi = set()
    
    # 1. 遍历所有分组
    for group, date_map in history_data.items():
        if group in excluded_groups:
            continue
        if not date_map:
            continue
            
        # 2. 获取该分组的最新日期
        sorted_dates = sorted(date_map.keys(), reverse=True)
        latest_date = sorted_dates[0]
        symbols = date_map[latest_date]
        
        # 3. 记录带有“抄底”的 Symbol
        for s in symbols:
            if "抄底" in s:
                symbols_with_chaodi.add(clean_ticker(s).upper())
        
        # 4. 清洗 Symbol 并去重
        clean_symbols = set(clean_ticker(s).upper() for s in symbols)
        
        # 5. 记录该 Symbol 所在的分组
        for sym in clean_symbols:
            if sym not in symbol_groups:
                symbol_groups[sym] = set()
            symbol_groups[sym].add(group)
            
    # 6. 按次数分组，并过滤掉无意义的 2 次共振
    count_to_symbols = {}
    for sym, groups in symbol_groups.items():
        
        # --- 核心修改点：过滤逻辑 ---
        
        # 逻辑 A: 如果存在 PE_Hot，剔除其源头组
        if "PE_Hot" in groups:
            groups = groups - pe_hot_sources
            
        # 逻辑 B: 如果 Symbol 带有“抄底”标记，且属于 PE_Volume_high (或者其他产生抄底的组)
        # 只要它带有“抄底”，就直接剔除 pe_hot_sources，防止它和这些组发生共振
        if sym in symbols_with_chaodi:
            groups = groups - pe_chaodi_sources
            
        count = len(groups)
        if count >= 2:
            # 特殊过滤逻辑：如果共振次数恰好为 2
            if count == 2:
                has_support = not groups.isdisjoint(support_level_groups)
                has_source = not groups.isdisjoint(source_groups)
                # 如果这 2 个分组刚好是一个衍生组配一个源头组，则毫无意义，直接跳过
                if has_support and has_source:
                    continue
            
            if count not in count_to_symbols:
                count_to_symbols[count] = []
            count_to_symbols[count].append(sym)
            
    # 7. 转换为数组，按次数降序排列，内部 Symbol 按字母排序
    result = []
    for count in sorted(count_to_symbols.keys(), reverse=True):
        result.append({
            'count': count,
            'symbols': sorted(count_to_symbols[count])
        })
    return result

def execute_external_script(script_type, keyword):
    script_configs = {
        'similar':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Search_Similar_Tag.py'),
        'tags':     os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'futu':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
    }
    script_path = script_configs.get(script_type)
    if not script_path: return
    try:
        if script_type in ['futu']:
            subprocess.Popen(['osascript', script_path, keyword])
        else:
            subprocess.Popen([sys.executable, script_path, keyword])
    except Exception as e:
        print(f"执行脚本错误: {e}")

def parse_high_low_file(path):
    data = OrderedDict()
    current_period, current_category = None, None
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                current_period = line[1:-1]
                data[current_period] = {'Low': [], 'High': []}
            elif line.lower() == 'low:': current_category = 'Low'
            elif line.lower() == 'high:': current_category = 'High'
            elif current_period and current_category:
                symbols = [s.strip() for s in line.split(',') if s.strip()]
                data[current_period][current_category].extend(symbols)
    return data

def parse_volume_high_file(path):
    data = OrderedDict()
    current_section = None
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            if line.startswith("===") and line.endswith("==="):
                current_section = line.replace("=", "").strip()
                data[current_section] = []
                continue
            if current_section:
                parts = line.split()
                if len(parts) >= 4:
                    data[current_section].append({
                        'symbol': parts[1],
                        'info': parts[2],
                        'tags': " ".join(parts[4:])
                    })
    return data

# 新增：解析 10年新高 文件
def parse_10y_newhigh_file(path):
    data = OrderedDict()
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            parts = line.split()
            if len(parts) >= 2:
                category = parts[0]
                symbol = parts[1]
                info = parts[2] if len(parts) > 2 else ""
                tags = " ".join(parts[3:]) if len(parts) > 3 else ""
                
                if category not in data:
                    data[category] = []
                data[category].append({
                    'symbol': symbol,
                    'info': info,
                    'tags': tags
                })
    return data

def parse_etf_file(path):
    items = []
    if not os.path.exists(path): return items
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                raw_symbol_part, content_part = line.split(':', 1)
                symbol = raw_symbol_part.split('.')[0].strip()
                parts = content_part.strip().split()
                if len(parts) >= 1:
                    items.append({
                        'symbol': symbol,
                        'percentage': parts[0],
                        'tags': " ".join(parts[3:]) if len(parts) > 3 else ""
                    })
    return items

def parse_stock_file(path):
    items = []
    if not os.path.exists(path): return items
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                left_part, right_part = line.split(':', 1)
                left_tokens = left_part.strip().split()
                if len(left_tokens) < 2: continue
                raw_symbol_str = left_tokens[1]
                if '.' in raw_symbol_str:
                    symbol, suffix_info = raw_symbol_str.split('.', 1)
                else:
                    symbol, suffix_info = raw_symbol_str, ""
                right_tokens = right_part.strip().split()
                if not right_tokens: continue
                percentage = right_tokens[0]
                tags = " ".join(right_tokens[1:]) if len(right_tokens) > 1 else ""
                items.append({
                    'symbol': symbol,
                    'suffix': suffix_info,
                    'display_text': f"{suffix_info} {percentage}" if suffix_info else percentage,
                    'tags': tags
                })
    return items

def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)

def load_text_data(path):
    data = {}
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                key, value = map(str.strip, line.split(':', 1))
                cleaned_key = key.split()[-1]
                data[cleaned_key] = value.split(',')[0].strip() if ',' in value else value
    return data

def fetch_mnspp_data_from_db(db_path, symbol):
    """从数据库获取财务数据"""
    if not os.path.exists(db_path):
        return "N/A", None, "N/A", "--"
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?"
            cursor.execute(query, (symbol,))
            result = cursor.fetchone()
            if result:
                return result  # 返回 (shares, marketcap, pe, pb)
            else:
                return "N/A", None, "N/A", "--"
    except Exception as e:
        print(f"查询财务数据出错: {e}")
        return "N/A", None, "N/A", "--"

# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------

class HighLowWindow(QMainWindow):
    def __init__(self, high_low_data, keyword_colors, sector_data, compare_data, json_data, high_low_5y_data, volume_high_data, etf_data, stock_data, earning_history_data, newhigh_10y_data):
        super().__init__()
        self.high_low_data = high_low_data
        self.keyword_colors = keyword_colors
        self.sector_data = sector_data
        self.compare_data = compare_data
        self.json_data = json_data
        self.high_low_5y_data = high_low_5y_data
        self.volume_high_data = volume_high_data
        self.etf_data = etf_data
        self.stock_data = stock_data
        self.earning_history_data = earning_history_data
        self.newhigh_10y_data = newhigh_10y_data
        
        # 计算多组共振数据
        self.resonance_data = calculate_frequency_data(self.earning_history_data)
        self.list_resonance = [sym for item in self.resonance_data for sym in item['symbols']]
        
        # 准备列表
        self.list_high_low = []
        for p in high_low_data.values():
            self.list_high_low.extend(p.get('Low', []) + p.get('High', []))
        self.list_high_low.extend(self.high_low_5y_data.get('5Y', {}).get('High', []))
        
        self.list_volume = [i['symbol'] for s in volume_high_data.values() for i in s]
        
        # 提取 10年新高 的所有 symbol 列表
        self.list_10y_newhigh = [item['symbol'] for items in self.newhigh_10y_data.values() for item in items]
        
        self.etf_gainers = [i['symbol'] for i in self.etf_data[:24]]
        self.etf_losers = [i['symbol'] for i in self.etf_data[-24:][::-1]]
        self.list_etf = self.etf_gainers + self.etf_losers
        
        self.stock_gainers = [i['symbol'] for i in self.stock_data[:24]]
        self.stock_losers = [i['symbol'] for i in self.stock_data[-24:][::-1]]
        self.list_stock = self.stock_gainers + self.stock_losers

        # 默认初始化为第一个 Tab 的数据
        self.symbol_manager = SymbolManager(self.list_resonance)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("High/Low & Volume Viewer")
        self.setGeometry(100, 100, 1600, 1000)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 0: 多组共振 (新增为第一个 Tab)
        self.tab_resonance = QWidget()
        self._init_resonance_tab(self.tab_resonance)
        self.tabs.addTab(self.tab_resonance, "多组共振")

        # Tab 1: Volume
        self.tab_volume = QWidget()
        self._init_volume_tab(self.tab_volume)
        self.tabs.addTab(self.tab_volume, "Volume成交额")

        # Tab 2: 10年新高 (新增)
        self.tab_10y_newhigh = QWidget()
        self._init_10y_newhigh_tab(self.tab_10y_newhigh)
        self.tabs.addTab(self.tab_10y_newhigh, "10年新高")

        # Tab 3: ETFs
        self.tab_etfs = QWidget()
        self._init_etf_tab(self.tab_etfs)
        self.tabs.addTab(self.tab_etfs, "ETFs")

        # Tab 4: Stocks
        self.tab_stocks = QWidget()
        self._init_stock_tab(self.tab_stocks)
        self.tabs.addTab(self.tab_stocks, "Stocks")

        # Tab 5: High/Low
        self.tab_high_low = QWidget()
        self._init_high_low_tab(self.tab_high_low)
        self.tabs.addTab(self.tab_high_low, "High / Low")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QShortcut(QKeySequence(Qt.Key.Key_Tab), self).activated.connect(self.switch_tab)
        QShortcut(QKeySequence("Shift+Tab"), self).activated.connect(self.switch_tab_reverse)

        self.apply_stylesheet()

    def on_tab_changed(self, index):
        mapping = {
            0: self.list_resonance,
            1: self.list_volume, 
            2: self.list_10y_newhigh, # 新增映射
            3: self.list_etf, 
            4: self.list_stock, 
            5: self.list_high_low
        }
        self.symbol_manager.update_symbols(mapping.get(index, []))

    def switch_tab(self): self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())
    def switch_tab_reverse(self): self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1 + self.tabs.count()) % self.tabs.count())

    # --- Tab 初始化方法 ---
    def _init_resonance_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        
        for item in self.resonance_data:
            count = item['count']
            symbols = item['symbols']
            col_lay = QHBoxLayout()
            title = f"共振 {count} 个分组 ({len(symbols)}只)"
            main_lay.addWidget(self._create_section_container(title, col_lay))
            
            for chunk in [symbols[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(symbols), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for sym in chunk:
                    col.addWidget(self.create_symbol_widget(sym))
                col.addStretch(1); col_lay.addLayout(col)
                
            self._add_separator(main_lay)

    def _init_high_low_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        
        self.low_columns_layout = QHBoxLayout()
        main_lay.addWidget(self._create_section_container("新低", self.low_columns_layout))
        self._add_separator(main_lay)
        self.high_columns_layout = QHBoxLayout()
        main_lay.addWidget(self._create_section_container("新高", self.high_columns_layout))
        self._add_separator(main_lay)
        self.high_5y_columns_layout = QHBoxLayout()
        main_lay.addWidget(self._create_section_container("5Y HIGH", self.high_5y_columns_layout))
        
        self._populate_category_columns(self.low_columns_layout, 'Low')
        self._populate_category_columns(self.high_columns_layout, 'High')
        self._populate_5y_high_section()

    def _init_volume_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        for title, items in self.volume_high_data.items():
            col_lay = QHBoxLayout()
            main_lay.addWidget(self._create_section_container(title, col_lay))
            self._populate_volume_items(col_lay, items)
            self._add_separator(main_lay)

    # 新增：10年新高 Tab 初始化
    def _init_10y_newhigh_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QVBoxLayout(content)
        
        for category, items in self.newhigh_10y_data.items():
            # 创建一个水平布局来容纳该分类的一行
            row_lay = QHBoxLayout()
            
            # --- 核心修改：在布局开头添加弹簧 ---
            row_lay.addStretch(1)
            
            # 左侧分类名 (垂直居中)
            cat_label = QLabel(category)
            cat_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            cat_label.setFixedWidth(200)
            cat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cat_label.setWordWrap(True)
            cat_label.setStyleSheet("background-color: #3A3A3A; color: #E0E0E0; border-radius: 8px; padding: 15px;")
            
            left_vlay = QVBoxLayout()
            left_vlay.addStretch()
            left_vlay.addWidget(cat_label)
            left_vlay.addStretch()
            row_lay.addLayout(left_vlay)
            
            # 右侧 Symbols 列表
            sym_lay = QHBoxLayout()
            for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for item in chunk:
                    col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['info'], override_tags=item['tags'], force_default=True))
                col.addStretch(1)
                sym_lay.addLayout(col)
                
            row_lay.addLayout(sym_lay)
            
            # --- 核心修改：在布局结尾添加弹簧 ---
            row_lay.addStretch(1)
            
            main_lay.addLayout(row_lay)
            self._add_separator_horizontal(main_lay)
            
        main_lay.addStretch(1)

    def _init_etf_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        top_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Gainers", top_lay))
        self._populate_etf_grid(top_lay, self.etf_data[:24])
        self._add_separator(main_lay)
        bot_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Losers", bot_lay))
        self._populate_etf_grid(bot_lay, self.etf_data[-24:][::-1])

    def _init_stock_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        top_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Gainers", top_lay))
        self._populate_stock_grid(top_lay, self.stock_data[:24])
        self._add_separator(main_lay)
        bot_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Losers", bot_lay))
        self._populate_stock_grid(bot_lay, self.stock_data[-24:][::-1])

    # --- 填充逻辑 ---
    def _populate_etf_grid(self, parent_layout, items):
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for item in chunk:
                # ETF 强制使用 Default 颜色
                col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['percentage'], override_tags=item['tags'], force_default=True))
            col.addStretch(1); parent_layout.addLayout(col)

    def _populate_stock_grid(self, parent_layout, items):
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for item in chunk:
                # 检查是否为财报 (后缀包含前或后)
                is_earnings = any(k in (item.get('suffix') or "") for k in ["前", "后"])
                style = "Earnings" if is_earnings else "Default"
                col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['display_text'], override_tags=item['tags'], force_style=style))
            col.addStretch(1); parent_layout.addLayout(col)

    def _populate_volume_items(self, parent_layout, items):
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for item in chunk:
                # Volume 强制使用 Default 颜色
                col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['info'], override_tags=item['tags'], force_default=True))
            col.addStretch(1); parent_layout.addLayout(col)

    def _populate_category_columns(self, parent_layout, cat):
        groups = []
        for p, cats in self.high_low_data.items():
            syms = cats.get(cat, [])
            if not syms: continue
            for i in range(0, len(syms), MAX_ITEMS_PER_COLUMN):
                groups.append((f"{p} {cat}" + (f" ({i//MAX_ITEMS_PER_COLUMN+1})" if len(syms)>MAX_ITEMS_PER_COLUMN else ""), syms[i:i+MAX_ITEMS_PER_COLUMN]))
        
        curr_col, curr_count = None, 0
        for title, syms in groups:
            if curr_col is None or (curr_count + len(syms) > MAX_ITEMS_PER_COLUMN):
                if curr_col: parent_layout.addLayout(curr_col)
                curr_col = QVBoxLayout(); curr_col.setAlignment(Qt.AlignmentFlag.AlignTop); curr_count = 0
            
            box = QGroupBox(title)
            b_lay = QVBoxLayout(box)
            
            # --- 关键修改：增加顶部边距 (Left, Top, Right, Bottom) ---
            # Top 设置为 35，确保卡片不会遮挡 GroupBox 的标题
            b_lay.setContentsMargins(8, 35, 8, 8) 
            b_lay.setSpacing(6) # 卡片之间的间距
            
            for s in syms: 
                b_lay.addWidget(self.create_symbol_widget(s)) 
            
            curr_col.addWidget(box)
            curr_count += len(syms)
        if curr_col: parent_layout.addLayout(curr_col)

    def _populate_5y_high_section(self):
        syms = self.high_low_5y_data.get('5Y', {}).get('High', [])
        for chunk in [syms[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(syms), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for s in chunk: col.addWidget(self.create_symbol_widget(s)) # High/Low 使用原配色
            col.addStretch(1); self.high_5y_columns_layout.addLayout(col)

    # --- 辅助方法 ---
    def _create_section_container(self, title_text, layout_ref):
        c = QWidget(); v = QVBoxLayout(c); v.setContentsMargins(10,0,10,0)
        t = QLabel(title_text); t.setFont(QFont("Arial", 20, QFont.Weight.Bold)); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t); v.addLayout(layout_ref); v.addStretch(1); return c

    def _add_separator(self, layout):
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine); sep.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(sep)

    def _add_separator_horizontal(self, layout):
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(sep)

    def apply_stylesheet(self):
        # 基础配色定义
        button_styles = {
            "Cyan": ("cyan", "black"), "Blue": ("blue", "white"),
            "Purple": ("purple", "white"), "Green": ("green", "white"),
            "White": ("white", "black"), "Yellow": ("yellow", "black"),
            "Orange": ("orange", "black"), "Red": ("red", "black"),
            "Black": ("black", "white"), "Default": ("#111111", "gray"),
            "Earnings": ("#111111", "red") # 财报样式：背景黑，文字红
        }
        qss = ""
        for name, (bg, fg) in button_styles.items():
            qss += f"QPushButton#{name} {{ background-color: {bg}; color: {fg}; font-size: 16px; padding: 5px; border: 1px solid #333; border-radius: 4px; text-align: left; padding-left: 8px; }}\n"
            qss += f"QPushButton#{name}:hover {{ background-color: {self.lighten_color(bg)}; }}\n"
        
        # --- 关键修改：QGroupBox 样式 ---
        qss += """
            QGroupBox { 
                font-size: 18px; 
                font-weight: bold; 
                margin-top: 25px;  /* 增加外边距 */
                border: 2px solid #555; 
                border-radius: 8px; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                padding: 0 5px; 
                left: 10px;
                top: 5px; /* 调整标题垂直位置 */
                color: #EEE;
            }
        """
        qss += "QMenu { background-color: #2C2C2C; color: #E0E0E0; border: 1px solid #555; }\n"
        qss += "QTabBar::tab:selected { background: #444; color: white; }\n"
        self.setStyleSheet(qss)

    def lighten_color(self, color_name, factor=1.2):
        if color_name.startswith("#111"): return "#222222"
        color = QColor(color_name); h, s, l, a = color.getHslF()
        color.setHslF(h, s, min(1.0, l * factor), a); return color.name()

    def get_button_style_name(self, symbol, force_default=False, force_style=None):
        # 如果强制指定了样式（如 Earnings 或 Default）
        if force_style: return force_style
        if force_default: return "Default"
        
        # 否则走 High/Low 的关键词配色逻辑
        color_map = {"red": "Red", "cyan": "Cyan", "blue": "Blue", "purple": "Purple", "yellow": "Yellow", "orange": "Orange", "black": "Black", "white": "White", "green": "Green"}
        for color, style_name in color_map.items():
            if symbol in self.keyword_colors.get(f"{color}_keywords", []):
                return style_name
        return "Default"

    def create_symbol_widget(self, symbol, override_text=None, override_tags=None, force_default=False, force_style=None):
        # 1. 按钮创建
        btn_text = f"{symbol} {override_text if override_text else self.compare_data.get(symbol, '')}"
        button = QPushButton(btn_text)
        button.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        button.setObjectName(self.get_button_style_name(symbol, force_default, force_style))
        
        tags_info = override_tags if override_tags else self.get_tags_for_symbol(symbol)
        if isinstance(tags_info, list): tags_info = ", ".join(tags_info)
        
        # 2. 标签部分 (实现自适应高度)
        label = ClickableLabel(tags_info)
        label.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        label.setWordWrap(True)
        # 垂直居中对齐
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # --- 【关键修改点 1：设置字体大小】 ---
        font_size = 16  # 你想设置的字体大小 (单位: pt 或 px)
        font = QFont("Arial", font_size)
        label.setFont(font) 
        
        # --- 【关键修改点 2：动态高度计算逻辑】 ---
        # 这里的 padding 必须与下方 StyleSheet 里的 padding 保持一致
        padding_h = 16  # 左右内边距总和 (left 8 + right 8)
        padding_v = 12  # 上下内边距总和 (top 6 + bottom 6)
        
        fm = label.fontMetrics() # 这里现在会基于 16px 的字体进行计算
        
        # 计算在固定宽度下，文本自动换行所需的矩形大小
        # 参数说明: (x, y, 限制宽度, 最大高度, 换行标志, 文本内容)
        rect = fm.boundingRect(
            0, 0, 
            SYMBOL_WIDGET_FIXED_WIDTH - padding_h, 
            5000, # 给一个足够大的上限
            Qt.TextFlag.TextWordWrap, 
            tags_info
        )
        
        # 最终高度 = 文本计算高度 + 上下边距
        # 设置一个最小高度（如 28），防止没字时卡片消失
        calculated_height = rect.height() + padding_v
        final_height = max(calculated_height, 35) # 字体变大后，最小高度也相应调高
        
        label.setFixedHeight(final_height)
        
        # --- 【关键修改点 3：更新样式表】 ---
        label.setStyleSheet(f"""
            background-color: lightyellow;
            color: black;
            font-size: {font_size}px; 
            padding-left: 8px;
            padding-right: 8px;
            padding-top: 6px;
            padding-bottom: 6px;
            border-radius: 4px;
            border: 1px solid #e0e0d0;
        """)

        # 事件绑定
        label.clicked.connect(lambda: self.on_symbol_click(symbol))
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))

        # 容器封装
        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(4) 
        vlay.addWidget(button)
        vlay.addWidget(label)
        vlay.addStretch() # 重要：向下方挤压，确保容器高度由内容决定
        
        container.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        return container

    def get_tags_for_symbol(self, symbol):
        for item in self.json_data.get("stocks", []) + self.json_data.get("etfs", []):
            if item.get("symbol") == symbol: return item.get("tag", "无标签")
        return "无标签"
    
        # --- 修改点 2: 添加动态计算子分类和索引的方法 ---
    def get_symbol_group_info(self, symbol):
        current_tab = self.tabs.currentIndex()

        # Tab 0: 多组共振
        if current_tab == 0:
            for item in self.resonance_data:
                if symbol in item['symbols']:
                    idx = item['symbols'].index(symbol)
                    return f"共振{item['count']}组 ({idx + 1}/{len(item['symbols'])})"

        # Tab 1: Volume High
        elif current_tab == 1:
            for group_name, items in self.volume_high_data.items():
                symbols_in_group = [item['symbol'] for item in items]
                if symbol in symbols_in_group:
                    idx = symbols_in_group.index(symbol)
                    return f"{group_name} ({idx + 1}/{len(symbols_in_group)})"

        # Tab 2: 10年新高
        elif current_tab == 2:
            for group_name, items in self.newhigh_10y_data.items():
                symbols_in_group = [item['symbol'] for item in items]
                if symbol in symbols_in_group:
                    idx = symbols_in_group.index(symbol)
                    return f"{group_name} ({idx + 1}/{len(symbols_in_group)})"

        # Tab 3: ETFs
        elif current_tab == 3:
            if symbol in self.etf_gainers:
                idx = self.etf_gainers.index(symbol)
                return f"Top Gainers ({idx + 1}/{len(self.etf_gainers)})"
            elif symbol in self.etf_losers:
                idx = self.etf_losers.index(symbol)
                return f"Top Losers ({idx + 1}/{len(self.etf_losers)})"

        # Tab 4: Stocks
        elif current_tab == 4:
            if symbol in self.stock_gainers:
                idx = self.stock_gainers.index(symbol)
                return f"Top Gainers ({idx + 1}/{len(self.stock_gainers)})"
            elif symbol in self.stock_losers:
                idx = self.stock_losers.index(symbol)
                return f"Top Losers ({idx + 1}/{len(self.stock_losers)})"

        # Tab 5: High/Low
        curr_list = self.symbol_manager.symbols
        if symbol in curr_list:
            return f"({curr_list.index(symbol) + 1}/{len(curr_list)})"
        
        return ""

    def on_symbol_click(self, symbol):
        self.symbol_manager.set_current_symbol(symbol)
        
        # --- 修改点 3: 使用新方法获取标题文本 ---
        group_info = self.get_symbol_group_info(symbol)
        pos_str = f"{symbol} {group_info}".strip()
        
        # --- 新增：获取财务数据 ---
        shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, symbol)
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        
        try:
            # --- 修改：将获取到的真实数据传入 plot_financial_data ---
            plot_financial_data(
                DB_PATH, 
                sector, 
                symbol, 
                self.compare_data.get(symbol, "N/A"), 
                (shares_val, pb),   # 对应 share 参数，传入元组 (shares, pb)
                marketcap,          # 对应 marketcap 参数
                pe,                 # 对应 pe 参数
                self.json_data, 
                '1Y', 
                False, 
                callback=self.handle_chart_callback, 
                window_title_text=pos_str  # <--- 这里传入了新的标题格式
            )
            self.setFocus()
        except Exception as e: print(f"绘图错误: {e}")

    def handle_chart_callback(self, action):
        if action == 'next': QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('next'))
        elif action == 'prev': QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('prev'))

    def navigate_symbol_from_chart(self, direction):
        s = self.symbol_manager.next_symbol() if direction == 'next' else self.symbol_manager.previous_symbol()
        if s: self.on_symbol_click(s)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
        elif event.key() == Qt.Key.Key_Down: self.navigate_symbol_from_chart('next')
        elif event.key() == Qt.Key.Key_Up: self.navigate_symbol_from_chart('prev')
        else: super().keyPressEvent(event)

    def show_context_menu(self, symbol):
        menu = QMenu(self)
        menu.addAction("查相似").triggered.connect(lambda: execute_external_script('similar', symbol))
        menu.addAction("富途查询").triggered.connect(lambda: execute_external_script('futu', symbol))
        menu.addSeparator()
        menu.addAction("编辑 Tags").triggered.connect(lambda: execute_external_script('tags', symbol))
        menu.exec(QCursor.pos())

    def closeEvent(self, event):
        self.symbol_manager.reset(); QApplication.quit(); event.accept()

if __name__ == '__main__':
    try:
        hl = parse_high_low_file(HIGH_LOW_PATH)
        colors = load_json(COLORS_PATH)
        desc = load_json(DESCRIPTION_PATH)
        sects = load_json(SECTORS_ALL_PATH)
        comp = load_text_data(COMPARE_DATA_PATH)
        hl5y = parse_high_low_file(HIGH_LOW_5Y_PATH)
        vol = parse_volume_high_file(VOLUME_HIGH_PATH)
        etf = parse_etf_file(COMPARE_ETFS_PATH)
        stk = parse_stock_file(COMPARE_STOCK_PATH)
        earn_hist = load_json(EARNING_HISTORY_PATH)
        
        # 新增：加载 10年新高 数据
        newhigh_10y = parse_10y_newhigh_file(NEW_HIGH_10Y_PATH)
        
        app = QApplication(sys.argv)
        # 传入 newhigh_10y
        win = HighLowWindow(hl, colors, sects, comp, desc, hl5y, vol, etf, stk, earn_hist, newhigh_10y)
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"启动失败: {e}")