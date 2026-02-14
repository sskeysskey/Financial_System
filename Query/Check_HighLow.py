import sys
import json
import os
from collections import OrderedDict
import subprocess

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 修改: 切换到 PyQt6 ---
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QLabel, QFrame,
    QMenu, QTabWidget  # <--- 新增 QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer 
# --- 修改: 引入 QShortcut, QKeySequence ---
from PyQt6.QtGui import QCursor, QColor, QFont, QAction, QShortcut, QKeySequence

sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# 常量 / 全局配置
# ----------------------------------------------------------------------
MAX_ITEMS_PER_COLUMN = 11

# 文件路径
HIGH_LOW_PATH = os.path.join(BASE_CODING_DIR, "News", "HighLow.txt")
CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")
COLORS_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Colors.json")
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")

HIGH_LOW_5Y_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "HighLow.txt")
# ### 新增 ###: Volume High 文件路径
VOLUME_HIGH_PATH = os.path.join(BASE_CODING_DIR, "News", "0.5Y_volume_high.txt")

# 按钮＋标签固定宽度（像素）
SYMBOL_WIDGET_FIXED_WIDTH = 150

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ----------------------------------------------------------------------
# Classes
# ----------------------------------------------------------------------
class SymbolManager:
    def __init__(self, symbol_list):
        self.symbols = list(OrderedDict.fromkeys(symbol_list))
        self.current_index = -1
        if not self.symbols:
            print("Warning: SymbolManager received an empty list of symbols.")

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
            print(f"Warning: Symbol '{symbol}' not found in the manager's list.")

    def reset(self):
        self.current_index = -1

# ----------------------------------------------------------------------
# 工具 / 辅助函数
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
            python_path = sys.executable
            subprocess.Popen([python_path, script_path, keyword])
    except Exception as e:
        print(f"执行脚本 '{script_path}' 时发生错误: {e}")

def parse_high_low_file(path):
    data = OrderedDict()
    current_period = None
    current_category = None
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                current_period = line[1:-1]
                data[current_period] = {'Low': [], 'High': []}
                current_category = None
            elif line.lower() == 'low:':
                if current_period: current_category = 'Low'
            elif line.lower() == 'high:':
                if current_period: current_category = 'High'
            elif current_period and current_category:
                symbols = [symbol.strip() for symbol in line.split(',') if symbol.strip()]
                data[current_period][current_category].extend(symbols)
    return data

# ### 新增 ###: 解析 Volume High 文件的函数
def parse_volume_high_file(path):
    """
    解析格式如下的文件：
    ========== PRICE UP / FLAT (Top 2 Vol) ==========
    Sector Symbol Info Volume Tags...
    """
    data = OrderedDict()
    current_section = None
    
    if not os.path.exists(path):
        return data

    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            
            # 检测标题行
            if line.startswith("===") and line.endswith("==="):
                # 去除 === 和空格，获取纯标题
                current_section = line.replace("=", "").strip()
                data[current_section] = []
                continue
            
            # 解析数据行
            if current_section:
                parts = line.split()
                if len(parts) >= 4:
                    # 格式: Sector(0) Symbol(1) Info(2) Volume(3) Tags(4...)
                    item = {
                        'symbol': parts[1],
                        'info': parts[2], # e.g. 9.56% or 0212前...
                        'tags': " ".join(parts[4:]) # 拼接剩余部分作为 tags
                    }
                    data[current_section].append(item)
    return data

def load_json(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)

def load_text_data(path):
    data = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            key, value = map(str.strip, line.split(':', 1))
            cleaned_key = key.split()[-1]
            if ',' in value:
                parts = [p.strip() for p in value.split(',')]
                data[cleaned_key] = tuple(parts)
            else:
                data[cleaned_key] = value
    return data

# ----------------------------------------------------------------------
# PyQt6 主应用窗口
# ----------------------------------------------------------------------

