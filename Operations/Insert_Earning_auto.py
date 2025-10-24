import sys
import json
import sqlite3
import subprocess
from datetime import date, timedelta
from functools import partial
from collections import OrderedDict

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QShortcut, QLabel,
    QMenu, QAction, QHeaderView
)
from PyQt5.QtGui import QCursor, QKeySequence, QFont, QBrush, QColor
from PyQt5.QtCore import Qt

# 添加自定义模块的路径，以便可以导入 Chart_input
sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
from Chart_input import plot_financial_data

# 定义所有需要用到的文件路径，方便管理
TXT_PATH = "/Users/yanzhang/Coding/News/Earnings_Release_new.txt"
SECTORS_JSON_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
DB_PATH = "/Users/yanzhang/Coding/Database/Finance.db"
DESCRIPTION_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
PANEL_CONFIG_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'

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
    base_path = '/Users/yanzhang/Coding/Financial_System'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar': f'{base_path}/Query/Search_Similar_Tag.py',
        'tags': f'{base_path}/Operations/Editor_Tags.py',
        'input_earning': f'{base_path}/Operations/Insert_Earning_Manual.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'event_input': f'{base_path}/Operations/Insert_Events.py',
        'event_editor': f'{base_path}/Operations/Editor_Events.py',
        'futu': '/Users/yanzhang/Coding/ScriptEditor/Stock_CheckFutu.scpt',
        'kimi': '/Users/yanzhang/Coding/ScriptEditor/Check_Earning.scpt'
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
    with sqlite3.connect(db_path) as conn:
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
        if event.button() == Qt.LeftButton:
            mods = event.modifiers()
            # Option(⌥) + 左键 → 找相似
            if mods & Qt.AltModifier:
                execute_external_script('similar', self.text())
                return
            # Shift + 左键 → 在富途中搜索
            elif mods & Qt.ShiftModifier:
                execute_external_script('futu', self.text())
                return
        # 其他情况走原有行为（例如普通左键点击会触发 on_symbol_button_clicked）
        super().mousePressEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Earnings 百分比处理")

        # --- 1. 数据处理更新：增加今天的日期 ---
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

        esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)

        self.db_path = DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        # --- 新增：加载移动分组配置 ---
        from json import load
        with open(PANEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
            self.panel_config = load(f, object_pairs_hook=OrderedDict)
        self.panel_config_path = PANEL_CONFIG_PATH

        self._init_ui()

        # --- 3. 数据处理更新：调用所有处理函数 ---
        self.process_today() # 处理今天
        self.process_date1() # 处理昨天
        self.process_date2() # 处理前天

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
        self.table2.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table2.customContextMenuRequested.connect(self.show_table_context_menu)
        lay2.addWidget(self.table2)
        gb2.setLayout(lay2)

        # --- 昨天栏目 (中) ---
        gb1 = QGroupBox(f"日期 {self.date1} （盘后 AMC）（点击“替换”写入/覆盖）")
        lay1 = QVBoxLayout()
        self.table1 = QTableWidget(0, 5)
        self.table1.setHorizontalHeaderLabels(["Symbol股票代码", "时段", "百分比(%)", "操作", "———————————"])
        self.table1.verticalHeader().setVisible(False)
        self.table1.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table1.customContextMenuRequested.connect(self.show_table_context_menu)
        lay1.addWidget(self.table1)
        gb1.setLayout(lay1)

        # --- 2. UI更新：新增今天栏目 (右) ---
        gb_today = QGroupBox(f"日期 {self.today_str} (盘前 BMO)")
        lay_today = QVBoxLayout()
        self.table_today = QTableWidget(0, 3) # 只有两列
        self.table_today.setHorizontalHeaderLabels(["Symbol", "时段", "————————————————————————"])
        self.table_today.verticalHeader().setVisible(False)
        self.table_today.setContextMenuPolicy(Qt.CustomContextMenu)
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

    def apply_stylesheet(self):
        """定义并应用全局样式表"""
        qss = """
        /* SymbolButton 保持不变 */
        QPushButton#SymbolButton {
            background-color: #3498db; color: white; border: none;
            padding: 5px 10px; border-radius: 4px; font-weight: bold;
        }
        QPushButton#SymbolButton[period="BMO"] { background-color: #3498db; color: black; }
        QPushButton#SymbolButton[period="BMO"]:hover { background-color: #2980b9; }
        /* AMC 按钮改为淡绿色 */
        QPushButton#SymbolButton[period="AMC"] {
        background-color: #7C9B67;   /* 淡绿色 (lightgreen) */
        color: black;                /* 字体白/黑随你喜好 */
        }
        QPushButton#SymbolButton[period="AMC"]:hover {
        background-color: #6E8B3D;   /* 深一点的绿色 hover 效果 */
        }
        QPushButton#SymbolButton[period="TNS"] { background-color: #2c3e50; color: white; }
        QPushButton#SymbolButton[period="TNS"]:hover { background-color: #1f2d3d; }

        /* 把写入/替换按钮改为深灰色 */
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
        ### 修改 4：为Tags标签应用文本溢出截断样式 ###
        lbl.setStyleSheet("""
            color: lightyellow; 
            font-size: 18pt;
            padding: 4px;
        """)
        table.setCellWidget(row + 1, 0, lbl)
        for c in range(table.columnCount()):
            item = table.item(row + 1, c)
            if item:
                item.setFlags(Qt.NoItemFlags)

        table.setRowHeight(insert_row, 45)  # 比如 30px

    def show_table_context_menu(self, pos):
        """当在表格上右键点击时，创建并显示上下文菜单"""
        table = self.sender()
        if not table:
            return

        # 根据点击位置确定行、列
        row = table.rowAt(pos.y())
        col = table.columnAt(pos.x())
        # 只允许在第一列（Symbol / Tag 列）弹菜单
        if row == -1 or col != 0:
            return

        # 尝试拿当前行第0列的 widget
        widget = table.cellWidget(row, 0)
        symbol_button = None

        if isinstance(widget, SymbolButton):
            # 直接点在 SymbolButton 上
            symbol_button = widget
        elif isinstance(widget, QLabel):
            # 点在标签行，去上一行取 SymbolButton
            if row > 0:
                prev = table.cellWidget(row - 1, 0)
                if isinstance(prev, SymbolButton):
                    symbol_button = prev
        else:
            # 既不是按钮也不是标签，忽略
            return

        if not symbol_button:
            return

        symbol = symbol_button.text()

        menu = QMenu()

        # --- 新增：移动（复制到组）子菜单 ---
        move_menu = menu.addMenu("移动")
        allowed_groups = ["Must", "Today", "Watching", "Next Week", "2 Weeks", "3 Weeks"]
        for group in allowed_groups:
            # 判断 symbol 是否已在该组中
            cfg_val = self.panel_config.get(group, [])
            in_cfg = symbol in (cfg_val if isinstance(cfg_val, list) else cfg_val.keys())
            act = QAction(group, self)
            act.setEnabled(not in_cfg)
            act.triggered.connect(partial(self.copy_symbol_to_group, symbol, group))
            move_menu.addAction(act)
        menu.addSeparator()

        # --- 原有脚本执行菜单项 ---
        menu_config = [
            ("新增事件", "event_input"), None,
            ("编辑 Tags", "tags"), None,
            ("编辑事件", "event_editor"), ("Kimi检索财报", "kimi"), None,
            ("在富途中搜索", "futu"), None,
            ("找相似", "similar"), None,
            ("新增 财报", "input_earning"), ("编辑 Earing 数据", "editor_earning"), None,
            ("加入黑名单", "blacklist"),
        ]
        for item in menu_config:
            if item is None:
                menu.addSeparator()
            else:
                label, script_type = item
                action = QAction(label, self)
                action.triggered.connect(partial(execute_external_script, script_type, symbol))
                menu.addAction(action)

        menu.exec_(QCursor.pos())

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
    
    def on_symbol_button_clicked(self, symbol):
        """当 Symbol 按钮被点击时，从数据库获取数据并显示图表"""
        # ←—— 在这里重新加载你可能修改过的文件
        self.description_data = load_json(DESCRIPTION_PATH)
        sector = self.symbol_to_sector.get(symbol)
        if not sector:
            QMessageBox.warning(self, "错误", f"未找到 Symbol '{symbol}' 对应的板块(Sector)。")
            return

        compare_value = self.compare_data.get(symbol, "N/A")
        shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(self.db_path, symbol)

        print(f"正在为 {symbol} (板块: {sector}) 生成图表...")
        try:
            plot_financial_data(
                self.db_path, sector, symbol, compare_value,
                (shares_val, pb_val), marketcap_val, pe_val,
                self.description_data, '1Y', False
            )
        except Exception as e:
            QMessageBox.critical(self, "绘图失败", f"生成图表时发生错误: {e}")
            print(f"绘图失败: {e}")

    def center_window(self):
        """将窗口移动到屏幕中央"""
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                screens = QApplication.screens()
                if not screens: return
                screen = screens[0]
            screen_geometry = screen.availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())
        except Exception as e:
            print(f"Error centering window: {e}")

    def _get_prev_price(self, table: str, dt: str, symbol: str):
        """从指定表里找 name=symbol 且 date<dt 的最近一条 price"""
        sql = f"SELECT price FROM `{table}` WHERE name=? AND date<? ORDER BY date DESC LIMIT 1"
        self.cur.execute(sql, (symbol, dt))
        r = self.cur.fetchone()
        return r["price"] if r else None
    
    def _get_price_from_table(self, table: str, dt: str, symbol: str):
        """从指定表里取单个价格"""
        try:
            self.cur.execute(f"SELECT price FROM `{table}` WHERE date=? AND name=?", (dt, symbol))
            r = self.cur.fetchone()
            return r["price"] if r else None
        except sqlite3.OperationalError:
            return None

    ### 修改：重构 process_today 以解决布局问题 ###
    def process_today(self):
        table = self.table_today
        
        # 步骤 1: 添加所有数据行，并收集tags
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.today_str]:
            # 只关心 BMO (盘前)
            if period != "BMO":
                continue

            row = table.rowCount()
            table.insertRow(row)

            table.setItem(row, 0, QTableWidgetItem())
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol))
            table.setCellWidget(row, 0, btn)
            
            tags = get_tags_for_symbol(symbol, self.description_data)
            tags_to_add.append(tags) # 收集tags

            # 1: 时段
            display_period = PERIOD_DISPLAY.get(period, period)
            table.setItem(row, 1, QTableWidgetItem(display_period))

        # 步骤 2: 根据已添加的数据行计算并设置列宽
        table.resizeColumnsToContents()
        
        # 步骤 3: 锁定列宽，防止后续添加的tags行影响它
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        # 步骤 4: 倒序遍历，插入tag行 (倒序是为了防止插入操作影响后续行的索引)
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
            row = table.rowCount()
            table.insertRow(row)

            table.setItem(row, 0, QTableWidgetItem())
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol))
            table.setCellWidget(row, 0, btn)
            
            tags = get_tags_for_symbol(symbol, self.description_data)
            tags_to_add.append(tags)

            table.setItem(row, 1, QTableWidgetItem(PERIOD_DISPLAY.get(period, period)))

            # 百分比
            item_pct = QTableWidgetItem(f"{pct}")
            font = QFont("Arial", 14, QFont.Bold)
            item_pct.setFont(font)
            color = QColor(255, 0, 0) if pct < 0 else QColor(255, 215, 0)
            item_pct.setForeground(QBrush(color))
            table.setItem(row, 2, item_pct)

            # “写入” 按钮
            replace_btn = QPushButton("写入")
            replace_btn.setObjectName("ReplaceButton")
            replace_btn.setCursor(QCursor(Qt.PointingHandCursor))
            replace_btn.clicked.connect(partial(self.on_replace_date1, symbol, pct, replace_btn))
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.addWidget(replace_btn)
            hl.setAlignment(Qt.AlignCenter)
            hl.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 3, container)
            
            if period == "BMO":
                self.auto_write_date1(symbol, pct, replace_btn)

        # 步骤 2, 3, 4
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i in range(len(tags_to_add) - 1, -1, -1):
            self._add_tag_row(table, i, tags_to_add[i])

    def auto_write_date1(self, symbol, pct, btn):
        """如果当天 self.date1 在 Earning 表里还没有 symbol 记录，就插入"""
        self.cur.execute("SELECT 1 FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        if not self.cur.fetchone():
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
            self.conn.commit()
        btn.setText("已写入")
        btn.setEnabled(False)
    
    def on_replace_date1(self, symbol, pct, btn):
        self.cur.execute("SELECT id FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        exists = self.cur.fetchone() is not None

        if exists:
            reply = QMessageBox.question(self, "确认覆盖", f"Earning 表中已存在 {symbol} 在 {self.date1} 的记录，是否覆盖？", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes: return
            self.cur.execute("UPDATE Earning SET price=? WHERE date=? AND name=?", (pct, self.date1, symbol))
            action = "已覆盖"
        else:
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
            action = "已写入"

        self.conn.commit()
        btn.setText(action)
        btn.setEnabled(False)

    ### 修改：重构 process_date2 以解决布局问题 ###
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

            self.cur.execute("SELECT id, price FROM Earning WHERE name=? AND date>=? ORDER BY date DESC LIMIT 1", (symbol, self.three_days_ago))
            rowr = self.cur.fetchone()
            
            auto_written = False
            if rowr:
                old_pct = float(rowr["price"])
                record_id = rowr["id"]
            else:
                self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct_new))
                self.conn.commit()
                old_pct = pct_new
                record_id = self.cur.lastrowid
                auto_written = True

            row = table.rowCount()
            table.insertRow(row)

            # Symbol 按钮
            btn_sym = SymbolButton(symbol)
            btn_sym.setObjectName("SymbolButton")
            btn_sym.setProperty("period", period)
            btn_sym.setCursor(QCursor(Qt.PointingHandCursor))
            btn_sym.clicked.connect(partial(self.on_symbol_button_clicked, symbol))
            table.setCellWidget(row, 0, btn_sym)

            tags = get_tags_for_symbol(symbol, self.description_data)
            tags_to_add.append(tags)

            table.setItem(row, 1, QTableWidgetItem(PERIOD_DISPLAY.get(period, period)))

            font = QFont("Arial", 14, QFont.Bold)
            # 修改为判断正负：
            item_new = QTableWidgetItem(f"{pct_new}")
            item_new.setFont(font)
            color_new = QColor(255, 0, 0) if pct_new < 0 else QColor(255, 215, 0)
            item_new.setForeground(QBrush(color_new))
            table.setItem(row, 2, item_new)

            item_old = QTableWidgetItem(f"{old_pct}")
            item_old.setFont(font)
            color_old = QColor(255, 0, 0) if old_pct < 0 else QColor(255, 215, 0)
            item_old.setForeground(QBrush(color_old))
            table.setItem(row, 3, item_old)

            op_btn = QPushButton()
            op_btn.setObjectName("ReplaceButton")
            op_btn.setCursor(QCursor(Qt.PointingHandCursor))

            if auto_written or pct_new == old_pct:
                op_btn.setText("已写入" if auto_written else "已写入")
                op_btn.setEnabled(False)
            else:
                op_btn.setText("替换")
                op_btn.clicked.connect(partial(self.on_replace_date2, symbol, pct_new, record_id, op_btn))

            container = QWidget()
            hl = QHBoxLayout(container)
            hl.addWidget(op_btn)
            hl.setAlignment(Qt.AlignCenter)
            hl.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 4, container)

        # 步骤 2, 3, 4
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i in range(len(tags_to_add) - 1, -1, -1):
            self._add_tag_row(table, i, tags_to_add[i])

    def on_replace_date2(self, symbol, new_pct, record_id, btn):
        """替换三天内的旧记录"""
        reply = QMessageBox.question(
            self,
            "确认替换",
            f"真的要把 {symbol} 最近一次 ({self.three_days_ago} 之后) 的旧百分比替换成 {new_pct}% 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # 1. 更新数据库
        self.cur.execute(
            "UPDATE Earning SET price=?, date=? WHERE id=?",
            (new_pct, self.date1, record_id)
        )
        self.conn.commit()

        # 2. 在表格中找到这个按钮所在的行
        table = self.table2
        found_row = None
        for r in range(table.rowCount()):
            container = table.cellWidget(r, 4)  # 我们把操作按钮放在第 4 列
            if container:
                # container 是一个 QWidget，我们把按钮放在它的 layout[0]
                btn_in_cell = container.layout().itemAt(0).widget()
                if btn_in_cell is btn:
                    found_row = r
                    break

        # 3. 更新“旧百分比”这一列（第 3 列）
        if found_row is not None:
            item_old = table.item(found_row, 3)
            if item_old:
                # 修改为重新设色：
                item_old.setText(str(new_pct))
                np = float(new_pct)
                color = QColor(255, 0, 0) if np < 0 else QColor(255, 215, 0)
                item_old.setForeground(QBrush(color))
            else:
                table.setItem(found_row, 3, QTableWidgetItem(str(new_pct)))

        # 4. 禁用按钮并改文字
        btn.setText("已替换")
        btn.setEnabled(False)

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()