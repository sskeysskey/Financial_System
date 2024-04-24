import sqlite3
import tkinter as tk
from datetime import datetime
import tkinter.font as tkFont
from tkinter import scrolledtext

def get_user_input_custom(root, prompt):
    # 创建一个新的顶层窗口
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    # 设置窗口大小和位置
    window_width = 280
    window_height = 90
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 3 - window_height / 2)  # 将窗口位置提升到屏幕1/3高度处
    input_dialog.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # 添加输入框，设置较大的字体和垂直填充
    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)  # 增加内部垂直填充
    entry.focus_set()

    # 设置确认按钮，点击后销毁窗口并返回输入内容
    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()

    # 绑定回车键和ESC键
    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())

    # 运行窗口，等待用户输入
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input

def query_database(db_file, table_name, condition):
    today_date = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
    cursor.execute(query)
    rows = cursor.fetchall()
    if not rows:
        return "今天没有数据可显示。\n"
    columns = [description[0] for description in cursor.description]
    col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]
    output_text = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
    output_text += '-' * len(output_text) + '\n'
    for row in rows:
        output_text += ' | '.join([str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)]) + '\n'
    conn.close()
    return output_text

def create_window(parent, content):
    # 创建Toplevel窗口
    top = tk.Toplevel(parent)
    top.title("数据库查询结果")
    window_width = 900
    window_height = 600
    screen_width = top.winfo_screenwidth()
    screen_height = top.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    top.bind('<Escape>', close_app)  # 绑定ESC到关闭程序的函数
    text_font = tkFont.Font(family="Courier", size=20)
    text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')

def close_app(event=None):
    root.destroy()  # 使用destroy来确保彻底关闭所有窗口和退出

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    root.bind('<Escape>', close_app)  # 同样绑定ESC到关闭程序的函数

    # 定义数据库信息的字典
    database_info = {
        'StocksDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks'},
        'CryptoDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto'},
        'CurrencyDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies'},
        'CommodityDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'},
        'BondsDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Bonds'},
    }

    # 将数据库信息键映射到一组关键字
    database_mapping = {
        'StocksDB': {'NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX'},
        'CryptoDB': {"Bitcoin", "Ether", "Binance", "Bitcoin Cash", "Solana", "Monero", "Litecoin"},
        'CurrencyDB': {'DXY', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHY', 'USDINR', 'USDBRL', 'USDRUB', 'USDKRW', 'USDTRY', 'USDSGD', 'USDHKD'},
        'CommodityDB': {'Crude Oil', 'Brent', 'Natural gas', 'Coal', 'Uranium', 'Gold', 'Silver', 'Copper', 'Steel', 'Iron Ore', 'Lithium', 'Soybeans', 'Wheat', 'Lumber', 'Palm Oil', 'Rubber', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Canola', 'Corn', 'Bitumen', 'Cobalt', 'Lead', 'Aluminum', 'Nickel', 'Tin', 'Zinc', 'Lean Hogs', 'Beef', 'Poultry', 'Salmon'},
        'BondsDB': {'United States', 'United Kingdom', 'Japan', 'Russia', 'Brazil', 'India', 'Turkey'},
    }

    # 反向映射，从关键字到数据库信息键
    reverse_mapping = {}
    for db_key, keywords in database_mapping.items():
        for keyword in keywords:
            reverse_mapping[keyword] = db_key

    # 获取用户输入
    prompt = "请输入关键字查询数据库:"
    value = get_user_input_custom(root, prompt)

    # 使用反向映射表查询数据库信息
    if value and value in reverse_mapping:
        db_key = reverse_mapping[value]
        db_info = database_info[db_key]
        condition = f"name = '{value}'"
        result = query_database(db_info['path'], db_info['table'], condition)
        create_window(root, result)
    else:
        print("输入值无效或未配置数据库信息。程序退出。")
        close_app()

    root.mainloop()  # 主事件循环