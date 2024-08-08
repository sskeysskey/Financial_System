import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
from datetime import datetime

def query_database(db_file, table_name, condition, fields, include_condition):
    # 获取今天的日期
    today_date = datetime.now().strftime('%Y-%m-%d')

    # 连接到 SQLite 数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 根据 include_condition 决定是否添加 WHERE 条件
    if include_condition and condition:
        query = f"SELECT {fields} FROM {table_name} WHERE {condition} ORDER BY date DESC;"
    else:
        query = f"SELECT {fields} FROM {table_name} ORDER BY DATE DESC;"
    
    cursor.execute(query)
    
    # 获取查询结果
    rows = cursor.fetchall()
    if not rows:
        return "没有数据可显示。\n"

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
    root.lift()
    root.focus_force()

    # 窗口尺寸和位置设置
    window_width = 900
    window_height = 600
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # 按ESC键关闭窗口
    root.bind('<Escape>', lambda e: root.destroy())
    
    # 创建带滚动条的文本区域
    text_font = tkFont.Font(family="Courier", size=20)
    text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=30, font=text_font)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    
    # 插入文本内容
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')
    
    # 运行窗口
    root.mainloop()

if __name__ == '__main__':
    db_info = [
        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Economics',
        #  'condition': "name = 'USInflation'", 'fields': '*',
        #  'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Analysis.db', 'table': 'High_low',
        #   'condition': "name = 'Energy'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Indices',
        #   'condition': "name = 'Nikkei'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies',
        #   'condition': "name = 'CNYTHB'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities',
        #     'condition': "name = 'Zinc'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto',
        #   'condition': "name = 'Solana'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Bonds',
        #   'condition': "name = 'US10Y'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'ETFs',
        #   'condition': "name = 'SCO'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Basic_Materials',
        #     'condition': "name = 'CTA-PB'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Communication_Services',
        #     'condition': "id = '284897'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Consumer_Cyclical',
        #     'condition': "name = 'VVV'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Consumer_Defensive',
        #     'condition': "name = 'WMT'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Energy',
        #     'condition': "name = 'VVV'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Financial_Services',
        #     'condition': "name = 'STEP'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Healthcare',
        #     'condition': "name = 'INSM'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Industrials',
        #     'condition': "name = 'GNRC'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Real_Estate',
        #     'condition': "name = ''", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Technology',
        #     'condition': "name = 'SATS'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Technology',
        #   'condition': "id = 779743", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Utilities',
        #     'condition': "name = ''", 'fields': '*',
        # 'include_condition': True},
    ]
    
    # 遍历数据库信息列表，对每个数据库执行查询并收集结果
    full_content = ""
    for info in db_info:
        full_content += f"Querying table {info['table']} in database at: {info['path']}\n"
        result = query_database(info['path'], info['table'], info['condition'], info['fields'], info['include_condition'])
        full_content += result + "\n" + "-"*50+"\n"
    # 创建窗口展示查询结果
    create_window(full_content)