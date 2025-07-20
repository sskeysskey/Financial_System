import sys
import json
import sqlite3
from collections import OrderedDict
import subprocess
from decimal import Decimal

# ----------------------------------------------------------------------
# PyQt5 Imports
# ----------------------------------------------------------------------
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, 
    QMenu, QAction, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor

# ----------------------------------------------------------------------
# Update sys.path so we can import from custom modules
# ----------------------------------------------------------------------
sys.path.append('/Users/yanzhang/Documents/Financial_System/Query')
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# Constants / Global Configurations
# ----------------------------------------------------------------------
CONFIG_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
COLORS_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
DESCRIPTION_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
SECTORS_ALL_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'
EARNINGS_FILE_PATH = '/Users/yanzhang/Documents/News/Earnings_Release_new.txt'
TAGS_WEIGHT_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json'

# --- 新增常量 ---
# 用于保存展开/折叠状态的文件路径
EXPANSION_STATE_PATH = '/Users/yanzhang/Documents/Financial_System/Query/Check_Earning_Similar.json'
# 控制显示的相关股票数量
RELATED_SYMBOLS_LIMIT = 10

# 全局变量
symbol_manager = None
compare_data = {}
config = {}
keyword_colors = {}
sector_data = {}
json_data = {}
tags_weight_config = {}
DEFAULT_WEIGHT = Decimal('1')


class SymbolManager:    
    def __init__(self, symbols_list):
        self.symbols = symbols_list
        self.current_index = -1
        if not self.symbols: print("Warning: No symbols loaded into SymbolManager.")
    def next_symbol(self):
        if not self.symbols: return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]
    def previous_symbol(self):
        if not self.symbols: return None
        self.current_index = (self.current_index - 1) % len(self.symbols)
        return self.symbols[self.current_index]
    def set_current_symbol(self, symbol):
        if symbol in self.symbols: self.current_index = self.symbols.index(symbol)
        else: print(f"Warning: Symbol {symbol} not found in the list.")
    def reset(self): self.current_index = -1

# ----------------------------------------------------------------------
# Utility / Helper Functions
# ----------------------------------------------------------------------

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file, object_pairs_hook=OrderedDict)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading JSON from {path}: {e}")
        return {}

