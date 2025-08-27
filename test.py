import sys
import os
import json
import sqlite3
import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
                             QVBoxLayout, QWidget, QHeaderView)
from PyQt5.QtCore import QTimer, Qt, QTime
from PyQt5.QtGui import QColor

# --- 用户配置区 ---
# 请将这里的路径替换为您自己的真实文件路径
PANEL_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
SECTORS_ALL_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
DATABASE_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

# --- 时间与计算配置区 (方便测试) ---
# 您可以在这里修改时间来测试程序效果，无需等到真实开盘时间
MARKET_OPEN_HOUR = 21       # 真实开盘小时 (24小时制)
MARKET_OPEN_MINUTE = 30     # 真实开盘分钟
MARKET_CLOSE_HOUR = 4       # 真实收盘小时
MARKET_CLOSE_MINUTE = 00     # 真实收盘分钟

# 重要提示：如果修改了开关盘时间，建议手动更新下面的总分钟数以保证逻辑正确。
# 默认值 390 是从 21:30 到次日 04:00 的总分钟数 (6.5小时 * 60分钟/小时)。
# 如果您只是为了临时测试，不修改此值也可以，但最终数值可能无法在收盘时恰好等于总量。
TOTAL_TRADING_MINUTES = 390 

# --- 辅助函数：用于创建虚拟文件和数据（如果真实文件不存在） ---
def create_dummy_files_if_not_exist():
    """
    检查所需文件是否存在，如果不存在，则创建用于测试的虚拟文件和数据。
    在实际使用中，您可以注释掉或删除此函数的调用。
    """
    if not os.path.exists(PANEL_JSON_PATH):
        print(f"警告：找不到文件 {PANEL_JSON_PATH}。正在创建虚拟文件...")
        os.makedirs(os.path.dirname(PANEL_JSON_PATH), exist_ok=True)
        dummy_panel = {
            "Today": {
                "DT": "",
                "AAPL": ""
            }
        }
        with open(PANEL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(dummy_panel, f, ensure_ascii=False, indent=4)

    if not os.path.exists(SECTORS_ALL_JSON_PATH):
        print(f"警告：找不到文件 {SECTORS_ALL_JSON_PATH}。正在创建虚拟文件...")
        os.makedirs(os.path.dirname(SECTORS_ALL_JSON_PATH), exist_ok=True)
        dummy_sectors_all = {
            "Technology": ["AAPL", "DT", "MSFT"],
            "Energy": ["XOM"]
        }
        with open(SECTORS_ALL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(dummy_sectors_all, f, ensure_ascii=False, indent=4)

    if not os.path.exists(DATABASE_PATH):
        print(f"警告：找不到数据库 {DATABASE_PATH}。正在创建虚拟数据库...")
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # 创建 Technology 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Technology (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                name TEXT,
                price REAL,
                volume INTEGER
            )
        ''')
        
        # 插入虚拟数据
        # DT: volume涨, price跌
        cursor.execute("INSERT INTO Technology (date, name, price, volume) VALUES ('2025-08-25', 'DT', 52.50, 1000000)")
        cursor.execute("INSERT INTO Technology (date, name, price, volume) VALUES ('2025-08-26', 'DT', 51.80, 1200000)") # 最新
        
        # AAPL: volume跌, price涨
        cursor.execute("INSERT INTO Technology (date, name, price, volume) VALUES ('2025-08-25', 'AAPL', 180.00, 60000000)")
        cursor.execute("INSERT INTO Technology (date, name, price, volume) VALUES ('2025-08-26', 'AAPL', 182.50, 55000000)") # 最新

        conn.commit()
        conn.close()

# --- 数据处理核心函数 ---
def load_and_prepare_data():
    """
    从JSON和SQLite加载数据，并进行所有必要的计算。
    """
    try:
        with open(PANEL_JSON_PATH, 'r', encoding='utf-8') as f:
            sectors_panel = json.load(f)
        with open(SECTORS_ALL_JSON_PATH, 'r', encoding='utf-8') as f:
            sectors_all = json.load(f)
    except FileNotFoundError as e:
        print(f"错误：无法加载JSON文件 - {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件格式错误 - {e}")
        return []

    # 1. 获取 "Today" 分组的 symbols
    today_symbols = list(sectors_panel.get('Today', {}).keys())
    if not today_symbols:
        print("信息：'Today' 分组中没有找到任何股票代码。")
        return []

    # 2. 创建 symbol -> table_name 的映射以便快速查找
    symbol_to_table_map = {}
    for table_name, symbols_in_table in sectors_all.items():
        for symbol in symbols_in_table:
            symbol_to_table_map[symbol] = table_name

    # 3. 连接数据库并为每个 symbol 获取和计算数据
    processed_data = []
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
    except sqlite3.Error as e:
        print(f"错误：无法连接到数据库 - {e}")
        return []

    for symbol in today_symbols:
        table_name = symbol_to_table_map.get(symbol)
        if not table_name:
            print(f"警告：在 Sectors_All.json 中找不到股票代码 '{symbol}' 的分组信息，已跳过。")
            continue

        # 4. 查询最近两次的数据
        # 使用 [] 替换表名是不安全的，但由于表名来自我们控制的json文件，风险较低。
        # 正常情况下应验证表名。
        query = f"SELECT price, volume FROM \"{table_name}\" WHERE name = ? ORDER BY date DESC LIMIT 2"
        cursor.execute(query, (symbol,))
        rows = cursor.fetchall()

        if len(rows) < 2:
            print(f"警告：股票代码 '{symbol}' 在表 '{table_name}' 中的数据不足两条，无法进行比较。")
            continue

        latest_price, latest_volume = rows[0]
        previous_price, previous_volume = rows[1]

        if previous_price == 0:
            print(f"警告：'{symbol}' 的前一天价格为0，无法计算涨跌幅。")
            continue
        
        volume_is_up = latest_volume > previous_volume
        price_change_percent = ((latest_price - previous_price) / previous_price) * 100
        price_is_up = price_change_percent > 0

        # 6. 根据您的规则判断操作建议
        # | 第二列(vol) | 第四列(price) | 第五列(advice) |
        # |-------------|---------------|----------------|
        # | 涨 (Up)     | 跌 (Down)     | 必须跌         |
        # | 跌 (Down)   | 跌 (Down)     | 必须涨         |
        # | 跌 (Down)   | 涨 (Up)       | 必须跌         |
        # | 涨 (Up)     | 涨 (Up)       | 必须涨         |
        advice = ""
        if volume_is_up and not price_is_up:
            advice = "跌"
        elif not volume_is_up and not price_is_up:
            advice = "涨"
        elif not volume_is_up and price_is_up:
            advice = "跌"
        elif volume_is_up and price_is_up:
            advice = "涨"

        processed_data.append({
            "symbol": symbol,
            "latest_volume": latest_volume,
            "volume_is_up": volume_is_up,
            "price_change_percent": price_change_percent,
            "price_is_up": price_is_up,
            "advice": advice
        })

    conn.close()
    return processed_data

# --- PyQt5 主窗口类 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("股票实时监控面板 (单位: 万股)")
        self.setGeometry(100, 100, 900, 400)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.table = QTableWidget()
        self.layout.addWidget(self.table)
        
        self.data = []

        self.setup_ui()
        self.populate_table()
        self.setup_timer()

    def setup_ui(self):
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "代码", "最新成交量", "实时预估 (每分钟)", "价格涨跌幅", "操作建议"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers) # 禁止编辑

    def populate_table(self):
        self.data = load_and_prepare_data()
        self.table.setRowCount(len(self.data))

        red_color = QColor("red")
        green_color = QColor("green")

        for row_index, stock_data in enumerate(self.data):
            # Column 1: Symbol
            self.table.setItem(row_index, 0, QTableWidgetItem(stock_data["symbol"]))

            # Column 2: Latest Volume
            volume_item = QTableWidgetItem(f"{stock_data['latest_volume']:,}")
            volume_item.setForeground(red_color if stock_data["volume_is_up"] else green_color)
            volume_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, 1, volume_item)

            # --- 修改点 1 ---
            # 将初始值设为 "0.0万股" 以保持格式统一
            live_item = QTableWidgetItem("0.0万股")
            live_item.setData(Qt.UserRole, stock_data['latest_volume'])
            live_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, 2, live_item)

            price_item = QTableWidgetItem(f"{stock_data['price_change_percent']:+.2f}%")
            price_item.setForeground(red_color if stock_data["price_is_up"] else green_color)
            price_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, 3, price_item)
            
            # Column 5: Advice
            advice_text = stock_data["advice"]
            advice_item = QTableWidgetItem(advice_text)
            
            # --- 修改点：根据建议内容设置字体颜色 ---
            if "涨" in advice_text:
                advice_item.setForeground(red_color)
            elif "跌" in advice_text:
                advice_item.setForeground(green_color)
            
            advice_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, 4, advice_item)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_live_volume)
        # 每10秒更新一次，您可以改为60000毫秒（1分钟）
        self.timer.start(10000) 
        # 立即执行一次以显示初始状态
        self.update_live_volume()

    def update_live_volume(self):
        """由定时器触发，使用顶部的配置变量更新第三列的实时预估成交量"""
        now = datetime.datetime.now()
        
        # 使用顶部的配置变量来定义开关盘时间
        market_open_time = QTime(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
        market_close_time = QTime(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)

        minutes_passed = 0
        is_market_open = False
        
        # 判断时间逻辑，处理跨天情况
        if market_open_time > market_close_time: # 跨天交易，如 21:30 -> 04:00
            if now.time() >= market_open_time or now.time() < market_close_time:
                is_market_open = True
                if now.time() >= market_open_time: # 当天开盘后
                    open_datetime = now.replace(hour=market_open_time.hour(), minute=market_open_time.minute(), second=0, microsecond=0)
                else: # 次日收盘前
                    open_datetime = (now - datetime.timedelta(days=1)).replace(hour=market_open_time.hour(), minute=market_open_time.minute(), second=0, microsecond=0)
                delta = now - open_datetime
                minutes_passed = delta.total_seconds() / 60
        else: # 当天内交易，如 09:30 -> 16:00
            if market_open_time <= now.time() < market_close_time:
                is_market_open = True
                open_datetime = now.replace(hour=market_open_time.hour(), minute=market_open_time.minute(), second=0, microsecond=0)
                delta = now - open_datetime
                minutes_passed = delta.total_seconds() / 60

        # 遍历表格更新第三列
        for row in range(self.table.rowCount()):
            live_item = self.table.item(row, 2)
            if not live_item:
                continue
            
            latest_volume = live_item.data(Qt.UserRole)
            if not latest_volume or TOTAL_TRADING_MINUTES == 0:
                live_item.setText("N/A")
                continue

            display_value = 0
            if is_market_open:
                per_minute_volume = latest_volume / TOTAL_TRADING_MINUTES
                display_value = per_minute_volume * minutes_passed
                display_value = min(display_value, latest_volume) # 确保不超过总量
            elif (market_open_time > market_close_time and market_close_time <= now.time() < market_open_time):
                # 盘后（跨天情况）
                display_value = latest_volume
            elif (market_open_time < market_close_time and (now.time() >= market_close_time or now.time() < market_open_time)):
                 # 盘后（当天情况）
                 display_value = latest_volume

            # --- 修改点 2 ---
            # 将计算出的值除以10000，格式化为带一位小数的字符串，并添加“万股”单位
            value_in_wan = display_value / 10000
            live_item.setText(f"{value_in_wan:.1f}万股")

# --- 主程序入口 ---
if __name__ == '__main__':
    # 检查并创建虚拟文件（如果需要）
    # 在您配置好真实路径后，可以删除或注释掉下面这行
    create_dummy_files_if_not_exist()

    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())