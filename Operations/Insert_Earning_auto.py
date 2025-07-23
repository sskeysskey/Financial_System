import sys
import json
import sqlite3
import subprocess  # 1. 新增导入：用于执行外部脚本
from datetime import date, timedelta
from functools import partial
from collections import OrderedDict  # 导入以支持 b.py 中的 load_json

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem, # 新增 QHBoxLayout
    QPushButton, QMessageBox, QShortcut,
    QMenu, QAction  # 1. 新增导入：用于创建右键菜单
)
from PyQt5.QtGui import QCursor, QKeySequence # 1. 新增导入：用于获取光标位置
from PyQt5.QtCore import Qt # 1. 新增导入：用于设置菜单策略

# 添加自定义模块的路径，以便可以导入 Chart_input
sys.path.append('/Users/yanzhang/Documents/Financial_System/Query')
from Chart_input import plot_financial_data

# 定义所有需要用到的文件路径，方便管理
TXT_PATH = "/Users/yanzhang/Documents/News/Earnings_Release_new.txt"
SECTORS_JSON_PATH = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
DB_PATH = "/Users/yanzhang/Documents/Database/Finance.db"
DESCRIPTION_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'

def execute_external_script(script_type, keyword):
    """
    执行外部脚本（AppleScript 或 Python）。
    此函数直接从 b.py 移植而来。
    """
    base_path = '/Users/yanzhang/Documents/Financial_System'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar': f'{base_path}/Query/Find_Similar_Tag.py',
        'tags': f'{base_path}/Operations/Editor_Symbol_Tags.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'futu': '/Users/yanzhang/Documents/ScriptEditor/Stock_CheckFutu.scpt',
        'kimi': '/Users/yanzhang/Documents/ScriptEditor/CheckKimi_Earning.scpt'
    }

    try:
        # 使用 Popen 进行非阻塞调用
        if script_type in ['futu', 'kimi']:
            # 对于 AppleScript，使用 osascript
            subprocess.Popen(['osascript', script_configs[script_type], keyword])
        else:
            # 对于 Python 脚本
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.Popen([python_path, script_configs[script_type], keyword])
    except Exception as e:
        # 在GUI中，最好用QMessageBox显示错误，但此处为了简单，先打印
        print(f"执行脚本时出错: {e}")
        QMessageBox.critical(None, "脚本执行错误", f"执行 '{script_type}' 脚本时发生错误:\n{e}")

# ... (之前添加的数据加载函数 load_json, load_text_data 等保持不变) ...
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

# ### 删除 ###: 移除了不再需要的 load_marketcap_pe_data 函数

