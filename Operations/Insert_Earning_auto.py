import sys
import json
import sqlite3
import subprocess
import os
from datetime import date, timedelta
from functools import partial
from collections import OrderedDict

# --- 修改: 切换到 PyQt6 ---
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QLabel,
    QMenu, QHeaderView
)
from PyQt6.QtGui import QCursor, QKeySequence, QFont, QBrush, QColor, QShortcut, QAction
from PyQt6.QtCore import Qt, QTimer

# --- 路径动态化处理 ---
HOME = os.path.expanduser("~") 

# 添加自定义模块的路径
sys.path.append(os.path.join(HOME, 'Coding/Financial_System/Query'))
from Chart_input import plot_financial_data

# 定义所有需要用到的文件路径
TXT_PATH = os.path.join(HOME, "Coding/News/Earnings_Release_new.txt")
SECTORS_JSON_PATH = os.path.join(HOME, "Coding/Financial_System/Modules/Sectors_All.json")
DB_PATH = os.path.join(HOME, "Coding/Database/Finance.db")
DESCRIPTION_PATH = os.path.join(HOME, 'Coding/Financial_System/Modules/description.json')
COMPARE_DATA_PATH = os.path.join(HOME, 'Coding/News/backup/Compare_All.txt')
PANEL_CONFIG_PATH = os.path.join(HOME, 'Coding/Financial_System/Modules/Sectors_panel.json')

PERIOD_DISPLAY = {
    "BMO": "↩︎",
    "AMC": "↪︎",
    "TNS": "？"
}

def get_tags_for_symbol(symbol, desc_data):
    """
    仿 b.py 中的逻辑：从 description.json（desc_data）里找 tags。
    desc_data 格式应包含 "stocks" / "etfs" 两个列表，每项是 { "symbol": ..., "tag": [...] }
    """
    for item in desc_data.get("stocks", []):
        if item.get("symbol") == symbol:
            return item.get("tag", [])
    for item in desc_data.get("etfs", []):
        if item.get("symbol") == symbol:
            return item.get("tag", [])
    return []

def execute_external_script(script_type, keyword):
    """
    执行外部脚本（AppleScript 或 Python）。
    """
    # 路径动态化
    base_path = os.path.join(HOME, 'Coding/Financial_System')
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar': f'{base_path}/Query/Search_Similar_Tag.py',
        'tags': f'{base_path}/Operations/Editor_Tags.py',
        'input_earning': f'{base_path}/Operations/Insert_Earning_Manual.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'event_input': f'{base_path}/Operations/Insert_Events.py',
        'event_editor': f'{base_path}/Operations/Editor_Events.py',
        'futu': os.path.join(HOME, 'Coding/ScriptEditor/Stock_CheckFutu.scpt'),
        'kimi': os.path.join(HOME, 'Coding/ScriptEditor/Check_Earning.scpt')
    }

    try:
        if script_type in ['futu', 'kimi']:
            subprocess.Popen(['osascript', script_configs[script_type], keyword])
        else:
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.Popen([python_path, script_configs[script_type], keyword])
    except Exception as e:
        print(f"执行脚本时出错: {e}")
        QMessageBox.critical(None, "脚本执行错误", f"执行 '{script_type}' 脚本时发生错误:\n{e}")

def load_json(path):
    """加载 JSON 文件，并保持顺序"""
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)

def load_text_data(path):
    """加载 key: value 格式的文本文件"""
    data = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            key, value = map(str.strip, line.split(':', 1))
            cleaned_key = key.split()[-1]
            if ',' in value:
                parts = [p.strip() for p in value.split(',')]
                data[cleaned_key] = tuple(parts)
            else:
                data[cleaned_key] = value
    return data

def fetch_mnspp_data_from_db(db_path, symbol):
    """
    根据股票代码从MNSPP表中查询 shares, marketcap, pe_ratio, pb。
    如果未找到，则返回默认值。
    """
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?"
        cursor.execute(query, (symbol,))
        result = cursor.fetchone()

    if result:
        shares, marketcap, pe, pb = result
        return shares, marketcap, pe, pb
    else:
        return "N/A", None, "N/A", "--"

