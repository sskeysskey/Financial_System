import sys
import json
import sqlite3
import subprocess
import os
from datetime import date, timedelta
from functools import partial
from collections import OrderedDict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QLabel,
    QMenu
)
from PyQt6.QtGui import QCursor, QKeySequence, QFont, QBrush, QColor, QShortcut, QAction
from PyQt6.QtCore import Qt, QTimer

# --- 路径处理 ---
HOME = os.path.expanduser("~") 
sys.path.append(os.path.join(HOME, 'Coding/Financial_System/Query'))
from Chart_input import plot_financial_data

TXT_PATH = os.path.join(HOME, "Coding/News/Earnings_Release_new.txt")
SECTORS_JSON_PATH = os.path.join(HOME, "Coding/Financial_System/Modules/Sectors_All.json")
DB_PATH = os.path.join(HOME, "Coding/Database/Finance.db")
DESCRIPTION_PATH = os.path.join(HOME, 'Coding/Financial_System/Modules/description.json')
COMPARE_DATA_PATH = os.path.join(HOME, 'Coding/News/backup/Compare_All.txt')
PANEL_CONFIG_PATH = os.path.join(HOME, 'Coding/Financial_System/Modules/Sectors_panel.json')
# 新增：Polymarket 预测数据路径
POLYMARKET_TXT_PATH = os.path.join(HOME, "Coding/News/earning_polymarket.txt")

PERIOD_DISPLAY = {"BMO": "↩︎", "AMC": "↪︎", "TNS": "？"}
PERIOD_CN_MAP = {"BMO": "前", "AMC": "后", "TNS": "未"} # 用于标题显示的中文映射

def get_tags_for_symbol(symbol, desc_data):
    for key in ["stocks", "etfs"]:
        for item in desc_data.get(key, []):
            if item.get("symbol") == symbol:
                return item.get("tag", [])
    return []

def execute_external_script(script_type, keyword):
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
        QMessageBox.critical(None, "脚本执行错误", f"执行 '{script_type}' 失败:\n{e}")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=OrderedDict)

def load_text_data(path):
    data = {}
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ':' not in line: continue
            key, value = map(str.strip, line.split(':', 1))
            cleaned_key = key.split()[-1]
            data[cleaned_key] = tuple(p.strip() for p in value.split(',')) if ',' in value else value
    return data

def fetch_mnspp_data_from_db(db_path, symbol):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?", (symbol,))
        result = cursor.fetchone()
    return result if result else ("N/A", None, "N/A", "--")

class SymbolButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        # --- 修改：设置鼠标悬停时为手型 ---
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.AltModifier:
                execute_external_script('similar', self.text())
                return
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                execute_external_script('futu', self.text())
                return
        super().mousePressEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Earnings 百分比处理")
        
        # 导航变量
        self.ordered_symbols_on_screen = []
        self.current_symbol_index = -1
        
        # --- 新增：用于记录每个分栏的数量 ---
        self.count_date2 = 0  # 前天
        self.count_date1 = 0  # 昨天
        self.count_today = 0  # 今天

        today = date.today()
        self.today_str = today.strftime("%Y-%m-%d")
        self.date1 = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        self.date2 = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        self.three_days_ago = (today - timedelta(days=3)).strftime("%Y-%m-%d")

        self.symbols_by_date = {self.today_str: [], self.date1: [], self.date2: []}
        self.symbol_to_period = {}

        if os.path.exists(TXT_PATH):
            with open(TXT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = [p.strip() for p in line.split(":")]
                    if len(parts) < 3: continue
                    symbol, period, dt = parts[0], parts[1], parts[2]
                    if dt in self.symbols_by_date:
                        self.symbols_by_date[dt].append((symbol, period))
                        self.symbol_to_period[symbol] = period

        desired_order = ['BMO', 'AMC', 'TNS']
        for dt in self.symbols_by_date:
            self.symbols_by_date[dt].sort(key=lambda x: (desired_order.index(x[1]) if x[1] in desired_order else 99, x[0]))

        self.symbol_to_sector = {}
        sectors = load_json(SECTORS_JSON_PATH)
        for sector_name, syms in sectors.items():
            for s in syms: self.symbol_to_sector[s] = sector_name

        self.description_data = load_json(DESCRIPTION_PATH)
        self.compare_data = load_text_data(COMPARE_DATA_PATH)
        self.panel_config = load_json(PANEL_CONFIG_PATH)
        self.panel_config_path = PANEL_CONFIG_PATH

        # --- 新增：读取 polymarket 预测数据 ---
        self.polymarket_data = {}
        if os.path.exists(POLYMARKET_TXT_PATH):
            with open(POLYMARKET_TXT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        sym, pct = line.split(":", 1)
                        self.polymarket_data[sym.strip()] = pct.strip()

        self.conn = sqlite3.connect(DB_PATH, timeout=60.0)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.close)
        QShortcut(QKeySequence(Qt.Key.Key_Slash), self).activated.connect(self.show_search_dialog)  # 新增
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        cw = QWidget()
        hlay = QHBoxLayout(cw)
        self.apply_stylesheet()

        # 表格配置 (修改表头，将“时段”改为“预测”)
        self.table2 = QTableWidget(0, 6)
        self.table2.setHorizontalHeaderLabels(["Symbol", "预测", "旧百分比%", "新百分比%", "操作", "———————————————"])
        
        self.table1 = QTableWidget(0, 5)
        self.table1.setHorizontalHeaderLabels(["Symbol", "预测", "百分比(%)", "操作", "——————————————————————"])
        
        self.table_today = QTableWidget(0, 3)
        self.table_today.setHorizontalHeaderLabels(["Symbol", "预测", "——————————————————————————"])

        for t in [self.table2, self.table1, self.table_today]:
            t.verticalHeader().setVisible(False)
            t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            t.customContextMenuRequested.connect(self.show_table_context_menu)

        hlay.addWidget(self._create_group(f"日期 {self.date2} (已发布)", self.table2), 5)
        hlay.addWidget(self._create_group(f"日期 {self.date1} (盘后 AMC)", self.table1), 5)
        hlay.addWidget(self._create_group(f"日期 {self.today_str} (盘前 BMO)", self.table_today), 4)

        self.setCentralWidget(cw)
        self.resize(1500, 1000)
        self.center_window()

    def _create_group(self, title, table):
        gb = QGroupBox(title)
        lay = QVBoxLayout(gb)
        lay.addWidget(table)
        return gb

    def show_search_dialog(self):
        """按 / 键弹出搜索框"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "搜索 Symbol", "请输入 Symbol（回车确认）:")
        if ok and text.strip():
            self.search_and_locate_symbol(text.strip().upper())

    def search_and_locate_symbol(self, symbol):
        """在三个表格中查找 Symbol 并定位+高亮"""
        tables = [
            (self.table2, "前天"),
            (self.table1, "昨天"),
            (self.table_today, "今天"),
        ]
        for table, _name in tables:
            for row in range(table.rowCount()):
                w = table.cellWidget(row, 0)
                if isinstance(w, SymbolButton) and w.text().upper() == symbol:
                    # 1) 选中该行（视觉上多一层提示）
                    table.setCurrentCell(row, 0)
                    # 2) 滚动到中间位置
                    index = table.model().index(row, 0)
                    table.scrollTo(index, table.ScrollHint.PositionAtCenter)
                    # 3) 让该表格获得焦点（这样选中行的高亮颜色更明显）
                    table.setFocus()
                    # 4) 闪烁高亮按钮
                    self.flash_highlight(w)
                    return
        QMessageBox.information(self, "未找到", f"未找到 Symbol: {symbol}")

    def flash_highlight(self, btn):
        """让按钮闪烁几次，提醒用户"""
        original_style = btn.styleSheet()
        highlight_style = original_style + "border: 3px solid #FFD700;"  # 金色边框

        state = {"count": 0, "on": False}

        def toggle():
            if state["count"] >= 6:  # 闪 3 次
                btn.setStyleSheet(original_style)
                return
            btn.setStyleSheet(highlight_style if not state["on"] else original_style)
            state["on"] = not state["on"]
            state["count"] += 1
            QTimer.singleShot(250, toggle)

        toggle()
    
    def refresh_data(self):
        self.ordered_symbols_on_screen.clear()
        # --- 重置计数器 ---
        self.count_date2 = 0
        self.count_date1 = 0
        self.count_today = 0
        
        self.table2.setRowCount(0)
        self.table1.setRowCount(0)
        self.table_today.setRowCount(0)
        self.process_date2()
        self.process_date1()
        self.process_today()

    # --- 核心导航逻辑 ---
    def handle_chart_callback(self, symbol, action):
        if action in ('next', 'prev'):
            QTimer.singleShot(50, lambda: self.navigate_to_adjacent_symbol(action))

    def navigate_to_adjacent_symbol(self, direction):
        total = len(self.ordered_symbols_on_screen)
        if total == 0: return
        if direction == 'next':
            new_index = (self.current_symbol_index + 1) % total
        else:
            new_index = (self.current_symbol_index - 1 + total) % total
        self.on_symbol_button_clicked(self.ordered_symbols_on_screen[new_index], btn_index=new_index)

    def on_symbol_button_clicked(self, symbol, btn_index=None):
        self.description_data = load_json(DESCRIPTION_PATH)
        sector = self.symbol_to_sector.get(symbol)
        if not sector: return

        if btn_index is not None:
            self.current_symbol_index = btn_index
        else:
            try: self.current_symbol_index = self.ordered_symbols_on_screen.index(symbol)
            except ValueError: self.current_symbol_index = -1

        compare_val = self.compare_data.get(symbol, "N/A")
        shares, mktcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, symbol)
        
        # --- 标题逻辑计算 (更新部分) ---
        total_global = len(self.ordered_symbols_on_screen)
        idx = self.current_symbol_index
        
        # 1. 确定属于哪个日期组，并获取该组的所有 Symbol 列表
        if idx < self.count_date2:
            date_category = "前天"
            group_count = self.count_date2
            # 切片取出该组的 Symbol 列表
            current_group_symbols = self.ordered_symbols_on_screen[0 : self.count_date2]
        elif idx < (self.count_date2 + self.count_date1):
            date_category = "昨天"
            group_count = self.count_date1
            current_group_symbols = self.ordered_symbols_on_screen[self.count_date2 : self.count_date2 + self.count_date1]
        else:
            date_category = "今天"
            group_count = self.count_today
            current_group_symbols = self.ordered_symbols_on_screen[self.count_date2 + self.count_date1 : ]

        # 2. 获取当前 Symbol 的时段 (BMO/AMC)
        period_code = self.symbol_to_period.get(symbol, "TNS")
        period_cn = PERIOD_CN_MAP.get(period_code, "?")

        # 3. 计算在当前日期组内，同属该时段的 Symbol 的位置和总数
        # 筛选出同组内所有时段相同的 Symbol
        same_period_symbols = [s for s in current_group_symbols if self.symbol_to_period.get(s) == period_code]
        
        period_total = len(same_period_symbols)
        try:
            # 找到当前 Symbol 在这个细分列表中的位置 (1-based)
            local_period_idx = same_period_symbols.index(symbol) + 1
        except ValueError:
            local_period_idx = 0

        # 4. 拼接标题: "Symbol (日期/时段 时段位置/时段总数/日期组总数/全局总数)"
        # 例如: AAPL (前天/后 1/12/23/34)
        title = f"{date_category}/{period_cn}     {local_period_idx}/{period_total}/{group_count}/{total_global}"

        try:
            plot_financial_data(
                DB_PATH, sector, symbol, compare_val,
                (shares, pb), mktcap, pe,
                self.description_data, '1Y', False,
                callback=lambda action: self.handle_chart_callback(symbol, action),
                window_title_text=title
            )
        except Exception as e:
            QMessageBox.critical(self, "绘图失败", f"错误: {e}")

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QPushButton#SymbolButton { background-color: #3498db; color: white; border: none; padding: 5px; border-radius: 4px; font-weight: bold; }
            QPushButton#SymbolButton[period="BMO"] { background-color: #7C9B67; color: black; }
            QPushButton#SymbolButton[period="AMC"] { background-color: #3498db; color: black; }
            QPushButton#SymbolButton[period="TNS"] { background-color: #2c3e50; color: white; }
            QPushButton#ReplaceButton { background-color: #555555; color: white; border: none; padding: 5px 15px; border-radius: 4px; }
            QPushButton#ReplaceButton:disabled { background-color: #333333; color: #888888; }
        """)

    def _add_tag_row(self, table, row, tags):
        tag_str = ", ".join(tags) if tags else "无标签"
        insert_row = row + 1
        table.insertRow(insert_row)
        table.setSpan(insert_row, 0, 1, table.columnCount())
        lbl = QLabel(tag_str)
        lbl.setStyleSheet("color: lightyellow; font-size: 18pt; padding: 4px;")
        table.setCellWidget(insert_row, 0, lbl)
        table.setRowHeight(insert_row, 45)

    def _get_price(self, table, dt, sym):
        self.cur.execute(f"SELECT price FROM `{table}` WHERE date=? AND name=?", (dt, sym))
        r = self.cur.fetchone()
        return r["price"] if r else None

    def _get_prev_price(self, table, dt, sym):
        self.cur.execute(f"SELECT price FROM `{table}` WHERE name=? AND date<? ORDER BY date DESC LIMIT 1", (sym, dt))
        r = self.cur.fetchone()
        return r["price"] if r else None

    def auto_write_date1(self, symbol, pct, btn):
        self.cur.execute("SELECT 1 FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        if not self.cur.fetchone():
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
            self.conn.commit()
        btn.setText("已写入")
        btn.setEnabled(False)

    def process_today(self):
        table = self.table_today
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.today_str]:
            if period != "BMO": continue
            self.ordered_symbols_on_screen.append(symbol)
            self.count_today += 1  # 计数增加
            idx = len(self.ordered_symbols_on_screen) - 1
            
            row = table.rowCount()
            table.insertRow(row)
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
            table.setCellWidget(row, 0, btn)
            
            # --- 修改：填入预测数据 ---
            pred_val = self.polymarket_data.get(symbol, "")
            pred_item = QTableWidgetItem(pred_val)
            pred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # --- 新增样式 ---
            pred_item.setFont(QFont("Arial", 22, QFont.Weight.Bold))
            pred_item.setForeground(QBrush(QColor(255, 165, 0))) # 橙色
            table.setItem(row, 1, pred_item)
            
            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add)-1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

    def process_date1(self):
        table = self.table1
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.date1]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector: continue
            p1 = self._get_price(sector, self.date1, symbol)
            p2 = self._get_prev_price(sector, self.date1, symbol)
            if p1 is None or not p2: continue
            pct = round((p1 - p2) / p2 * 100, 2)

            self.ordered_symbols_on_screen.append(symbol)
            self.count_date1 += 1 # 计数增加
            idx = len(self.ordered_symbols_on_screen) - 1
            row = table.rowCount()
            table.insertRow(row)
            
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
            table.setCellWidget(row, 0, btn)
            
            # --- 修改：填入预测数据 ---
            pred_val = self.polymarket_data.get(symbol, "")
            pred_item = QTableWidgetItem(pred_val)
            pred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # --- 新增样式 ---
            pred_item.setFont(QFont("Arial", 22, QFont.Weight.Bold))
            pred_item.setForeground(QBrush(QColor(255, 165, 0))) # 橙色
            table.setItem(row, 1, pred_item)
            
            item_pct = QTableWidgetItem(f"{pct}")
            item_pct.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            # 正数(>=0)为红色(255, 0, 0)，负数(<0)为绿色(0, 255, 0)
            item_pct.setForeground(QBrush(QColor(255, 0, 0) if pct >= 0 else QColor(0, 255, 0)))
            table.setItem(row, 2, item_pct)

            rep_btn = QPushButton("写入")
            rep_btn.setObjectName("ReplaceButton")
            # --- 修改：设置鼠标悬停时为手型 ---
            rep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rep_btn.clicked.connect(partial(self.on_replace_date1, symbol, pct, rep_btn))
            table.setCellWidget(row, 3, rep_btn)
            
            if period == "BMO": self.auto_write_date1(symbol, pct, rep_btn)
            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add)-1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

    def process_date2(self):
        table = self.table2
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.date2]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector: continue
            p1, p2 = self._get_price(sector, self.date1, symbol), self._get_price(sector, self.date2, symbol)
            if p1 is None or not p2: continue
            pct_new = round((p1 - p2) / p2 * 100, 2)

            # --- 不再使用 id ---
            self.cur.execute("SELECT price, date FROM Earning WHERE name=? AND date>=? ORDER BY date DESC LIMIT 1", (symbol, self.three_days_ago))
            rowr = self.cur.fetchone()
            if rowr:
                old_pct, old_date, auto = float(rowr["price"]), rowr["date"], False
            else:
                self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct_new))
                self.conn.commit()
                old_pct, old_date, auto = pct_new, self.date1, True

            self.ordered_symbols_on_screen.append(symbol)
            self.count_date2 += 1 # 计数增加
            idx = len(self.ordered_symbols_on_screen) - 1
            row = table.rowCount()
            table.insertRow(row)
            
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
            table.setCellWidget(row, 0, btn)
            
            # --- 修改：填入预测数据 ---
            pred_val = self.polymarket_data.get(symbol, "")
            pred_item = QTableWidgetItem(pred_val)
            pred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # --- 新增样式 ---
            pred_item.setFont(QFont("Arial", 22, QFont.Weight.Bold))
            pred_item.setForeground(QBrush(QColor(255, 165, 0))) # 橙色
            table.setItem(row, 1, pred_item)
            
            for i, val in enumerate([old_pct, pct_new]):
                item = QTableWidgetItem(f"{val}")
                item.setFont(QFont("Arial", 14, QFont.Weight.Bold))
                # 颜色逻辑保持你刚才要求的：正红、负绿
                item.setForeground(QBrush(QColor(255, 0, 0) if val >= 0 else QColor(0, 255, 0)))
                table.setItem(row, 2 + i, item)

            op_btn = QPushButton("已写入" if (auto or pct_new == old_pct) else "替换")
            op_btn.setObjectName("ReplaceButton")
            op_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            op_btn.setEnabled(not (auto or pct_new == old_pct))
            if op_btn.isEnabled(): 
                op_btn.clicked.connect(partial(self.on_replace_date2, symbol, pct_new, old_date, op_btn))
            table.setCellWidget(row, 4, op_btn)
            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add)-1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

    def on_replace_date1(self, symbol, pct, btn):
        self.cur.execute("SELECT 1 FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        if self.cur.fetchone():
            if QMessageBox.question(self, "确认覆盖", f"覆盖 {symbol} 在 {self.date1} 的记录？") != QMessageBox.StandardButton.Yes: 
                return
            self.cur.execute("UPDATE Earning SET price=? WHERE date=? AND name=?", (pct, self.date1, symbol))
            txt = "已覆盖"
        else:
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
            txt = "已写入"
        self.conn.commit()
        btn.setText(txt)
        btn.setEnabled(False)

    def on_replace_date2(self, symbol, new_pct, old_date, btn):
        msg = f"真的要把 {symbol} 在 {old_date} 的旧百分比替换成 {new_pct}% 吗？\n(记录将更新到 {self.date1})"
        if QMessageBox.question(self, "确认替换", msg) == QMessageBox.StandardButton.Yes:
            self.cur.execute("DELETE FROM Earning WHERE date=? AND name=?", (old_date, symbol))
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, new_pct))
            self.conn.commit()
            btn.setText("已替换")
            btn.setEnabled(False)
            # 更新界面显示
            index = self.table2.indexAt(btn.pos())
            if index.isValid():
                # 现在旧百分比在第 2 列 (索引 2)
                item = self.table2.item(index.row(), 2)
                if item:
                    item.setText(str(new_pct))
                    # 正数(>=0)为红色(255, 0, 0)，负数(<0)为绿色(0, 255, 0)
                    item.setForeground(QBrush(QColor(255, 0, 0) if new_pct >= 0 else QColor(0, 255, 0)))

    def show_table_context_menu(self, pos):
        table = self.sender()
        row = table.rowAt(pos.y())
        if row == -1: return
        
        # 向上查找 SymbolButton
        symbol = None
        for r in range(row, -1, -1):
            w = table.cellWidget(r, 0)
            if isinstance(w, SymbolButton):
                symbol = w.text()
                break
        if not symbol: return

        menu = QMenu()
        move_menu = menu.addMenu("移动")
        for group in ["Must", "Today", "Short"]:
            # 检查是否已存在
            cfg_val = self.panel_config.get(group, [])
            in_cfg = symbol in (cfg_val if isinstance(cfg_val, list) else cfg_val.keys())
            act = QAction(group, self)
            act.setEnabled(not in_cfg)
            act.triggered.connect(partial(self.copy_symbol_to_group, symbol, group))
            move_menu.addAction(act)
        
        menu.addSeparator()
        # 恢复原始代码中完整的菜单项
        items = [
            ("新增事件", "event_input"), ("编辑 Tags", "tags"), ("编辑事件", "event_editor"), 
            None,
            ("Kimi检索", "kimi"), ("富途搜索", "futu"), ("找相似", "similar"),
            None,
            ("新增 财报", "input_earning"), ("编辑 Earing 数据", "editor_earning"), ("加入黑名单", "blacklist")
        ]
        for item in items:
            if item is None: menu.addSeparator()
            else: menu.addAction(item[0], partial(execute_external_script, item[1], symbol))
        menu.exec(QCursor.pos())

    def copy_symbol_to_group(self, symbol, group):
        cfg = self.panel_config
        if group not in cfg: cfg[group] = {}
        if isinstance(cfg[group], dict): cfg[group][symbol] = ""
        else: 
            if symbol not in cfg[group]: cfg[group].append(symbol)
        with open(self.panel_config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        QMessageBox.information(self, "成功", f"已复制 {symbol} 到 {group}")

    def center_window(self):
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())