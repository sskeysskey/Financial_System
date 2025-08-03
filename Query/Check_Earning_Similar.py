import sys
import json
import sqlite3
from collections import OrderedDict
import subprocess
from decimal import Decimal

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QMenu, QAction,
    QGridLayout, QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCursor

sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
from Chart_input import plot_financial_data


COLORS_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Colors.json'
DESCRIPTION_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
SECTORS_ALL_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'
EARNINGS_FILE_PATH = '/Users/yanzhang/Coding/News/Earnings_Release_new.txt'
EARNINGS_FILE_NEXT_PATH = '/Users/yanzhang/Coding/News/Earnings_Release_next.txt'
TAGS_WEIGHT_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/tags_weight.json'

RELATED_SYMBOLS_LIMIT = 10
MAX_PER_COLUMN = 20

symbol_manager = None
compare_data = {}
keyword_colors = {}
sector_data = {}
json_data = {}
tags_weight_config = {}
DEFAULT_WEIGHT = Decimal('1')

# 新增：SymbolButton 子类
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

class SymbolManager:
    def __init__(self, symbols_list):
        self.symbols = symbols_list
        self.current_index = -1
        if not self.symbols:
            print("Warning: No symbols loaded into SymbolManager.")

    def next_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index - 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        if symbol in self.symbols:
            self.current_index = self.symbols.index(symbol)
        else:
            print(f"Warning: Symbol {symbol} not found in the list.")

    def reset(self):
        self.current_index = -1


def parse_multiple_earnings_files(paths):
    merged = OrderedDict()
    all_symbols = []

    for p in paths:
        sched, syms = parse_earnings_file(p)
        for date_str, times in sched.items():
            merged.setdefault(date_str, OrderedDict())
            for tc, slist in times.items():
                merged[date_str].setdefault(tc, [])
                for s in slist:
                    if s not in merged[date_str][tc]:
                        merged[date_str][tc].append(s)
        for s in syms:
            if s not in all_symbols:
                all_symbols.append(s)

    for date_str, times in merged.items():
        ordered = OrderedDict()
        if 'BMO' in times: ordered['BMO'] = times['BMO']
        if 'AMC' in times: ordered['AMC'] = times['AMC']
        for tc, slist in times.items():
            if tc not in ordered:
                ordered[tc] = slist
        merged[date_str] = ordered

    merged = OrderedDict(sorted(merged.items()))
    return merged, all_symbols


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
                    tc = time_code.upper()
                    earnings_schedule.setdefault(date_str, OrderedDict())
                    earnings_schedule[date_str].setdefault(tc, [])
                    earnings_schedule[date_str][tc].append(symbol)
                    if symbol not in all_symbols:
                        all_symbols.append(symbol)
    except FileNotFoundError:
        print(f"Error: Earnings file not found at {path}")

    for date_str, times in earnings_schedule.items():
        sorted_times = OrderedDict()
        if 'BMO' in times: sorted_times['BMO'] = times['BMO']
        if 'AMC' in times: sorted_times['AMC'] = times['AMC']
        for tc, slist in times.items():
            if tc not in sorted_times:
                sorted_times[tc] = slist
        earnings_schedule[date_str] = sorted_times

    return OrderedDict(sorted(earnings_schedule.items())), all_symbols


def get_symbol_type(symbol):
    for item in json_data.get('stocks', []):
        if item.get('symbol') == symbol:
            return 'stock'
    for item in json_data.get('etfs', []):
        if item.get('symbol') == symbol:
            return 'etf'
    return None


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file, object_pairs_hook=OrderedDict)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading JSON from {path}: {e}")
        return {}