# --- 新增函数：加载展开/折叠状态 ---
def load_expansion_states(path):
    """从JSON文件加载并返回展开/折叠状态字典"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 如果文件不存在或格式错误，返回空字典，程序将使用默认展开状态
        return {}

def load_text_data(path):
    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or ':' not in line: continue
                key, value = map(str.strip, line.split(':', 1))
                cleaned_key = key.split()[-1]
                data[cleaned_key] = tuple(p.strip() for p in value.split(',')) if ',' in value else value
    except FileNotFoundError:
        print(f"Error: Text data file not found at {path}")
    return data

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
                    if date_str not in earnings_schedule:
                        earnings_schedule[date_str] = {'BMO': [], 'AMC': []}
                    if time_code.upper() in ['BMO', 'AMC']:
                        earnings_schedule[date_str][time_code.upper()].append(symbol)
                        if symbol not in all_symbols:
                            all_symbols.append(symbol)
    except FileNotFoundError:
        print(f"Error: Earnings file not found at {path}")
    return OrderedDict(sorted(earnings_schedule.items())), all_symbols

# ... (其他辅助函数 fetch_mnspp_data_from_db, get_tags_for_symbol, 等等都无变化, 为简洁省略) ...
def fetch_mnspp_data_from_db(db_path, symbol):
    with sqlite3.connect(db_path) as conn:
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
    base_path = '/Users/yanzhang/Documents/Financial_System'
    script_configs = { 'blacklist': f'{base_path}/Operations/Insert_Blacklist.py', 'similar': f'{base_path}/Query/Find_Similar_Tag.py', 'tags': f'{base_path}/Operations/Editor_Symbol_Tags.py', 'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py', 'earning': f'{base_path}/Operations/Insert_Earning.py', 'futu': '/Users/yanzhang/Documents/ScriptEditor/Stock_CheckFutu.scpt', 'kimi': '/Users/yanzhang/Documents/ScriptEditor/CheckKimi_Earning.scpt' }
    try:
        if script_type in ['futu', 'kimi']: subprocess.Popen(['osascript', script_configs[script_type], keyword])
        else:
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.Popen([python_path, script_configs[script_type], keyword])
    except Exception as e: print(f"执行脚本时出错: {e}")
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

# <<< 关键修正：替换为 b.py 的完整两阶段匹配逻辑 >>>
def find_symbols_by_tags_b(target_tags_with_weight, data, original_symbol):
    """
    使用精确匹配和部分匹配两阶段算法查找相关股票。
    """
    related_symbols = {'stocks': [], 'etfs': []}
    target_tags_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}

    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            # 跳过原始股票本身
            if item.get('symbol') == original_symbol:
                continue

            tags = item.get('tag', [])
            matched_tags_with_weight = []
            used_target_tags = set()  # 用于记录已经匹配过的目标标签，避免重复计算

            # 第一阶段：精确匹配
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in target_tags_dict and tag_lower not in used_target_tags:
                    matched_tags_with_weight.append((tag, target_tags_dict[tag_lower]))
                    used_target_tags.add(tag_lower)

            # 第二阶段：部分匹配 (模糊匹配)
            for tag in tags:
                tag_lower = tag.lower()
                # 如果这个标签已经被精确匹配过了，就跳过
                if tag_lower in used_target_tags:
                    continue
                
                for target_tag, target_weight in target_tags_dict.items():
                    # 如果目标标签已经被用过了，也跳过
                    if target_tag in used_target_tags:
                        continue
                    
                    # 检查是否为包含关系（任意一方包含另一方），且不完全相等
                    if (target_tag in tag_lower or tag_lower in target_tag) and tag_lower != target_tag:
                        # 根据原始权重决定部分匹配的权重
                        weight_to_use = Decimal('1.0') if target_weight > Decimal('1.0') else target_weight
                        matched_tags_with_weight.append((tag, weight_to_use))
                        used_target_tags.add(target_tag) # 标记此目标tag已用
                        break # 移动到下一个item的tag

            if matched_tags_with_weight:
                total_weight = sum(weight for _, weight in matched_tags_with_weight)
                related_symbols[category].append((item['symbol'], total_weight))

    # 合并并按总权重降序排序
    combined_list = related_symbols['stocks'] + related_symbols['etfs']
    combined_list.sort(key=lambda x: x[1], reverse=True)
    
    return combined_list


# ----------------------------------------------------------------------
# PyQt5 Main Application Window
# ----------------------------------------------------------------------
class EarningsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = config
        # --- 修改：加载状态 ---
        self.expansion_states = load_expansion_states(EXPANSION_STATE_PATH)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("财报日历查看器 (V3 - 状态记忆)")
        # ... (init_ui 的其余部分无变化, 为简洁省略) ...
        self.setFocusPolicy(Qt.StrongFocus)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.setCentralWidget(self.scroll_area)
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.scroll_content.setLayout(self.main_layout)
        self.main_layout.setAlignment(Qt.AlignTop)
        self.apply_stylesheet()
        self.populate_ui()

    def apply_stylesheet(self):
        button_styles = { "Cyan": ("cyan", "black"), "Blue": ("blue", "white"), "Purple": ("purple", "white"), "Green": ("green", "white"), "White": ("white", "black"), "Yellow": ("yellow", "black"), "Orange": ("orange", "black"), "Red": ("red", "black"), "Black": ("black", "white"), "Default": ("#ddd", "black") }
        qss = ""
        for name, (bg, fg) in button_styles.items():
            qss += f""" QPushButton#{name} {{ background-color: {bg}; color: {fg}; font-size: 16px; padding: 5px; border: 1px solid #333; border-radius: 4px; }} QPushButton#{name}:hover {{ background-color: {self.lighten_color(bg)}; }} """
        qss += """ QGroupBox { font-size: 16px; font-weight: bold; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; } QGroupBox[checkable="true"]::indicator { left: 5px; } QGroupBox[checkable="true"]::title { padding-left: 25px; } QWidget#RelatedContainer { border: 1px solid #ccc; border-radius: 4px; margin-left: 5px; } """
        self.setStyleSheet(qss)

    def lighten_color(self, color_name, factor=1.2):
        from PyQt5.QtGui import QColor
        color = QColor(color_name)
        h, s, l, a = color.getHslF()
        l = min(1.0, l * factor)
        color.setHslF(h, s, l, a)
        return color.name()

    def get_button_style_name(self, keyword):
        color_map = { "cyan": "Cyan", "blue": "Blue", "purple": "Purple", "yellow": "Yellow", "orange": "Orange", "black": "Black", "white": "White", "green": "Green", "red": "Red",}
        for color, style_name in color_map.items():
            if keyword in keyword_colors.get(f"{color}_keywords", []): return style_name
        return "Default"

    def populate_ui(self):
        earnings_schedule, _ = parse_earnings_file(EARNINGS_FILE_PATH)

        # 预先构建一个所有合法 sector symbols 的集合，用于过滤
        valid_symbols = set()
        for names in sector_data.values():
            valid_symbols.update(names)

        for date_str, data in earnings_schedule.items():
            # 1) 日期 GroupBox
            date_group = QGroupBox(date_str)
            date_group.setCheckable(True)
            is_date_expanded = self.expansion_states.get(date_str, {}).get("_is_expanded", True)
            date_group.setChecked(is_date_expanded)
            self.main_layout.addWidget(date_group)

            # 日期内容容器
            date_content_widget = QWidget()
            date_content_widget.setVisible(is_date_expanded)
            date_group_layout = QVBoxLayout(date_content_widget)
            date_group_layout.setContentsMargins(10, 5, 5, 5)

            date_group.setLayout(QVBoxLayout())
            date_group.layout().addWidget(date_content_widget)
            date_group.toggled.connect(date_content_widget.setVisible)

            # 盘前/盘后两个子分组
            for time_code in ['BMO', 'AMC']:
                symbols = data.get(time_code)
                if not symbols:
                    continue

                time_label = "盘前 (BMO)" if time_code == 'BMO' else "盘后 (AMC)"
                time_group = QGroupBox(time_label)
                time_group.setCheckable(True)
                is_time_expanded = self.expansion_states.get(date_str, {}).get(time_code, True)
                time_group.setChecked(is_time_expanded)
                date_group_layout.addWidget(time_group)

                # 时间段内容容器
                time_content_widget = QWidget()
                time_content_widget.setVisible(is_time_expanded)
                time_layout = QGridLayout(time_content_widget)
                time_layout.setColumnStretch(1, 1)

                time_group.setLayout(QVBoxLayout())
                time_group.layout().addWidget(time_content_widget)
                time_group.toggled.connect(time_content_widget.setVisible)

                # 为每个 ticker 创建按钮和关联按钮
                for row_index, symbol in enumerate(symbols):
                    # 主按钮
                    button_text = f"{symbol} {compare_data.get(symbol, '')}"
                    symbol_button = QPushButton(button_text)
                    symbol_button.setObjectName(self.get_button_style_name(symbol))
                    symbol_button.clicked.connect(lambda _, k=symbol: self.on_keyword_selected_chart(k))
                    tags_info = get_tags_for_symbol(symbol)
                    tags_info_str = ", ".join(tags_info) if isinstance(tags_info, list) else tags_info
                    symbol_button.setToolTip(
                        f"<div style='font-size:20px;background-color:lightyellow;color:black;'>{tags_info_str}</div>"
                    )
                    symbol_button.setContextMenuPolicy(Qt.CustomContextMenu)
                    symbol_button.customContextMenuRequested.connect(
                        lambda pos, k=symbol: self.show_context_menu(k)
                    )

                    # 相关符号容器
                    related_container = QWidget()
                    related_layout = QHBoxLayout(related_container)
                    related_layout.setContentsMargins(2, 2, 2, 2)
                    related_layout.setSpacing(5)
                    related_layout.setAlignment(Qt.AlignLeft)

                    # 计算关联 symbols，并过滤掉不在 sector_data 里的
                    target_tags = find_tags_by_symbol_b(symbol, json_data)
                    if target_tags:
                        related_symbols_data = find_symbols_by_tags_b(target_tags, json_data, symbol)
                        if related_symbols_data:
                            related_container.setObjectName("RelatedContainer")
                            count = 0
                            for rel_symbol, _ in related_symbols_data:
                                if rel_symbol not in valid_symbols:
                                    continue
                                if count >= RELATED_SYMBOLS_LIMIT:
                                    break
                                rel_button = QPushButton(f"{rel_symbol} {compare_data.get(rel_symbol, '')}")
                                rel_button.setObjectName(self.get_button_style_name(rel_symbol))
                                rel_button.clicked.connect(
                                    lambda _, k=rel_symbol: self.on_keyword_selected_chart(k)
                                )
                                rel_tags = get_tags_for_symbol(rel_symbol)
                                rel_tags_str = ", ".join(rel_tags) if isinstance(rel_tags, list) else rel_tags
                                rel_button.setToolTip(
                                    f"<div style='font-size:20px;background-color:lightyellow;color:black;'>{rel_tags_str}</div>"
                                )
                                rel_button.setContextMenuPolicy(Qt.CustomContextMenu)
                                rel_button.customContextMenuRequested.connect(
                                    lambda pos, k=rel_symbol: self.show_context_menu(k)
                                )
                                related_layout.addWidget(rel_button)
                                count += 1

                    # 将按钮和相关容器加入布局
                    time_layout.addWidget(symbol_button, row_index, 0)
                    time_layout.addWidget(related_container, row_index, 1)

    # --- 新增方法：保存展开/折叠状态 ---
    def save_expansion_states(self):
        """遍历UI并保存所有可折叠GroupBox的状态到JSON文件"""
        states = {}
        # 遍历主布局中的所有日期GroupBox
        for i in range(self.main_layout.count()):
            date_group = self.main_layout.itemAt(i).widget()
            if isinstance(date_group, QGroupBox) and date_group.isCheckable():
                date_str = date_group.title()
                states[date_str] = {"_is_expanded": date_group.isChecked()}
                
                # 查找日期GroupBox内的盘前/盘后GroupBox
                time_groups = date_group.findChildren(QGroupBox)
                for time_group in time_groups:
                    if time_group.isCheckable():
                        title = time_group.title()
                        if "BMO" in title:
                            states[date_str]["BMO"] = time_group.isChecked()
                        elif "AMC" in title:
                            states[date_str]["AMC"] = time_group.isChecked()
        
        try:
            with open(EXPANSION_STATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(states, f, indent=4)
        except Exception as e:
            print(f"保存状态文件时出错: {e}")

    def show_context_menu(self, keyword):
        menu = QMenu(self)
        actions = [ ("添加到 Earning", lambda: execute_external_script('earning', keyword)), ("编辑 Earing DB", lambda: execute_external_script('editor_earning', keyword)), ("Kimi检索财报", lambda: execute_external_script('kimi', keyword)), None, ("编辑 Tags", lambda: execute_external_script('tags', keyword)), ("在富途中搜索", lambda: execute_external_script('futu', keyword)), ("找相似(旧版)", lambda: execute_external_script('similar', keyword)), None, ("加入黑名单", lambda: execute_external_script('blacklist', keyword)), ]
        for item in actions:
            if item is None: menu.addSeparator()
            else:
                text, callback = item
                menu.addAction(QAction(text, self, triggered=callback))
        menu.exec_(QCursor.pos())

    def on_keyword_selected_chart(self, value):
        global symbol_manager
        sector = next((s for s, names in sector_data.items() if value in names), None)
        if sector:
            symbol_manager.set_current_symbol(value)
            compare_value = compare_data.get(value, "N/A")
            shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(DB_PATH, value)
            plot_financial_data( DB_PATH, sector, value, compare_value, (shares_val, pb_val), marketcap_val, pe_val, json_data, '1Y', False )
            self.setFocus()

    def handle_arrow_key(self, direction):
        global symbol_manager
        symbol = symbol_manager.next_symbol() if direction == 'down' else symbol_manager.previous_symbol()
        if symbol: self.on_keyword_selected_chart(symbol)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape: self.close()
        elif key == Qt.Key_Down: self.handle_arrow_key('down')
        elif key == Qt.Key_Up: self.handle_arrow_key('up')
        else: super().keyPressEvent(event)

    def closeEvent(self, event):
        """在关闭窗口前保存状态"""
        # --- 修改：调用保存状态的方法 ---
        self.save_expansion_states()
        
        global symbol_manager
        symbol_manager.reset()
        QApplication.quit()
        # event.accept() # QApplication.quit()会处理关闭，所以这行不是必须的

if __name__ == '__main__':
    keyword_colors = load_json(COLORS_PATH)
    config = load_json(CONFIG_PATH)
    json_data = load_json(DESCRIPTION_PATH)
    sector_data = load_json(SECTORS_ALL_PATH)
    compare_data = load_text_data(COMPARE_DATA_PATH)
    weight_groups = load_weight_groups()
    tags_weight_config = {tag: weight for weight, tags in weight_groups.items() for tag in tags}
    _, all_symbols_in_earnings = parse_earnings_file(EARNINGS_FILE_PATH)
    symbol_manager = SymbolManager(all_symbols_in_earnings)
    app = QApplication(sys.argv)
    main_window = EarningsWindow()
    main_window.showMaximized()
    sys.exit(app.exec_())