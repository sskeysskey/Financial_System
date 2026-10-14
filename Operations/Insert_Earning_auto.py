import sys
import json
import sqlite3
import subprocess
import os
import tempfile
from datetime import date, datetime, timedelta
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
# Polymarket 预测数据路径
POLYMARKET_TXT_PATH = os.path.join(HOME, "Coding/News/earning_polymarket.txt")
# 新增：Firstrade 盘前涨跌数据路径
FIRSTRADE_JSON_PATH = os.path.join(HOME, "Coding/Financial_System/Modules/firstrade_watchlist_earning.json")

PERIOD_DISPLAY = {"BMO": "↩︎", "AMC": "↪︎", "TNS": "？"}
PERIOD_CN_MAP = {"BMO": "前", "AMC": "后", "TNS": "未"}  # 用于标题显示的中文映射

# --- 列索引常量（避免加列后硬编码索引错位） ---
COL_SYMBOL = 0
COL_PRED = 1
COL_PREMARKET = 2

# table2（前天）
T2_COL_OLD = 3
T2_COL_NEW = 4
T2_COL_OP = 5
T2_HEADERS = ["Symbol", "预测", "盘前", "旧百分比%", "新百分比%", "操作", "———————————————"]

# table1（昨天）
T1_COL_PCT = 3
T1_COL_OP = 4
T1_HEADERS = ["Symbol", "预测", "盘前", "百分比(%)", "操作", "——————————————————————"]

# table_today（今天）
T0_HEADERS = ["Symbol", "预测", "盘前", "——————————————————————————"]

COLOR_UP = QColor(255, 0, 0)        # 涨：红
COLOR_DOWN = QColor(0, 255, 0)      # 跌：绿
COLOR_STALE = QColor(128, 128, 128)  # 过期数据：灰
COLOR_PRED = QColor(255, 165, 0)    # 预测：橙


def pct_color(val):
    """与现有规则保持一致：>=0 红色，<0 绿色"""
    return COLOR_UP if val >= 0 else COLOR_DOWN


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


def save_json_atomic(path, data):
    """原子写入 JSON，避免写到一半崩溃导致配置文件损坏"""
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load_text_data(path):
    data = {}
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ':' not in line: continue
            key, value = map(str.strip, line.split(':', 1))
            if not key: continue
            cleaned_key = key.split()[-1]
            data[cleaned_key] = tuple(p.strip() for p in value.split(',')) if ',' in value else value
    return data


def load_premarket_data(path):
    """
    读取 Firstrade 盘前 JSON。
    返回: (quotes_dict, meta_dict)
      quotes_dict: {SYMBOL: {"text": "-2.50%", "num": -2.50, "last": "1,706.40"}}
    文件缺失/损坏时返回空字典，不影响主程序运行。
    """
    if not os.path.exists(path):
        return {}, {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[警告] 读取盘前数据失败: {path}\n{e}")
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}

    meta = raw.get("_meta") or {}
    quotes = raw.get("quotes") or {}
    result = {}
    if not isinstance(quotes, dict):
        return result, meta

    for key, q in quotes.items():
        if not isinstance(q, dict):
            continue
        sym = str(q.get("symbol") or key).strip().upper()
        if not sym:
            continue
        text = str(q.get("change_pct") or "").strip()

        num = q.get("change_pct_num")
        try:
            num = float(num) if num is not None and num != "" else None
        except (TypeError, ValueError):
            num = None
        # 数值缺失时尝试从文本解析
        if num is None and text:
            try:
                num = float(text.replace('%', '').replace(',', '').replace('+', '').strip())
            except ValueError:
                num = None
        # 文本缺失时由数值生成
        if not text and num is not None:
            text = f"{num:+.2f}%"
        if not text:
            continue

        result[sym] = {"text": text, "num": num, "last": str(q.get("last", "") or "")}
    return result, meta


def is_meta_today(meta, today):
    """判断盘前数据是否为今天更新的；无法判断时视为今天（不误伤）"""
    ts = meta.get("updated_at")
    try:
        if ts is not None:
            return date.fromtimestamp(float(ts)) == today
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    s = meta.get("updated_at_str")
    if isinstance(s, str) and len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date() == today
        except ValueError:
            pass
    return True


def fetch_mnspp_data_from_db(db_path, symbol):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?", (symbol,))
        result = cursor.fetchone()
    return result if result else ("N/A", None, "N/A", "--")


class SymbolButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
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

        # 记录每个分栏的数量
        self.count_date2 = 0  # 前天
        self.count_date1 = 0  # 昨天
        self.count_today = 0  # 今天

        today = date.today()
        self.today = today
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

        # 读取 polymarket 预测数据
        self.polymarket_data = {}
        if os.path.exists(POLYMARKET_TXT_PATH):
            with open(POLYMARKET_TXT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        sym, pct = line.split(":", 1)
                        self.polymarket_data[sym.strip().upper()] = pct.strip()

        # 盘前数据（在 refresh_data 中加载，便于以后刷新时同步更新）
        self.premarket_data = {}
        self.premarket_meta = {}
        self.premarket_is_fresh = True

        self.conn = sqlite3.connect(DB_PATH, timeout=60.0)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.close)
        QShortcut(QKeySequence(Qt.Key.Key_Slash), self).activated.connect(self.show_search_dialog)
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        cw = QWidget()
        hlay = QHBoxLayout(cw)
        self.apply_stylesheet()

        self.table2 = QTableWidget(0, len(T2_HEADERS))
        self.table2.setHorizontalHeaderLabels(T2_HEADERS)

        self.table1 = QTableWidget(0, len(T1_HEADERS))
        self.table1.setHorizontalHeaderLabels(T1_HEADERS)

        self.table_today = QTableWidget(0, len(T0_HEADERS))
        self.table_today.setHorizontalHeaderLabels(T0_HEADERS)

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

    # ------------------------------------------------------------------
    # 盘前数据相关
    # ------------------------------------------------------------------
    def _load_premarket(self):
        self.premarket_data, self.premarket_meta = load_premarket_data(FIRSTRADE_JSON_PATH)
        self.premarket_is_fresh = is_meta_today(self.premarket_meta, self.today)
        self._update_premarket_headers()

    def _update_premarket_headers(self):
        updated = self.premarket_meta.get("updated_at_str", "未知")
        header_text = "盘前" if self.premarket_is_fresh else "盘前(旧)"
        tip = f"Firstrade 盘前数据\n更新时间: {updated}\n条数: {len(self.premarket_data)}"
        if not self.premarket_is_fresh:
            tip += "\n⚠️ 数据非今日更新，仅供参考"
        for t in [self.table2, self.table1, self.table_today]:
            hdr = t.horizontalHeaderItem(COL_PREMARKET)
            if hdr is None:
                hdr = QTableWidgetItem()
                t.setHorizontalHeaderItem(COL_PREMARKET, hdr)
            hdr.setText(header_text)
            hdr.setToolTip(tip)

    def _lookup_premarket(self, symbol):
        """兼容 BRK.B / BRK-B 等写法差异"""
        s = symbol.strip().upper()
        for k in (s, s.replace('-', '.'), s.replace('.', '-')):
            if k in self.premarket_data:
                return self.premarket_data[k]
        return None

    def _set_premarket_cell(self, table, row, symbol):
        info = self._lookup_premarket(symbol)
        item = QTableWidgetItem(info["text"] if info else "")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if info:
            if not self.premarket_is_fresh:
                item.setForeground(QBrush(COLOR_STALE))
            elif info["num"] is not None:
                item.setForeground(QBrush(pct_color(info["num"])))
            tip = f"最新价: {info['last'] or 'N/A'}\n更新时间: {self.premarket_meta.get('updated_at_str', '未知')}"
            if not self.premarket_is_fresh:
                tip += "\n⚠️ 数据非今日更新"
            item.setToolTip(tip)
        table.setItem(row, COL_PREMARKET, item)

    def _set_pred_cell(self, table, row, symbol):
        pred_val = self.polymarket_data.get(symbol.upper(), "")
        pred_item = QTableWidgetItem(pred_val)
        pred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        pred_item.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        pred_item.setForeground(QBrush(COLOR_PRED))
        pred_item.setFlags(pred_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, COL_PRED, pred_item)

    def _make_symbol_button(self, table, row, symbol, period, idx):
        btn = SymbolButton(symbol)
        btn.setObjectName("SymbolButton")
        btn.setProperty("period", period)
        btn.clicked.connect(partial(self.on_symbol_button_clicked, symbol, idx))
        table.setCellWidget(row, COL_SYMBOL, btn)
        return btn

    def _make_pct_item(self, val):
        item = QTableWidgetItem(f"{val}")
        item.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        item.setForeground(QBrush(pct_color(val)))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def show_search_dialog(self):
        """按 / 键弹出搜索框"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "搜索 Symbol", "请输入 Symbol（回车确认）:")
        if ok and text.strip():
            self.search_and_locate_symbol(text.strip().upper())

    def search_and_locate_symbol(self, symbol):
        """在三个表格中查找 Symbol 并定位+高亮"""
        for table in (self.table2, self.table1, self.table_today):
            for row in range(table.rowCount()):
                w = table.cellWidget(row, COL_SYMBOL)
                if isinstance(w, SymbolButton) and w.text().upper() == symbol:
                    table.setCurrentCell(row, COL_SYMBOL)
                    index = table.model().index(row, COL_SYMBOL)
                    table.scrollTo(index, table.ScrollHint.PositionAtCenter)
                    table.setFocus()
                    self.flash_highlight(w)
                    return
        QMessageBox.information(self, "未找到", f"未找到 Symbol: {symbol}")

    def flash_highlight(self, btn):
        """让按钮闪烁几次，提醒用户"""
        # 修复：连续搜索时避免把"高亮样式"当作原样式保存导致边框残留
        original_style = btn.property("_orig_style")
        if original_style is None:
            original_style = btn.styleSheet()
            btn.setProperty("_orig_style", original_style)
        highlight_style = original_style + "border: 3px solid #FFD700;"

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
        self.current_symbol_index = -1
        self.count_date2 = 0
        self.count_date1 = 0
        self.count_today = 0

        self._load_premarket()

        self.table2.setRowCount(0)
        self.table1.setRowCount(0)
        self.table_today.setRowCount(0)
        self.process_date2()
        self.process_date1()
        self.process_today()

    # ------------------------------------------------------------------
    # 核心导航逻辑
    # ------------------------------------------------------------------
    def handle_chart_callback(self, symbol, action):
        if action in ('next', 'prev'):
            QTimer.singleShot(50, lambda: self.navigate_to_adjacent_symbol(action))

    def navigate_to_adjacent_symbol(self, direction):
        total = len(self.ordered_symbols_on_screen)
        if total == 0: return
        step = 1 if direction == 'next' else -1
        new_index = self.current_symbol_index
        if new_index < 0 and step == -1:
            new_index = 0
        # 修复：跳过没有 sector 的 Symbol，避免导航卡死
        for _ in range(total):
            new_index = (new_index + step) % total
            if self.ordered_symbols_on_screen[new_index] in self.symbol_to_sector:
                break
        else:
            return
        self.on_symbol_button_clicked(self.ordered_symbols_on_screen[new_index], btn_index=new_index)

    def on_symbol_button_clicked(self, symbol, btn_index=None):
        sector = self.symbol_to_sector.get(symbol)
        if not sector:
            QMessageBox.information(self, "无法绘图", f"{symbol} 未在 Sectors_All.json 中找到所属板块。")
            return

        if btn_index is not None:
            self.current_symbol_index = btn_index
        else:
            try: self.current_symbol_index = self.ordered_symbols_on_screen.index(symbol)
            except ValueError: self.current_symbol_index = -1

        compare_val = self.compare_data.get(symbol, "N/A")
        shares, mktcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, symbol)

        total_global = len(self.ordered_symbols_on_screen)
        idx = self.current_symbol_index

        if idx < self.count_date2:
            date_category = "前天"
            group_count = self.count_date2
            current_group_symbols = self.ordered_symbols_on_screen[0: self.count_date2]
        elif idx < (self.count_date2 + self.count_date1):
            date_category = "昨天"
            group_count = self.count_date1
            current_group_symbols = self.ordered_symbols_on_screen[self.count_date2: self.count_date2 + self.count_date1]
        else:
            date_category = "今天"
            group_count = self.count_today
            current_group_symbols = self.ordered_symbols_on_screen[self.count_date2 + self.count_date1:]

        period_code = self.symbol_to_period.get(symbol, "TNS")
        period_cn = PERIOD_CN_MAP.get(period_code, "?")

        same_period_symbols = [s for s in current_group_symbols if self.symbol_to_period.get(s) == period_code]
        period_total = len(same_period_symbols)
        try:
            local_period_idx = same_period_symbols.index(symbol) + 1
        except ValueError:
            local_period_idx = 0

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
            self.count_today += 1
            idx = len(self.ordered_symbols_on_screen) - 1

            row = table.rowCount()
            table.insertRow(row)
            self._make_symbol_button(table, row, symbol, period, idx)
            self._set_pred_cell(table, row, symbol)
            self._set_premarket_cell(table, row, symbol)

            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add) - 1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

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
            self.count_date1 += 1
            idx = len(self.ordered_symbols_on_screen) - 1
            row = table.rowCount()
            table.insertRow(row)

            self._make_symbol_button(table, row, symbol, period, idx)
            self._set_pred_cell(table, row, symbol)
            self._set_premarket_cell(table, row, symbol)
            table.setItem(row, T1_COL_PCT, self._make_pct_item(pct))

            rep_btn = QPushButton("写入")
            rep_btn.setObjectName("ReplaceButton")
            rep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rep_btn.clicked.connect(partial(self.on_replace_date1, symbol, pct, rep_btn))
            table.setCellWidget(row, T1_COL_OP, rep_btn)

            if period == "BMO": self.auto_write_date1(symbol, pct, rep_btn)
            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add) - 1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

    def process_date2(self):
        table = self.table2
        tags_to_add = []
        for symbol, period in self.symbols_by_date[self.date2]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector: continue
            p1, p2 = self._get_price(sector, self.date1, symbol), self._get_price(sector, self.date2, symbol)
            if p1 is None or not p2: continue
            pct_new = round((p1 - p2) / p2 * 100, 2)

            self.cur.execute("SELECT price, date FROM Earning WHERE name=? AND date>=? ORDER BY date DESC LIMIT 1", (symbol, self.three_days_ago))
            rowr = self.cur.fetchone()
            old_pct = None
            if rowr and rowr["price"] is not None:
                try:
                    old_pct = round(float(rowr["price"]), 2)
                except (TypeError, ValueError):
                    old_pct = None
            if old_pct is not None:
                old_date, auto = rowr["date"], False
            else:
                if rowr is None:
                    self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, pct_new))
                    self.conn.commit()
                    old_date, auto = self.date1, True
                else:
                    # 记录存在但 price 无效：允许用户替换
                    old_date, auto = rowr["date"], False
                old_pct = pct_new if auto else 0.0

            self.ordered_symbols_on_screen.append(symbol)
            self.count_date2 += 1
            idx = len(self.ordered_symbols_on_screen) - 1
            row = table.rowCount()
            table.insertRow(row)

            self._make_symbol_button(table, row, symbol, period, idx)
            self._set_pred_cell(table, row, symbol)
            self._set_premarket_cell(table, row, symbol)

            table.setItem(row, T2_COL_OLD, self._make_pct_item(old_pct))
            table.setItem(row, T2_COL_NEW, self._make_pct_item(pct_new))

            same = (round(pct_new, 2) == round(old_pct, 2))
            op_btn = QPushButton("已写入" if (auto or same) else "替换")
            op_btn.setObjectName("ReplaceButton")
            op_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            op_btn.setEnabled(not (auto or same))
            if op_btn.isEnabled():
                op_btn.clicked.connect(partial(self.on_replace_date2, symbol, pct_new, old_date, op_btn))
            table.setCellWidget(row, T2_COL_OP, op_btn)
            tags_to_add.append(get_tags_for_symbol(symbol, self.description_data))

        table.resizeColumnsToContents()
        for i in range(len(tags_to_add) - 1, -1, -1): self._add_tag_row(table, i, tags_to_add[i])

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
        if QMessageBox.question(self, "确认替换", msg) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.cur.execute("DELETE FROM Earning WHERE date=? AND name=?", (old_date, symbol))
            self.cur.execute("INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)", (self.date1, symbol, new_pct))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            QMessageBox.critical(self, "数据库错误", f"替换失败:\n{e}")
            return
        btn.setText("已替换")
        btn.setEnabled(False)

        # 修复：按按钮所在行精确定位，并使用列常量（不再硬编码第 2 列）
        for r in range(self.table2.rowCount()):
            if self.table2.cellWidget(r, T2_COL_OP) is btn:
                item = self.table2.item(r, T2_COL_OLD)
                if item:
                    item.setText(str(new_pct))
                    item.setForeground(QBrush(pct_color(new_pct)))
                break

    def show_table_context_menu(self, pos):
        table = self.sender()
        row = table.rowAt(pos.y())
        if row == -1: return

        # 向上查找 SymbolButton
        symbol = None
        for r in range(row, -1, -1):
            w = table.cellWidget(r, COL_SYMBOL)
            if isinstance(w, SymbolButton):
                symbol = w.text()
                break
        if not symbol: return

        menu = QMenu(self)
        move_menu = menu.addMenu("移动")
        for group in ["Must", "Today", "Short"]:
            cfg_val = self.panel_config.get(group, [])
            in_cfg = symbol in (cfg_val if isinstance(cfg_val, list) else cfg_val.keys())
            act = QAction(group, self)
            act.setEnabled(not in_cfg)
            act.triggered.connect(partial(self.copy_symbol_to_group, symbol, group))
            move_menu.addAction(act)

        menu.addSeparator()
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

    def copy_symbol_to_group(self, symbol, group, *_):
        cfg = self.panel_config
        if group not in cfg: cfg[group] = {}
        if isinstance(cfg[group], dict):
            cfg[group][symbol] = ""
        else:
            if symbol not in cfg[group]: cfg[group].append(symbol)
        try:
            save_json_atomic(self.panel_config_path, cfg)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入配置文件失败:\n{e}")
            return
        QMessageBox.information(self, "成功", f"已复制 {symbol} 到 {group}")

    def center_window(self):
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def closeEvent(self, event):
        # 修复：退出时关闭数据库连接
        try:
            self.conn.close()
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())