def load_text_data(path):
    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                key, value = map(str.strip, line.split(':', 1))
                cleaned_key = key.split()[-1]
                data[cleaned_key] = tuple(p.strip() for p in value.split(',')) if ',' in value else value
    except FileNotFoundError:
        print(f"Error: Text data file not found at {path}")
    return data


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
    base_path = '/Users/yanzhang/Coding/Financial_System'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar':  f'{base_path}/Query/Find_Similar_Tag.py',
        'tags':     f'{base_path}/Operations/Editor_Tags.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'earning':  f'{base_path}/Operations/Insert_Earning.py',
        'futu':     '/Users/yanzhang/Coding/ScriptEditor/Stock_CheckFutu.scpt',
        'kimi':     '/Users/yanzhang/Coding/ScriptEditor/CheckKimi_Earning.scpt'
    }
    try:
        if script_type in ['futu', 'kimi']:
            subprocess.Popen(['osascript', script_configs[script_type], keyword])
        else:
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.Popen([python_path, script_configs[script_type], keyword])
    except Exception as e:
        print(f"执行脚本时出错: {e}")


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


def find_symbols_by_tags_b(target_tags_with_weight, data, original_symbol):
    related = {'stocks': [], 'etfs': []}
    target_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}

    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            sym = item.get('symbol')
            if sym == original_symbol:
                continue
            tags = item.get('tag', [])
            matched = []
            used = set()

            for tag in tags:
                tl = tag.lower()
                if tl in target_dict and tl not in used:
                    matched.append((tag, target_dict[tl]))
                    used.add(tl)

            for tag in tags:
                tl = tag.lower()
                if tl in used:
                    continue
                for tgt, w in target_dict.items():
                    if tgt in tl or tl in tgt:
                        if tl != tgt and tgt not in used:
                            weight_to_use = Decimal('1.0') if w > Decimal('1.0') else w
                            matched.append((tag, weight_to_use))
                            used.add(tgt)
                        break

            if matched:
                total = sum(w for _, w in matched)
                related[category].append((sym, total))

    for cat in related:
        related[cat].sort(key=lambda x: x[1], reverse=True)

    stype = get_symbol_type(original_symbol)
    order = ['etfs', 'stocks'] if stype == 'etf' else ['stocks', 'etfs']
    combined = []
    for cat in order:
        combined.extend(related[cat])
    return combined


class EarningsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.button_mapping = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("财报日历查看器 (延迟计算相关)")
        self.setFocusPolicy(Qt.StrongFocus)

        # 搜索栏
        top_widget = QWidget()
        top_lay = QHBoxLayout(top_widget)
        self.search_line = QLineEdit()
        self.search_button = QPushButton("搜索 Symbol")
        top_lay.addWidget(self.search_line)
        top_lay.addWidget(self.search_button)
        self.search_line.setPlaceholderText("输入要搜索的 Symbol，然后按回车或点击“搜索 Symbol”")
        self.search_line.returnPressed.connect(self.on_search)
        self.search_button.clicked.connect(self.on_search)

        # 主滚动区
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout = QHBoxLayout(self.scroll_content)
        self.main_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        container = QWidget()
        container_l = QVBoxLayout(container)
        container_l.setContentsMargins(0, 0, 0, 0)
        container_l.addWidget(top_widget)
        container_l.addWidget(self.scroll_area)
        self.setCentralWidget(container)

        self.apply_stylesheet()
        self.populate_ui()

    def apply_stylesheet(self):
        button_styles = {
            "Cyan": ("cyan", "black"), "Blue": ("blue", "white"),
            "Purple": ("purple", "white"), "Green": ("green", "white"),
            "White": ("white", "black"), "Yellow": ("yellow", "black"),
            "Orange": ("orange", "black"), "Red": ("red", "black"),
            "Black": ("black", "white"), "Default": ("#ddd", "black")
        }
        qss = ""
        for name, (bg, fg) in button_styles.items():
            qss += (
                f"QPushButton#{name} {{ background-color: {bg}; color: {fg}; "
                f"font-size:16px; padding:5px; border:1px solid #333; border-radius:4px; }} "
                f"QPushButton#{name}:hover {{ background-color:{self.lighten_color(bg)}; }} "
            )
        qss += "QGroupBox { font-size:16px; font-weight:bold; margin-top:10px; }"
        self.setStyleSheet(qss)

    def lighten_color(self, color_name, factor=1.2):
        from PyQt5.QtGui import QColor
        color = QColor(color_name)
        h, s, l, a = color.getHslF()
        l = min(1.0, l * factor)
        color.setHslF(h, s, l, a)
        return color.name()

    def get_button_style_name(self, keyword):
        color_map = {
            "cyan": "Cyan", "blue": "Blue", "purple": "Purple",
            "yellow": "Yellow", "orange": "Orange", "black": "Black",
            "white": "White", "green": "Green", "red": "Red",
        }
        for color, style_name in color_map.items():
            if keyword in keyword_colors.get(f"{color}_keywords", []):
                return style_name
        return "Default"

    def on_search(self):
        key = self.search_line.text().strip().upper()
        if not key:
            return
        if key not in self.button_mapping:
            QMessageBox.information(self, "未找到", f"Symbol “{key}” 不在当前列表中。")
            return
        btn, _, _ = self.button_mapping[key]
        QTimer.singleShot(100, lambda: self.scroll_area.ensureWidgetVisible(btn))
        btn.setFocus()

    def populate_ui(self):
        earnings_schedule, _ = parse_multiple_earnings_files([
            EARNINGS_FILE_PATH,
            EARNINGS_FILE_NEXT_PATH
        ])

        valid_symbols = set()
        for names in sector_data.values():
            valid_symbols.update(names)

        known_time_labels = {"BMO": "盘前 (BMO)", "AMC": "盘后 (AMC)", "TNS": "待定 (TNS)"}

        for date_str, times in earnings_schedule.items():
            # 日期分组
            date_group = QGroupBox(date_str)
            date_layout = QVBoxLayout()
            date_layout.setContentsMargins(10, 25, 10, 10)   # ← 留出标题高度
            date_layout.setSpacing(10)
            date_group.setLayout(date_layout)
            self.main_layout.addWidget(date_group, 0, Qt.AlignLeft | Qt.AlignTop)

            for tc, symbols in times.items():
                if not symbols:
                    continue
                time_group = QGroupBox(known_time_labels.get(tc, tc))
                time_layout = QGridLayout()
                time_layout.setContentsMargins(10, 20, 10, 10)  # ← 同样留出标题高度
                time_layout.setHorizontalSpacing(5)
                time_layout.setVerticalSpacing(5)
                time_group.setLayout(time_layout)
                date_layout.addWidget(time_group)

                for idx, sym in enumerate(symbols):
                    row = idx % MAX_PER_COLUMN
                    col_block = idx // MAX_PER_COLUMN
                    base_col = col_block * 3

                    txt = f"{sym}"
                    btn = SymbolButton(txt)
                    btn.setObjectName(self.get_button_style_name(sym))
                    btn.clicked.connect(lambda _, s=sym: self.on_keyword_selected_chart(s))

                    related = QPushButton("...")
                    related.setFixedWidth(50)

                    tags = get_tags_for_symbol(sym)
                    tags_str = ", ".join(tags) if isinstance(tags, list) else tags
                    self.button_mapping[sym] = (btn, date_group, time_group)

                    btn.setToolTip(
                        f"<div style='font-size:20px;background-color:lightyellow;color:black;'>{tags_str}</div>")
                    btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    btn.customContextMenuRequested.connect(lambda pos, s=sym: self.show_context_menu(s))

                    # 相关容器
                    container = QWidget()
                    hl = QHBoxLayout(container)
                    hl.setContentsMargins(2, 2, 2, 2)
                    hl.setSpacing(5)
                    hl.setAlignment(Qt.AlignLeft)
                    container.setVisible(False)

                    # 点击“相关”才动态计算并展开
                    related.clicked.connect(
                        lambda _, s=sym, c=container, vs=valid_symbols: self.toggle_related(s, c, vs)
                    )

                    time_layout.addWidget(btn, row, base_col)
                    time_layout.addWidget(related, row, base_col + 1)
                    time_layout.addWidget(container, row, base_col + 2)

    def toggle_related(self, sym, container, valid_symbols):
        # 如果还没有计算过，就动态计算并添加按钮
        layout = container.layout()
        if layout.count() == 0:
            tg = find_tags_by_symbol_b(sym, json_data)
            if tg:
                rels = find_symbols_by_tags_b(tg, json_data, sym)
                cnt = 0
                for r_sym, _ in rels:
                    if r_sym not in valid_symbols or cnt >= RELATED_SYMBOLS_LIMIT:
                        continue
                    rb = SymbolButton(f"{r_sym}")
                    rb.setObjectName(self.get_button_style_name(r_sym))
                    rb.clicked.connect(lambda _, s=r_sym: self.on_keyword_selected_chart(s))
                    rt = get_tags_for_symbol(r_sym)
                    rt_str = ", ".join(rt) if isinstance(rt, list) else rt
                    rb.setToolTip(
                        f"<div style='font-size:20px;background-color:lightyellow;color:black;'>{rt_str}</div>")
                    rb.setContextMenuPolicy(Qt.CustomContextMenu)
                    rb.customContextMenuRequested.connect(lambda pos, s=r_sym: self.show_context_menu(s))
                    layout.addWidget(rb)
                    cnt += 1
        # 切换显示/隐藏
        container.setVisible(not container.isVisible())

    def show_context_menu(self, keyword):
        menu = QMenu(self)
        acts = [
            ("在富途中搜索", lambda: execute_external_script('futu', keyword)),
            None,
            ("找相似", lambda: execute_external_script('similar', keyword)),
            None,
            ("编辑 Tags", lambda: execute_external_script('tags', keyword)),
            None,
            ("添加到 Earning", lambda: execute_external_script('earning', keyword)),
            ("编辑 Earing DB", lambda: execute_external_script('editor_earning', keyword)),
            ("Kimi检索财报", lambda: execute_external_script('kimi', keyword)),
            None,
            ("加入黑名单", lambda: execute_external_script('blacklist', keyword)),
        ]
        for item in acts:
            if item is None:
                menu.addSeparator()
            else:
                text, cb = item
                menu.addAction(QAction(text, self, triggered=cb))
        menu.exec_(QCursor.pos())

    def on_keyword_selected_chart(self, sym):
        global symbol_manager
        sector = next((s for s, lst in sector_data.items() if sym in lst), None)
        if sector:
            symbol_manager.set_current_symbol(sym)
            cmp = compare_data.get(sym, "N/A")
            shares, mcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, sym)
            plot_financial_data(DB_PATH, sector, sym, cmp, (shares, pb), mcap, pe, json_data, '1Y', False)
            self.setFocus()

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Escape:
            self.close()
        elif k == Qt.Key_Down:
            self.on_arrow('down')
        elif k == Qt.Key_Up:
            self.on_arrow('up')
        else:
            super().keyPressEvent(ev)

    def on_arrow(self, dir_):
        global symbol_manager
        sym = symbol_manager.next_symbol() if dir_ == 'down' else symbol_manager.previous_symbol()
        if sym:
            self.on_keyword_selected_chart(sym)

    def closeEvent(self, ev):
        global symbol_manager
        symbol_manager.reset()
        QApplication.quit()


if __name__ == '__main__':
    keyword_colors = load_json(COLORS_PATH)
    json_data = load_json(DESCRIPTION_PATH)
    sector_data = load_json(SECTORS_ALL_PATH)
    compare_data = load_text_data(COMPARE_DATA_PATH)
    wg = load_weight_groups()
    tags_weight_config = {tag: w for w, tags in wg.items() for tag in tags}
    _, syms = parse_multiple_earnings_files([EARNINGS_FILE_PATH, EARNINGS_FILE_NEXT_PATH])
    symbol_manager = SymbolManager(syms)

    app = QApplication(sys.argv)
    win = EarningsWindow()
    win.showMaximized()
    sys.exit(app.exec_())