class HighLowWindow(QMainWindow):
    # ### 修改 ###: 增加 volume_high_data 参数
    def __init__(self, high_low_data, keyword_colors, sector_data, compare_data, json_data, high_low_5y_data, volume_high_data):
        super().__init__()
        
        self.high_low_data = high_low_data
        self.keyword_colors = keyword_colors
        self.sector_data = sector_data
        self.compare_data = compare_data
        self.json_data = json_data
        self.high_low_5y_data = high_low_5y_data
        # ### 新增 ###
        self.volume_high_data = volume_high_data
        
        # --- 创建并初始化 SymbolManager ---
        all_symbols = []
        
        # 1. High/Low symbols
        for period_data in high_low_data.values():
            all_symbols.extend(period_data.get('Low', []))
            all_symbols.extend(period_data.get('High', []))
        
        # 2. 5Y High symbols
        five_y_high_symbols = self.high_low_5y_data.get('5Y', {}).get('High', [])
        all_symbols.extend(five_y_high_symbols)

        # ### 新增 ###: 3. Volume High symbols (确保可以通过键盘切换到这些 symbol)
        for section_items in self.volume_high_data.values():
            for item in section_items:
                all_symbols.append(item['symbol'])

        self.symbol_manager = SymbolManager(all_symbols)
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("High/Low & Volume Viewer")
        self.setGeometry(100, 100, 1600, 1000)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # --- 修改: 使用 QTabWidget 作为中心组件 ---
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1: 原始的 High/Low 页面
        self.tab_high_low = QWidget()
        self._init_high_low_tab(self.tab_high_low)
        self.tabs.addTab(self.tab_high_low, "High / Low")

        # Tab 2: 新增的 Volume High 页面
        self.tab_volume = QWidget()
        self._init_volume_tab(self.tab_volume)
        self.tabs.addTab(self.tab_volume, "Volume High")

        # --- 修改: 使用 QShortcut 强制捕获 Tab 键 ---
        self.tab_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Tab), self)
        self.tab_shortcut.activated.connect(self.switch_tab)

        self.apply_stylesheet()

    # --- 新增: 切换 Tab 的槽函数 ---
    def switch_tab(self):
        current_idx = self.tabs.currentIndex()
        next_idx = (current_idx + 1) % self.tabs.count()
        self.tabs.setCurrentIndex(next_idx)

    def _init_high_low_tab(self, parent_widget):
        # 原来的 ScrollArea 逻辑移到这里
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # 主布局
        main_layout = QHBoxLayout(scroll_content)
        scroll_content.setLayout(main_layout)

        # 1. LOW 区域
        low_main_container = QWidget()
        low_main_layout = QVBoxLayout(low_main_container)
        low_main_layout.setContentsMargins(10, 0, 10, 0)
        low_title = QLabel("新低")
        low_title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        low_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.low_columns_layout = QHBoxLayout()
        low_main_layout.addWidget(low_title)
        low_main_layout.addLayout(self.low_columns_layout)
        low_main_layout.addStretch(1)

        # 2. HIGH 区域
        high_main_container = QWidget()
        high_main_layout = QVBoxLayout(high_main_container)
        high_main_layout.setContentsMargins(10, 0, 10, 0)
        high_title = QLabel("新高")
        high_title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        high_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.high_columns_layout = QHBoxLayout()
        high_main_layout.addWidget(high_title)
        high_main_layout.addLayout(self.high_columns_layout)
        high_main_layout.addStretch(1)

        # 3. 5Y HIGH 区域
        high_5y_main_container = QWidget()
        high_5y_main_layout = QVBoxLayout(high_5y_main_container)
        high_5y_main_layout.setContentsMargins(10, 0, 10, 0)
        high_5y_title = QLabel("5Y HIGH")
        high_5y_title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        high_5y_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.high_5y_columns_layout = QHBoxLayout()
        high_5y_main_layout.addWidget(high_5y_title)
        high_5y_main_layout.addLayout(self.high_5y_columns_layout)
        high_5y_main_layout.addStretch(1)

        # 添加到主布局
        main_layout.addWidget(low_main_container)
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep1)
        main_layout.addWidget(high_main_container)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep2)
        main_layout.addWidget(high_5y_main_container)
        main_layout.addStretch(1)

        # 填充数据
        self._populate_category_columns(self.low_columns_layout, 'Low')
        self._populate_category_columns(self.high_columns_layout, 'High')
        self._populate_5y_high_section()

    # --- 新增: Volume Tab 的布局逻辑 ---
    def _init_volume_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # 使用水平布局来横向排列不同的 Section (Price Up, Price Down)
        main_layout = QHBoxLayout(scroll_content)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll_content.setLayout(main_layout)

        # 遍历解析到的数据，为每个 Section 创建一列
        for section_title, items in self.volume_high_data.items():
            # 容器
            section_container = QWidget()
            section_layout = QVBoxLayout(section_container)
            section_layout.setContentsMargins(10, 0, 10, 0)
            section_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            # 标题
            title_label = QLabel(section_title)
            title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setWordWrap(True) # 标题可能很长
            section_layout.addWidget(title_label)
            
            # 内容列容器 (用于分列显示)
            columns_layout = QHBoxLayout()
            section_layout.addLayout(columns_layout)
            
            # 填充内容 (复用分列逻辑)
            self._populate_volume_items(columns_layout, items)
            
            section_layout.addStretch(1)
            
            main_layout.addWidget(section_container)
            
            # 分隔符
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
            main_layout.addWidget(sep)

        main_layout.addStretch(1)

    def _populate_volume_items(self, parent_layout, items):
        """
        类似于 _populate_category_columns，但专门用于 Volume 数据结构
        """
        if not items: return

        current_column_layout = None
        
        # 简单的分列逻辑：每 MAX_ITEMS_PER_COLUMN 个项目一列
        for i, item in enumerate(items):
            if i % MAX_ITEMS_PER_COLUMN == 0:
                if current_column_layout:
                    current_column_layout.addStretch(1)
                    parent_layout.addLayout(current_column_layout)
                
                current_column_layout = QVBoxLayout()
                current_column_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            # 创建特殊的 Volume Widget
            # item 结构: {'symbol': 'HRB', 'info': '9.56%', 'tags': '税务...'}
            widget = self.create_symbol_widget(
                item['symbol'], 
                override_text=item['info'], 
                override_tags=item['tags']
            )
            current_column_layout.addWidget(widget)

        if current_column_layout:
            current_column_layout.addStretch(1)
            parent_layout.addLayout(current_column_layout)

    def apply_stylesheet(self):
        button_styles = {
            "Cyan": ("cyan", "black"), "Blue": ("blue", "white"),
            "Purple": ("purple", "white"), "Green": ("green", "white"),
            "White": ("white", "black"), "Yellow": ("yellow", "black"),
            "Orange": ("orange", "black"), "Red": ("red", "black"),
            "Black": ("black", "white"), "Default": ("#111111", "gray")
        }
        qss = ""
        for name, (bg, fg) in button_styles.items():
            qss += f"""
            QPushButton#{name} {{
                background-color: {bg};
                color: {fg};
                font-size: 16px;
                padding: 5px;
                border: 1px solid #333;
                border-radius: 4px;
                text-align: left;
                padding-left: 8px;
            }}
            QPushButton#{name}:hover {{
                background-color: {self.lighten_color(bg)};
            }}
            """
        qss += """
        QMenu {
            background-color: #2C2C2C;
            color: #E0E0E0;
            border: 1px solid #555;
        }
        QMenu::item {
            padding: 6px 25px 6px 20px;
            background: transparent;
        }
        QMenu::item:selected {
            background-color: #007ACC;
            color: white;
        }
        QMenu::separator {
            height: 1px;
            background: #555;
            margin: 4px 10px 4px 10px;
        }
        QGroupBox {
            font-size: 16px;
            font-weight: bold;
            margin-top: 15px;
            border: 1px solid gray;
            border-radius: 5px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 10px;
        }
        /* Tab 样式 */
        QTabWidget::pane { 
            border: 1px solid #444; 
        }
        QTabBar::tab {
            background: #2C2C2C;
            color: #AAA;
            padding: 8px 20px;
            border: 1px solid #444;
            border-bottom-color: #444; 
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected {
            background: #444;
            color: white;
            border-bottom-color: #444;
        }
        QTabBar::tab:hover {
            background: #383838;
        }
        """
        self.setStyleSheet(qss)

    def lighten_color(self, color_name, factor=1.2):
        color = QColor(color_name)
        h, s, l, a = color.getHslF()
        l = min(1.0, l * factor)
        color.setHslF(h, s, l, a)
        return color.name()

    def get_button_style_name(self, keyword):
        color_map = {
            "red": "Red", "cyan": "Cyan", "blue": "Blue", "purple": "Purple",
            "yellow": "Yellow", "orange": "Orange", "black": "Black",
            "white": "White", "green": "Green"
        }
        for color, style_name in color_map.items():
            if keyword in self.keyword_colors.get(f"{color}_keywords", []):
                return style_name
        return "Default"

    def _populate_category_columns(self, parent_layout, category_name):
        all_display_groups = []
        for period, categories in self.high_low_data.items():
            symbols = categories.get(category_name, [])
            if not symbols: continue

            original_title = f"{period} {category_name}"
            num_symbols = len(symbols)

            if num_symbols > MAX_ITEMS_PER_COLUMN:
                for i in range(0, num_symbols, MAX_ITEMS_PER_COLUMN):
                    symbol_chunk = symbols[i:i + MAX_ITEMS_PER_COLUMN]
                    chunk_index = (i // MAX_ITEMS_PER_COLUMN) + 1
                    chunk_title = f"{original_title} ({chunk_index})"
                    all_display_groups.append((chunk_title, symbol_chunk))
            else:
                all_display_groups.append((original_title, symbols))

        if not all_display_groups: return

        current_column_layout = None
        current_column_count = 0

        for title, symbols in all_display_groups:
            group_item_count = len(symbols)
            if current_column_layout is None or (current_column_count + group_item_count > MAX_ITEMS_PER_COLUMN):
                if current_column_layout is not None:
                    parent_layout.addLayout(current_column_layout)
                current_column_layout = QVBoxLayout()
                current_column_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                current_column_count = 0

            group_box = self._create_period_groupbox(title, symbols)
            current_column_layout.addWidget(group_box)
            current_column_count += group_item_count

        if current_column_layout is not None:
            parent_layout.addLayout(current_column_layout)

    def _populate_5y_high_section(self):
        symbols = self.high_low_5y_data.get('5Y', {}).get('High', [])
        if not symbols: return
        
        parent_layout = self.high_5y_columns_layout
        num_symbols = len(symbols)
        
        if num_symbols > MAX_ITEMS_PER_COLUMN:
            current_column_layout = None
            for i, symbol in enumerate(symbols):
                if i % MAX_ITEMS_PER_COLUMN == 0:
                    if current_column_layout is not None:
                        current_column_layout.addStretch(1)
                        parent_layout.addLayout(current_column_layout)
                    current_column_layout = QVBoxLayout()
                    current_column_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                
                widget = self.create_symbol_widget(symbol)
                current_column_layout.addWidget(widget)
            if current_column_layout is not None:
                current_column_layout.addStretch(1)
                parent_layout.addLayout(current_column_layout)
        else:
            column_layout = QVBoxLayout()
            column_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            for symbol in symbols:
                widget = self.create_symbol_widget(symbol)
                column_layout.addWidget(widget)
            column_layout.addStretch(1)
            parent_layout.addLayout(column_layout)

    def _create_period_groupbox(self, title, symbols):
        group_box = QGroupBox(title)
        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)
        for symbol in symbols:
            widget = self.create_symbol_widget(symbol)
            group_layout.addWidget(widget)
        return group_box

    def get_tags_for_symbol(self, symbol):
        for item in self.json_data.get("stocks", []):
            if item.get("symbol") == symbol: return item.get("tag", "无标签")
        for item in self.json_data.get("etfs", []):
            if item.get("symbol") == symbol: return item.get("tag", "无标签")
        return "无标签"
    
    def show_context_menu(self, symbol):
        menu = QMenu(self)
        actions = [
            ("查相似",  lambda: execute_external_script('similar', symbol)),
            ("富途查询",      lambda: execute_external_script('futu', symbol)),
            ("----",            None),
            ("编辑 Tags",     lambda: execute_external_script('tags', symbol)),
        ]
        for text, callback in actions:
            if callback is None:
                menu.addSeparator()
            else:
                act = menu.addAction(text)
                act.triggered.connect(callback)
        menu.exec(QCursor.pos())

    # ### 修改 ###: 增加可选参数 override_text
    def create_symbol_button(self, symbol, override_text=None):
        # 如果有 override_text (来自 volume 文件)，则显示它，否则去 compare_data 查找
        if override_text:
            button_text = f"{symbol} {override_text}"
        else:
            button_text = f"{symbol} {self.compare_data.get(symbol, '')}"
            
        button = QPushButton(button_text)
        button.setObjectName(self.get_button_style_name(symbol))
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))

        tags_info = self.get_tags_for_symbol(symbol)
        if isinstance(tags_info, list):
            tags_info = ", ".join(tags_info)
        button.setToolTip(f"<div style='font-size: 20px; background-color: lightyellow; color: black;'>{tags_info}</div>")

        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))
        return button

    def on_symbol_click(self, symbol):
        print(f"按钮 '{symbol}' 被点击，准备显示图表...")
        self.symbol_manager.set_current_symbol(symbol)
        
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        compare_value = self.compare_data.get(symbol, "N/A")
        
        try:
            plot_financial_data(
                DB_PATH, sector, symbol, compare_value, "N/A", None, "N/A", 
                self.json_data, '1Y', False, callback=self.handle_chart_callback
            )
            self.setFocus()
        except Exception as e:
            print(f"调用 plot_financial_data 时出错: {e}")
    
    def handle_chart_callback(self, action):
        if action == 'next':
            QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('next'))
        elif action == 'prev':
            QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('prev'))

    def navigate_symbol_from_chart(self, direction):
        symbol = None
        if direction == 'next': symbol = self.symbol_manager.next_symbol()
        elif direction == 'prev': symbol = self.symbol_manager.previous_symbol()
        if symbol: self.on_symbol_click(symbol)

    def handle_arrow_key(self, direction):
        if direction == 'down': symbol = self.symbol_manager.next_symbol()
        elif direction == 'up': symbol = self.symbol_manager.previous_symbol()
        else: return
        if symbol: self.on_symbol_click(symbol)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Down:
            self.handle_arrow_key('down')
        elif key == Qt.Key.Key_Up:
            self.handle_arrow_key('up')
        # 注意：Tab 键不再在此处处理，而是由 QShortcut 处理
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        print("Resetting symbol manager and quitting.")
        self.symbol_manager.reset()
        QApplication.quit()
        event.accept()

    # ### 修改 ###: 增加 override_text 和 override_tags 参数
    def create_symbol_widget(self, symbol, override_text=None, override_tags=None):
        # 1) 按钮
        button = self.create_symbol_button(symbol, override_text)
        button.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)

        # 2) 标签文本
        if override_tags:
            tags_info = override_tags
        else:
            tags_info = self.get_tags_for_symbol(symbol)
            if isinstance(tags_info, list):
                tags_info = ", ".join(tags_info)

        label = ClickableLabel(tags_info)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        
        # 自动换行设置，防止 Tags 太多显示不全
        label.setWordWrap(True)

        if override_tags:
             # 简单的估算：每行约 20px
             fm = label.fontMetrics()
             rect = fm.boundingRect(0, 0, SYMBOL_WIDGET_FIXED_WIDTH, 1000, Qt.TextFlag.TextWordWrap, tags_info)
             label.setFixedHeight(rect.height() + 10)
        else:
             fm = label.fontMetrics()
             label.setFixedHeight(fm.height() + 14)

        label.setStyleSheet("""
            background-color: lightyellow;
            color: black;
            font-size: 14px; /* 稍微调小一点字体以容纳更多 tags */
            padding-left: 4px;
        """)
        
        label.clicked.connect(lambda: self.on_symbol_click(symbol))
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))
        
        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(2)
        vlay.addWidget(button)
        vlay.addWidget(label)
        container.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        return container

