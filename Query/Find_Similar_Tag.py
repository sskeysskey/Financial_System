import json
import re
import pyperclip
import subprocess
import sys
import time
from decimal import Decimal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QInputDialog, QMessageBox, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QGroupBox, QScrollArea, QLabel, QMenu, QAction)
from PyQt5.QtGui import QCursor

# --- 检查并添加必要的路径 ---
# 确保可以找到 Chart_input 模块
chart_input_path = '/Users/yanzhang/Documents/Financial_System/Query'
if chart_input_path not in sys.path:
    sys.path.append(chart_input_path)

try:
    from Chart_input import plot_financial_data
except ImportError:
    print(f"错误：无法从路径 '{chart_input_path}' 导入 'plot_financial_data'。请检查文件是否存在。")
    sys.exit(1)

# --- 文件路径 ---
DESCRIPTION_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
WEIGHT_CONFIG_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'
SECTORS_ALL_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'

# --- 默认权重 ---
DEFAULT_WEIGHT = Decimal('1')

# --- 核心逻辑函数 (来自 a.py) ---

def load_weight_groups():
    """读取权重配置文件"""
    try:
        with open(WEIGHT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            return {Decimal(k): v for k, v in raw_data.items()}
    except Exception as e:
        print(f"加载权重配置文件时出错: {e}")
        return {}

def find_tags_by_symbol(symbol, data, tags_weight_config):
    """根据 symbol 查找其 tags 和对应的权重"""
    tags_with_weight = []
    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            if item.get('symbol') == symbol:
                for tag in item.get('tag', []):
                    weight = tags_weight_config.get(tag, DEFAULT_WEIGHT)
                    tags_with_weight.append((tag, weight))
                return tags_with_weight
    return []

def get_symbol_type(symbol, data):
    """判断 symbol 属于 stock 还是 etf"""
    for item in data.get('stocks', []):
        if item.get('symbol') == symbol:
            return 'stock'
    for item in data.get('etfs', []):
        if item.get('symbol') == symbol:
            return 'etf'
    return None

def find_symbols_by_tags(target_tags_with_weight, data):
    """根据目标 tags 查找所有相关的 symbols"""
    related_symbols = {'stocks': [], 'etfs': []}
    target_tags_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}

    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            tags = item.get('tag', [])
            matched_tags = []
            used_tags = set()

            # 完全匹配
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in target_tags_dict and tag_lower not in used_tags:
                    matched_tags.append((tag, target_tags_dict[tag_lower]))
                    used_tags.add(tag_lower)

            # 部分匹配
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in used_tags:
                    continue
                for target_tag, target_weight in target_tags_dict.items():
                    if (target_tag in tag_lower or tag_lower in target_tag) and tag_lower != target_tag:
                        if target_tag not in used_tags:
                            weight_to_use = Decimal('1.0') if target_weight > Decimal('1.0') else target_weight
                            matched_tags.append((tag, weight_to_use))
                            used_tags.add(target_tag)
                        break
            
            if matched_tags:
                related_symbols[category].append((item['symbol'], matched_tags, tags))

    for category in related_symbols:
        related_symbols[category].sort(key=lambda x: sum(w for _, w in x[1]), reverse=True)

    return related_symbols

def load_compare_data(file_path):
    """加载 Compare_All.txt 数据"""
    compare_data = {}
    try:
        with open(file_path, 'r') as file:
            for line in file:
                if ':' in line:
                    sym, value = line.split(':', 1)
                    compare_data[sym.strip()] = value.strip()
    except FileNotFoundError:
        print(f"警告: 找不到文件 {file_path}")
    return compare_data

