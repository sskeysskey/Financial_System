import sys
import json
from collections import OrderedDict
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QLabel
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor, QColor

# ----------------------------------------------------------------------
# 确保可以从您的自定义模块导入
# ----------------------------------------------------------------------
# 请确保此路径正确，以便能够导入 plot_financial_data
sys.path.append('/Users/yanzhang/Documents/Financial_System/Query')
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# 常量 / 全局配置 (从 a.py 借用)
# ----------------------------------------------------------------------
# 新增 HighLow 文件路径
HIGH_LOW_PATH = '/Users/yanzhang/Documents/News/HighLow.txt'

# 复用 a.py 中的路径
CONFIG_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
COLORS_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
DESCRIPTION_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
SECTORS_ALL_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
SHARES_PATH = '/Users/yanzhang/Documents/News/backup/Shares.txt'
MARKETCAP_PATH = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'

# ----------------------------------------------------------------------
# 工具 / 辅助函数 (部分从 a.py 借用)
# ----------------------------------------------------------------------

def parse_high_low_file(path):
    """
    解析 HighLow.txt 文件，返回一个有序字典。
    结构: {'5Y': {'Low': ['SPXS', ...], 'High': ['USDTRY', ...]}, ...}
    """
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
        
        self.init_ui()

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle("High/Low Viewer")
        self.setGeometry(150, 150, 1200, 800)

        # 使用 QScrollArea 以便内容可滚动
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # 主布局：一个水平布局，分为左右两列
        main_layout = QHBoxLayout(scroll_content)
        scroll_content.setLayout(main_layout)

        # 创建左列 (Low) 和右列 (High) 的垂直布局
        self.low_layout = QVBoxLayout()
        self.low_layout.setAlignment(Qt.AlignTop)
        self.high_layout = QVBoxLayout()
        self.high_layout.setAlignment(Qt.AlignTop)

        main_layout.addLayout(self.low_layout)
        main_layout.addLayout(self.high_layout)

        # 应用样式并填充控件
        self.apply_stylesheet()
        self.populate_ui()

    def apply_stylesheet(self):
        """创建并应用 QSS 样式表 (从 a.py 借用)"""
        button_styles = {
            "Cyan": ("cyan", "black"), "Blue": ("blue", "white"),
            "Purple": ("purple", "white"), "Green": ("green", "white"),
            "White": ("white", "black"), "Yellow": ("yellow", "black"),
            "Orange": ("orange", "black"), "Red": ("red", "black"),
            "Black": ("black", "white"), "Default": ("gray", "black")
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
        根据解析的 high_low_data 动态创建界面上的所有控件
        """
        # 遍历每个时间段 (e.g., '5Y', '2Y')
        for period, categories in self.high_low_data.items():
            # --- 处理 Low 列表 ---
            low_symbols = categories.get('Low', [])
            if low_symbols: # 仅当列表不为空时创建 GroupBox
                low_group_box = QGroupBox(f"{period} Low")
                low_group_layout = QVBoxLayout()
                low_group_box.setLayout(low_group_layout)
                
                for symbol in low_symbols:
                    button = self.create_symbol_button(symbol)
                    low_group_layout.addWidget(button)
                
                self.low_layout.addWidget(low_group_box)

            # --- 处理 High 列表 ---
            high_symbols = categories.get('High', [])
            if high_symbols: # 仅当列表不为空时创建 GroupBox
                high_group_box = QGroupBox(f"{period} High")
                high_group_layout = QVBoxLayout()
                high_group_box.setLayout(high_group_layout)

                for symbol in high_symbols:
                    button = self.create_symbol_button(symbol)
                    high_group_layout.addWidget(button)

                self.high_layout.addWidget(high_group_box)

    def create_symbol_button(self, symbol):
        """辅助函数，用于创建一个配置好的 symbol 按钮"""
        button_text = f"{symbol} {self.compare_data.get(symbol, '')}"
        button = QPushButton(button_text)
        button.setObjectName(self.get_button_style_name(symbol))
        button.setCursor(QCursor(Qt.PointingHandCursor))
        # 使用 lambda 捕获当前的 symbol 值
        button.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))
        return button

    def on_symbol_click(self, symbol):
        """
        当一个 symbol 按钮被点击时调用此函数，功能与 a.py 中的 on_keyword_selected_chart 类似
        """
        print(f"按钮 '{symbol}' 被点击，准备显示图表...")
        
        # 1. 查找 symbol 属于哪个 sector
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        
        if not sector:
            print(f"警告: 在 Sectors_All.json 中找不到 '{symbol}' 的板块信息。")
            # 即使找不到板块，也可以尝试绘图，plot_financial_data 内部可能有备用逻辑
            # 或者在这里直接返回
            # return

        # 2. 获取相关数据
        compare_value = self.compare_data.get(symbol, "N/A")
        shares_value = self.shares.get(symbol, "N/A")
        marketcap_val, pe_val = self.marketcap_pe_data.get(symbol, (None, 'N/A'))

        # 3. 调用绘图函数
        try:
            plot_financial_data(
                DB_PATH, sector, symbol, compare_value, shares_value,
                marketcap_val, pe_val, self.json_data, '1Y', False
            )
        except Exception as e:
            print(f"调用 plot_financial_data 时出错: {e}")


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