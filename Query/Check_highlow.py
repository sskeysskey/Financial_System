import sys
import json
from collections import OrderedDict
import subprocess

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QLabel, QFrame,
    QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QColor, QFont

sys.path.append('/Users/yanzhang/Documents/Financial_System/Query')
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# 常量 / 全局配置
# ----------------------------------------------------------------------
# 如果一个时间段内的项目超过这个数量，则单独成为一列。
# 同时，这也是合并列中项目总数的上限。
MAX_ITEMS_PER_COLUMN = 11

# 文件路径
HIGH_LOW_PATH = '/Users/yanzhang/Documents/News/HighLow.txt'
CONFIG_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
COLORS_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
DESCRIPTION_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
SECTORS_ALL_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
SHARES_PATH = '/Users/yanzhang/Documents/News/backup/Shares.txt'
MARKETCAP_PATH = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'
# 按钮＋标签固定宽度（像素）
SYMBOL_WIDGET_FIXED_WIDTH = 150

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 鼠标变手型
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ----------------------------------------------------------------------
# Classes
# ----------------------------------------------------------------------
# --- 1. 从 panel.py 移植并修改 SymbolManager 类 ---
class SymbolManager:
    """
    一个更通用的 SymbolManager，直接接收一个 symbol 列表。
    """
    def __init__(self, symbol_list):
        # 使用 OrderedDict.fromkeys 来自动去重并保持顺序
        self.symbols = list(OrderedDict.fromkeys(symbol_list))
        self.current_index = -1
        if not self.symbols:
            print("Warning: SymbolManager received an empty list of symbols.")

    def next_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index - 1 + len(self.symbols)) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        try:
            self.current_index = self.symbols.index(symbol)
        except ValueError:
            print(f"Warning: Symbol '{symbol}' not found in the manager's list.")
            # 保持当前索引不变或重置
            # self.current_index = -1

    def reset(self):
        self.current_index = -1

# ----------------------------------------------------------------------
# 工具 / 辅助函数
# ----------------------------------------------------------------------

# --- 2. 从 panel.py 移植过来的函数 ---
def execute_external_script(script_type, keyword):
    """
    使用非阻塞方式执行外部脚本。
    """
    base_path = '/Users/yanzhang/Documents/Financial_System'
    # 我们只需要 'tags' 的配置，但为了完整性，可以保留其他配置
    script_configs = {
        'tags': f'{base_path}/Operations/Editor_Symbol_Tags.py',
        # ... 其他脚本配置可以放在这里 ...
    }

    script_path = script_configs.get(script_type)
    if not script_path:
        print(f"错误: 未知的脚本类型 '{script_type}'")
        return

    try:
        python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
        # 使用 Popen 进行非阻塞调用
        subprocess.Popen([python_path, script_path, keyword])
    except Exception as e:
        print(f"执行脚本 '{script_path}' 时发生错误: {e}")

# (其他辅助函数无变动)
def parse_high_low_file(path):
    data = OrderedDict()
    current_period = None
    current_category = None
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue

            if line.startswith('[') and line.endswith(']'):
                current_period = line[1:-1]
                data[current_period] = {'Low': [], 'High': []}
                current_category = None # 新周期开始，重置类别
            elif line.lower() == 'low:':
                if current_period:
                    current_category = 'Low'
            elif line.lower() == 'high:':
                if current_period:
                    current_category = 'High'
            elif current_period and current_category:
                # 这一行是 symbols
                symbols = [symbol.strip() for symbol in line.split(',') if symbol.strip()]
                data[current_period][current_category].extend(symbols)
    return data

