import sys
import json
import os
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

# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------

class HighLowWindow(QMainWindow):
    def __init__(self, high_low_data, keyword_colors, sector_data, compare_data, json_data, high_low_5y_data, volume_high_data, etf_data, stock_data):
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
        
        # 准备列表
        self.list_high_low = []
        for p in high_low_data.values():
            self.list_high_low.extend(p.get('Low', []) + p.get('High', []))
        self.list_high_low.extend(self.high_low_5y_data.get('5Y', {}).get('High', []))
        self.list_volume = [i['symbol'] for s in volume_high_data.values() for i in s]
        self.list_etf = [i['symbol'] for i in (self.etf_data[:24] + self.etf_data[-24:][::-1])]
        self.list_stock = [i['symbol'] for i in (self.stock_data[:24] + self.stock_data[-24:][::-1])]

        self.symbol_manager = SymbolManager(self.list_volume)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("High/Low & Volume Viewer")
        self.setGeometry(100, 100, 1600, 1000)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1: Volume
        self.tab_volume = QWidget()
        self._init_volume_tab(self.tab_volume)
        self.tabs.addTab(self.tab_volume, "Volume High")

        # Tab 2: ETFs
        self.tab_etfs = QWidget()
        self._init_etf_tab(self.tab_etfs)
        self.tabs.addTab(self.tab_etfs, "ETFs")

        # Tab 3: Stocks
        self.tab_stocks = QWidget()
        self._init_stock_tab(self.tab_stocks)
        self.tabs.addTab(self.tab_stocks, "Stocks")

        # Tab 4: High/Low
        self.tab_high_low = QWidget()
        self._init_high_low_tab(self.tab_high_low)
        self.tabs.addTab(self.tab_high_low, "High / Low")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QShortcut(QKeySequence(Qt.Key.Key_Tab), self).activated.connect(self.switch_tab)
        QShortcut(QKeySequence("Shift+Tab"), self).activated.connect(self.switch_tab_reverse)

        self.apply_stylesheet()

    def on_tab_changed(self, index):
        mapping = {0: self.list_volume, 1: self.list_etf, 2: self.list_stock, 3: self.list_high_low}
        self.symbol_manager.update_symbols(mapping.get(index, []))

    def switch_tab(self): self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())
    def switch_tab_reverse(self): self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1 + self.tabs.count()) % self.tabs.count())

    # --- Tab 初始化方法 (逻辑同前，仅调用 create_symbol_widget 传参不同) ---
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
            box = QGroupBox(title); b_lay = QVBoxLayout(box)
            for s in syms: b_lay.addWidget(self.create_symbol_widget(s)) # High/Low 使用原配色
            curr_col.addWidget(box); curr_count += len(syms)
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
        qss += "QMenu { background-color: #2C2C2C; color: #E0E0E0; border: 1px solid #555; }\n"
        qss += "QGroupBox { font-size: 16px; font-weight: bold; margin-top: 15px; border: 1px solid gray; border-radius: 5px; }\n"
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
        
        # --- 动态高度计算逻辑 ---
        padding_h = 12  # 左右内边距总和 (left 6 + right 6)
        padding_v = 10  # 上下内边距总和 (top 5 + bottom 5)
        
        fm = label.fontMetrics()
        # 计算在固定宽度下，文本自动换行所需的矩形大小
        # 参数说明: (x, y, 限制宽度, 最大高度, 换行标志, 文本内容)
        rect = fm.boundingRect(
            0, 0, 
            SYMBOL_WIDGET_FIXED_WIDTH - padding_h, 
            2000, 
            Qt.TextFlag.TextWordWrap, 
            tags_info
        )
        
        # 最终高度 = 文本计算高度 + 上下边距
        # 设置一个最小高度（如 28），防止没字时卡片消失
        calculated_height = rect.height() + padding_v
        final_height = max(calculated_height, 28) 
        
        label.setFixedHeight(final_height)
        
        # 设置样式，确保 padding 和计算逻辑对应
        label.setStyleSheet(f"""
            background-color: lightyellow;
            color: black;
            font-size: 13px;
            padding-left: 6px;
            padding-right: 6px;
            padding-top: 5px;
            padding-bottom: 5px;
            border-radius: 3px;
            border: 1px solid #e0e0d0; /* 增加浅色边框更有质感 */
        """)

        # 事件绑定
        label.clicked.connect(lambda: self.on_symbol_click(symbol))
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))

        # 容器封装
        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(3) # 按钮和Tag卡片之间的微小间距
        vlay.addWidget(button)
        vlay.addWidget(label)
        vlay.addStretch() # 重要：向下方挤压，确保容器高度由内容决定
        
        container.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        return container

    def get_tags_for_symbol(self, symbol):
        for item in self.json_data.get("stocks", []) + self.json_data.get("etfs", []):
            if item.get("symbol") == symbol: return item.get("tag", "无标签")
        return "无标签"

    def on_symbol_click(self, symbol):
        self.symbol_manager.set_current_symbol(symbol)
        curr_list = self.symbol_manager.symbols
        pos_str = f"{symbol} ({curr_list.index(symbol)+1}/{len(curr_list)})" if symbol in curr_list else symbol
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        try:
            plot_financial_data(DB_PATH, sector, symbol, self.compare_data.get(symbol, "N/A"), "N/A", None, "N/A", 
                                self.json_data, '1Y', False, callback=self.handle_chart_callback, window_title_text=pos_str)
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
        app = QApplication(sys.argv)
        win = HighLowWindow(hl, colors, sects, comp, desc, hl5y, vol, etf, stk)
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"启动失败: {e}")