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
# 0. 引入外部绘图模块 (来自 a.py)
# ==========================================
sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
try:
    from Chart_input import plot_financial_data
except ImportError:
    print("Warning: Could not import 'Chart_input'. Clicking cards will not open charts.")
    # 定义一个空函数防止报错，方便调试 UI
    def plot_financial_data(*args, **kwargs):
        print("Mock: Plotting data...", args)

# ==========================================
# 1. 数据处理层 (Data Handler)
# ==========================================

class DataManager:
    def __init__(self):
        # 文件路径配置
        self.path_csv = r"/Users/yanzhang/Coding/News/Options_Change.csv"
        self.path_db = r"/Users/yanzhang/Coding/Database/Finance.db"
        self.path_txt = r"/Users/yanzhang/Coding/News/backup/Compare_All.txt"
        self.path_json = r"/Users/yanzhang/Coding/Financial_System/Modules/description.json"
        self.path_sectors = r"/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
        
        # 缓存原始数据供绘图使用
        self.full_json_data = {} 
        self.sectors_data = {}

    def load_data(self):
        # 1. 获取基础 Symbol 列表 (CSV)
        if not os.path.exists(self.path_csv):
            return []
        
        try:
            df = pd.read_csv(self.path_csv)
            symbols = df['Symbol'].unique().tolist()
        except Exception as e:
            print(f"CSV Read Error: {e}")
            return []

        # 2. 加载板块数据 (用于绘图查找 Sector)
        if os.path.exists(self.path_sectors):
            try:
                with open(self.path_sectors, 'r', encoding='utf-8') as f:
                    self.sectors_data = json.load(f)
            except Exception as e:
                print(f"Sectors Load Error: {e}")

        # 3. 连接数据库 (SQLite) - 获取更多字段 (shares, pe, pb)
        mnspp_data = {}
        options_data = {}
        
        if os.path.exists(self.path_db):
            try:
                conn = sqlite3.connect(self.path_db)
                cursor = conn.cursor()
                
                # 获取 MNSPP 详细数据
                placeholders = ','.join('?' for _ in symbols)
                # 增加 shares, pe_ratio, pb 字段查询
                sql_mnspp = f"SELECT symbol, marketcap, shares, pe_ratio, pb FROM MNSPP WHERE symbol IN ({placeholders})"
                cursor.execute(sql_mnspp, symbols)
                for row in cursor.fetchall():
                    # row: (symbol, marketcap, shares, pe, pb)
                    mnspp_data[row[0]] = {
                        'marketcap': row[1] if row[1] is not None else 0,
                        'shares': row[2] if row[2] is not None else "N/A",
                        'pe': row[3] if row[3] is not None else "N/A",
                        'pb': row[4] if row[4] is not None else "--"
                    }

                # 获取 Options 数据
                sql_options = f"SELECT name, date, iv, price, change FROM Options WHERE name IN ({placeholders}) ORDER BY date DESC"
                df_opts = pd.read_sql_query(sql_options, conn, params=symbols)
                
                for sym in symbols:
                    sym_opts = df_opts[df_opts['name'] == sym]
                    top2 = sym_opts.head(2).to_dict('records')
                    options_data[sym] = top2
                    
                conn.close()
            except Exception as e:
                print(f"Database Error: {e}")
        
        # 4. 解析文本对比数据 (Text)
        compare_parsed = {}   # 用于排序和提取数值
        compare_raw = {}      # 用于传给绘图函数 (保留原始文本)
        
        if os.path.exists(self.path_txt):
            try:
                with open(self.path_txt, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 提取数值用于逻辑
                    pattern = re.compile(r"^([A-Z0-9\-\.]+):\s*.*?([+\-]?\d+(?:\.\d+)?)%", re.MULTILINE)
                    for sym, val in pattern.findall(content):
                        compare_parsed[sym] = float(val)
                    
                    # 重新读取用于获取原始字符串 (模仿 a.py 的 load_text_data)
                    f.seek(0)
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        if ':' in line:
                            key, value = map(str.strip, line.split(':', 1))
                            cleaned_key = key.split()[-1]
                            # 如果包含逗号，转为元组 (兼容 a.py 逻辑)
                            if ',' in value:
                                compare_raw[cleaned_key] = tuple(p.strip() for p in value.split(','))
                            else:
                                compare_raw[cleaned_key] = value
            except Exception as e:
                print(f"Text Parse Error: {e}")

        # 5. 解析标签 (JSON)
        tags_data = {}
        if os.path.exists(self.path_json):
            try:
                with open(self.path_json, 'r', encoding='utf-8') as f:
                    self.full_json_data = json.load(f) # 保存完整 JSON 供绘图用
                    sources = self.full_json_data.get('stocks', []) + self.full_json_data.get('etfs', [])
                    for item in sources:
                        sym = item.get('symbol')
                        tags = item.get('tag', [])
                        if sym:
                            tags_data[sym] = tags
            except Exception as e:
                print(f"JSON Error: {e}")

        # 6. 整合数据
        final_list = []
        for sym in symbols:
            # MNSPP Info
            m_info = mnspp_data.get(sym, {'marketcap': None, 'shares': "N/A", 'pe': "N/A", 'pb': "--"})
            
            # Options Data
            opts = options_data.get(sym, [])
            while len(opts) < 2:
                opts.append({'iv': None, 'price': 0, 'change': 0})
            
            # Helpers
            def parse_iv(val):
                if not val or not isinstance(val, str): return 0.0
                return float(val.replace('%', '').replace(' ', ''))
            
            iv1 = parse_iv(opts[0]['iv'])
            iv2 = parse_iv(opts[1]['iv'])
            
            sum1 = (opts[0]['price'] or 0) + (opts[0]['change'] or 0)
            sum2 = (opts[1]['price'] or 0) + (opts[1]['change'] or 0)
            
            comp_val = compare_parsed.get(sym, 0.0)
            raw_comp = compare_raw.get(sym, "N/A")
            
            tags = tags_data.get(sym, [])
            
            final_list.append({
                'symbol': sym,
                'marketcap': m_info['marketcap'],
                'shares': m_info['shares'],
                'pe': m_info['pe'],
                'pb': m_info['pb'],
                'iv1': iv1,
                'iv2': iv2,
                'compare': comp_val,
                'raw_compare': raw_comp,
                'sum1': sum1,
                'sum2': sum2,
                'tags': tags
            })

        # 7. 排序
        def sort_key(item):
            mcap = item['marketcap']
            if mcap is None:
                return (0, item['symbol'])
            else:
                return (1, -mcap)
        
        final_list.sort(key=sort_key)
        return final_list

# ==========================================
# 2. 界面展示层 (UI - PyQt6)
# ==========================================

class StockCard(QFrame):
    # 定义点击信号，传递数据字典
    clicked = pyqtSignal(dict)

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.init_ui()
        # 设置鼠标手型，提示可点击
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
    def mousePressEvent(self, event):
        # 响应鼠标左键点击
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(event)

    def init_ui(self):
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # --- Symbol ---
        lbl_symbol = QLabel(self.data['symbol'])
        lbl_symbol.setObjectName("SymbolLabel")
        lbl_symbol.setFixedWidth(80)
        layout.addWidget(lbl_symbol)
        
        # --- Data Area ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        # Row 1: Numbers
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
        
        # Row 2: Tags
        tags_text = "  ".join([f"#{t}" for t in self.data['tags']])
        lbl_tags = QLabel(tags_text if tags_text else "No Tags")
        lbl_tags.setObjectName("TagsLabel")
        lbl_tags.setWordWrap(True)
        right_layout.addWidget(lbl_tags)
        
        layout.addWidget(right_widget, 1)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Market Analyzer Pro")
        self.resize(1000, 700)
        
        # 初始化数据管理器
        self.data_manager = DataManager()
        
        # UI Setup
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

    def load_and_render(self):
        data_list = self.data_manager.load_data()
        
        # Clear old items (except stretch)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for item_data in data_list:
            card = StockCard(item_data)
            # 连接点击信号到处理函数
            card.clicked.connect(self.on_card_clicked)
            # 插入到 stretch 之前
            self.list_layout.insertWidget(self.list_layout.count()-1, card)

    def on_card_clicked(self, data):
        """处理卡片点击，调用外部绘图函数"""
        symbol = data['symbol']
        print(f"Opening chart for {symbol}...")
        
        # 1. 查找 Sector (从加载的数据中)
        sector = next((k for k, v in self.data_manager.sectors_data.items() if symbol in v), None)
        
        # 2. 准备参数
        # 对应: plot_financial_data(DB_PATH, sector, value, compare_value, (shares, pb), marketcap, pe, json_data, '1Y', False)
        
        db_path = self.data_manager.path_db
        compare_val = data['raw_compare']
        shares_val = data['shares']
        pb_val = data['pb']
        marketcap_val = data['marketcap']
        pe_val = data['pe']
        json_content = self.data_manager.full_json_data
        
        # 3. 调用绘图
        try:
            plot_financial_data(
                db_path, 
                sector, 
                symbol, 
                compare_val, 
                (shares_val, pb_val), 
                marketcap_val, 
                pe_val, 
                json_content, 
                '1Y', 
                False
            )
        except Exception as e:
            print(f"Error invoking plot_financial_data: {e}")

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QScrollArea { background-color: transparent; }
            QWidget { background-color: transparent; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            #Header { font-size: 24px; font-weight: bold; color: #ffffff; margin-bottom: 15px; }
            #Card { background-color: #2d2d2d; border-radius: 10px; border: 1px solid #3d3d3d; }
            #Card:hover { background-color: #353535; border: 1px solid #505050; }
            #SymbolLabel { font-size: 22px; font-weight: 900; color: #ffffff; }
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
