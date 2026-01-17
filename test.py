import re
import os
import sys
import time
import json
import sqlite3
import pyperclip
import subprocess
import platform 
from decimal import Decimal
from datetime import datetime, date

# PyQt6
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import (QApplication, QInputDialog, QMessageBox, QMainWindow, QWidget,
                             QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
                             QScrollArea, QLabel, QMenu, QLineEdit)
from PyQt6.QtGui import QCursor, QAction

# ================= 配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")
SCRIPT_EDITOR_DIR = os.path.join(BASE_CODING_DIR, "ScriptEditor")

# 3. 模块导入路径
QUERY_DIR = os.path.join(FINANCIAL_SYSTEM_DIR, "Query")
OPERATIONS_DIR = os.path.join(FINANCIAL_SYSTEM_DIR, "Operations")

# 4. 具体文件路径
DESCRIPTION_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "description.json")
WEIGHT_CONFIG_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "tags_weight.json")
SECTORS_ALL_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
PANEL_CONFIG_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_panel.json")
COMPARE_DATA_PATH = os.path.join(NEWS_BACKUP_DIR, "Compare_All.txt")
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
STOCK_CHART_SCRIPT = os.path.join(QUERY_DIR, "Stock_Chart.py")

# ================= 动态导入区域 =================

# 检查并添加必要的路径
if QUERY_DIR not in sys.path:
    sys.path.append(QUERY_DIR)

# 尝试导入绘图模块，失败则使用空函数代替，防止程序崩溃
try:
    from Chart_input import plot_financial_data
except ImportError:
    print(f"Warning: 无法从 '{QUERY_DIR}' 导入 'plot_financial_data'。")
    # 定义 Mock 函数
    def plot_financial_data(*args, **kwargs):
        print("Mock: 绘图功能不可用 (模块缺失)")
        QMessageBox.warning(None, "缺失模块", "Chart_input 模块未找到，无法绘图。")

# ================= 核心逻辑 =================

# --- 默认权重 ---
DEFAULT_WEIGHT = Decimal('1')

# --- 核心逻辑函数 ---

def fetch_mnspp_data_from_db(db_path, symbol):
    if not os.path.exists(db_path):
        return "N/A", None, "N/A", "--"
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?",
                (symbol,)
            )
            row = cur.fetchone()
        if row:
            return row  # shares, marketcap, pe_ratio, pb
        else:
            return "N/A", None, "N/A", "--"
    except sqlite3.Error:
        return "N/A", None, "N/A", "--"

def load_weight_groups():
    """读取权重配置文件"""
    try:
        if not os.path.exists(WEIGHT_CONFIG_PATH): return {}
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
        related_symbols[category].sort(
            key=lambda item: (
                sum(w for _, w in item[1]),              # 先按总分降序
                fetch_mnspp_data_from_db(DB_PATH, item[0])[1] or 0 # 再按 marketcap 降序
            ),
            reverse=True  # 对 tuple 的每个维度都倒序
        )
    return related_symbols

def load_compare_data(file_path):
    """加载 Compare_All.txt 数据"""
    compare_data = {}
    try:
        if os.path.exists(file_path):
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
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        return {}
    except FileNotFoundError:
        print(f"警告: 找不到 JSON 文件 {file_path}")
        return {}

def get_stock_symbol(default_symbol=""):
    """使用 PyQt6 对话框获取股票代码"""
    app = QApplication.instance() or QApplication(sys.argv)
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    # PyQt6: 使用 WindowType
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    
    # PyQt6: exec_() -> exec()
    if input_dialog.exec() == QInputDialog.DialogCode.Accepted:
        return input_dialog.textValue().strip().upper()
    return None

