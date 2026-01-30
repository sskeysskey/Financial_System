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
    QMenu, QHeaderView
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

PERIOD_DISPLAY = {"BMO": "↩︎", "AMC": "↪︎", "TNS": "？"}

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

        self.conn = sqlite3.connect(DB_PATH, timeout=60.0)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.close)
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        cw = QWidget()
        hlay = QHBoxLayout(cw)
        self.apply_stylesheet()

        # 表格配置
        self.table2 = QTableWidget(0, 6)
        self.table2.setHorizontalHeaderLabels(["Symbol", "时段", "新百分比%", "旧百分比%", "操作", "—————————————————————"])
        
        self.table1 = QTableWidget(0, 5)
        self.table1.setHorizontalHeaderLabels(["Symbol", "时段", "百分比(%)", "操作", "———————————————————————————"])
        
        self.table_today = QTableWidget(0, 3)
        self.table_today.setHorizontalHeaderLabels(["Symbol", "时段", "——————————————————————————————"])

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

    def refresh_data(self):
        self.ordered_symbols_on_screen.clear()
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
        
        total = len(self.ordered_symbols_on_screen)
        title = f"{symbol}  ({self.current_symbol_index + 1}/{total})"

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

    def process_today(self):
        table = self.table_today
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.today_str]:
            if period != "BMO": continue
            self.ordered_symbols_on_screen.append(symbol)
            idx = len(self.ordered_symbols_on_screen) - 1
            
            row = table.rowCount()
            table.insertRow(row)
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
            table.setCellWidget(row, 0, btn)
            table.setItem(row, 1, QTableWidgetItem(PERIOD_DISPLAY.get(period, period)))
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
            idx = len(self.ordered_symbols_on_screen) - 1
            row = table.rowCount()
            table.insertRow(row)
            
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
            table.setCellWidget(row, 0, btn)
            
            item_pct = QTableWidgetItem(f"{pct}")
            item_pct.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            item_pct.setForeground(QBrush(QColor(255, 0, 0) if pct < 0 else QColor(255, 215, 0)))
            table.setItem(row, 2, item_pct)

            rep_btn = QPushButton("写入")
            rep_btn.setObjectName("ReplaceButton")
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

            self.cur.execute("SELECT id, price FROM Earning WHERE name=? AND date>=? ORDER BY date DESC LIMIT 1", (symbol, self.three_days_ago))
            rowr = self.cur.fetchone()
            if rowr:
                old_pct, rid, auto = float(rowr["price"]), rowr["id"], False
            else:
                self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct_new))
                self.conn.commit()
                old_pct, rid, auto = pct_new, self.cur.lastrowid, True

            self.ordered_symbols_on_screen.append(symbol)
            idx = len(self.ordered_symbols_on_screen) - 1
            row = table.rowCount()
            table.insertRow(row)
            
            btn = SymbolButton(symbol)
            btn.setObjectName("SymbolButton")
            btn.setProperty("period", period)
            btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
            table.setCellWidget(row, 0, btn)
            
            for i, val in enumerate([pct_new, old_pct]):
                item = QTableWidgetItem(f"{val}")
                item.setFont(QFont("Arial", 14, QFont.Weight.Bold))
                item.setForeground(QBrush(QColor(255, 0, 0) if val < 0 else QColor(255, 215, 0)))
                table.setItem(row, 2 + i, item)

            op_btn = QPushButton("已写入" if (auto or pct_new == old_pct) else "替换")
            op_btn.setObjectName("ReplaceButton")
            op_btn.setEnabled(not (auto or pct_new == old_pct))
            if op_btn.isEnabled(): op_btn.clicked.connect(partial(self.on_replace_date2, symbol, pct_new, rid, op_btn))
            table.setCellWidget(row, 4, op_btn)
            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add)-1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

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

    def on_replace_date1(self, symbol, pct, btn):
        self.cur.execute("SELECT id FROM Earning WHERE date=? AND name=?", (self.date1, symbol))
        if self.cur.fetchone():
            if QMessageBox.question(self, "确认覆盖", f"覆盖 {symbol} 在 {self.date1} 的记录？") != QMessageBox.StandardButton.Yes: return
            self.cur.execute("UPDATE Earning SET price=? WHERE date=? AND name=?", (pct, self.date1, symbol))
            txt = "已覆盖"
        else:
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct))
            txt = "已写入"
        self.conn.commit()
        btn.setText(txt); btn.setEnabled(False)

    def on_replace_date2(self, symbol, new_pct, rid, btn):
        msg = f"真的要把 {symbol} 最近一次 ({self.three_days_ago} 之后) 的旧百分比替换成 {new_pct}% 吗？"
        if QMessageBox.question(self, "确认替换", msg) == QMessageBox.StandardButton.Yes:
            self.cur.execute("UPDATE Earning SET price=?, date=? WHERE id=?", (new_pct, self.date1, rid))
            self.conn.commit()
            btn.setText("已替换"); btn.setEnabled(False)
            # 更新界面上的旧百分比显示
            index = self.table2.indexAt(btn.pos())
            if index.isValid():
                item = self.table2.item(index.row(), 3)
                if item:
                    item.setText(str(new_pct))
                    item.setForeground(QBrush(QColor(255, 0, 0) if new_pct < 0 else QColor(255, 215, 0)))

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