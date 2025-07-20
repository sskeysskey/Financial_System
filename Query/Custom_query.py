import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext

def query_database(db_file, table_name, condition, fields, include_condition):
    # 连接到 SQLite 数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # 先读取一下表结构，拿到所有列名
    cursor.execute(f"PRAGMA table_info({table_name});")
    info = cursor.fetchall()
    col_names = [col[1] for col in info]  # col[1] 是列名

    # 决定 ORDER BY 用哪个字段
    if 'date' in col_names:
        order_col = 'date'
    elif 'changed_at' in col_names:
        order_col = 'changed_at'
    else:
        order_col = 'id'

    # ==================== 新增代码开始 ====================
    # 检查是否需要格式化 changed_at 字段
    # 只有当用户想查询所有字段('*')，并且表中确实存在'changed_at'列时，我们才进行处理
    query_fields = fields
    if fields == '*' and 'changed_at' in col_names:
        field_list = []
        for col in col_names:
            if col == 'changed_at':
                # 对 changed_at 使用 strftime 进行格式化，并转换为本地时间
                # 使用 'AS changed_at' 来保持列名在结果中不变
                field_list.append("strftime('%Y-%m-%d %H:%M:%S', changed_at, 'localtime') AS changed_at")
            else:
                # 其他字段保持原样，加上引号以避免列名是关键字等问题
                field_list.append(f'"{col}"')
        
        # 将字段列表组合成一个字符串，替换掉原来的 '*'
        query_fields = ", ".join(field_list)
    # ==================== 新增代码结束 ====================

    # 生成 SQL (注意这里从 fields 变成了 query_fields)
    if include_condition and condition:
        sql = f"SELECT {query_fields} FROM {table_name} WHERE {condition} ORDER BY {order_col} DESC, id DESC;"
    else:
        sql = f"SELECT {query_fields} FROM {table_name} ORDER BY {order_col} DESC, id DESC;"
    
    # 打印最终执行的SQL语句，方便调试
    print("Executing SQL:", sql)

    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        return "没有数据可显示。\n"

    # header + 宽度对齐
    columns = [d[0] for d in cursor.description]
    col_widths = [max(len(str(r[i])) for r in rows + [columns]) for i in range(len(columns))]

    # 组装文本
    output = ' | '.join(c.ljust(col_widths[idx]) for idx, c in enumerate(columns)) + '\n'
    output += '-' * len(output) + '\n'
    for row in rows:
        output += ' | '.join(str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)) + '\n'

    conn.close()
    return output

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
        #  'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Analysis.db', 'table': 'High_low',
        #   'condition': "name = 'Energy'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Indices',
        #   'condition': "name = 'Nikkei'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies',
        #   'condition': "name = 'EURUSD'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities',
        #     'condition': "name = 'Rice'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto',
        #   'condition': "name = 'Solana'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Bonds',
        #   'condition': "name = 'US10Y'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'ETFs',
        #   'condition': "id = '2263847'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Basic_Materials',
        #     'condition': "name = 'CTA-PB'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Communication_Services',
        #     'condition': "id = '284897'", 'fields': '*',
        # 'include_condition': False},

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
        #     'condition': "name = 'TRU'", 'fields': '*',
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

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Earning',
        #     'condition': "name = 'WAL'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Downloads/Finance.db', 'table': 'Earning',
        #     'condition': "name = 'WAL'", 'fields': '*',
        # 'include_condition': True},

        # {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'sync_log',
        #     'condition': "table_name = 'Earning'", 'fields': '*',
        # 'include_condition': False},

        # {'path': '/Users/yanzhang/Downloads/Finance.db', 'table': 'MNSPP',
        #     'condition': "name = 'WAL'", 'fields': '*',
        # 'include_condition': False},
    ]
    
    # 遍历数据库信息列表，对每个数据库执行查询并收集结果
    full_content = ""
    for info in db_info:
        full_content += f"Querying table {info['table']} in database at: {info['path']}\n"
        result = query_database(info['path'], info['table'], info['condition'], info['fields'], info['include_condition'])
        full_content += result + "\n" + "-"*50+"\n"
    # 创建窗口展示查询结果
    create_window(full_content)