def copy2clipboard():
    """跨平台复制"""
    if platform.system() == 'Darwin':
        try:
            script = 'tell application "System Events" to keystroke "c" using {command down}'
            subprocess.run(['osascript', '-e', script], check=True, timeout=1)
            time.sleep(0.2)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"复制操作失败: {e}")
            return False
    else:
        # Windows
        try:
            import pyautogui
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.2)
            return True
        except Exception as e:
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
    
    # 动态构建路径
    script_configs = {
        'blacklist': os.path.join(OPERATIONS_DIR, 'Insert_Blacklist.py'),
        'similar':   os.path.join(QUERY_DIR, 'Find_Similar_Tag.py'),
        'tags':      os.path.join(OPERATIONS_DIR, 'Editor_Tags.py'),
        'editor_earning': os.path.join(OPERATIONS_DIR, 'Editor_Earning_DB.py'),
        'earning':   os.path.join(OPERATIONS_DIR, 'Insert_Earning.py'),
        'event_input': os.path.join(OPERATIONS_DIR, 'Insert_Events.py'),
        'event_editor': os.path.join(OPERATIONS_DIR, 'Editor_Events.py'),
        'futu':      os.path.join(SCRIPT_EDITOR_DIR, 'Stock_CheckFutu.scpt'),
        'kimi':      os.path.join(SCRIPT_EDITOR_DIR, 'Check_Earning.scpt')
    }
    
    script_path = script_configs.get(script_type)
    if not script_path:
        print(f"错误: 未知的脚本类型 '{script_type}'")
        return
        
    try:
        if script_type in ['futu', 'kimi']:
            if platform.system() == 'Darwin':
                # 执行 AppleScript (仅限 Mac)
                subprocess.Popen(['osascript', script_path, keyword])
            else:
                print(f"提示: AppleScript 脚本 '{script_type}' 无法在 Windows/Linux 上运行。")
        else:
            # 执行 Python 脚本 (跨平台)
            # 使用 sys.executable 确保环境一致
            subprocess.Popen([sys.executable, script_path, keyword])
            
    except Exception as e:
        print(f"执行脚本 '{script_path}' 时发生错误: {e}")

