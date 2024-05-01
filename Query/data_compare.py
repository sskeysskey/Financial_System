import sys
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from name2chart import plot_financial_data

def create_connection(db_file):
    """ 创建到SQLite数据库的连接 """
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        error_msg = f"数据库连接失败: {e}"
        print(error_msg)
        return None, error_msg

def get_price_comparison(cursor, table_name, months_back, name, today):
    # 使用 dateutil.relativedelta 计算过去的日期
    yesterday = today - timedelta(days=1)
    day_of_week = yesterday.weekday()  # 周一为0，周日为6

    if day_of_week == 5:  # 昨天是周六
        yesterday = today - timedelta(days=2)  # 取周五
    elif day_of_week == 6:  # 昨天是周日
        yesterday = today - timedelta(days=3)  # 取上周五

    past_date = yesterday - relativedelta(months=months_back)
    
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d"), name))
    result = cursor.fetchone()
    return result if result else (None, None)

def execute_query(cursor, query, params):
    """ 执行SQL查询并处理异常 """
    try:
        cursor.execute(query, params)
        return cursor.fetchall(), None
    except sqlite3.DatabaseError as e:
        return None, f"SQL执行错误: {e}"

def compare_today_yesterday(cursor, table_name, name, output, today):
    yesterday = today - timedelta(days=1)
    # 判断昨天是周几
    day_of_week = yesterday.weekday()  # 周一为0，周日为6

    if day_of_week == 0:  # 昨天是周一
        ex_yesterday = today - timedelta(days=4)  # 取上周六
    elif day_of_week == 5:  # 昨天是周六
        yesterday = today - timedelta(days=2)  # 取周五
        ex_yesterday = yesterday  - timedelta(days=1)
    elif day_of_week == 6:  # 昨天是周日
        yesterday = today - timedelta(days=3)  # 取上周五
        ex_yesterday = yesterday  - timedelta(days=1) #取上周四
    else:
        ex_yesterday = yesterday  - timedelta(days=1)

    query = f"""
    SELECT date, price FROM {table_name} 
    WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
    """
    results, error = execute_query(cursor, query, (name, yesterday.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d")))
    if error:
        output.append(error)
        return

    if len(results) == 2:
        yesterday_price = results[0][1]
        ex_yesterday_price = results[1][1]
        change = yesterday_price - ex_yesterday_price
        percentage_change = (change / ex_yesterday_price) * 100

        if change > 0:
            output.append(f"{name}:今天 {yesterday_price} 比昨天涨了 {abs(percentage_change):.2f}%。")
        elif change < 0:
            output.append(f"{name}:今天 {yesterday_price} 比昨天跌了 {abs(percentage_change):.2f}%。")
        else:
            output.append(f"{name}:今天 {yesterday_price} 与昨天持平。")

        # 检查是否浮动超过10%
        if abs(percentage_change) > 10:
            output.append("#浮动超过10%，查一下是什么原因！")

    elif len(results) == 1:
        result_date = results[0][0]
        result_price = results[0][1]  # 提取价格
        if result_date == yesterday.strftime("%Y-%m-%d"):
            output.append(f"{name}:仅找到今天的数据{result_price}，无法比较。")
        else:
            output.append(f"{name}:仅找到昨天的数据{result_price}，无法比较。")
    else:
        output.append(f"{name}:没有找到今天和昨天的数据。")

def create_window(parent, content):
    top = tk.Toplevel(parent)
    top.bind('<Escape>', quit_app)  # 在新创建的窗口上也绑定 ESC 键

    # 更新窗口状态以获取准确的屏幕尺寸
    # top.update_idletasks()
    # w = top.winfo_screenwidth()  # 获取屏幕宽度
    # h = top.winfo_screenheight()  # 获取屏幕高度
    # size = (800, 600)  # 定义窗口大小
    # x = w - size[0]  # 窗口右边缘与屏幕右边缘对齐
    # y = h - size[1] - 30 # 窗口下边缘与屏幕下边缘对齐
    # 设置窗口出现在屏幕右下角
    # top.geometry("%dx%d+%d+%d" % (size[0], size[1], x, y))

    # 更新窗口状态以获取准确的屏幕尺寸
    top.update_idletasks()
    w = top.winfo_screenwidth()  # 获取屏幕宽度
    h = top.winfo_screenheight()  # 获取屏幕高度
    size = (800, 800)  # 定义窗口大小
    x = (w // 2) - (size[0] // 2)  # 计算窗口左上角横坐标
    y = (h // 2) - (size[1] // 2)  # 计算窗口左上角纵坐标
    # 设置窗口出现在屏幕中央
    top.geometry("%dx%d+%d+%d" % (size[0], size[1], x, y))

    # 定义字体
    clickable_font = tkFont.Font(family='Courier', size=23, weight='bold')  # 可点击项的字体
    text_font = tkFont.Font(family='Courier', size=20)  # 文本项的字体

    # 创建滚动文本区域，但不直接插入文本，而是插入带有点击事件的Label
    container = tk.Canvas(top)
    scrollbar = tk.Scrollbar(top, command=container.yview)
    scrollable_frame = tk.Frame(container)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: container.configure(
            scrollregion=container.bbox("all")
        )
    )

    container.create_window((0, 0), window=scrollable_frame, anchor="nw")
    container.configure(yscrollcommand=scrollbar.set)

    # 解析内容并为每个name创建一个可点击的Label
    for line in content.split('\n'):
        if ':' in line:
            name, message = line.split(':', 1)
            lbl = tk.Label(scrollable_frame, text=name, fg="gold", cursor="hand2", font=clickable_font)
            lbl.pack(anchor='w')
            lbl.bind("<Button-1>", lambda e, idx=name: show_grapher(idx))
            tk.Label(scrollable_frame, text=message, font=text_font).pack(anchor='w')
        elif '#' in line:
            line = line.replace('#', '')
            tk.Label(scrollable_frame, text=line, fg="red", font=text_font).pack(anchor='w')
        elif '@' in line:
            line = line.replace('@', '')
            tk.Label(scrollable_frame, text=line, fg="orange", font=text_font).pack(anchor='w')
        else:
            tk.Label(scrollable_frame, text=line, font=text_font).pack(anchor='w')

    container.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

def show_grapher(name):
    """调用 name2chart.py 中的函数以显示财务数据图表"""
    plot_financial_data(name)

def quit_app(event=None):
    root.destroy()

def main():
    today = datetime.now()
    day_of_week = today.weekday()  # 周一为0，周日为6
    if day_of_week == 0:  # 昨天是周一
        real_today = today - timedelta(days=3)  # 取上周六
    elif day_of_week == 6:  # 昨天是周日
        real_today = today - timedelta(days=2)  # 取上周五
    else:
        real_today = today - timedelta(days=1)

    output = []  # 用于收集输出信息的列表
    databases = [
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Stocks', 'names': ('NASDAQ Composite', 'S&P 500',
            'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX', 'Russell 2000',
            'CBOE Volatility Index')},
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto', 'names': ('Bitcoin', 'Ether', 'Solana')},
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies', 'names': ('DXY', 'EURCNY', 'GBPCNY',
            'USDJPY', 'USDCNY', 'CNYJPY', 'USDARS')},
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities', 'names': ('Brent',
            'Natural gas', 'Uranium', 'Gold', 'Silver', 'Copper', 'Lithium', 'Soybeans', 'Wheat', 'Cocoa', 'Rice', 'Nickel')},
    ]
    intervals = [600, 360, 240, 120, 60, 24, 12, 6, 3]  # 以月份表示的时间间隔列表
    
    for db_config in databases:
        db_path = db_config['path']
        table_name = db_config['table']
        names = db_config['names']
        
        with create_connection(db_path) as conn:
            cursor = conn.cursor()
        
            for name in names:
                compare_today_yesterday(cursor, table_name, name, output, today)
                today_price_query = f"SELECT price FROM {table_name} WHERE date = ? AND name = ?"
                cursor.execute(today_price_query, (real_today.strftime("%Y-%m-%d"), name))
                result = cursor.fetchone()

                if result:
                    today_price = result[0]
                else:
                    output.append(f"没有找到今天的{name}价格。")
                    continue
                
                price_extremes = {}
                for months in intervals:
                    max_price, min_price = get_price_comparison(cursor, table_name, months, name, today)
                    price_extremes[months] = (max_price, min_price)  # 存储最大和最小价格

                # 检查是否接近最高价格
                found_max = False
                close_max = False
                for months in intervals:
                    if found_max or close_max:
                        break
                    max_price, _ = price_extremes.get(months, (None, None))
                    if max_price is not None:
                        diff_ratio = (max_price - today_price) / max_price * 100
                        abs_diff_ratio = abs(diff_ratio)
                        if today_price >= max_price:
                            found_max = True
                            if today_price > max_price:
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"@创了 {years} 年来的新高！！")
                                else:
                                    output.append(f"@创了 {months} 个月来的新高！！")
                            else:  # today_price == max_price
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"@逼平 {years} 年来的新高！！")
                                else:
                                    output.append(f"@逼平 {months} 个月来的新高！！")
                        elif abs_diff_ratio <= 3:
                            if abs_diff_ratio <= 1:
                                difference_desc = "仅仅差"
                            elif abs_diff_ratio <= 2:
                                difference_desc = "仅差"
                            else:
                                difference_desc = "差"
                            if months >= 12:
                                years = months // 12
                                output.append(f"距 {years} 年来的最高价 {max_price} {difference_desc} {diff_ratio:.2f}%")
                            else:
                                output.append(f"距 {months} 个月来的最高价 {max_price} {difference_desc} {diff_ratio:.2f}%")
                            close_max = True

                # 同样的逻辑适用于最低价格检查
                found_min = False
                close_min = False
                for months in intervals:
                    if found_min or close_min:
                        break
                    _, min_price = price_extremes.get(months, (None, None))
                    if min_price is not None:
                        diff_ratio = (today_price - min_price) / min_price * 100
                        abs_diff_ratio = abs(diff_ratio)
                        if today_price <= min_price:
                            found_min = True
                            if today_price < min_price:
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"@创了 {years} 年来的新低！！！")
                                else:
                                    output.append(f"@创了 {months} 个月来的新低！！！")
                            else:  # today_price == min_price
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"@与 {years} 年来的最低值撞衫！！")
                                else:
                                    output.append(f"@与 {months} 个月来的最低值撞衫！！")
                        elif abs_diff_ratio <= 3:
                            if abs_diff_ratio <= 1:
                                difference_desc = "仅仅差"
                            elif abs_diff_ratio <= 2:
                                difference_desc = "仅差"
                            else:
                                difference_desc = "差"
                            if months >= 12:
                                years = months // 12
                                output.append(f"距 {years} 年来的最低价 {min_price} {difference_desc} {diff_ratio:.2f}%")
                            else:
                                output.append(f"距 {months} 个月来的最低价 {min_price} {difference_desc} {diff_ratio:.2f}%")
                            close_min = True

                output.append(f"\n")
            cursor.close()
    final_output = "\n".join(output)
    # 将输出保存到文件
    path = '/Users/yanzhang/Documents/News/'  # 您可以修改这个路径到您想要保存的目录
    filename = 'financial_output.txt'
    file_path = path + filename
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(final_output)
    print(f"文件已保存到 {file_path}")

    create_window(None, final_output)  # 假设没有父窗口

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    main()            # 先运行main函数，确保所有GUI组件都已经初始化
    root.mainloop()   # 启动事件循环，这行代码会在所有窗口关闭后执行结束