# ----------------------------------------------------------------------
# 主执行入口
# ----------------------------------------------------------------------

if __name__ == '__main__':
    print("正在加载数据...")
    try:
        high_low_data = parse_high_low_file(HIGH_LOW_PATH)
        keyword_colors = load_json(COLORS_PATH)
        json_data = load_json(DESCRIPTION_PATH)
        sector_data = load_json(SECTORS_ALL_PATH)
        compare_data = load_text_data(COMPARE_DATA_PATH)
        high_low_5y_data = parse_high_low_file(HIGH_LOW_5Y_PATH)
        
        # ### 新增 ###: 加载 Volume High 数据
        volume_high_data = parse_volume_high_file(VOLUME_HIGH_PATH)
        
        print("数据加载完成。")
    except FileNotFoundError as e:
        print(f"错误: 找不到文件 {e.filename}。请检查路径是否正确。")
        sys.exit(1)
    except Exception as e:
        print(f"加载数据时发生未知错误: {e}")
        sys.exit(1)

    app = QApplication(sys.argv)
    
    main_window = HighLowWindow(
        high_low_data,
        keyword_colors,
        sector_data,
        compare_data,
        json_data,
        high_low_5y_data,
        volume_high_data # ### 新增 ###
    )
    main_window.show()
    sys.exit(app.exec())