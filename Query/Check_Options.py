import sys
import os
import sqlite3
import json
import re
import pandas as pd
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 0. 关键修改: 引入 holidays 库 ---
try:
    import holidays
except ImportError:
    print("错误：未找到 holidays 模块。请运行: pip install holidays")
    sys.exit(1)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QScrollArea, QFrame, QLineEdit, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor

# 0. 引入外部绘图模块
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
try:
    from Chart_input import plot_financial_data
except ImportError:
    print("Warning: Could not import 'Chart_input'. Clicking cards will not open charts.")
    def plot_financial_data(*args, **kwargs):
        print("Mock: Plotting data...", args)

# --- 新增: 交易日计算工具类 ---
class TradingDateHelper:
    """
    使用 holidays 库自动计算美股(NYSE)交易日。
    """
    @staticmethod
    def get_last_trading_date(base_date=None):
        """
        获取相对于 base_date (默认今天) 的最近一个有效交易日字符串 (YYYY-MM-DD)。
        """
        if base_date is None:
            base_date = datetime.date.today()
        
        # 获取 NYSE 专属日历 (自动处理周末补休规则)
        nyse_holidays = holidays.NYSE()
        
        # 从"昨天"开始找 (因为今天是盘中或还没开盘，通常看的是昨收)
        target_date = base_date - datetime.timedelta(days=1)
        
        while True:
            # 1. 检查周末 (5=Sat, 6=Sun)
            if target_date.weekday() >= 5:
                target_date -= datetime.timedelta(days=1)
                continue
            
            # 2. 检查 NYSE 节假日
            if target_date in nyse_holidays:
                target_date -= datetime.timedelta(days=1)
                continue
                
            # 找到交易日
            return target_date.strftime("%Y-%m-%d")

# 1. 数据处理层 (Data Handler)
class DataManager:
    def __init__(self):
        self.path_csv = os.path.join(BASE_CODING_DIR, "News", "Options_Change.csv")
        self.path_db = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
        self.path_txt = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
        self.path_json = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
        self.path_sectors = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
        
        self.full_json_data = {} 
        self.sectors_data = {}

    def load_data(self):
        if not os.path.exists(self.path_csv): return []
        
        try:
            df = pd.read_csv(self.path_csv)
            symbols = df['Symbol'].unique().tolist()
        except Exception: return []

        if os.path.exists(self.path_sectors):
            try:
                with open(self.path_sectors, 'r', encoding='utf-8') as f:
                    self.sectors_data = json.load(f)
            except Exception: pass

        mnspp_data = {}
        options_data = {}
        
        if os.path.exists(self.path_db):
            try:
                conn = sqlite3.connect(self.path_db)
                cursor = conn.cursor()
                placeholders = ','.join('?' for _ in symbols)
                
                sql_mnspp = f"SELECT symbol, marketcap, shares, pe_ratio, pb FROM MNSPP WHERE symbol IN ({placeholders})"
                cursor.execute(sql_mnspp, symbols)
                for row in cursor.fetchall():
                    mnspp_data[row[0]] = {
                        'marketcap': row[1] if row[1] is not None else 0,
                        'shares': row[2] if row[2] is not None else "N/A",
                        'pe': row[3] if row[3] is not None else "N/A",
                        'pb': row[4] if row[4] is not None else "--"
                    }

                sql_options = f"SELECT name, date, iv, price, change FROM Options WHERE name IN ({placeholders}) ORDER BY date DESC"
                df_opts = pd.read_sql_query(sql_options, conn, params=symbols)
                
                for sym in symbols:
                    sym_opts = df_opts[df_opts['name'] == sym]
                    top2 = sym_opts.head(2).to_dict('records')
                    options_data[sym] = top2
                    
                conn.close()
            except Exception: pass
        
        compare_parsed = {}
        compare_raw = {}
        if os.path.exists(self.path_txt):
            try:
                with open(self.path_txt, 'r', encoding='utf-8') as f:
                    content = f.read()
                    pattern = re.compile(r"^([A-Z0-9\-\.]+):\s*.*?([+\-]?\d+(?:\.\d+)?)%", re.MULTILINE)
                    for sym, val in pattern.findall(content):
                        compare_parsed[sym] = float(val)
                    
                    f.seek(0)
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        if ':' in line:
                            key, value = map(str.strip, line.split(':', 1))
                            cleaned_key = key.split()[-1]
                            if ',' in value:
                                compare_raw[cleaned_key] = tuple(p.strip() for p in value.split(','))
                            else:
                                compare_raw[cleaned_key] = value
            except Exception: pass

        tags_data = {}
        if os.path.exists(self.path_json):
            try:
                with open(self.path_json, 'r', encoding='utf-8') as f:
                    self.full_json_data = json.load(f)
                    sources = self.full_json_data.get('stocks', []) + self.full_json_data.get('etfs', [])
                    for item in sources:
                        if item.get('symbol'):
                            tags_data[item.get('symbol')] = item.get('tag', [])
            except Exception: pass

        # --- 核心修改：计算理论上的最近交易日 ---
        target_date_str = TradingDateHelper.get_last_trading_date()
        # print(f"理论最近交易日: {target_date_str}") # Debug用

        final_list = []
        for sym in symbols:
            m_info = mnspp_data.get(sym, {'marketcap': None, 'shares': "N/A", 'pe': "N/A", 'pb': "--"})
            
            # 获取数据库里的原始数据
            raw_opts = options_data.get(sym, [])
            
            # --- 核心修改：日期校验与过滤 ---
            valid_opts = []
            
            # 1. 检查第一条数据（最新数据）是否匹配理论日期
            if len(raw_opts) > 0:
                latest_data = raw_opts[0]
                db_date = latest_data['date'] # 假设格式为 YYYY-MM-DD
                
                if db_date == target_date_str:
                    # 日期匹配，视为有效数据
                    valid_opts = raw_opts
                else:
                    # 日期不匹配（数据过期或缺失），视为无数据
                    # 你也可以选择保留 valid_opts = []，或者填充空值
                    valid_opts = [] 
            
            # 填充空数据以防列表越界 (保持原有的 while 逻辑，但针对 valid_opts)
            while len(valid_opts) < 2: 
                valid_opts.append({'iv': None, 'price': 0, 'change': 0})
            
            def parse_iv(val):
                return float(val.replace('%', '').replace(' ', '')) if (val and isinstance(val, str)) else 0.0
            
            final_list.append({
                'symbol': sym,
                'marketcap': m_info['marketcap'],
                'shares': m_info['shares'],
                'pe': m_info['pe'],
                'pb': m_info['pb'],
                # 使用经过校验的 valid_opts
                'iv1': parse_iv(valid_opts[0]['iv']),
                'iv2': parse_iv(valid_opts[1]['iv']),
                'sum1': (valid_opts[0]['price'] or 0) + (valid_opts[0]['change'] or 0),
                'sum2': (valid_opts[1]['price'] or 0) + (valid_opts[1]['change'] or 0),
                'compare': compare_parsed.get(sym, 0.0),
                'raw_compare': compare_raw.get(sym, "N/A"),
                'tags': tags_data.get(sym, [])
            })

        def sort_key(item):
            return (0, item['symbol']) if item['marketcap'] is None else (1, -item['marketcap'])
        
        final_list.sort(key=sort_key)
        return final_list