# ### 新增 ###: 从 b.py 和 a.py 借鉴的数据库查询函数
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Earnings 百分比处理")

        # 1. 计算日期
        today = date.today()
        self.date1 = (today - timedelta(days=1)).strftime("%Y-%m-%d")   # 昨天
        self.date2 = (today - timedelta(days=2)).strftime("%Y-%m-%d")   # 前天
        self.three_days_ago = (today - timedelta(days=3)).strftime("%Y-%m-%d")

        # 2. 解析 txt 文件
        self.symbols_by_date = {self.date1: [], self.date2: []}
        self.symbol_to_period = {}
        with open(TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(":")]
                # e.g. ["COKE", "AMC", "2025-07-24"]
                symbol, period, dt = parts[0], parts[1], parts[2]
                if dt in self.symbols_by_date:
                    self.symbols_by_date[dt].append((symbol, period))
                    self.symbol_to_period[symbol] = period

        # 2. 对每个日期的列表按照指定顺序排序
        desired_order = ['BMO', 'AMC', 'TNS']
        def order_key(item):
            _, per = item
            if per in desired_order:
                return (desired_order.index(per), "")
            else:
                return (len(desired_order), per)
        for dt in self.symbols_by_date:
            self.symbols_by_date[dt].sort(key=order_key)

        # 3. 载入 sector 配置
        self.symbol_to_sector = {}
        with open(SECTORS_JSON_PATH, "r", encoding="utf-8") as f:
            sectors = json.load(f)
        for sector_name, syms in sectors.items():
            for s in syms:
                self.symbol_to_sector[s] = sector_name

        # ### 修改 ###: 移除对 shares 和 marketcap 文件的加载
        self.description_data = load_json(DESCRIPTION_PATH)
        self.compare_data = load_text_data(COMPARE_DATA_PATH)

        # 增加一行：Esc 退出
        esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)

        # 5. 连接数据库
        self.db_path = DB_PATH  # 将路径保存为实例变量
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        # 5. 构建界面
        self._init_ui()

        # 6. 分两部分处理
        self.process_date1()
        self.process_date2()

    def _init_ui(self):
        cw = QWidget()
        # vlay = QVBoxLayout()
        hlay = QHBoxLayout()

        # --- 1. 新增：定义QSS样式表 ---
        self.apply_stylesheet()
        
        # 第一部分：昨天的 symbols，延迟写入，带“替换”按钮

        gb1 = QGroupBox(f"日期 {self.date1} 符合条件的 Symbols（点击“替换”写入/覆盖）")
        lay1 = QVBoxLayout()
        # 3 列：Symbol, 百分比, 操作
        self.table1 = QTableWidget(0, 4)
        self.table1.setHorizontalHeaderLabels(
            ["Symbol", "时段", "百分比(%)", "操作"]
        )
        self.table1.horizontalHeader().setStretchLastSection(True)
        # --- 2. 移除 cellClicked 连接，因为现在点击的是按钮 ---
        # self.table1.cellClicked.connect(self.on_symbol_clicked)
        self.table1.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table1.customContextMenuRequested.connect(self.show_table_context_menu)
        lay1.addWidget(self.table1)
        gb1.setLayout(lay1)
        # vlay.addWidget(gb1)
        hlay.addWidget(gb1)

        # 第二部分
        gb2 = QGroupBox(f"日期 {self.date2} 符合条件的 Symbols （点击 Symbol 显示图表，可替换旧百分比）")
        lay2 = QVBoxLayout()
        # table2 现在有 5 列：Symbol, 时段, 新百分比, 旧百分比, 操作
        self.table2 = QTableWidget(0, 5)
        self.table2.setHorizontalHeaderLabels(
            ["Symbol", "时段", "新百分比(%)", "旧百分比(%)", "操作"]
        )
        self.table2.horizontalHeader().setStretchLastSection(True)
        # --- 2. 移除 cellClicked 连接 ---
        # self.table2.cellClicked.connect(self.on_symbol_clicked)
        self.table2.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table2.customContextMenuRequested.connect(self.show_table_context_menu)
        lay2.addWidget(self.table2)
        gb2.setLayout(lay2)
        # vlay.addWidget(gb2)
        hlay.addWidget(gb2)

        # cw.setLayout(vlay)
        cw.setLayout(hlay)
        self.setCentralWidget(cw)
        self.resize(1200, 1000)

        # 新增：将窗口移动到屏幕中央
        self.center_window()

    # --- 1. 修改：为“替换”按钮添加新样式 ---
    def apply_stylesheet(self):
        """定义并应用全局样式表"""
        qss = """
        /* Symbol 按钮的样式 */
        QPushButton#SymbolButton {
            background-color: #3498db; /* 漂亮的蓝色 */
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px; /* 圆角 */
            font-weight: bold;
        }
        /* BMO：保持原先的蓝色 */
        QPushButton#SymbolButton[period="BMO"] {
            background-color: #3498db;
            color: white;
        }
        QPushButton#SymbolButton[period="BMO"]:hover {
            background-color: #2980b9;
        }

        /* AMC：深蓝色 */
        QPushButton#SymbolButton[period="AMC"] {
            background-color: #2c3e50;
            color: white;
        }
        QPushButton#SymbolButton[period="AMC"]:hover {
            background-color: #1f2d3d;
        }

        /* TNS：紫色 */
        QPushButton#SymbolButton[period="TNS"] {
            background-color: #8e44ad;
            color: white;
        }
        QPushButton#SymbolButton[period="TNS"]:hover {
            background-color: #732d91;
        }

        /* 替换按钮的样式 */
        QPushButton#ReplaceButton {
            background-color: #2ecc71; /* 漂亮的绿色 */
            color: white;
            border: none;
            padding: 5px 15px; /* 增加水平内边距 */
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton#ReplaceButton:hover {
            background-color: #27ae60; /* 悬停时变深 */
        }
        QPushButton#ReplaceButton:disabled {
            background-color: #95a5a6; /* 禁用时变为灰色 */
            color: #ecf0f1;
        }
        """
        self.setStyleSheet(qss)

    def show_table_context_menu(self, pos):
        """当在表格上右键点击时，创建并显示上下文菜单"""
        # 获取被点击的表格控件
        table = self.sender()
        if not table:
            return

        # 根据点击位置获取单元格项目
        item = table.itemAt(pos)
        if item is None or item.column() != 0: return

        # --- 3. 修改：从cell widget获取symbol，而不是item的文本 ---
        symbol_button = table.cellWidget(item.row(), 0)
        if not isinstance(symbol_button, QPushButton):
            return # 如果单元格里不是按钮，则忽略
        
        symbol = symbol_button.text()

        # 1. 定义菜单的结构和内容
        # 格式: (菜单显示文本, 对应的 script_type)
        # None 代表一个分隔符
        menu_config = [
            ("在富途中搜索", "futu"),
            ("编辑 Earing DB", "editor_earning"),
            None,  # 分隔符
            ("编辑 Tags", "tags"),
            ("Kimi检索财报", "kimi"),
            ("找相似", "similar"),
            None,  # 分隔符
            ("加入黑名单", "blacklist"),
        ]

        # 2. 创建菜单并动态添加项目
        menu = QMenu()
        for item in menu_config:
            if item is None:
                menu.addSeparator()
            else:
                label, script_type = item
                action = QAction(label, self)
                # 使用 lambda 和 partial 确保传递正确的参数
                action.triggered.connect(
                    partial(execute_external_script, script_type, symbol)
                )
                menu.addAction(action)
        
        # 3. 显示菜单
        menu.exec_(QCursor.pos())

    # ### 修改 ###: 更新此方法以使用新的数据库查询逻辑
    def on_symbol_button_clicked(self, symbol):
        """当Symbol按钮被点击时，从数据库获取数据并显示图表"""
        sector = self.symbol_to_sector.get(symbol)
        if not sector:
            QMessageBox.warning(self, "错误", f"未找到 Symbol '{symbol}' 对应的板块(Sector)。")
            return

        compare_value = self.compare_data.get(symbol, "N/A")
        
        # 从数据库获取 shares, marketcap, pe, pb
        shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(self.db_path, symbol)

        print(f"正在为 {symbol} (板块: {sector}) 生成图表...")
        try:
            # 调用绘图函数，注意参数的变化
            plot_financial_data(
                self.db_path,
                sector,
                symbol,
                compare_value,
                (shares_val, pb_val),  # 将 shares 和 pb 组合成元组传入
                marketcap_val,
                pe_val,
                self.description_data,
                '1Y',  # 默认时间周期
                False
            )
        except Exception as e:
            QMessageBox.critical(self, "绘图失败", f"生成图表时发生错误: {e}")
            print(f"绘图失败: {e}")

    def center_window(self):
        """将窗口移动到屏幕中央"""
        try:
            # 获取主屏幕
            screen = QApplication.primaryScreen()
            if not screen:
                # 如果没有主屏幕（不太可能，但作为备用），尝试获取第一个屏幕
                screens = QApplication.screens()
                if not screens:
                    return # 没有可用屏幕
                screen = screens[0]

            screen_geometry = screen.availableGeometry() # 获取可用屏幕区域几何信息
            window_geometry = self.frameGeometry()    # 获取窗口框架几何信息（包括标题栏）

            # 计算中心点并移动窗口
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())

        except Exception as e:
            print(f"Error centering window: {e}")

    def _get_prev_price(self, table: str, dt: str, symbol: str):
        """
        从指定表里找 name=symbol 且 date<dt 的最近一条 price
        """
        sql = f"""
            SELECT price
              FROM `{table}`
             WHERE name=? AND date<? 
          ORDER BY date DESC
             LIMIT 1
        """
        self.cur.execute(sql, (symbol, dt))
        r = self.cur.fetchone()
        return r["price"] if r else None
    
    def process_date1(self):
        """
        扫描“昨天”的 symbols，计算百分比，
        在界面添加“替换”按钮，点击后可写入/覆盖；
        如果时段是 BMO，则在启动时就自动写入（仅首次），
        并更新按钮状态。
        """
        for symbol, period in self.symbols_by_date[self.date1]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector:
                continue
            # 从 sector 表中取 price
            # 1) 当日收盘
            p1 = self._get_price_from_table(sector, self.date1, symbol)
            if p1 is None:
                continue

            # 2) 上一交易日收盘（动态查找）
            p2 = self._get_prev_price(sector, self.date1, symbol)
            if p2 is None or p2 == 0:
                continue

            # 计算涨跌 %
            pct = round((p1 - p2) / p2 * 100, 2)

            # 插入一行
            row = self.table1.rowCount()
            self.table1.insertRow(row)

            # --- 5. 修改：将Symbol文本替换为QPushButton ---
            # 创建一个空的item占位，因为setCellWidget需要一个item存在
            # 0: Symbol 按钮
            self.table1.setItem(row, 0, QTableWidgetItem())
            btn = QPushButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)        # ← 增加这一行
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol))
            self.table1.setCellWidget(row, 0, btn)

            # 1: 时段
            self.table1.setItem(row, 1, QTableWidgetItem(period))

            # 2: 百分比
            self.table1.setItem(row, 2, QTableWidgetItem(str(pct)))

            # 3: “写入” 按钮
            replace_btn = QPushButton("写入")
            replace_btn.setObjectName("ReplaceButton")
            replace_btn.setCursor(QCursor(Qt.PointingHandCursor))
            replace_btn.clicked.connect(
                partial(self.on_replace_date1, symbol, pct, replace_btn)
            )

            container = QWidget()
            hl = QHBoxLayout(container)
            hl.addWidget(replace_btn)
            hl.setAlignment(Qt.AlignCenter)
            hl.setContentsMargins(0,0,0,0) # 移除布局边距
            self.table1.setCellWidget(row, 3, container) # 将容器放入单元格
            
            # --- BMO 自动写入 ---
            if period == "BMO":
                self.auto_write_date1(symbol, pct, replace_btn)

    def auto_write_date1(self, symbol, pct, btn):
        """
        如果当天 self.date1 在 Earning 表里还没有 symbol 记录，就插入；
        无论插入与否，都把按钮设为“已写入”并禁用。
        """
        # 检查当天是否已写入
        self.cur.execute(
            "SELECT 1 FROM Earning WHERE date=? AND name=?",
            (self.date1, symbol)
        )
        already = self.cur.fetchone() is not None

        if not already:
            # 执行插入，不弹框
            self.cur.execute(
                "INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)",
                (self.date1, symbol, pct)
            )
            self.conn.commit()

        # 更新按钮状态
        btn.setText("已写入")
        btn.setEnabled(False)
    
    def on_replace_date1(self, symbol, pct, btn):
        # ... (数据库操作逻辑不变) ...
        self.cur.execute("SELECT id FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        exists = self.cur.fetchone() is not None

        if exists:
            reply = QMessageBox.question(
                self, "确认覆盖",
                f"Earning 表中已存在 {symbol} 在 {self.date1} 的记录，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            # 执行更新
            self.cur.execute(
                "UPDATE Earning SET price=? WHERE date=? AND name=?",
                (pct, self.date1, symbol)
            )
            action = "已覆盖"
        else:
            # 执行插入
            self.cur.execute(
                "INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)",
                (self.date1, symbol, pct)
            )
            action = "已写入"

        self.conn.commit()
        
        # 修改这里：同时改变按钮文本和状态
        btn.setText(action)  # 新增这行：改变按钮文本为"已写入"或"已覆盖"
        btn.setEnabled(False)

    # --- 4. 修改：在 process_date2 中也使用容器和布局 ---
    def process_date2(self):
        """
        对前天的 symbols：
         - 计算 pct_new
         - 三天内查 Earning 表，看是替换还是写入
         - 在 table2 里显示“新百分比”、“旧百分比”，按钮根据场景不同
        """
        for symbol, period in self.symbols_by_date[self.date2]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector:
                continue

            # 计算 pct_new
            p1 = self._get_price_from_table(sector, self.date1, symbol)
            p2 = self._get_price_from_table(sector, self.date2, symbol)
            if p1 is None or p2 is None or p2 == 0:
                continue
            pct_new = round((p1 - p2) / p2 * 100, 2)

            # 三天内查最新一条 Earning
            self.cur.execute(
                "SELECT id, price FROM Earning "
                " WHERE name=? AND date>=? "
                " ORDER BY date DESC LIMIT 1",
                (symbol, self.three_days_ago)
            )
            rowr = self.cur.fetchone()
            if rowr:
                old_pct = rowr["price"]
                exists = True
                record_id = rowr["id"]
            else:
                old_pct = None
                exists = False
                record_id = None

            # 插入一行到 table2
            row = self.table2.rowCount()
            self.table2.insertRow(row)

            # —— Symbol 按钮
            self.table2.setItem(row, 0, QTableWidgetItem())
            btn_sym = QPushButton(symbol)
            btn_sym.setObjectName("SymbolButton")
            btn_sym.setProperty("period", period)
            btn_sym.setCursor(QCursor(Qt.PointingHandCursor))
            btn_sym.clicked.connect(partial(self.on_symbol_button_clicked, symbol))
            self.table2.setCellWidget(row, 0, btn_sym)

            # 1: 时段
            self.table2.setItem(row, 1, QTableWidgetItem(period))

            # 2: 新百分比
            self.table2.setItem(row, 2, QTableWidgetItem(str(pct_new)))

            # 3: 旧百分比
            self.table2.setItem(row, 3, QTableWidgetItem("" if old_pct is None else str(old_pct)))

            # 4: 操作按钮：替换 或 写入
            op_btn = QPushButton("替换" if exists else "写入")
            op_btn.setObjectName("ReplaceButton")
            op_btn.setCursor(QCursor(Qt.PointingHandCursor))

            if exists:
                # 替换：更新已有那条 record_id
                op_btn.clicked.connect(
                    partial(self.on_replace_date2, symbol, pct_new, record_id, row, op_btn)
                )
            else:
                # 走写入 —— 直接复用 date1 的“写入”逻辑
                op_btn.clicked.connect(
                    lambda _,
                        sym=symbol,
                        pct=pct_new,
                        r=row,
                        b=op_btn: (
                        # 1) 调用 date1 那边的写入/覆盖
                        self.on_replace_date1(sym, pct, b),
                        # 2) 写完之后把“旧百分比”列（索引 3）更新一下
                        self.table2.setItem(r, 3, QTableWidgetItem(str(pct)))
                    )
                )

            # 将按钮居中放入 cell
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.addWidget(op_btn)
            hl.setAlignment(Qt.AlignCenter)
            hl.setContentsMargins(0,0,0,0)
            self.table2.setCellWidget(row, 4, container)

    def on_replace_date2(self, symbol, new_pct, record_id, row, btn):
        """
        已有三天内旧记录时，替换那条 id=record_id。
        """
        # 首先确认覆盖
        reply = QMessageBox.question(
            self, "确认替换",
            f"真的要把 {symbol} 最近一次 ({self.three_days_ago} 之后) 的旧百分比替换成 {new_pct}% 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes   # 这里把 YES 设为默认
        )
        if reply != QMessageBox.Yes:
            return

        # 更新那条记录，并把 date 改成昨天（self.date1）
        self.cur.execute(
            "UPDATE Earning SET price=?, date=? WHERE id=?",
            (new_pct, self.date1, record_id)
        )
        self.conn.commit()

        # 界面同步
        self.table2.setItem(row, 3, QTableWidgetItem(str(new_pct)))
        btn.setText("已替换")
        btn.setEnabled(False)

    def center_window(self):
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
        except Exception as e: print(f"Error centering window: {e}")
    def _get_prev_price(self, table: str, dt: str, symbol: str):
        sql = f"SELECT price FROM `{table}` WHERE name=? AND date<? ORDER BY date DESC LIMIT 1"
        self.cur.execute(sql, (symbol, dt))
        r = self.cur.fetchone()
        return r["price"] if r else None
    def _get_price_from_table(self, table: str, dt: str, symbol: str):
        """
        从指定表里取单个价格
        """
        try:
            self.cur.execute(
                f"SELECT price FROM `{table}` WHERE date=? AND name=?",
                (dt, symbol)
            )
            r = self.cur.fetchone()
            return r["price"] if r else None
        except sqlite3.OperationalError:
            return None

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()