class SymbolButton(QPushButton):
    def mousePressEvent(self, event):
        # PyQt6: 使用 Qt.MouseButton.LeftButton
        if event.button() == Qt.MouseButton.LeftButton:
            mods = event.modifiers()
            # PyQt6: 使用 Qt.KeyboardModifier.AltModifier
            # Option(⌥) + 左键 → 找相似
            if mods & Qt.KeyboardModifier.AltModifier:
                execute_external_script('similar', self.text())
                return
            # PyQt6: 使用 Qt.KeyboardModifier.ShiftModifier
            # Shift + 左键 → 在富途中搜索
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                execute_external_script('futu', self.text())
                return
        # 其他情况走原有行为（例如普通左键点击会触发 on_symbol_button_clicked）
        super().mousePressEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Earnings 百分比处理")
        
        # --- 导航相关变量 ---
        self.ordered_symbols_on_screen = [] # 存储当前界面所有 Symbol 的顺序列表
        self.current_symbol_index = -1      # 当前打开的 Symbol 索引

        today = date.today()
        self.today_str = today.strftime("%Y-%m-%d") # 今天
        self.date1 = (today - timedelta(days=1)).strftime("%Y-%m-%d") # 昨天
        self.date2 = (today - timedelta(days=2)).strftime("%Y-%m-%d") # 前天
        self.three_days_ago = (today - timedelta(days=3)).strftime("%Y-%m-%d")

        # --- 2. 数据处理更新：初始化字典以包含今天 ---
        self.symbols_by_date = {self.today_str: [], self.date1: [], self.date2: []}
        self.symbol_to_period = {}

        with open(TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = [p.strip() for p in line.split(":")]
                symbol, period, dt = parts[0], parts[1], parts[2]
                
                # 现在如果dt是今天，也能被正确添加到字典中
                if dt in self.symbols_by_date:
                    self.symbols_by_date[dt].append((symbol, period))
                    self.symbol_to_period[symbol] = period

        desired_order = ['BMO', 'AMC', 'TNS']
        def order_key(item):
            _, per = item
            if per in desired_order:
                return (desired_order.index(per), "")
            else:
                return (len(desired_order), per)

        for dt in self.symbols_by_date:
            self.symbols_by_date[dt].sort(key=order_key)

        self.symbol_to_sector = {}
        with open(SECTORS_JSON_PATH, "r", encoding="utf-8") as f:
            sectors = json.load(f)
        for sector_name, syms in sectors.items():
            for s in syms:
                self.symbol_to_sector[s] = sector_name

        self.description_data = load_json(DESCRIPTION_PATH)
        self.compare_data = load_text_data(COMPARE_DATA_PATH)

        # PyQt6: 使用 Qt.Key.Key_Escape
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)

        self.db_path = DB_PATH
        self.conn = sqlite3.connect(self.db_path, timeout=60.0)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        with open(PANEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
            self.panel_config = json.load(f, object_pairs_hook=OrderedDict)
        self.panel_config_path = PANEL_CONFIG_PATH

        self._init_ui()
        self.refresh_data()

    def refresh_data(self):
        """刷新并重新填充所有表格，同时更新导航列表"""
        self.ordered_symbols_on_screen.clear()
        
        # 清空表格内容
        self.table2.setRowCount(0)
        self.table1.setRowCount(0)
        self.table_today.setRowCount(0)

        # 按照视觉顺序填充：前天 -> 昨天 -> 今天
        self.process_date2()
        self.process_date1()
        self.process_today()

    def _init_ui(self):
        cw = QWidget()
        hlay = QHBoxLayout()

        self.apply_stylesheet()
        
        # --- 前天栏目 (左) ---
        gb2 = QGroupBox(f"日期 {self.date2} 财报已发布 （可替换旧百分比）")
        lay2 = QVBoxLayout()
        self.table2 = QTableWidget(0, 6)
        self.table2.setHorizontalHeaderLabels(["Symbol股票代码", "时段", "新百分比(%)", "旧百分比(%)", "操作", "————————————"])
        self.table2.verticalHeader().setVisible(False)
        # PyQt6: 使用 Qt.ContextMenuPolicy.CustomContextMenu
        self.table2.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table2.customContextMenuRequested.connect(self.show_table_context_menu)
        lay2.addWidget(self.table2)
        gb2.setLayout(lay2)

        # --- 昨天栏目 (中) ---
        gb1 = QGroupBox(f"日期 {self.date1} （盘后 AMC）（点击“替换”写入/覆盖）")
        lay1 = QVBoxLayout()
        self.table1 = QTableWidget(0, 5)
        self.table1.setHorizontalHeaderLabels(["Symbol股票代码", "时段", "百分比(%)", "操作", "———————————"])
        self.table1.verticalHeader().setVisible(False)
        self.table1.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table1.customContextMenuRequested.connect(self.show_table_context_menu)
        lay1.addWidget(self.table1)
        gb1.setLayout(lay1)

        # --- 2. UI更新：新增今天栏目 (右) ---
        gb_today = QGroupBox(f"日期 {self.today_str} (盘前 BMO)")
        lay_today = QVBoxLayout()
        self.table_today = QTableWidget(0, 3) # 只有两列
        self.table_today.setHorizontalHeaderLabels(["Symbol", "时段", "————————————————————————"])
        self.table_today.verticalHeader().setVisible(False)
        self.table_today.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_today.customContextMenuRequested.connect(self.show_table_context_menu)
        lay_today.addWidget(self.table_today)
        gb_today.setLayout(lay_today)

        # --- 3. UI更新：调整布局顺序和伸缩比例 ---
        # 按 左-中-右 的顺序添加 GroupBox
        hlay.addWidget(gb2, 5)          # 前天 (左)，伸缩比例为3
        hlay.addWidget(gb1, 5)          # 昨天 (中)，伸缩比例为3
        hlay.addWidget(gb_today, 4)     # 今天 (右)，伸缩比例为1，使其更窄

        gb2 .setMaximumWidth(500)
        gb1 .setMaximumWidth(420)
        gb_today.setMaximumWidth(400)

        cw.setLayout(hlay)
        self.setCentralWidget(cw)
        self.resize(1400, 1000) # 增加了宽度以容纳新栏目
        self.center_window()

    # ================= 核心导航逻辑 =================
    def handle_chart_callback(self, symbol, action):
        """处理 Chart_input 发回的导航指令"""
        if action in ('next', 'prev'):
            # 延迟一小会儿执行，确保窗口状态稳定
            QTimer.singleShot(50, lambda: self.navigate_to_adjacent_symbol(action))

    def navigate_to_adjacent_symbol(self, direction):
        total_count = len(self.ordered_symbols_on_screen)
        if total_count == 0: return

        if direction == 'next':
            new_index = (self.current_symbol_index + 1) % total_count
        else:
            new_index = (self.current_symbol_index - 1 + total_count) % total_count
            
        next_symbol = self.ordered_symbols_on_screen[new_index]
        # 显式传递 new_index
        self.on_symbol_button_clicked(next_symbol, btn_index=new_index)

    def on_symbol_button_clicked(self, symbol, btn_index=None):
        """点击 Symbol 按钮或导航切换时触发"""
        self.description_data = load_json(DESCRIPTION_PATH)
        sector = self.symbol_to_sector.get(symbol)
        if not sector: return

        # 关键修复：如果传入了明确的索引，就使用它；否则才去查找
        if btn_index is not None:
            self.current_symbol_index = btn_index
        else:
            # 这种情况通常发生在右键菜单或其他非列表点击触发时
            try:
                self.current_symbol_index = self.ordered_symbols_on_screen.index(symbol)
            except ValueError:
                self.current_symbol_index = -1

        compare_value = self.compare_data.get(symbol, "N/A")
        shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(self.db_path, symbol)

        # 准备窗口标题（显示当前是第几个）
        total_count = len(self.ordered_symbols_on_screen)
        window_title = f"{symbol}  ({self.current_symbol_index + 1}/{total_count})"

        plot_financial_data(
            self.db_path, sector, symbol, compare_value,
            (shares_val, pb_val), marketcap_val, pe_val,
            self.description_data, '1Y', False,
            callback=lambda action: self.handle_chart_callback(symbol, action),
            window_title_text=window_title
        )
    # ===============================================

    def apply_stylesheet(self):
        """定义并应用全局样式表"""
        qss = """
        /* SymbolButton 基础样式 */
        QPushButton#SymbolButton {
            background-color: #3498db; color: white; border: none;
            padding: 5px 10px; border-radius: 4px; font-weight: bold;
        }

        /* 1. BMO (盘前) 改为绿色 */
        QPushButton#SymbolButton[period="BMO"] { 
            background-color: #7C9B67;   /* 原 AMC 的淡绿色 */
            color: black; 
        }
        QPushButton#SymbolButton[period="BMO"]:hover { 
            background-color: #6E8B3D;   /* 原 AMC 的深一点的绿色 hover */
        }

        /* 2. AMC (盘后) 改为蓝色 */
        QPushButton#SymbolButton[period="AMC"] {
            background-color: #3498db;   /* 原 BMO 的蓝色 */
            color: black;                
        }
        QPushButton#SymbolButton[period="AMC"]:hover {
            background-color: #2980b9;   /* 原 BMO 的深蓝色 hover */
        }

        /* TNS 保持不变 */
        QPushButton#SymbolButton[period="TNS"] { background-color: #2c3e50; color: white; }
        QPushButton#SymbolButton[period="TNS"]:hover { background-color: #1f2d3d; }

        /* 写入/替换按钮样式保持不变 */
        QPushButton#ReplaceButton {
            background-color: #555555;    /* 深灰 */
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton#ReplaceButton:hover {
            background-color: #444444;    /* 更深灰 */
        }
        QPushButton#ReplaceButton:disabled {
            background-color: #333333;    /* 最深灰 */
            color: #888888;               /* 灰色文字 */
        }
        """
        self.setStyleSheet(qss)

    def _add_tag_row(self, table: QTableWidget, row: int, tags: list):
        """在 table 的 row 行后面插入一行，用来显示 tags。"""
        tag_str = ", ".join(tags) if tags else "无标签"
        insert_row = row + 1
        table.insertRow(insert_row)
        table.setSpan(insert_row, 0, 1, table.columnCount())
        lbl = QLabel(tag_str)
        # 修改 4：为Tags标签应用文本溢出截断样式
        lbl.setStyleSheet("""
            color: lightyellow; 
            font-size: 18pt;
            padding: 4px;
        """)
        table.setCellWidget(row + 1, 0, lbl)
        
        for c in range(table.columnCount()):
            item = table.item(row + 1, c)
            if item:
                # PyQt6: 使用 Qt.ItemFlag.NoItemFlags
                item.setFlags(Qt.ItemFlag.NoItemFlags)
        
        table.setRowHeight(insert_row, 45)

    def process_today(self):
        table = self.table_today
        
        # 步骤 1: 添加所有数据行，并收集tags
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.today_str]:
            if period != "BMO": continue
            
            # 1. 先加入列表，获取它在全局的索引
            self.ordered_symbols_on_screen.append(symbol)
            current_idx = len(self.ordered_symbols_on_screen) - 1

            row = table.rowCount()
            table.insertRow(row)

            table.setItem(row, 0, QTableWidgetItem())
            
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            # PyQt6: 使用 Qt.CursorShape.PointingHandCursor
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            # 2. 关键修复：将 current_idx 绑定到点击事件中
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, current_idx))
            table.setCellWidget(row, 0, btn)
            
            tags = get_tags_for_symbol(symbol, self.description_data)
            tags_to_add.append(tags) # 收集tags

            # 1: 时段
            display_period = PERIOD_DISPLAY.get(period, period)
            table.setItem(row, 1, QTableWidgetItem(display_period))

        # 步骤 2: 根据已添加的数据行计算并设置列宽
        table.resizeColumnsToContents()
        # PyQt6: QHeaderView.ResizeMode.Interactive
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        for i in range(len(tags_to_add) - 1, -1, -1):
            self._add_tag_row(table, i, tags_to_add[i])

    ### 修改：重构 process_date1 以解决布局问题 ###
    def process_date1(self):
        table = self.table1
        
        # 步骤 1: 添加数据行并收集tags
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.date1]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector: continue
            
            p1 = self._get_price_from_table(sector, self.date1, symbol)
            if p1 is None: continue

            p2 = self._get_prev_price(sector, self.date1, symbol)
            if p2 is None or p2 == 0: continue

            pct = round((p1 - p2) / p2 * 100, 2)

            # 1. 加入列表并获取索引
            self.ordered_symbols_on_screen.append(symbol)
            current_idx = len(self.ordered_symbols_on_screen) - 1

            row = table.rowCount()
            table.insertRow(row)

            table.setItem(row, 0, QTableWidgetItem())
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            # 2. 关键修复：绑定索引
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, current_idx))
            table.setCellWidget(row, 0, btn)
            
            tags = get_tags_for_symbol(symbol, self.description_data)
            tags_to_add.append(tags)

            table.setItem(row, 1, QTableWidgetItem(PERIOD_DISPLAY.get(period, period)))

            # 百分比
            item_pct = QTableWidgetItem(f"{pct}")
            font = QFont("Arial", 14, QFont.Weight.Bold)
            item_pct.setFont(font)
            color = QColor(255, 0, 0) if pct < 0 else QColor(255, 215, 0)
            item_pct.setForeground(QBrush(color))
            table.setItem(row, 2, item_pct)

            # “写入” 按钮
            replace_btn = QPushButton("写入")
            replace_btn.setObjectName("ReplaceButton")
            replace_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            replace_btn.clicked.connect(partial(self.on_replace_date1, symbol, pct, replace_btn))
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.addWidget(replace_btn)
            # PyQt6: Qt.AlignmentFlag.AlignCenter
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 3, container)
            
            if period == "BMO":
                self.auto_write_date1(symbol, pct, replace_btn)

        # 步骤 2, 3, 4
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i in range(len(tags_to_add) - 1, -1, -1):
            self._add_tag_row(table, i, tags_to_add[i])

    def process_date2(self):
        table = self.table2
        
        # 步骤 1: 添加数据行并收集tags
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.date2]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector: continue

            p1 = self._get_price_from_table(sector, self.date1, symbol)
            p2 = self._get_price_from_table(sector, self.date2, symbol)
            if p1 is None or p2 is None or p2 == 0: continue
            pct_new = round((p1 - p2) / p2 * 100, 2)

            # 1. 加入列表并获取索引
            self.ordered_symbols_on_screen.append(symbol)
            current_idx = len(self.ordered_symbols_on_screen) - 1

            self.cur.execute("SELECT id, price FROM Earning WHERE name=? AND date>=? ORDER BY date DESC LIMIT 1", (symbol, self.three_days_ago))
            rowr = self.cur.fetchone()
            
            auto_written = False
            if rowr:
                old_pct, record_id = float(rowr["price"]), rowr["id"]
            else:
                self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct_new))
                self.conn.commit()
                old_pct, record_id, auto_written = pct_new, self.cur.lastrowid, True

            row = table.rowCount()
            table.insertRow(row)

            # Symbol 按钮
            btn_sym = SymbolButton(symbol)
            btn_sym.setObjectName("SymbolButton")
            btn_sym.setProperty("period", period)
            # 2. 关键修复：绑定索引
            btn_sym.clicked.connect(partial(self.on_symbol_button_clicked, symbol, current_idx))
            table.setCellWidget(row, 0, btn_sym)

            tags = get_tags_for_symbol(symbol, self.description_data)
            tags_to_add.append(tags)

            table.setItem(row, 1, QTableWidgetItem(PERIOD_DISPLAY.get(period, period)))
            
            for i, val in enumerate([pct_new, old_pct]):
                item = QTableWidgetItem(f"{val}")
                item.setFont(QFont("Arial", 14, QFont.Weight.Bold))
                item.setForeground(QBrush(QColor(255, 0, 0) if val < 0 else QColor(255, 215, 0)))
                table.setItem(row, 2 + i, item)

            op_btn = QPushButton("已写入" if (auto_written or pct_new == old_pct) else "替换")
            op_btn.setObjectName("ReplaceButton")
            op_btn.setEnabled(not (auto_written or pct_new == old_pct))
            if op_btn.isEnabled():
                op_btn.clicked.connect(partial(self.on_replace_date2, symbol, pct_new, record_id, op_btn))

            container = QWidget()
            hl = QHBoxLayout(container)
            hl.addWidget(op_btn)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 4, container)

        # 步骤 2, 3, 4
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i in range(len(tags_to_add) - 1, -1, -1):
            self._add_tag_row(table, i, tags_to_add[i])

    # ================= 其余辅助函数 =================
    def apply_stylesheet(self):
        qss = """
        QPushButton#SymbolButton { background-color: #3498db; color: white; border: none; padding: 5px 10px; border-radius: 4px; font-weight: bold; }
        QPushButton#SymbolButton[period="BMO"] { background-color: #7C9B67; color: black; }
        QPushButton#SymbolButton[period="AMC"] { background-color: #3498db; color: black; }
        QPushButton#SymbolButton[period="TNS"] { background-color: #2c3e50; color: white; }
        QPushButton#ReplaceButton { background-color: #555555; color: white; border: none; padding: 5px 15px; border-radius: 4px; font-weight: bold; }
        QPushButton#ReplaceButton:disabled { background-color: #333333; color: #888888; }
        """
        self.setStyleSheet(qss)

    def _add_tag_row(self, table, row, tags):
        tag_str = ", ".join(tags) if tags else "无标签"
        insert_row = row + 1
        table.insertRow(insert_row)
        table.setSpan(insert_row, 0, 1, table.columnCount())
        lbl = QLabel(tag_str)
        lbl.setStyleSheet("color: lightyellow; font-size: 18pt; padding: 4px;")
        table.setCellWidget(insert_row, 0, lbl)
        table.setRowHeight(insert_row, 45)

    def _get_prev_price(self, table, dt, symbol):
        self.cur.execute(f"SELECT price FROM `{table}` WHERE name=? AND date<? ORDER BY date DESC LIMIT 1", (symbol, dt))
        r = self.cur.fetchone()
        return r["price"] if r else None
    
    def _get_price_from_table(self, table, dt, symbol):
        try:
            self.cur.execute(f"SELECT price FROM `{table}` WHERE date=? AND name=?", (dt, symbol))
            r = self.cur.fetchone()
            return r["price"] if r else None
        except: return None

    def auto_write_date1(self, symbol, pct, btn):
        self.cur.execute("SELECT 1 FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        if not self.cur.fetchone():
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
            self.conn.commit()
        btn.setText("已写入")
        btn.setEnabled(False)
    
    def on_replace_date1(self, symbol, pct, btn):
        self.cur.execute("SELECT id FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        if self.cur.fetchone():
            if QMessageBox.question(self, "确认", f"覆盖 {symbol} {self.date1} 记录？") != QMessageBox.StandardButton.Yes: return
            self.cur.execute("UPDATE Earning SET price=? WHERE date=? AND name=?", (pct, self.date1, symbol))
        else:
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
        self.conn.commit()
        btn.setText("已处理")
        btn.setEnabled(False)

    def on_replace_date2(self, symbol, new_pct, record_id, btn):
        if QMessageBox.question(self, "确认", f"替换 {symbol} 旧百分比为 {new_pct}%？") == QMessageBox.StandardButton.Yes:
            # 1. 更新数据库
            self.cur.execute("UPDATE Earning SET price=?, date=? WHERE id=?", (new_pct, self.date1, record_id))
            self.conn.commit()
            
            # 2. 更新按钮状态
            btn.setText("已替换")
            btn.setEnabled(False)

            # --- 3. 新增：更新界面上的“旧百分比”显示 ---
            # 我们需要找到这个按钮所在的行
            # 在 QTableWidget 中，可以通过 indexAt 找到 widget 所在的 modelIndex
            index = self.table2.indexAt(btn.parent().pos()) 
            if index.isValid():
                row = index.row()
                # 旧百分比在第 3 列（索引为 3，因为列是：Symbol, 时段, 新%, 旧%, 操作...）
                # 注意：在你的代码中，新%是索引2，旧%是索引3
                old_pct_item = self.table2.item(row, 3)
                if old_pct_item:
                    old_pct_item.setText(f"{new_pct}")
                    # 也可以顺便更新颜色（可选）
                    color = QColor(255, 0, 0) if new_pct < 0 else QColor(255, 215, 0)
                    old_pct_item.setForeground(QBrush(color))

    def show_table_context_menu(self, pos):
        table = self.sender()
        row = table.rowAt(pos.y())
        if row == -1: return
        
        # 循环向上查找，直到找到 SymbolButton 为止（防止点在 Tag 行上）
        widget = None
        for r in range(row, -1, -1):
            widget = table.cellWidget(r, 0)
            if isinstance(widget, SymbolButton):
                break
        
        if not isinstance(widget, SymbolButton): return
        symbol = widget.text()

        menu = QMenu()
        move_menu = menu.addMenu("移动")
        for group in ["Must", "Today", "Short"]:
            act = QAction(group, self)
            act.triggered.connect(partial(self.copy_symbol_to_group, symbol, group))
            move_menu.addAction(act)
        
        menu.addSeparator()
        for label, stype in [("新增事件","event_input"), ("编辑 Tags","tags"), ("编辑事件","event_editor"), ("Kimi检索","kimi"), ("富途搜索","futu"), ("找相似","similar")]:
            menu.addAction(label, partial(execute_external_script, stype, symbol))
        menu.exec(QCursor.pos())

    def copy_symbol_to_group(self, symbol, group):
        cfg = self.panel_config
        if group not in cfg: cfg[group] = {}
        if isinstance(cfg[group], dict): cfg[group][symbol] = ""
        else: cfg[group].append(symbol)
        with open(self.panel_config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        QMessageBox.information(self, "成功", f"已复制 {symbol} 到 {group}")

    def center_window(self):
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    # PyQt6: exec 替代 exec_
    sys.exit(app.exec())

if __name__ == "__main__":
    main()