# ==========================================
# 2. 界面展示层 (UI - PyQt6)
# ==========================================

class StockCard(QFrame):
    clicked = pyqtSignal(dict)
    
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.init_ui()
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
    def set_highlight(self, active: bool):
        if active:
            self.setProperty("highlighted", "true")
        else:
            self.setProperty("highlighted", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(event)

    def init_ui(self):
        self.setObjectName("Card")
        self.setProperty("highlighted", "false")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # --- 左侧：Symbol ---
        lbl_symbol = QLabel(self.data['symbol'])
        lbl_symbol.setObjectName("SymbolLabel")
        lbl_symbol.setFixedWidth(80)
        lbl_symbol.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_symbol.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        layout.addWidget(lbl_symbol)
        
        # --- 右侧：数据区域 ---
        right_widget = QWidget()
        right_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        row1 = QHBoxLayout()
        row1.setSpacing(15)
        
        def create_value_label(val, role='primary', is_percent=False):
            # 处理 NaN: 无论是 None 还是 0.0 (如果被解析失败)
            # 在 load_data 里的逻辑是：如果 valid_opts 为空，iv 解析为 0.0
            # 我们可以简单判断：如果 val 为 0.0 且 role 是 primary (iv1)，则可能表示无数据
            # 或者更严谨地，利用 pandas isna
            
            display_txt = "--"
            has_data = False
            
            if not pd.isna(val):
                # 这里有个小技巧：如果数据无效，我们在 load_data 里填的是 0 或 None
                # 对于 IV 来说，0.0 也是可能的，但极少。为了界面整洁，如果完全校验失败，
                # load_data 里的 iv1 会是 0.0 (parse_iv 默认值)
                # 我们可以根据 iv1 是否为 0.0 来决定是否显示颜色
                
                # 如果是百分比模式且值为 0，有可能是无数据，也有可能是真的0
                # 暂时按正常数值处理
                display_txt = f"{val:.2f}%" if is_percent else f"{val:.2f}"
                has_data = True
            
            lbl = QLabel(display_txt)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            color = "#DDDDDD" 
            if has_data:
                # 简单的 0 值判断可能不够完美，但够用了
                if val > 0.001: # 稍微给个阈值
                    if role == 'secondary': color = "#E57373"
                    else: color = "#FF4500"
                elif val < -0.001:
                    if role == 'secondary': color = "#81C784"
                    else: color = "#00FA9A"
            
            font_size = "14px"
            font_weight = "bold"
            extra_style = ""
            
            if role == 'primary':
                font_size = "20px"
                font_weight = "900"
            elif role == 'compare':
                extra_style = "background-color: #2c3e50; border-radius: 4px; padding: 4px;"
            
            style = f"color: {color}; font-weight: {font_weight}; font-size: {font_size}; {extra_style}"
            lbl.setStyleSheet(style)
            return lbl

        # 1. Latest IV
        row1.addWidget(create_value_label(self.data['iv1'], role='primary', is_percent=True))
        # 2. 2nd Latest IV
        row1.addWidget(create_value_label(self.data['iv2'], role='secondary', is_percent=True))
        # 3. Compare
        row1.addWidget(create_value_label(self.data['compare'], role='compare', is_percent=True))
        # 4. 2nd Latest Sum
        row1.addWidget(create_value_label(self.data['sum2'], role='secondary'))
        # 5. Latest Sum
        row1.addWidget(create_value_label(self.data['sum1'], role='primary'))
        
        row1.addStretch()
        right_layout.addLayout(row1)
        
        # Tags
        tags_text = "  ".join([str(t) for t in self.data['tags']])
        lbl_tags = QLabel(tags_text if tags_text else "No Tags")
        lbl_tags.setObjectName("TagsLabel")
        lbl_tags.setWordWrap(True)
        right_layout.addWidget(lbl_tags)
        
        layout.addWidget(right_widget, 1)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Market Analyzer Pro")
        self.resize(1000, 1000) 
        self.center()
        
        self.data_manager = DataManager()
        self.cards_map = {}
        self.last_highlighted_card = None

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        header = QLabel("Stock Options Monitor")
        header.setObjectName("Header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Symbol (e.g. AAPL)...")
        self.search_input.setObjectName("SearchInput")
        self.search_input.returnPressed.connect(self.perform_search)
        
        search_btn = QPushButton("Search")
        search_btn.setObjectName("SearchButton")
        search_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        search_btn.clicked.connect(self.perform_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        main_layout.addLayout(search_layout)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        main_layout.addWidget(self.scroll)
        
        self.load_and_render()
        self.apply_styles()

    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            super().keyPressEvent(event)

    def load_and_render(self):
        data_list = self.data_manager.load_data()
        self.cards_map.clear()
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        for item_data in data_list:
            card = StockCard(item_data)
            card.clicked.connect(self.on_card_clicked)
            self.cards_map[item_data['symbol'].upper()] = card
            self.list_layout.insertWidget(self.list_layout.count()-1, card)

    def perform_search(self):
        search_text = self.search_input.text().strip().upper()
        if not search_text: return
        
        if search_text in self.cards_map:
            target_card = self.cards_map[search_text]
            if self.last_highlighted_card:
                self.last_highlighted_card.set_highlight(False)
            self.scroll.ensureWidgetVisible(target_card, 50, 50)
            target_card.set_highlight(True)
            self.last_highlighted_card = target_card
        else:
            print(f"Symbol {search_text} not found.")

    def on_card_clicked(self, data):
        symbol = data['symbol']
        print(f"Opening chart for {symbol}...")
        sector = next((k for k, v in self.data_manager.sectors_data.items() if symbol in v), None)
        try:
            plot_financial_data(
                self.data_manager.path_db, 
                sector, 
                symbol, 
                data['raw_compare'], 
                (data['shares'], data['pb']), 
                data['marketcap'], 
                data['pe'], 
                self.data_manager.full_json_data, 
                '1Y', False
            )
        except Exception as e:
            print(f"Chart Error: {e}")

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QScrollArea { background-color: transparent; }
            QWidget { background-color: transparent; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            #Header { font-size: 24px; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
            #SearchInput { 
                background-color: #2d2d2d; 
                border: 1px solid #555; 
                border-radius: 5px; 
                padding: 8px; 
                font-size: 14px; 
                color: white; 
                margin-bottom: 10px;
            }
            #SearchInput:focus { border: 1px solid #0078d7; }
            #SearchButton {
                background-color: #3d3d3d;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px 15px;
                margin-bottom: 10px;
                font-weight: bold;
            }
            #SearchButton:hover { background-color: #505050; }
            #SearchButton:pressed { background-color: #0078d7; }
            #Card { background-color: #2d2d2d; border-radius: 10px; border: 1px solid #3d3d3d; }
            #Card:hover { background-color: #353535; border: 1px solid #505050; }
            #Card[highlighted="true"] { 
                background-color: #3d3d3d; 
                border: 2px solid #0078d7; 
            }
            #SymbolLabel { font-size: 22px; font-weight: 900; color: #ffffff; selection-background-color: #0078d7; selection-color: #ffffff; }
            #TagsLabel { font-size: 12px; color: #aaaaaa; font-style: italic; }
            QScrollBar:vertical { border: none; background: #1e1e1e; width: 10px; }
            QScrollBar::handle:vertical { background: #555; min-height: 20px; border-radius: 5px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
