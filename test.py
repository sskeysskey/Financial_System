import sys
import os
import sqlite3
import json
import re
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont

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

    def load_data(self):
        # 1. 获取基础 Symbol 列表 (CSV)
        if not os.path.exists(self.path_csv):
            print(f"Error: File not found {self.path_csv}")
            return []
        
        try:
            df = pd.read_csv(self.path_csv)
            # 假设 csv 第一列是 Symbol，如果不是请调整
            symbols = df['Symbol'].unique().tolist()
        except Exception as e:
            print(f"CSV Read Error: {e}")
            return []

        # 2. 连接数据库 (SQLite)
        market_caps = {}
        options_data = {}
        
        if os.path.exists(self.path_db):
            try:
                conn = sqlite3.connect(self.path_db)
                cursor = conn.cursor()
                
                # 获取 MarketCap
                # 构造 WHERE IN 查询
                placeholders = ','.join('?' for _ in symbols)
                sql_mnspp = f"SELECT symbol, marketcap FROM MNSPP WHERE symbol IN ({placeholders})"
                cursor.execute(sql_mnspp, symbols)
                for row in cursor.fetchall():
                    # row: (symbol, marketcap)
                    market_caps[row[0]] = row[1] if row[1] is not None else 0

                # 获取 Options 数据 (IV, Price, Change)
                # 为每个 Symbol 获取按日期倒序的前两条记录
                # 优化：在 Python 中处理分组比在 SQL 中写复杂 Window 函数兼容性更好
                sql_options = f"SELECT name, date, iv, price, change FROM Options WHERE name IN ({placeholders}) ORDER BY date DESC"
                df_opts = pd.read_sql_query(sql_options, conn, params=symbols)
                
                for sym in symbols:
                    # 筛选该 Symbol 的数据
                    sym_opts = df_opts[df_opts['name'] == sym]
                    # df 已按 date DESC 排序，直接取前两行
                    top2 = sym_opts.head(2).to_dict('records')
                    options_data[sym] = top2
                    
                conn.close()
            except Exception as e:
                print(f"Database Error: {e}")
        
        # 3. 解析文本对比数据 (Text)
        compare_data = {}
        if os.path.exists(self.path_txt):
            try:
                with open(self.path_txt, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 正则匹配：Symbol: (中间任意字符) 数字%
                    # 例子: DOW: 29前3.81%* -> 提取 3.81
                    # 例子: GFI: -0.23%- -> 提取 -0.23
                    pattern = re.compile(r"^([A-Z0-9\-\.]+):\s*.*?([+\-]?\d+(?:\.\d+)?)%", re.MULTILINE)
                    matches = pattern.findall(content)
                    for sym, val in matches:
                        compare_data[sym] = float(val)
            except Exception as e:
                print(f"Text Parse Error: {e}")

        # 4. 解析标签 (JSON)
        tags_data = {}
        if os.path.exists(self.path_json):
            try:
                with open(self.path_json, 'r', encoding='utf-8') as f:
                    jdata = json.load(f)
                    # 遍历 stocks 和 etfs (如果有)
                    sources = jdata.get('stocks', []) + jdata.get('etfs', [])
                    for item in sources:
                        sym = item.get('symbol')
                        tags = item.get('tag', [])
                        if sym:
                            tags_data[sym] = tags
            except Exception as e:
                print(f"JSON Error: {e}")

        # 5. 整合数据
        final_list = []
        for sym in symbols:
            # Market Cap (用于排序)
            mcap = market_caps.get(sym, None) # None 表示未找到
            
            # Options Data
            opts = options_data.get(sym, [])
            # 补齐数据，确保有2个条目
            while len(opts) < 2:
                opts.append({'iv': None, 'price': 0, 'change': 0})
            
            # 处理 IV (转浮点)
            def parse_iv(val):
                if not val or not isinstance(val, str): return 0.0
                return float(val.replace('%', '').replace(' ', ''))
            
            iv1 = parse_iv(opts[0]['iv'])
            iv2 = parse_iv(opts[1]['iv'])
            
            # 处理 Sum (Change + Price)
            sum1 = (opts[0]['price'] or 0) + (opts[0]['change'] or 0)
            sum2 = (opts[1]['price'] or 0) + (opts[1]['change'] or 0)
            
            # Compare Data
            comp_val = compare_data.get(sym, 0.0) # 默认为0
            
            # Tags
            tags = tags_data.get(sym, [])
            
            final_list.append({
                'symbol': sym,
                'marketcap': mcap,
                'iv1': iv1,
                'iv2': iv2,
                'compare': comp_val,
                'sum1': sum1,
                'sum2': sum2,
                'tags': tags
            })

        # 6. 排序逻辑
        # 规则：如果有 marketcap，按大小倒序；如果没有，排在最前面，内部按 A-Z 排序。
        # 我们可以构造一个 tuple key: (is_valid_mcap, value_for_sort)
        # Python 排序默认是升序 (Small -> Large)
        # Group 0: No Mcap (排最前) -> key: (0, symbol_asc)
        # Group 1: Has Mcap (排后面) -> key: (1, -marketcap) (负号使其变为降序)
        
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
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.init_ui()
        
    def init_ui(self):
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # --- 左侧：Symbol ---
        lbl_symbol = QLabel(self.data['symbol'])
        lbl_symbol.setObjectName("SymbolLabel")
        lbl_symbol.setFixedWidth(80) # 固定宽度对齐
        layout.addWidget(lbl_symbol)
        
        # --- 右侧：数据区域 (两行) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        # 第一行：5个数字
        row1 = QHBoxLayout()
        row1.setSpacing(15)
        
        # 辅助函数：创建彩色数值 Label
        def create_value_label(val, is_percent=False, is_compare=False):
            txt = f"{val:.2f}%" if is_percent else f"{val:.2f}"
            lbl = QLabel(txt)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 颜色逻辑：正红负绿 (Stock Market Style)
            # 背景逻辑：如果是 compare 且为特殊样式
            
            color = "#FF4500" if val > 0 else "#00FA9A" if val < 0 else "#DDDDDD"
            
            style = f"color: {color}; font-weight: bold; font-size: 14px;"
            if is_compare:
                # Compare 特殊样式：蓝色背景，保持文字颜色或者反白
                style += "background-color: #2c3e50; border-radius: 4px; padding: 4px;"
                
            lbl.setStyleSheet(style)
            return lbl

        # 1. Latest IV
        row1.addWidget(create_value_label(self.data['iv1'], is_percent=True))
        # 2. 2nd Latest IV
        row1.addWidget(create_value_label(self.data['iv2'], is_percent=True))
        # 3. Compare (Special Style)
        row1.addWidget(create_value_label(self.data['compare'], is_percent=True, is_compare=True))
        # 4. Latest Sum
        row1.addWidget(create_value_label(self.data['sum1']))
        # 5. 2nd Latest Sum
        row1.addWidget(create_value_label(self.data['sum2']))
        
        row1.addStretch() # 向左对齐
        right_layout.addLayout(row1)
        
        # 第二行：Tags
        tags_text = "  ".join([f"#{t}" for t in self.data['tags']])
        lbl_tags = QLabel(tags_text if tags_text else "No Tags")
        lbl_tags.setObjectName("TagsLabel")
        lbl_tags.setWordWrap(True)
        right_layout.addWidget(lbl_tags)
        
        layout.addWidget(right_widget, 1) # 右侧占用剩余空间

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Market Analyzer Pro")
        self.resize(1000, 700)
        
        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 标题栏
        header = QLabel("Stock Options Monitor")
        header.setObjectName("Header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # 列表容器
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch() # 确保内容从上往下堆叠
        
        scroll.setWidget(self.list_container)
        main_layout.addWidget(scroll)
        
        # 加载数据
        self.load_data()
        
        # 设置样式
        self.apply_styles()

    def load_data(self):
        manager = DataManager()
        data_list = manager.load_data()
        
        # 清除旧的 stretch
        item = self.list_layout.takeAt(self.list_layout.count() - 1)
        if item:
            del item
            
        for item_data in data_list:
            card = StockCard(item_data)
            self.list_layout.addWidget(card)
            
        self.list_layout.addStretch()

    def apply_styles(self):
        # 现代深色主题 QSS
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QScrollArea {
                background-color: transparent;
            }
            QWidget {
                background-color: transparent;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            #Header {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                margin-bottom: 15px;
            }
            #Card {
                background-color: #2d2d2d;
                border-radius: 10px;
                border: 1px solid #3d3d3d;
            }
            #Card:hover {
                background-color: #353535;
                border: 1px solid #505050;
            }
            #SymbolLabel {
                font-size: 22px;
                font-weight: 900;
                color: #ffffff;
            }
            #TagsLabel {
                font-size: 12px;
                color: #aaaaaa;
                font-style: italic;
            }
            /* 滚动条美化 */
            QScrollBar:vertical {
                border: none;
                background: #1e1e1e;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