# ================= UI 组件 =================
class RowWidget(QWidget):
    def __init__(self, symbol: str, click_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbol = symbol
        self.click_callback = click_callback

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.click_callback(self.symbol)
        return False  # 不拦截

class SymbolButton(QPushButton):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            mods = event.modifiers()
            # PyQt6: 使用 Qt.KeyboardModifier
            if mods & Qt.KeyboardModifier.AltModifier:
                execute_external_script('similar', self.text())
                return
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                execute_external_script('futu', self.text())
                return
        # 其他情况走原有行为（例如普通左键点击会触发 on_symbol_button_clicked）
        super().mousePressEvent(event)

class SimilarityViewerWindow(QMainWindow):
    def __init__(self, source_symbol, source_tags, related_symbols, all_data):
        super().__init__()
        self.source_symbol = source_symbol
        self.source_tags = source_tags
        self.related_symbols = related_symbols
        self.panel_config      = all_data.get('panel_config', {})
        self.panel_config_path = all_data.get('panel_config_path')
        
        # 将所有需要的数据存储为实例变量
        self.all_data = all_data
        self.json_data    = all_data['description']
        self.compare_data = all_data['compare']
        self.sector_data  = all_data['sectors']
        # 从 all_data 拿到 tags_weight_config
        self.tags_weight_config = all_data['tags_weight']
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
        # 将 layout 绑定为实例属性，以便后面清空或重绘
        self.main_layout = QVBoxLayout(main_widget)
        # 填充内容（包含源 Symbol 栏，第二级才是所有相似列表）
        self.populate_ui(self.main_layout)

        # --- 界面创建完毕后，让搜索输入框自动获得焦点并全选 ---
        if hasattr(self, 'search_input'):
            self.search_input.setFocus()
            self.search_input.selectAll()

    def populate_ui(self, layout):
        """动态创建和填充UI元素，Stocks 列占 70%，ETFs 列占 30%"""
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
            # 标题
            category_title = "-" if category == 'etfs' else "-"
            symbols_list = self.related_symbols.get(category, [])
            
            if not symbols_list: # 如果没有相关内容，则跳过
                continue

            group_box = QGroupBox(category_title)
            group_layout = QVBoxLayout()
            group_box.setLayout(group_layout)
            group_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            
            for sym, matched_tags, all_tags in symbols_list:
                # 排除源 symbol 自身
                if sym == self.source_symbol:
                    continue
                # 如果没有 compare_all 数据，就跳过
                # （compare_data 存在才显示）
                cmp = self.compare_data.get(sym, "").strip()
                if not cmp:
                    continue
                widget = self.create_similar_symbol_widget(sym, matched_tags, all_tags)
                group_layout.addWidget(widget)
            
            # 按照 Stocks:ETFs = 70:30 设置 stretch
            if category == 'stocks':
                related_layout.addWidget(group_box, 7)
            else:  # category == 'etfs'
                related_layout.addWidget(group_box, 3)

        layout.addLayout(related_layout)
        layout.addStretch(1) # 添加一个伸缩项，让所有内容向上推
    
    def clear_layout(self, layout):
        """递归删除一个 layout 下的所有 item"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

    def clear_content(self):
        """仅保留最上方的搜索栏，清空其它所有控件/布局"""
        for i in reversed(range(self.main_layout.count())):
            item = self.main_layout.takeAt(i)
            if not item:
                continue
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

    def on_search(self):
        """回车时重新加载 symbol 并刷新界面"""
        symbol = self.search_input.text().strip().upper()
        if not symbol:
            return
        # 1) 找 tags
        tags = find_tags_by_symbol(symbol,
                                   self.all_data['description'],
                                   self.tags_weight_config)
        if not tags:
            QMessageBox.information(self, "未找到", f"在数据库中找不到符号 '{symbol}' 的标签。")
            return
        # 2) 找相似
        related = find_symbols_by_tags(tags, self.all_data['description'])
        # 3) 更新实例变量
        self.source_symbol   = symbol
        self.source_tags     = tags
        self.related_symbols = related
        # 4) 清空旧内容并重绘
        self.clear_content()
        self.populate_ui(self.main_layout)

    def copy_symbol_to_group(self, symbol: str, group: str):
        """
        将 symbol “复制” 到 panel_config[group]，避免重复，
        并写回 JSON 文件。
        """
        cfg = self.panel_config

        # 如果这个组本来不存在，默认建成 dict，和现有 "Watching" 结构保持一致
        if group not in cfg:
            cfg[group] = {}

        if isinstance(cfg[group], dict):
            if symbol in cfg[group]:
                return  # 已有，不重复
            # 原来是 {}，改为 ""，避免写成 "ADI": {}
            cfg[group][symbol] = ""
        elif isinstance(cfg[group], list):
            if symbol in cfg[group]:
                return
            cfg[group].append(symbol)
        else:
            QMessageBox.warning(self, "错误", f"组 {group} 类型不支持: {type(cfg[group])}")
            return

        # 写回 JSON
        try:
            with open(self.panel_config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "复制成功", f"已将 {symbol} 复制到组「{group}」")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 {self.panel_config_path} 时出错: {e}")

    def get_color_decision_data(self, symbol: str):
        try:
            if not os.path.exists(DB_PATH): return None, None, None
            with sqlite3.connect(DB_PATH, timeout=60.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT date, price FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 2",
                    (symbol,)
                )
                earning_rows = cursor.fetchall()
            if not earning_rows:
                return None, None, None # 没有财报记录

            latest_earning_date_str, latest_earning_price_str = earning_rows[0]
            latest_earning_date = datetime.strptime(latest_earning_date_str, "%Y-%m-%d").date()
            latest_earning_price = float(latest_earning_price_str) if latest_earning_price_str is not None else 0.0

            # --- 新规则 1: 如果最新财报在75天前，则强制为白色 ---
            days_diff = (date.today() - latest_earning_date).days
            if days_diff > 75:
                # 返回None趋势，使调用处逻辑判定为白色
                return latest_earning_price, None, latest_earning_date

            # --- 新规则：如果只有一条财报记录，使用 'single' 模式，仅按 earning price 正负着色 ---
            if len(earning_rows) < 2:
                # 不再返回 None，而是标记为 'single'
                return latest_earning_price, 'single', latest_earning_date

            # 存在至少两条财报记录，继续计算趋势
            previous_earning_date_str, _ = earning_rows[1]
            previous_earning_date = datetime.strptime(previous_earning_date_str, "%Y-%m-%d").date()

            # 步骤 2: 查找 sector 表名
            sector_table = next((s for s, names in self.sector_data.items() if symbol in names), None)
            if not sector_table:
                # 找不到板块，也无法比较
                return latest_earning_price, None, latest_earning_date

            # 步骤 3: 获取两个日期的收盘价
            with sqlite3.connect(DB_PATH, timeout=60.0) as conn:
                cursor = conn.cursor()
                
                # 获取最新财报日的收盘价
                cursor.execute(
                    f'SELECT price FROM "{sector_table}" WHERE name = ? AND date = ?',
                    (symbol, latest_earning_date.isoformat())
                )
                latest_stock_price_row = cursor.fetchone()
                
                # 获取前一次财报日的收盘价
                cursor.execute(
                    f'SELECT price FROM "{sector_table}" WHERE name = ? AND date = ?',
                    (symbol, previous_earning_date.isoformat())
                )
                previous_stock_price_row = cursor.fetchone()
                
            if not latest_stock_price_row or not previous_stock_price_row:
                # 缺少任一天的股价数据
                return latest_earning_price, None, latest_earning_date
            
            latest_stock_price = float(latest_stock_price_row[0])
            previous_stock_price = float(previous_stock_price_row[0])
            
            # 步骤 4: 判断趋势
            trend = 'rising' if latest_stock_price > previous_stock_price else 'falling'
            return latest_earning_price, trend, latest_earning_date
        except Exception as e:
            print(f"[颜色决策数据获取错误] {symbol}: {e}")
            return None, None, None

    def create_source_symbol_widget(self):
        """为源 Symbol 创建一整行可点击的控件（除搜索框外）"""
        # 使用 RowWidget 作为顶层容器
        container = RowWidget(self.source_symbol, self.on_symbol_click)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        # 1. 左侧按钮
        button = self.create_symbol_button(self.source_symbol)
        # <<< 修改：增加最小高度以适应更大的字体
        button.setMinimumHeight(35) 

        # 2. 源 symbol 的 Compare 值（提取数值并按正负上色：正红，负绿，零橙）
        compare_value = self.compare_data.get(self.source_symbol, "")
        compare_label = QLabel(compare_value)
        compare_label.setFixedWidth(150)
        compare_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        compare_label.setTextFormat(Qt.TextFormat.RichText)

        # 将“前/后/未”以及其紧邻的最多两位数字整体着橙
        # 例：09前、12后、3未、前、后、未
        def orange_keywords_with_digits(s: str) -> str:
            return re.sub(r'(\d{0,2})(前|后|未)',
                          lambda m: f"<span style='color:#CD853F;'>{m.group(1)}{m.group(2)}</span>",
                          s)

        m = re.search(r'(-?\d+(?:\.\d+)?)\s*%', compare_value)
        if m:
            val = float(m.group(1))
            val_color = "#FF5555" if val > 0 else "#2ECC71" if val < 0 else "#CD853F"
            start, end = m.span()
            compare_label.setText(orange_keywords_with_digits(compare_value[:start]) + 
                                  f"<span style='color:{val_color};'>{compare_value[start:end]}</span>" + 
                                  orange_keywords_with_digits(compare_value[end:]))
        else:
            compare_label.setText(orange_keywords_with_digits(compare_value))

        # 3. 标签及权重（已在之前修改过：24px，只有非零分显示一位小数）
        highlight_color = "#F9A825"
        html_tags_str = ", ".join([f"{tag} <font color='{highlight_color}'>{float(weight):.1f}</font>" if float(weight) > 0 else tag for tag, weight in self.source_tags])
        tags_label = QLabel(f"<div style='font-size:24px;'>{html_tags_str}</div>")
        tags_label.setWordWrap(True)
        tags_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        search_input = QLineEdit()
        search_input.setFixedWidth(200)
        search_input.setFixedHeight(32)
        font = search_input.font(); font.setPointSize(14); search_input.setFont(font)
        search_input.setStyleSheet("QLineEdit { padding: 4px; border: 1px solid #555; border-radius: 4px; background-color: #3A3A3A; color: #E0E0E0; } QLineEdit:focus { border: 1px solid #00AEEF; }")
        search_input.setPlaceholderText("输入股票代码…")
        search_input.returnPressed.connect(self.on_search)
        self.search_input = search_input
        
        for w in (compare_label, tags_label): w.installEventFilter(container)
        layout.addWidget(button, 1)
        layout.addWidget(compare_label, 1)
        layout.addWidget(tags_label, 4)
        layout.addStretch()
        layout.addWidget(search_input)
        return container

    def create_similar_symbol_widget(self, sym, matched_tags, all_tags):
        """
        为每个相似的 Symbol 创建一行：
        - 总权重数字字体变小
        - 点击整行（除 Symbol 按钮外）都能触发 on_symbol_click
        """
        # 改用 RowWidget 作容器
        container = RowWidget(sym, self.on_symbol_click)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 2, 0, 2)

        # 1. Symbol 按钮（保留原有行为，包括 Alt/Shift/右键菜单）
        button = self.create_symbol_button(sym)
        button.setMinimumHeight(60)

        # 2. Compare 值（提取数值并按正负上色：正红，负绿，零橙）
        compare_value = self.compare_data.get(sym, '')
        compare_label = QLabel(compare_value)
        compare_label.setFixedWidth(140)
        compare_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        compare_label.setTextFormat(Qt.TextFormat.RichText)
        
        # 简化版逻辑复制
        def orange_keywords_with_digits(s: str) -> str:
            return re.sub(r'(\d{0,2})(前|后|未)', lambda m: f"<span style='color:#CD853F;'>{m.group(1)}{m.group(2)}</span>", s)
        
        m = re.search(r'(-?\d+(?:\.\d+)?)\s*%', compare_value)
        if m:
            val = float(m.group(1))
            val_color = "#FF5555" if val > 0 else "#2ECC71" if val < 0 else "#CD853F"
            start, end = m.span()
            compare_label.setText(orange_keywords_with_digits(compare_value[:start]) + 
                                  f"<span style='color:{val_color};'>{compare_value[start:end]}</span>" + 
                                  orange_keywords_with_digits(compare_value[end:]))
        else:
            compare_label.setText(orange_keywords_with_digits(compare_value))

        # 3. 总权重（字体小一点，比如 14px）
        total_weight = round(sum(float(w) for _, w in matched_tags), 1)
        weight_label = QLabel(f"{total_weight:.1f}")
        weight_label.setFixedWidth(45)
        weight_label.setObjectName("WeightLabel")
        weight_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        weight_label.setStyleSheet("font-size:14px;")

        # 4. 所有 Tags 及其得分（一位小数，分数为0时只显示 tag）
        highlight_color = "#F9A825"
        html_tags_str = ",   ".join([f"{tag} <font color='{highlight_color}'>{w:.1f}</font>" if (w:=next((float(w0) for t0, w0 in matched_tags if t0 == tag), 0.0)) > 0 else tag for tag in all_tags])
        tags_label = QLabel(f"<div style='font-size:22px;'>{html_tags_str}</div>")
        tags_label.setObjectName("TagsLabel")
        tags_label.setWordWrap(True)
        tags_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        for w in (compare_label, weight_label, tags_label): w.installEventFilter(container)
        
        layout.addWidget(button, 2)
        layout.addWidget(compare_label, 3)
        layout.addWidget(weight_label, 1)
        layout.addWidget(tags_label, 8)
        return container

    # ### 修改 START: 重构 create_symbol_button 以使用新的颜色逻辑 ###
    def create_symbol_button(self, symbol):
        """创建并配置一个标准的 Symbol 按钮，Tooltip 改为最新财报日期，颜色根据复杂逻辑决定"""
        button = SymbolButton(symbol)
        # PyQt6: CursorShape
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.setFixedWidth(90)
        button.setObjectName("SymbolButton")

        # 左键点击事件
        button.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))
        
        # --- 核心修改：调用新函数并根据结果设置颜色 ---
        earning_price, price_trend, latest_date = self.get_color_decision_data(symbol)
        tooltip_text = f"最新财报日期: {latest_date.isoformat()}" if latest_date else "最新财报日期: 未知"
        button.setToolTip(f"<div style='font-size:16px; background-color:#FFFFE0; color:black; padding:5px;'>{tooltip_text}</div>")
        
        # PyQt6: ContextMenuPolicy
        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))
        
        color = 'white'
        if earning_price is not None and price_trend is not None:
            if price_trend == 'single':
                color = 'red' if earning_price > 0 else 'green' if earning_price < 0 else 'white'
            else:
                # 原有：基于两次收盘价比较的趋势和 earning price 正负的组合
                is_price_positive = earning_price > 0
                is_trend_rising = price_trend == 'rising'
                if is_trend_rising and is_price_positive: color = 'red'
                elif not is_trend_rising and is_price_positive: color = '#008B8B'
                elif is_trend_rising and not is_price_positive: color = '#912F2F'
                elif not is_trend_rising and not is_price_positive: color = 'green'
        
        button.setStyleSheet((button.styleSheet() or "") + f"; color: {color};")
        return button

    def on_symbol_click(self, symbol):
        """处理 Symbol 按钮的左键点击事件"""
        print(f"正在为 '{symbol}' 生成图表...")
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        compare_value = self.compare_data.get(symbol, "N/A")
        # 先取出四个指标
        shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(DB_PATH, symbol)
        
        try:
            # 调用从 b.py 移植的绘图函数
            plot_financial_data(
            DB_PATH,
            sector,
            symbol,
            compare_value,
            (shares_val, pb_val),
            marketcap_val,
            pe_val,
            self.json_data,
            '1Y',
            False
        )
        except Exception as e:
            QMessageBox.critical(self, "绘图错误", f"调用 plot_financial_data 时出错: {e}")
            print(f"调用 plot_financial_data 时出错: {e}")

    # ### 修改 2: 扩展右键菜单的选项 ###
    def show_context_menu(self, symbol):
        """创建并显示一个包含丰富选项的右键上下文菜单（新增“移动”子菜单）"""
        menu = QMenu(self)

        # --- 新增：移动（复制到组）子菜单，只显示指定的五个分组 ---
        move_menu = menu.addMenu("移动")
        allowed_groups = ["Must", "Today", "Short"]
        for group in allowed_groups:
            # 如果 panel_config 里没有这个组，也让它显示（第一次复制时会新建）
            in_cfg = False
            if group in self.panel_config:
                val = self.panel_config[group]
                if isinstance(val, dict):
                    in_cfg = (symbol in val)
                elif isinstance(val, list):
                    in_cfg = (symbol in val)
            # 创建动作
            act = QAction(group, self)
            act.setEnabled(not in_cfg)
            act.triggered.connect(lambda _,
                                s=symbol,
                                g=group: self.copy_symbol_to_group(s, g))
            move_menu.addAction(act)
        menu.addSeparator()
        
        actions = [
            ("在富途中搜索", lambda: execute_external_script('futu', symbol)),
            ("编辑 Tags",     lambda: execute_external_script('tags', symbol)),
            None,
            ("找相似",       lambda: execute_external_script('similar', symbol)),
            None,
            ("添加新事件", lambda: execute_external_script('event_input', symbol)),
            ("编辑事件", lambda: execute_external_script('event_editor', symbol)),
            None,
            ("添加到 Earning", lambda: execute_external_script('earning', symbol)),
            ("编辑 Earing DB", lambda: execute_external_script('editor_earning', symbol)),
            ("Kimi检索财报", lambda: execute_external_script('kimi', symbol)),
            None,
            ("加入黑名单",   lambda: execute_external_script('blacklist', symbol)),
        ]
        
        for item in actions:
            if item is None:
                menu.addSeparator()
            else:
                text, callback = item
                action = QAction(text, self)
                action.triggered.connect(callback)
                menu.addAction(action)
        # PyQt6: exec()
        menu.exec(QCursor.pos())

    def keyPressEvent(self, event):
        # PyQt6: Qt.Key.Key_Escape
        if event.key() == Qt.Key.Key_Escape:
            print("ESC被按下，正在关闭窗口...")
            self.close()
            return

        # "/" 键激活搜索框
        # event.text() 能准确反映用户输入的字符
        if event.text() == '/':
            if hasattr(self, 'search_input'):
                self.search_input.setFocus()
                # 全选已有内容，便于快速替换
                self.search_input.selectAll()
            return

        # 其他按键交给父类处理
        super().keyPressEvent(event)

    def get_stylesheet(self):
        # 字体栈定义
        font_family = "Segoe UI, Microsoft YaHei, .AppleSystemUIFont, sans-serif"
        
        return f"""
        QMainWindow {{
            background-color: #2E2E2E;
            font-family: {font_family};
        }}
        QGroupBox {{
            font-size: 12px;
            font-weight: bold;
            color: #E0E0E0;
            border: 1px solid #555;
            border-radius: 8px;
            margin-top: 10px;
            padding: 20px 10px 10px 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 10px;
            color: #00AEEF;
            left: 10px;
        }}
        QScrollArea {{
            border: none;
        }}
        #SymbolButton {{
            background-color: #2E2E2E;
            color: white;
            font-size: 18px;
            font-weight: bold;
            padding: 5px;
            border-radius: 4px;
            /* 加一圈细白边 */
            border: 1px solid #FFFFFF;
        }}
        #SymbolButton:hover {{
            background-color: #3A3A3A;
            border: 1px solid #FFFFFF;
        }}
        QLabel {{
            font-size: 20px;
            color: #D0D0D0;
        }}
        #WeightLabel {{
            color: #BDBDBD;
            font-weight: bold;
            background-color: #2E2E2E;
            border-radius: 4px;
        }}
        #CompareLabel {{
            color: #A5D6A7;
            font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
        }}
        #TagsLabel {{
            color: #BDBDBD;
        }}
        QToolTip {{
            border: 1px solid #C0C0C0;
            border-radius: 4px;
        }}
        QMenu {{
            background-color: #3C3C3C;
            color: #E0E0E0;
            border: 1px solid #555;
            font-size: 14px;
        }}
        QMenu::item {{
            padding: 8px 25px 8px 20px;
        }}
        QMenu::item:selected {{
            background-color: #007ACC;
        }}
        QMenu::item:disabled {{
            color: #777777;
        }}
        QMenu::separator {{
            height: 1px;
            background: #555;
            margin-left: 10px;
            margin-right: 10px;
        }}
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
        sys.exit()

    # --- 步骤 2: 加载所有数据 ---
    print("正在加载所需数据...")
    try:
        description_data = load_json_data(DESCRIPTION_PATH)
        weight_groups = load_weight_groups()
        tags_weight_config = {tag: weight for weight, tags in weight_groups.items() for tag in tags}
        compare_data = load_compare_data(COMPARE_DATA_PATH)
        sector_data = load_json_data(SECTORS_ALL_PATH)
        panel_config = load_json_data(PANEL_CONFIG_PATH)
        
        all_data_package = {
            "description": description_data,
            "compare":    compare_data,
            "sectors":    sector_data,
            "tags_weight": tags_weight_config,
            "panel_config": panel_config,
            "panel_config_path": PANEL_CONFIG_PATH,
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
    main_window = SimilarityViewerWindow(
        symbol,
        target_tags,
        related_symbols,
        all_data_package
    )
    main_window.show()
    
    sys.exit(app.exec())
