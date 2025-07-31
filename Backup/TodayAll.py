import sqlite3
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime, timedelta

def query_database(db_file, table_name):
    # 获取今天的日期
    now = datetime.now()
    # 获取前一天的日期
    yesterday = now - timedelta(days=1)
    # 格式化输出
    today_date = yesterday.strftime('%Y-%m-%d')

    # 连接到 SQLite 数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 执行查询，使用参数化的表名
    query = f"SELECT * FROM {table_name} WHERE date = '{today_date}';"
    cursor.execute(query)
    
    # 获取查询结果
    rows = cursor.fetchall()
    if not rows:
        return "今天没有数据可显示。\n"

    # 获取列名，并确定每列的最大宽度
    columns = [description[0] for description in cursor.description]
    col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]
    
    # 准备输出的文本
    output_text = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
    output_text += '-' * len(output_text) + '\n'
    for row in rows:
        output_text += ' | '.join([str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)]) + '\n'
    
    # 关闭连接
    conn.close()
    return output_text

def create_window(content):
    # 创建主窗口
    root = tk.Tk()
    root.title("数据库查询结果")

    # 窗口尺寸和位置设置
    window_width = 800  # 窗口宽度
    window_height = 600  # 窗口高度（原来高度的两倍）
    screen_width = root.winfo_screenwidth()  # 屏幕宽度
    screen_height = root.winfo_screenheight()  # 屏幕高度
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # 按ESC键关闭窗口
    root.bind('<Escape>', lambda e: root.destroy())
    
    # 创建带滚动条的文本区域
    text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=30)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    
    # 插入文本内容
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')  # 禁止编辑文本内容
    
    # 运行窗口
    root.mainloop()

if __name__ == '__main__':
    # 数据库文件和表名的列表
    db_info = [
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Economics'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'ETFs'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Indices'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Currencies'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Commodities'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Crypto'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Bonds'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Financial_Services'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Energy'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Consumer_Defensive'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Technology'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Healthcare'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Consumer_Cyclical'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Industrials'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Basic_Materials'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Real_Estate'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Utilities'},
        {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Communication_Services'},
    ]
    
    # 遍历数据库信息列表，对每个数据库执行查询并收集结果
    full_content = ""
    for info in db_info:
        full_content += f"Querying table {info['table']} in database at: {info['path']}\n"
        result = query_database(info['path'], info['table'])
        full_content += result + "\n" + "-"*50 + "\n"
    
    # 创建并显示结果窗口
    create_window(full_content)