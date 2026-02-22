import re
import sys
import time
import json
import sqlite3
import pyperclip
import subprocess
import os
from decimal import Decimal
from datetime import datetime, date, timedelta


USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- PyQt6 核心组件 ---
# 新增导入 QTimer
from PyQt6.QtCore import Qt, QEvent, QSize, QTimer
from PyQt6.QtWidgets import (QApplication, QInputDialog, QMessageBox, QMainWindow, QWidget,
                             QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
                             QScrollArea, QLabel, QMenu, QLineEdit)
from PyQt6.QtGui import QCursor, QAction, QFont, QPalette, QColor

# --- 检查并添加必要的路径 ---
chart_input_path = os.path.join(BASE_CODING_DIR, "Financial_System", "Query")
if chart_input_path not in sys.path:
    sys.path.append(chart_input_path)

try:
    from Chart_input import plot_financial_data
except ImportError:
    print(f"错误：无法从路径 '{chart_input_path}' 导入 'plot_financial_data'。")
    sys.exit(1)

# --- 文件路径 ---
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
WEIGHT_CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "tags_weight.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
PANEL_CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")

DEFAULT_WEIGHT = Decimal('1')

# --- 核心逻辑函数 ---

def fetch_mnspp_data_from_db(db_path, symbol):
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cur = conn.cursor()
            cur.execute("SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?", (symbol,))
            row = cur.fetchone()
        return row if row else ("N/A", None, "N/A", "--")
    except Exception:
        return ("N/A", None, "N/A", "--")

def load_weight_groups():
    try:
        with open(WEIGHT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            return {Decimal(k): v for k, v in raw_data.items()}
    except Exception:
        return {}

def find_tags_by_symbol(symbol, data, tags_weight_config):
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
    for item in data.get('stocks', []):
        if item.get('symbol') == symbol: return 'stock'
    for item in data.get('etfs', []):
        if item.get('symbol') == symbol: return 'etf'
    return None

def find_symbols_by_tags(target_tags_with_weight, data):
    related_symbols = {'stocks': [], 'etfs': []}
    target_tags_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}
    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            tags = item.get('tag', [])
            matched_tags = []
            used_tags = set()
            # 完全匹配
            for tag in tags:
                t_low = tag.lower()
                if t_low in target_tags_dict and t_low not in used_tags:
                    matched_tags.append((tag, target_tags_dict[t_low]))
                    used_tags.add(t_low)
            # 部分匹配
            for tag in tags:
                t_low = tag.lower()
                if t_low in used_tags: continue
                for target_tag, target_weight in target_tags_dict.items():
                    if (target_tag in t_low or t_low in target_tag) and t_low != target_tag:
                        if target_tag not in used_tags:
                            weight_to_use = Decimal('1.0') if target_weight > Decimal('1.0') else target_weight
                            matched_tags.append((tag, weight_to_use))
                            used_tags.add(target_tag)
                        break
            if matched_tags:
                related_symbols[category].append((item['symbol'], matched_tags, tags))

    for cat in related_symbols:
        related_symbols[cat].sort(
            key=lambda x: (sum(w for _, w in x[1]), fetch_mnspp_data_from_db(DB_PATH, x[0])[1] or 0),
            reverse=True
        )
    return related_symbols

def load_compare_data(file_path):
    data = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if ':' in line:
                    s, v = line.split(':', 1)
                    data[s.strip()] = v.strip()
    except Exception: pass
    return data

def load_json_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception: return {}

def get_stock_symbol(default_symbol=""):
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    if input_dialog.exec() == QInputDialog.DialogCode.Accepted:
        return input_dialog.textValue().strip().upper()
    return None

def copy2clipboard():
    try:
        script = 'tell application "System Events" to keystroke "c" using {command down}'
        subprocess.run(['osascript', '-e', script], check=True, timeout=1)
        time.sleep(0.2)
        return True
    except Exception: return False

def get_clipboard_content():
    try: return pyperclip.paste().strip()
    except Exception: return ""

def execute_external_script(script_type, keyword):
    script_configs = {
        'blacklist': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Blacklist.py'),
        'similar':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Find_Similar_Tag.py'),
        'tags':     os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'editor_earning': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Earning_DB.py'),
        'earning':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Earning.py'),
        'event_input': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Events.py'),
        'event_editor': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Events.py'),
        'futu':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'kimi':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Check_Earning.scpt')
    }
    path = script_configs.get(script_type)
    if not path: return
    try:
        if script_type in ['futu', 'kimi']:
            subprocess.Popen(['osascript', path, keyword])
        else:
            py_path = sys.executable
            subprocess.Popen([py_path, path, keyword])
    except Exception as e: print(f"执行脚本错误: {e}")

