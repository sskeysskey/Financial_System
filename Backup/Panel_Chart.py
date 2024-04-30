import sqlite3
import tkinter as tk
import matplotlib.pyplot as plt
from datetime import datetime

def create_selection_window(root, database_mapping):
    selection_window = tk.Toplevel(root)
    selection_window.title("选择查询关键字")
    selection_window.geometry("1080x500")
    selection_window.bind('<Escape>', lambda e: close_app(root))  # 绑定ESC到关闭程序的函数

    # 创建一个滚动条
    canvas = tk.Canvas(selection_window)
    scrollbar = tk.Scrollbar(selection_window, orient="horizontal", command=canvas.xview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        )
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(xscrollcommand=scrollbar.set)

    # 为每个数据库类别创建一个LabelFrame横向排列
    for db_key, keywords in database_mapping.items():
        frame = tk.LabelFrame(scrollable_frame, text=db_key, padx=10, pady=10)
        frame.pack(side="left", padx=15, pady=10, fill="both", expand=True)
        for keyword in sorted(keywords):
            button = tk.Button(frame, text=keyword, command=lambda k=keyword: on_keyword_selected(k, selection_window))
            button.pack(side="top", fill="x", padx=5, pady=2)

    canvas.pack(side="top", fill="both", expand=True)
    scrollbar.pack(side="bottom", fill="x")

def on_keyword_selected(value, parent_window):
    db_key = reverse_mapping[value]
    db_info = database_info[db_key]
    condition = f"name = '{value}'"
    result = query_db2chart(db_info['path'], db_info['table'], condition, parent_window)

def query_db2chart(path, table, condition, parent_window):
    # 连接数据库
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    query = f"""
    SELECT date, price
    FROM {table}
    WHERE {condition}
    ORDER BY date;
    """
    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()
    conn.close()

    if not data:
        print("No data found.")
        return

    dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
    prices = [row[1] for row in data]

    plt.figure(figsize=(10, 5))
    plt.plot(dates, prices, marker='o', linestyle='-', color='b')
    plt.title(f'Price Over Time for {condition}')
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    def on_key(event):
        if event.key == 'escape':
            plt.close()
            parent_window.focus_set()  # 使选择窗口获得焦点，以便可以捕获 ESC 键

    plt.gcf().canvas.mpl_connect('key_press_event', on_key)
    plt.show()

def close_app(root):
    root.quit()
    root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    database_info = {
        'CommodityDB1': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities'},
        'CommodityDB2': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities'},
        'CommodityDB3': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities'},
        'StocksDB': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Stocks'},
        'CryptoDB': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto'},
        'CurrencyDB': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies'}
    }

    database_mapping = {
        'CommodityDB3': {'Soybeans', 'Wheat', 'Lumber', 'Palm Oil', 'Rubber', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Canola','Corn'},
        'CommodityDB2': {'Bitumen', 'Cobalt', 'Lead', 'Aluminum', 'Nickel', 'Tin', 'Zinc', 'Lean Hogs', 'Beef', 'Poultry', 'Salmon'},
        'CommodityDB1': {'Crude Oil', 'Brent', 'Natural gas', 'Coal', 'Uranium', 'Gold', 'Silver', 'Copper', 'Steel', 'Iron Ore', 'Lithium'},
        'CurrencyDB': {'DXY', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHY', 'USDINR', 'USDBRL', 'USDRUB', 'USDKRW', 'USDTRY', 'USDSGD', 'USDHKD'},
        'CryptoDB': {"Bitcoin", "Ether", "Binance", "Bitcoin Cash", "Solana", "Monero", "Litecoin"},
        'StocksDB': {'NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX'}
    }

    reverse_mapping = {}
    for db, keywords in database_mapping.items():
        for keyword in keywords:
            reverse_mapping[keyword] = db

    create_selection_window(root, database_mapping)
    root.mainloop()