def load_json(path):
    """加载 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)

def load_text_data(path):
    """加载文本文件数据，如 Compare_All.txt"""
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

def load_marketcap_pe_data(path):
    """加载市值和PE数据"""
    data = {}
    with open(path, 'r') as file:
        for line in file:
            key, values = map(str.strip, line.split(':', 1))
            parts = [p.strip() for p in values.split(',')]
            if len(parts) >= 2:
                marketcap_val, pe_val, *_ = parts
                data[key] = (float(marketcap_val), pe_val)
    return data

# ----------------------------------------------------------------------
# PyQt5 主应用窗口
# ----------------------------------------------------------------------
class HighLowWindow(QMainWindow):
    def __init__(self, high_low_data, keyword_colors, sector_data, compare_data, shares, marketcap_pe_data, json_data):
        super().__init__()
        
        # 将加载的数据存储为实例变量
        self.high_low_data = high_low_data
        self.keyword_colors = keyword_colors
        self.sector_data = sector_data
        self.compare_data = compare_data
        self.shares = shares
        self.marketcap_pe_data = marketcap_pe_data
        self.json_data = json_data
        
        # --- 2. 创建并初始化 SymbolManager ---
        # 从 high_low_data 构建一个扁平的、有序的 symbol 列表
        all_symbols = []
        
        # 第一步：先添加所有 Low 的 symbols
        for period_data in high_low_data.values():
            all_symbols.extend(period_data.get('Low', []))
            
        # 第二步：再添加所有 High 的 symbols
        for period_data in high_low_data.values():
            all_symbols.extend(period_data.get('High', []))
        
        # 将构建好的、具有正确顺序的列表传递给 SymbolManager
        self.symbol_manager = SymbolManager(all_symbols)
        # --- 【修改结束】 ---
        
        self.init_ui()

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle("High/Low Viewer")
        self.setGeometry(100, 100, 1600, 1000)

        # --- 【关键改动 1】: 设置焦点策略，让窗口能接收键盘事件 ---
        self.setFocusPolicy(Qt.StrongFocus)
        
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # 主布局：一个水平布局，容纳左右两个主要部分
        main_layout = QHBoxLayout(scroll_content)
        scroll_content.setLayout(main_layout)

        # --- 创建左侧 (LOW) 的主容器 ---
        low_main_container = QWidget()
        low_main_layout = QVBoxLayout(low_main_container)
        low_main_layout.setContentsMargins(10, 0, 10, 0)
        low_title = QLabel("LOW")
        low_title.setFont(QFont("Arial", 20, QFont.Bold))
        low_title.setAlignment(Qt.AlignCenter)
        
        # low_columns_layout 将水平容纳多个列
        self.low_columns_layout = QHBoxLayout()
        
        low_main_layout.addWidget(low_title)
        low_main_layout.addLayout(self.low_columns_layout)
        low_main_layout.addStretch(1) # 保证内容向上对齐

        # --- 创建右侧 (HIGH) 的主容器 ---
        high_main_container = QWidget()
        high_main_layout = QVBoxLayout(high_main_container)
        high_main_layout.setContentsMargins(10, 0, 10, 0)
        high_title = QLabel("HIGH")
        high_title.setFont(QFont("Arial", 20, QFont.Bold))
        high_title.setAlignment(Qt.AlignCenter)
        
        # high_columns_layout 将水平容纳多个列
        self.high_columns_layout = QHBoxLayout()

        high_main_layout.addWidget(high_title)
        high_main_layout.addLayout(self.high_columns_layout)
        high_main_layout.addStretch(1) # 保证内容向上对齐

        # --- 【关键改动 1】: 移除 addWidget 中的拉伸因子 ---
        # 之前是 addWidget(..., 1)，现在不带 '1'，让宽度自适应内容
        main_layout.addWidget(low_main_container)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        main_layout.addWidget(high_main_container)
        
        # 在末尾添加一个拉伸，这样所有内容会靠左对齐，而不是被拉伸以填满窗口
        main_layout.addStretch(1)

        self.apply_stylesheet()
        self.populate_ui()

    def apply_stylesheet(self):
        """创建并应用 QSS 样式表"""
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
            }}
            QPushButton#{name}:hover {{
                background-color: {self.lighten_color(bg)};
            }}
            """
        qss += """
        QGroupBox {
            font-size: 16px;
            font-weight: bold;
            margin-top: 15px;
            border: 1px solid gray;
            border-radius: 5px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center; /* 标题居中 */
            padding: 0 10px;
        }
        """
        self.setStyleSheet(qss)


    def lighten_color(self, color_name, factor=1.2):
        """一个简单的函数来让颜色变亮，用于:hover效果"""
        color = QColor(color_name)
        h, s, l, a = color.getHslF()
        l = min(1.0, l * factor)
        color.setHslF(h, s, l, a)
        return color.name()

    def get_button_style_name(self, keyword):
        """返回按钮的 objectName 以应用 QSS 样式 (从 a.py 借用)"""
        color_map = {
            "red": "Red", "cyan": "Cyan", "blue": "Blue", "purple": "Purple",
            "yellow": "Yellow", "orange": "Orange", "black": "Black",
            "white": "White", "green": "Green"
        }
        for color, style_name in color_map.items():
            if keyword in self.keyword_colors.get(f"{color}_keywords", []):
                return style_name
        return "Default"

    def populate_ui(self):
        """
        根据数据动态创建界面。超过阈值的项目将独立成列。
        """
        # 分别填充 Low 和 High 两大区域
        self._populate_category_columns(self.low_columns_layout, 'Low')
        self._populate_category_columns(self.high_columns_layout, 'High')

    def _populate_category_columns(self, parent_layout, category_name):
        """
        【关键改动】: 采用两步法：1. 扁平化数据 2. 应用统一的打包算法
        """
        # --- 步骤 1: 预处理和扁平化 ---
        # 创建一个统一的列表，其中所有分组都保证 <= 15 项。
        all_display_groups = []
        for period, categories in self.high_low_data.items():
            symbols = categories.get(category_name, [])
            if not symbols:
                continue

            original_title = f"{period} {category_name}"
            num_symbols = len(symbols)

            if num_symbols > MAX_ITEMS_PER_COLUMN:
                # 如果是“大分组”，则在此处将其拆分为带编号的小分组
                for i in range(0, num_symbols, MAX_ITEMS_PER_COLUMN):
                    symbol_chunk = symbols[i:i + MAX_ITEMS_PER_COLUMN]
                    chunk_index = (i // MAX_ITEMS_PER_COLUMN) + 1
                    chunk_title = f"{original_title} ({chunk_index})"
                    all_display_groups.append((chunk_title, symbol_chunk))
            else:
                # 如果是“小分组”，直接添加
                all_display_groups.append((original_title, symbols))

        # --- 步骤 2: 对扁平化后的列表应用统一的列打包算法 ---
        if not all_display_groups:
            return

        current_column_layout = None
        current_column_count = 0

        for title, symbols in all_display_groups:
            group_item_count = len(symbols)

            # 如果当前列无法容纳这个新分组，则“封箱”旧列，并创建新列
            if current_column_layout is None or (current_column_count + group_item_count > MAX_ITEMS_PER_COLUMN):
                # 如果当前列不是None（意味着它是一个已满的列），先把它添加到父布局中
                if current_column_layout is not None:
                    parent_layout.addLayout(current_column_layout)

                # 创建一个新列
                current_column_layout = QVBoxLayout()
                current_column_layout.setAlignment(Qt.AlignTop)
                current_column_count = 0  # 重置计数器

            # 将当前的 groupbox 添加到当前列中
            group_box = self._create_period_groupbox(title, symbols)
            current_column_layout.addWidget(group_box)
            current_column_count += group_item_count # 更新当前列的项目总数

        # 循环结束后，不要忘记添加最后一个正在构建的列
        if current_column_layout is not None:
            parent_layout.addLayout(current_column_layout)


    def _create_period_groupbox(self, title, symbols):
        """辅助函数，创建一个包含所有symbol按钮的GroupBox"""
        group_box = QGroupBox(title)
        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        for symbol in symbols:
            # 用新的小容器替代单个按钮
            widget = self.create_symbol_widget(symbol)
            group_layout.addWidget(widget)
        
        return group_box

    # --- 【新增方法】: 从 panel.py 移植过来的标签查找函数 ---
    def get_tags_for_symbol(self, symbol):
        """
        根据 symbol 在 self.json_data 中查找 tag 信息。
        这模拟了 panel.py 中的行为，遍历 'stocks' 和 'etfs' 列表。
        """
        for item in self.json_data.get("stocks", []):
            if item.get("symbol") == symbol:
                return item.get("tag", "无标签")
        for item in self.json_data.get("etfs", []):
            if item.get("symbol") == symbol:
                return item.get("tag", "无标签")
        return "无标签"
    
    # --- 3. 新增方法：用于创建和显示右键菜单 ---
    def show_context_menu(self, symbol):
        """
        创建并显示一个只包含“编辑 Tags”的右键菜单。
        """
        menu = QMenu()
        
        # 创建一个 QAction
        edit_tags_action = QAction("编辑 Tags", self)
        
        # 将其 triggered 信号连接到执行外部脚本的函数
        edit_tags_action.triggered.connect(
            lambda: execute_external_script('tags', symbol)
        )
        
        # 将 QAction 添加到菜单中
        menu.addAction(edit_tags_action)
        
        # 在当前鼠标位置显示菜单
        menu.exec_(QCursor.pos())

    def create_symbol_button(self, symbol):
        """辅助函数，用于创建一个配置好的 symbol 按钮。"""
        button_text = f"{symbol} {self.compare_data.get(symbol, '')}"
        button = QPushButton(button_text)
        button.setObjectName(self.get_button_style_name(symbol))
        button.setCursor(QCursor(Qt.PointingHandCursor))
        # 使用 lambda 捕获当前的 symbol 值
        button.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))

        # --- 【关键修改】: 调用新的辅助函数并美化 Tooltip ---
        tags_info = self.get_tags_for_symbol(symbol)
        
        # 如果返回的是列表（尽管在此函数中不会），将其转换为字符串
        if isinstance(tags_info, list):
            tags_info = ", ".join(tags_info)
            
        # 使用富文本格式化 Tooltip，就像 panel.py 中一样
        button.setToolTip(f"<div style='font-size: 20px; background-color: lightyellow; color: black;'>{tags_info}</div>")

        # --- 4. 启用并连接右键菜单 ---
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(
            # 使用 lambda 忽略 pos 参数，只传递 symbol
            lambda pos, s=symbol: self.show_context_menu(s)
        )
        # --- 修改结束 ---

        return button

    def on_symbol_click(self, symbol):
        # --- 3. 在点击时更新 SymbolManager 并设置焦点 ---
        print(f"按钮 '{symbol}' 被点击，准备显示图表...")
        
        # 告诉管理器当前查看的是哪个 symbol
        self.symbol_manager.set_current_symbol(symbol)
        
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        if not sector:
            print(f"警告: 在 Sectors_All.json 中找不到 '{symbol}' 的板块信息。")
        
        compare_value = self.compare_data.get(symbol, "N/A")
        shares_value = self.shares.get(symbol, "N/A")
        marketcap_val, pe_val = self.marketcap_pe_data.get(symbol, (None, 'N/A'))

        # 3. 调用绘图函数
        try:
            plot_financial_data(
                DB_PATH, sector, symbol, compare_value, shares_value,
                marketcap_val, pe_val, self.json_data, '1Y', False
            )
            # 在绘图后，让主窗口重新获得焦点以响应键盘事件
            self.setFocus()
        except Exception as e:
            print(f"调用 plot_financial_data 时出错: {e}")

    # --- 4. 新增处理方向键的方法 ---
    def handle_arrow_key(self, direction):
        """
        根据方向键获取下一个或上一个 symbol 并显示图表。
        """
        if direction == 'down':
            symbol = self.symbol_manager.next_symbol()
        elif direction == 'up':
            symbol = self.symbol_manager.previous_symbol()
        else:
            return

        if symbol:
            # 直接调用 on_symbol_click 来处理图表显示
            self.on_symbol_click(symbol)

    def keyPressEvent(self, event):
        """
        重写键盘事件处理器以响应按键。
        """
        key = event.key()
        
        # --- 5. 在键盘事件中添加对上下键的处理 ---
        if key == Qt.Key_Escape:
            print("Escape key pressed. Closing application...")
            self.close()
        elif key == Qt.Key_Down:
            self.handle_arrow_key('down')
        elif key == Qt.Key_Up:
            self.handle_arrow_key('up')
        else:
            # 对于其他按键，调用父类的实现以保留默认行为
            super().keyPressEvent(event)

    # --- 【关键改动 3】: 重写 closeEvent 方法以确保程序退出 ---
    def closeEvent(self, event):
        """
        重写关闭事件，确保应用程序完全退出。
        """
        # --- 6. 在关闭时重置 SymbolManager ---
        print("Resetting symbol manager and quitting.")
        self.symbol_manager.reset()
        QApplication.quit()
        event.accept() # 接受关闭事件

    def create_symbol_widget(self, symbol):
        """
        创建一个 QWidget，垂直包含按钮和它下方的左对齐文本标签，
        并统一固定宽度。
        """
        # 1) 按钮（保留原来的点击 & 右键菜单逻辑）
        button = self.create_symbol_button(symbol)
        button.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)

        # 2) 拿到标签文本
        tags_info = self.get_tags_for_symbol(symbol)
        if isinstance(tags_info, list):
            tags_info = ", ".join(tags_info)

        # --- 用 ClickableLabel 替代普通 QLabel ---
        label = ClickableLabel(tags_info)
        # 左对齐 + 垂直居中
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)

        # 用实例的 fontMetrics 拿高度
        fm = label.fontMetrics()
        label.setFixedHeight(fm.height() + 14)

        # 保持浅黄底黑字，给左侧留点 padding
        label.setStyleSheet("""
            background-color: lightyellow;
            color: black;
            font-size: 16px;
            padding-left: 4px;
        """)

        # 点击 label 时也调用 on_symbol_click
        label.clicked.connect(lambda: self.on_symbol_click(symbol))

        # --- 把按钮 + 可点标签 装容器 ---
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
    # 1. 加载所有需要的数据
    print("正在加载数据...")
    try:
        high_low_data = parse_high_low_file(HIGH_LOW_PATH)
        keyword_colors = load_json(COLORS_PATH)
        json_data = load_json(DESCRIPTION_PATH)
        sector_data = load_json(SECTORS_ALL_PATH)
        compare_data = load_text_data(COMPARE_DATA_PATH)
        shares = load_text_data(SHARES_PATH)
        marketcap_pe_data = load_marketcap_pe_data(MARKETCAP_PATH)
        print("数据加载完成。")
    except FileNotFoundError as e:
        print(f"错误: 找不到文件 {e.filename}。请检查路径是否正确。")
        sys.exit(1)
    except Exception as e:
        print(f"加载数据时发生未知错误: {e}")
        sys.exit(1)

    # 2. 创建并运行 PyQt5 应用
    app = QApplication(sys.argv)
    main_window = HighLowWindow(
        high_low_data,
        keyword_colors,
        sector_data,
        compare_data,
        shares,
        marketcap_pe_data,
        json_data
    )
    main_window.show()
    sys.exit(app.exec_())