# --- PyQt6 自定义组件 ---

class RowWidget(QWidget):
    def __init__(self, symbol: str, click_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbol = symbol
        self.click_callback = click_callback

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.click_callback(self.symbol)
        return False

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

class SimilarityViewerWindow(QMainWindow):
    def __init__(self, source_symbol, source_tags, related_symbols, all_data):
        super().__init__()
        self.source_symbol = source_symbol
        self.source_tags = source_tags
        self.related_symbols = related_symbols
        self.all_data = all_data
        self.json_data = all_data['description']
        self.compare_data = all_data['compare']
        self.sector_data = all_data['sectors']
        self.tags_weight_config = all_data['tags_weight']
        self.panel_config = all_data['panel_config']
        self.panel_config_path = all_data['panel_config_path']
        
        # 新增：用于方向键导航的变量
        self.ordered_symbols_on_screen = []
        self.current_symbol_index = -1
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"相似度分析: {self.source_symbol}")
        self.setGeometry(150, 150, 1600, 1000)
        self.setStyleSheet(self.get_stylesheet())

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setCentralWidget(scroll_area)

        main_widget = QWidget()
        scroll_area.setWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setSpacing(10)
        
        self.populate_ui(self.main_layout)

        if hasattr(self, 'search_input'):
            self.search_input.setFocus()
            self.search_input.selectAll()

    def populate_ui(self, layout):
        # 每次刷新UI时清空列表
        self.ordered_symbols_on_screen.clear()
        
        # 1. 源 Symbol 区域
        self.ordered_symbols_on_screen.append(self.source_symbol)
        source_group = QGroupBox("-")
        source_layout = QVBoxLayout(source_group)
        source_widget = self.create_source_symbol_widget()
        source_layout.addWidget(source_widget)
        layout.addWidget(source_group)

        # 2. 关联列表区域
        related_layout = QHBoxLayout()
        symbol_type = get_symbol_type(self.source_symbol, self.json_data)
        categories_order = ['etfs', 'stocks'] if symbol_type == 'etf' else ['stocks', 'etfs']

        for category in categories_order:
            symbols_list = self.related_symbols.get(category, [])
            if not symbols_list: continue

            group_box = QGroupBox("-")
            group_layout = QVBoxLayout(group_box)
            group_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            
            for sym, matched_tags, all_tags in symbols_list:
                if sym == self.source_symbol: continue
                if not self.compare_data.get(sym, "").strip(): continue
                
                self.ordered_symbols_on_screen.append(sym)
                widget = self.create_similar_symbol_widget(sym, matched_tags, all_tags)
                group_layout.addWidget(widget)
            
            # 比例 70:30
            stretch = 7 if category == 'stocks' else 3
            related_layout.addWidget(group_box, stretch)

        layout.addLayout(related_layout)
        layout.addStretch(1)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout(): self.clear_layout(item.layout())

    def clear_content(self):
        for i in reversed(range(self.main_layout.count())):
            item = self.main_layout.takeAt(i)
            if not item: continue
            if item.widget(): item.widget().deleteLater()
            elif item.layout(): self.clear_layout(item.layout())

    def on_search(self):
        symbol = self.search_input.text().strip().upper()
        if not symbol: return
        tags = find_tags_by_symbol(symbol, self.json_data, self.tags_weight_config)
        if not tags:
            QMessageBox.information(self, "未找到", f"找不到符号 '{symbol}' 的标签。")
            return
        self.source_symbol = symbol
        self.source_tags = tags
        self.related_symbols = find_symbols_by_tags(tags, self.json_data)
        self.clear_content()
        self.populate_ui(self.main_layout)

    def copy_symbol_to_group(self, symbol: str, group: str):
        cfg = self.panel_config
        if group not in cfg: cfg[group] = {}
        
        if isinstance(cfg[group], dict):
            if symbol in cfg[group]: return
            cfg[group][symbol] = ""
        elif isinstance(cfg[group], list):
            if symbol in cfg[group]: return
            cfg[group].append(symbol)
        
        try:
            with open(self.panel_config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "成功", f"已复制 {symbol} 到 {group}")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def get_color_decision_data(self, symbol: str):
        try:
            with sqlite3.connect(DB_PATH, timeout=60.0) as conn:
                cur = conn.cursor()
                cur.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 2", (symbol,))
                rows = cur.fetchall()

            if not rows: return None, None, None
            
            lat_date_str, lat_price_str = rows[0]
            lat_date = datetime.strptime(lat_date_str, "%Y-%m-%d").date()
            lat_price = float(lat_price_str) if lat_price_str else 0.0

            if (date.today() - lat_date).days > 90: return lat_price, None, lat_date
            if len(rows) < 2: return lat_price, 'single', lat_date

            prev_date_str = rows[1][0]
            prev_date = datetime.strptime(prev_date_str, "%Y-%m-%d").date()

            sec_table = next((s for s, names in self.sector_data.items() if symbol in names), None)
            if not sec_table: return lat_price, None, lat_date

            with sqlite3.connect(DB_PATH, timeout=60.0) as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT price FROM "{sec_table}" WHERE name=? AND date=?', (symbol, lat_date.isoformat()))
                r1 = cur.fetchone()
                cur.execute(f'SELECT price FROM "{sec_table}" WHERE name=? AND date=?', (symbol, prev_date.isoformat()))
                r2 = cur.fetchone()
            
            if not r1 or not r2: return lat_price, None, lat_date
            trend = 'rising' if float(r1[0]) > float(r2[0]) else 'falling'
            return lat_price, trend, lat_date
        except Exception: return None, None, None

    def create_source_symbol_widget(self):
        container = RowWidget(self.source_symbol, self.on_symbol_click)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        btn = self.create_symbol_button(self.source_symbol)
        btn.setMinimumHeight(35)

        comp_val = self.compare_data.get(self.source_symbol, "")
        comp_lab = QLabel()
        comp_lab.setFixedWidth(150)
        comp_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_rich_compare_text(comp_lab, comp_val)

        highlight = "#F9A825"
        html_tags = ", ".join([f"{t} <font color='{highlight}'>{float(w):.1f}</font>" if float(w) > 0 else t for t, w in self.source_tags])
        tags_lab = QLabel(f"<div style='font-size:24px;'>{html_tags}</div>")
        tags_lab.setWordWrap(True)
        tags_lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        sinp = QLineEdit()
        sinp.setFixedWidth(200)
        sinp.setFixedHeight(32)
        sinp.setPlaceholderText("输入代码…")
        sinp.returnPressed.connect(self.on_search)
        self.search_input = sinp
        
        for w in (comp_lab, tags_lab): w.installEventFilter(container)
        layout.addWidget(btn, 1)
        layout.addWidget(comp_lab, 1)
        layout.addWidget(tags_lab, 4)
        layout.addStretch()
        layout.addWidget(sinp)
        return container

    def create_similar_symbol_widget(self, sym, matched_tags, all_tags):
        container = RowWidget(sym, self.on_symbol_click)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 2, 0, 2)

        btn = self.create_symbol_button(sym)
        btn.setMinimumHeight(60)

        comp_val = self.compare_data.get(sym, '')
        comp_lab = QLabel()
        comp_lab.setFixedWidth(140)
        comp_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_rich_compare_text(comp_lab, comp_val)

        total_w = round(sum(float(w) for _, w in matched_tags), 1)
        w_lab = QLabel(f"{total_w:.1f}")
        w_lab.setFixedWidth(45)
        w_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_lab.setStyleSheet("font-size:14px; color: #BDBDBD; font-weight: bold;")

        highlight = "#F9A825"
        tag_items = []
        for tag in all_tags:
            w = next((float(w0) for t0, w0 in matched_tags if t0 == tag), 0.0)
            tag_items.append(f"{tag} <font color='{highlight}'>{w:.1f}</font>" if w > 0 else tag)
        
        tags_lab = QLabel(f"<div style='font-size:22px;'>{',   '.join(tag_items)}</div>")
        tags_lab.setWordWrap(True)
        tags_lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        for w in (comp_lab, w_lab, tags_lab): w.installEventFilter(container)
        layout.addWidget(btn, 2)
        layout.addWidget(comp_lab, 3)
        layout.addWidget(w_lab, 1)
        layout.addWidget(tags_lab, 8)
        return container

    def set_rich_compare_text(self, label, text):
        # 从你的样式表中定义颜色
        orange_color = '#CD853F'
        red_color = '#FF5555'
        green_color = '#2ECC71'
        default_color = '#D0D0D0'  # QLabel的默认文字颜色

        date_part_str = ""
        percent_part_html = ""
        
        # 首先查找百分比部分，这有助于我们分割字符串
        percent_match = re.search(r'(-?\d+(?:\.\d+)?)\s*%', text)

        if percent_match:
            # 如果找到百分比，字符串的其余部分就是日期部分
            date_part_str = text[:percent_match.start()].strip()
            percent_value_str = percent_match.group(1)
            percent_full_str = percent_match.group(0)

            # --- 百分比部分的上色逻辑 (保留原始逻辑) ---
            try:
                val = float(percent_value_str)
                percent_color = red_color if val > 0 else green_color if val < 0 else orange_color
                percent_part_html = f"<span style='color:{percent_color};'>{percent_full_str}</span>"
            except ValueError:
                percent_part_html = f"<span>{percent_full_str}</span>" # fallback
        else:
            # 如果没有找到百分比，则整个文本都视为日期部分
            date_part_str = text.strip()

        # --- 新的日期上色逻辑 ---
        date_color = default_color  # 默认为白色
        colored_date_part_html = f"<span>{date_part_str}</span>" # 默认无样式

        # 在日期部分中查找 MMDD前 的格式, 例如 "0128前"
        date_info_match = re.search(r'(\d{2})(\d{2})[前后未]$', date_part_str)
        
        if date_info_match:
            month_str, day_str = date_info_match.groups()
            try:
                # 获取当前年份，并创建日期对象
                current_year = date.today().year
                event_date = date(current_year, int(month_str), int(day_str))
                
                # 获取今天日期的前一天
                comparison_date = date.today() - timedelta(days=1)

                # 如果事件日期 >= 昨天，则使用橙色
                if event_date >= comparison_date:
                    date_color = orange_color
                
                colored_date_part_html = f"<span style='color:{date_color};'>{date_part_str}</span>"

            except ValueError:
                # 如果日期无效 (例如 02月30日), 则回退到旧逻辑，直接显示橙色
                colored_date_part_html = f"<span style='color:{orange_color};'>{date_part_str}</span>"
        else:
            # 如果不匹配 MMDD前 格式 (例如只有"未"或"3天后")，也使用旧逻辑，显示橙色
            colored_date_part_html = f"<span style='color:{orange_color};'>{date_part_str}</span>"


        # --- 组合最终的HTML并设置给Label ---
        final_html = f"{colored_date_part_html}{percent_part_html}"
        label.setText(final_html)

    def create_symbol_button(self, symbol):
        btn = SymbolButton(symbol)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setFixedWidth(90)
        btn.setObjectName("SymbolButton")
        btn.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))
        
        e_price, trend, l_date = self.get_color_decision_data(symbol)
        tip = f"最新财报日期: {l_date.isoformat()}" if l_date else "最新财报日期: 未知"
        btn.setToolTip(f"<div style='font-size:16px; background-color:#FFFFE0; color:black; padding:5px;'>{tip}</div>")
        
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))
        
        color = 'white'
        if e_price is not None and trend is not None:
            if trend == 'single':
                color = 'red' if e_price > 0 else 'green' if e_price < 0 else 'white'
            else:
                pos_p, rise_t = e_price > 0, trend == 'rising'
                if rise_t and pos_p: color = 'red'
                elif not rise_t and pos_p: color = '#008B8B'
                elif rise_t and not pos_p: color = '#912F2F'
                elif not rise_t and not pos_p: color = 'green'
        
        btn.setStyleSheet(f"color: {color};")
        return btn

    # 修改：支持 btn_index 记录当前索引，并传递 callback 给 Chart_input.py
    def on_symbol_click(self, symbol, btn_index=None):
        if btn_index is not None:
            self.current_symbol_index = btn_index
        elif symbol in self.ordered_symbols_on_screen:
            self.current_symbol_index = self.ordered_symbols_on_screen.index(symbol)

        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)
        comp = self.compare_data.get(symbol, "N/A")
        shares, mcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, symbol)
        try:
            plot_financial_data(
                DB_PATH, sector, symbol, comp, (shares, pb), mcap, pe, self.json_data, '1Y', False,
                callback=lambda action: self.handle_chart_callback(symbol, action)
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    # 新增：处理从图表界面传回来的 next/prev 操作
    def handle_chart_callback(self, symbol, action):
        if action in ('next', 'prev'):
            current_idx = self.current_symbol_index
            QTimer.singleShot(50, lambda: self.navigate_to_adjacent_symbol(action, current_idx))

    # 新增：计算上一个/下一个索引并打开图表
    def navigate_to_adjacent_symbol(self, direction, current_idx):
        total_count = len(self.ordered_symbols_on_screen)
        if total_count == 0:
            return

        new_index = current_idx
        if direction == 'next':
            new_index += 1
        elif direction == 'prev':
            new_index -= 1
            
        # 循环模式逻辑
        if new_index >= total_count:
            new_index = 0
        elif new_index < 0:
            new_index = total_count - 1
            
        next_symbol = self.ordered_symbols_on_screen[new_index]
        self.on_symbol_click(next_symbol, btn_index=new_index)

    def show_context_menu(self, symbol):
        menu = QMenu(self)
        move_menu = menu.addMenu("移动")
        for group in ["Must", "Today", "Short"]:
            in_cfg = False
            if group in self.panel_config:
                val = self.panel_config[group]
                in_cfg = (symbol in val)
            act = QAction(group, self)
            act.setEnabled(not in_cfg)
            act.triggered.connect(lambda _, s=symbol, g=group: self.copy_symbol_to_group(s, g))
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
            if item is None: menu.addSeparator()
            else:
                act = QAction(item[0], self)
                act.triggered.connect(item[1])
                menu.addAction(act)
        menu.exec(QCursor.pos())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.text() == '/':
            if hasattr(self, 'search_input'):
                self.search_input.setFocus()
                self.search_input.selectAll()
        else:
            super().keyPressEvent(event)

    def get_stylesheet(self):
        return """
        QMainWindow { background-color: #2E2E2E; }
        QGroupBox {
            font-size: 12px; font-weight: bold; color: #E0E0E0;
            border: 1px solid #555; border-radius: 8px;
            margin-top: 10px; padding: 20px 10px 10px 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 10px; color: #00AEEF; left: 10px;
        }
        QScrollArea { border: none; background-color: transparent; }
        #SymbolButton {
            background-color: #2E2E2E;
            font-size: 18px; font-weight: bold;
            padding: 5px; border-radius: 4px; border: 1px solid #FFFFFF;
        }
        #SymbolButton:hover { background-color: #3A3A3A; }
        QLabel { font-size: 20px; color: #D0D0D0; }
        QLineEdit {
            padding: 4px; border: 1px solid #555; border-radius: 4px;
            background-color: #3A3A3A; color: #E0E0E0; font-size: 14px;
        }
        QLineEdit:focus { border: 1px solid #00AEEF; }
        QToolTip {
            background-color: #3C3C3C; color: #FFFFFF;
            border: 1px solid #C0C0C0; border-radius: 4px;
        }
        QMenu { background-color: #3C3C3C; color: #E0E0E0; border: 1px solid #555; font-size: 14px; }
        QMenu::item { padding: 8px 25px 8px 20px; }
        QMenu::item:selected { background-color: #007ACC; }
        QMenu::item:disabled { color: #777777; }
        QMenu::separator { height: 1px; background: #555; margin: 5px 10px; }
        """

if __name__ == '__main__':
    # 启用高 DPI 支持
    app = QApplication(sys.argv)
    app.setApplicationName("SimilarityViewer")
    
    symbol = None
    if len(sys.argv) > 1:
        symbol = sys.argv[1].strip().upper()
    else:
        pyperclip.copy('')
        if copy2clipboard():
            content = get_clipboard_content()
            symbol = content if content and re.match('^[A-Z.-]+$', content) else get_stock_symbol(content)
        else:
            symbol = get_stock_symbol()

    if not symbol: sys.exit()

    try:
        desc_data = load_json_data(DESCRIPTION_PATH)
        w_groups = load_weight_groups()
        tw_cfg = {tag: w for w, tags in w_groups.items() for tag in tags}
        all_data = {
            "description": desc_data,
            "compare": load_compare_data(COMPARE_DATA_PATH),
            "sectors": load_json_data(SECTORS_ALL_PATH),
            "tags_weight": tw_cfg,
            "panel_config": load_json_data(PANEL_CONFIG_PATH),
            "panel_config_path": PANEL_CONFIG_PATH,
        }
    except Exception as e:
        QMessageBox.critical(None, "数据加载错误", str(e))
        sys.exit(1)

    target_tags = find_tags_by_symbol(symbol, desc_data, tw_cfg)
    if not target_tags:
        QMessageBox.information(None, "未找到", f"找不到符号 '{symbol}' 的标签。")
        sys.exit()

    related = find_symbols_by_tags(target_tags, desc_data)
    main_window = SimilarityViewerWindow(symbol, target_tags, related, all_data)
    main_window.show()
    sys.exit(app.exec())