def load_json_data(file_path):
    """通用 JSON 加载函数"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"警告: 找不到 JSON 文件 {file_path}")
        return {}

def get_stock_symbol(default_symbol=""):
    """使用 PyQt 对话框获取股票代码"""
    app = QApplication.instance() or QApplication(sys.argv)
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
    if input_dialog.exec_() == QInputDialog.Accepted:
        return input_dialog.textValue().strip().upper()
    return None

def copy2clipboard():
    """执行 macOS 复制命令"""
    try:
        script = 'tell application "System Events" to keystroke "c" using {command down}'
        subprocess.run(['osascript', '-e', script], check=True, timeout=1)
        time.sleep(0.2)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"复制操作失败: {e}")
        return False

def get_clipboard_content():
    """安全地获取剪贴板内容"""
    try:
        return pyperclip.paste().strip()
    except Exception:
        return ""

# ### 修改 1: 替换为功能更全的 execute_external_script 函数 ###
def execute_external_script(script_type, keyword):
    """以非阻塞方式执行外部脚本（Python 或 AppleScript）"""
    base_path = '/Users/yanzhang/Documents/Financial_System'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar':  f'{base_path}/Query/Find_Similar_Tag.py',
        'tags':     f'{base_path}/Operations/Editor_Symbol_Tags.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'earning':  f'{base_path}/Operations/Insert_Earning.py',
        'futu':     '/Users/yanzhang/Documents/ScriptEditor/Stock_CheckFutu.scpt',
        'kimi':     '/Users/yanzhang/Documents/ScriptEditor/CheckKimi_Earning.scpt'
    }
    script_path = script_configs.get(script_type)
    if not script_path:
        print(f"错误: 未知的脚本类型 '{script_type}'")
        return
        
    try:
        if script_type in ['futu', 'kimi']:
            # 执行 AppleScript
            subprocess.Popen(['osascript', script_path, keyword])
        else:
            # 执行 Python 脚本
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.Popen([python_path, script_path, keyword])
    except Exception as e:
        print(f"执行脚本 '{script_path}' 时发生错误: {e}")


# ======================================================================
# 2. PyQt5 主窗口类
# ======================================================================

class SimilarityViewerWindow(QMainWindow):
    def __init__(self, source_symbol, source_tags, related_symbols, all_data):
        super().__init__()
        self.source_symbol = source_symbol
        self.source_tags = source_tags
        self.related_symbols = related_symbols
        
        # 将所有需要的数据存储为实例变量
        self.json_data = all_data['description']
        self.compare_data = all_data['compare']
        self.sector_data = all_data['sectors']

        self.init_ui()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle(f"相似度分析: {self.source_symbol}")
        # ### 修改 3: 增加窗口默认宽度 ###
        self.setGeometry(150, 150, 1600, 1000)
        self.setStyleSheet(self.get_stylesheet())

        # --- 创建主滚动区域 ---
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        # --- 主容器和布局 ---
        main_widget = QWidget()
        scroll_area.setWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 填充内容 ---
        self.populate_ui(main_layout)

    def populate_ui(self, layout):
        """动态创建和填充UI元素"""
        # 1. 源 Symbol 信息
        source_group = QGroupBox("-")
        source_layout = QVBoxLayout()
        source_group.setLayout(source_layout)
        
        source_widget = self.create_source_symbol_widget()
        source_layout.addWidget(source_widget)
        layout.addWidget(source_group)

        # 2. 创建一个水平布局来并排显示 Stocks 和 ETFs
        related_layout = QHBoxLayout()
        
        symbol_type = get_symbol_type(self.source_symbol, self.json_data)
        # 根据源 symbol 类型决定显示顺序
        categories_order = ['etfs', 'stocks'] if symbol_type == 'etf' else ['stocks', 'etfs']

        for category in categories_order:
            category_title = "-" if category == 'etfs' else "-"
            symbols_list = self.related_symbols.get(category, [])
            
            if not symbols_list: # 如果没有相关内容，则跳过
                continue

            group_box = QGroupBox(category_title)
            group_layout = QVBoxLayout()
            group_box.setLayout(group_layout)
            group_layout.setAlignment(Qt.AlignTop) # 内容顶部对齐

            for sym, matched_tags, all_tags in symbols_list:
                # 排除源 symbol 自身
                if sym == self.source_symbol:
                    continue
                widget = self.create_similar_symbol_widget(sym, matched_tags, all_tags)
                group_layout.addWidget(widget)
            
            related_layout.addWidget(group_box)
        
        layout.addLayout(related_layout)
        layout.addStretch(1) # 添加一个伸缩项，让所有内容向上推

    def create_source_symbol_widget(self):
        """为源 Symbol 创建一个专属的信息展示控件"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        # 左侧按钮
        button = self.create_symbol_button(self.source_symbol)
        button.setMinimumHeight(20)

        # --- 新增：源 symbol 的 Compare 值 ---
        compare_value = self.compare_data.get(self.source_symbol, "")
        compare_label = QLabel(compare_value)
        compare_label.setFixedWidth(150)
        if re.search(r'-\d+(\.\d+)?%', compare_value):
            compare_label.setStyleSheet("color: #EF9A9A;")
        else:
            compare_label.setObjectName("CompareLabel")
        compare_label.setAlignment(Qt.AlignCenter)
        
        # ### 修改 2: 使用富文本(HTML)格式化标签，放大字体并突出权重数字 ###
        # 定义醒目的颜色
        highlight_color = "#F9A825" # 与下方权重标签一致的黄色
        
        # 构建HTML格式的标签字符串
        html_tags_parts = []
        for tag, weight in self.source_tags:
            html_tags_parts.append(f"{tag}  <font color='{highlight_color}'>{float(weight):.2f}</font>")
        
        html_tags_str = ", ".join(html_tags_parts)
        
        # 创建一个支持富文本的QLabel
        label = QLabel(f"<div style='font-size: 20px;'><b>   </b> {html_tags_str}</div>")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # 按钮、Compare、Tags 三部分并排
        layout.addWidget(button,       1)  # Symbol 按钮
        layout.addWidget(compare_label,1)  # Compare 值
        layout.addWidget(label,        4)  # Tags 显示

        return container

    def create_similar_symbol_widget(self, sym, matched_tags, all_tags):
        """为每个相似的 Symbol 创建一个信息行控件"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 2, 0, 2) # 紧凑的垂直边距

        # 1. Symbol 按钮
        button = self.create_symbol_button(sym)
        button.setMinimumHeight(60)
        
        # 2. 总权重
        total_weight = round(sum(float(w) for _, w in matched_tags), 2)
        weight_label = QLabel(f"{total_weight:.2f}")
        weight_label.setFixedWidth(45)
        weight_label.setObjectName("WeightLabel")
        weight_label.setAlignment(Qt.AlignCenter)

        # 3. Compare 值
        compare_value = self.compare_data.get(sym, '')
        compare_label = QLabel(compare_value)
        compare_label.setFixedWidth(140)
        # 如果是负数百分比，就整行显示淡红色，否则使用原有的绿色
        if re.search(r'-\d+(\.\d+)?%', compare_value):
            compare_label.setStyleSheet("color: #EF9A9A;")
        else:
            compare_label.setObjectName("CompareLabel")
        compare_label.setAlignment(Qt.AlignCenter)

        # 4. 所有 Tags
        tags_str = ",   ".join(all_tags)
        tags_label = QLabel(tags_str)
        tags_label.setObjectName("TagsLabel")
        tags_label.setWordWrap(True)

        layout.addWidget(button)
        layout.addWidget(weight_label)
        layout.addWidget(compare_label)
        layout.addWidget(tags_label)
        layout.setStretch(0, 2) # button
        layout.setStretch(1, 1) # weight
        layout.setStretch(2, 3) # compare
        layout.setStretch(3, 8) # tags

        return container

    def create_symbol_button(self, symbol):
        """创建并配置一个标准的 Symbol 按钮"""
        button = QPushButton(symbol)
        button.setCursor(QCursor(Qt.PointingHandCursor))
        button.setFixedWidth(90)
        button.setObjectName("SymbolButton")
        
        # 左键点击事件
        button.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))
        
        # 设置 Tooltip
        tags_info = self.get_tags_for_symbol(symbol)
        if isinstance(tags_info, list):
            tags_info = ", ".join(tags_info)
        button.setToolTip(f"<div style='font-size: 16px; background-color: #FFFFE0; color: black; padding: 5px;'>{tags_info}</div>")
        
        # 右键菜单事件
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))
        
        return button

    def on_symbol_click(self, symbol):
        """处理 Symbol 按钮的左键点击事件"""
        print(f"正在为 '{symbol}' 生成图表...")
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        compare_value = self.compare_data.get(symbol, "N/A")
        
        try:
            # 调用从 b.py 移植的绘图函数
            plot_financial_data(
                DB_PATH, sector, symbol, compare_value, 
                "N/A", None, "N/A", # 传递占位符
                self.json_data, '1Y', False
            )
        except Exception as e:
            QMessageBox.critical(self, "绘图错误", f"调用 plot_financial_data 时出错: {e}")
            print(f"调用 plot_financial_data 时出错: {e}")

    # ### 修改 2: 扩展右键菜单的选项 ###
    def show_context_menu(self, symbol):
        """创建并显示一个包含丰富选项的右键上下文菜单"""
        menu = QMenu(self)
        
        # 定义菜单项：(文本, 回调函数)
        actions = [
            ("在富途中搜索", lambda: execute_external_script('futu', symbol)),
            ("添加到 Earning", lambda: execute_external_script('earning', symbol)),
            ("编辑 Earing DB", lambda: execute_external_script('editor_earning', symbol)),
            ("Kimi检索财报", lambda: execute_external_script('kimi', symbol)),
            None,  # 分隔符
            ("编辑 Tags", lambda: execute_external_script('tags', symbol)),
            ("找相似(旧版)", lambda: execute_external_script('similar', symbol)),
            None,  # 分隔符
            ("加入黑名单", lambda: execute_external_script('blacklist', symbol)),
        ]

        # 动态创建并添加菜单项
        for item in actions:
            if item is None:
                menu.addSeparator()
            else:
                text, callback = item
                action = QAction(text, self)
                action.triggered.connect(callback)
                menu.addAction(action)
        
        menu.exec_(QCursor.pos())
        
    # ### 修改 1: 增加键盘事件处理，实现ESC键关闭功能 ###
    def keyPressEvent(self, event):
        """重写键盘事件处理器"""
        if event.key() == Qt.Key_Escape:
            print("ESC被按下，正在关闭窗口...")
            self.close()
        else:
            # 对于其他按键，调用父类的实现以保留默认行为
            super().keyPressEvent(event)

    def get_tags_for_symbol(self, symbol):
        """辅助函数，为 Tooltip 获取 tags"""
        for item in self.json_data.get("stocks", []):
            if item.get("symbol") == symbol:
                return item.get("tag", ["无标签"])
        for item in self.json_data.get("etfs", []):
            if item.get("symbol") == symbol:
                return item.get("tag", ["无标签"])
        return ["未找到"]

    def get_stylesheet(self):
        """返回整个应用的 QSS 样式表"""
        return """
        QMainWindow {
            background-color: #2E2E2E;
        }
        QGroupBox {
            font-size: 12px;
            font-weight: bold;
            color: #E0E0E0;
            border: 1px solid #555;
            border-radius: 8px;
            margin-top: 10px;
            padding: 20px 10px 10px 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 10px;
            color: #00AEEF; /* 亮蓝色标题 */
            left: 10px;
        }
        QScrollArea {
            border: none;
        }
        #SymbolButton {
            background-color: #007ACC;
            color: white;
            font-size: 14px;
            font-weight: bold;
            padding: 5px;
            border-radius: 4px;
            border: 1px solid #005C99;
        }
        #SymbolButton:hover {
            background-color: #0099FF;
        }
        QLabel {
            font-size: 20px;
            color: #D0D0D0;
        }
        #WeightLabel {
            color: #BDBDBD; /* 黄色以突出权重 */
            font-weight: bold;
            background-color: #2E2E2E;
            border-radius: 4px;
        }
        #CompareLabel {
            color: #A5D6A7; /* 浅绿色 */
            font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
        }
        #TagsLabel {
            color: #BDBDBD; /* 灰色 */
        }
        QToolTip {
            border: 1px solid #C0C0C0;
            border-radius: 4px;
        }
        QMenu {
            background-color: #3C3C3C;
            color: #E0E0E0;
            border: 1px solid #555;
            font-size: 14px;
        }
        QMenu::item {
            padding: 8px 25px 8px 20px;
        }
        QMenu::item:selected {
            background-color: #007ACC;
        }
        QMenu::separator {
            height: 1px;
            background: #555;
            margin-left: 10px;
            margin-right: 10px;
        }
        """

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # --- 步骤 1: 获取股票代码 (来自 a.py) ---
    symbol = None
    if len(sys.argv) > 1:
        symbol = sys.argv[1].strip().upper()
    else:
        pyperclip.copy('')
        if copy2clipboard():
            content = get_clipboard_content()
            if content and re.match('^[A-Z.-]+$', content):
                symbol = content
            else:
                symbol = get_stock_symbol(content)
        else:
            symbol = get_stock_symbol()

    if not symbol:
        QMessageBox.warning(None, "警告", "未提供有效的股票代码，程序将退出。")
        sys.exit()

    # --- 步骤 2: 加载所有数据 ---
    print("正在加载所需数据...")
    try:
        description_data = load_json_data(DESCRIPTION_PATH)
        weight_groups = load_weight_groups()
        tags_weight_config = {tag: weight for weight, tags in weight_groups.items() for tag in tags}
        compare_data = load_compare_data(COMPARE_DATA_PATH)
        sector_data = load_json_data(SECTORS_ALL_PATH)
        
        all_data_package = {
            "description": description_data,
            "compare": compare_data,
            "sectors": sector_data
        }
    except Exception as e:
        QMessageBox.critical(None, "错误", f"加载数据文件时出错: {e}")
        sys.exit(1)

    # --- 步骤 3: 执行核心分析逻辑 (来自 a.py 的 main 函数) ---
    print(f"正在为 '{symbol}' 分析相似度...")
    target_tags = find_tags_by_symbol(symbol, description_data, tags_weight_config)

    if not target_tags:
        QMessageBox.information(None, "未找到", f"在数据库中找不到符号 '{symbol}' 的标签。")
        sys.exit()

    related_symbols = find_symbols_by_tags(target_tags, description_data)
    
    # --- 步骤 4: 创建并显示GUI窗口 ---
    print("分析完成，正在启动UI...")
    main_window = SimilarityViewerWindow(symbol, target_tags, related_symbols, all_data_package)
    main_window.show()
    
    sys.exit(app.exec_())