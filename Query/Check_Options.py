import sys
import os
import sqlite3
import json
import re
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor

# ==========================================
# 0. 引入外部绘图模块
# ==========================================
sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
try:
    from Chart_input import plot_financial_data
except ImportError:
    print("Warning: Could not import 'Chart_input'. Clicking cards will not open charts.")
    def plot_financial_data(*args, **kwargs):
        print("Mock: Plotting data...", args)

# ==========================================
# 1. 数据处理层 (Data Handler)
# ==========================================

class DataManager:
    def __init__(self):
        self.path_csv = r"/Users/yanzhang/Coding/News/Options_Change.csv"
        self.path_db = r"/Users/yanzhang/Coding/Database/Finance.db"
        self.path_txt = r"/Users/yanzhang/Coding/News/backup/Compare_All.txt"
        self.path_json = r"/Users/yanzhang/Coding/Financial_System/Modules/description.json"
        self.path_sectors = r"/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
        
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

        final_list = []
        for sym in symbols:
            m_info = mnspp_data.get(sym, {'marketcap': None, 'shares': "N/A", 'pe': "N/A", 'pb': "--"})
            opts = options_data.get(sym, [])
            while len(opts) < 2: opts.append({'iv': None, 'price': 0, 'change': 0})
            
            def parse_iv(val):
                return float(val.replace('%', '').replace(' ', '')) if (val and isinstance(val, str)) else 0.0
            
            final_list.append({
                'symbol': sym,
                'marketcap': m_info['marketcap'],
                'shares': m_info['shares'],
                'pe': m_info['pe'],
                'pb': m_info['pb'],
                'iv1': parse_iv(opts[0]['iv']),
                'iv2': parse_iv(opts[1]['iv']),
                'sum1': (opts[0]['price'] or 0) + (opts[0]['change'] or 0),
                'sum2': (opts[1]['price'] or 0) + (opts[1]['change'] or 0),
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
        # 默认整个 Frame 都是手型光标（提示可点击）
        # 但是 SymbolLabel 上会覆盖这个光标变成 I-Beam
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
    def mousePressEvent(self, event):
        # 只有点击没有被子控件（如 SymbolLabel）消费的区域时，才触发绘图
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(event)

    def init_ui(self):
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # --- 左侧：Symbol (可选中) ---
        lbl_symbol = QLabel(self.data['symbol'])
        lbl_symbol.setObjectName("SymbolLabel")
        lbl_symbol.setFixedWidth(80)
        
        # >>>>> 关键修改：开启鼠标选中 <<<<<
        lbl_symbol.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # 显式设置光标为 IBeam，提示用户这里是选文字的
        lbl_symbol.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        
        layout.addWidget(lbl_symbol)
        
        # --- 右侧：数据区域 ---
        right_widget = QWidget()
        right_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True) # 让右侧点击穿透到 Frame
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        row1 = QHBoxLayout()
        row1.setSpacing(15)
        
        def create_value_label(val, is_percent=False, is_compare=False):
            txt = f"{val:.2f}%" if is_percent else f"{val:.2f}"
            lbl = QLabel(txt)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            color = "#FF4500" if val > 0 else "#00FA9A" if val < 0 else "#DDDDDD"
            style = f"color: {color}; font-weight: bold; font-size: 14px;"
            if is_compare:
                style += "background-color: #2c3e50; border-radius: 4px; padding: 4px;"
            lbl.setStyleSheet(style)
            return lbl

        row1.addWidget(create_value_label(self.data['iv1'], is_percent=True))
        row1.addWidget(create_value_label(self.data['iv2'], is_percent=True))
        row1.addWidget(create_value_label(self.data['compare'], is_percent=True, is_compare=True))
        row1.addWidget(create_value_label(self.data['sum1']))
        row1.addWidget(create_value_label(self.data['sum2']))
        row1.addStretch()
        right_layout.addLayout(row1)
        
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
        
        # >>> 修改1: 增加初始高度到 1000px <<<
        self.resize(1000, 1000) 
        
        # >>> 修改: 调用居中方法 <<<
        self.center()
        
        self.data_manager = DataManager()
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        header = QLabel("Stock Options Monitor")
        header.setObjectName("Header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch()
        scroll.setWidget(self.list_container)
        main_layout.addWidget(scroll)
        
        self.load_and_render()
        self.apply_styles()

    # >>> 新增: 屏幕居中逻辑 <<<
    def center(self):
        # 获取窗口当前的几何形状
        qr = self.frameGeometry()
        # 获取屏幕中心点 (处理多显示器情况，默认 primary)
        cp = self.screen().availableGeometry().center()
        # 将窗口矩形的中心移动到屏幕中心
        qr.moveCenter(cp)
        # 移动窗口左上角到新计算的位置
        self.move(qr.topLeft())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def load_and_render(self):
        data_list = self.data_manager.load_data()
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for item_data in data_list:
            card = StockCard(item_data)
            card.clicked.connect(self.on_card_clicked)
            self.list_layout.insertWidget(self.list_layout.count()-1, card)

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
            #Header { font-size: 24px; font-weight: bold; color: #ffffff; margin-bottom: 15px; }
            #Card { background-color: #2d2d2d; border-radius: 10px; border: 1px solid #3d3d3d; }
            #Card:hover { background-color: #353535; border: 1px solid #505050; }
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
