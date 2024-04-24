import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
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

def execute_query(cursor, query, params):
    """ 执行SQL查询并处理异常 """
    try:
        cursor.execute(query, params)
        return cursor.fetchall(), None
    except sqlite3.DatabaseError as e:
        return None, f"SQL执行错误: {e}"

def get_price_comparison(cursor, table_name, months_back, index_name, today):
    # 使用 dateutil.relativedelta 计算过去的日期
    past_date = today - relativedelta(months=months_back)
    end_date = today - timedelta(days=1)
    
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), index_name))
    result = cursor.fetchone()
    return result if result else (None, None)

def compare_today_yesterday(cursor, table_name, index_name, output, today):
    yesterday = today - timedelta(days=1)
    query = f"""
    SELECT date, price FROM {table_name} 
    WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
    """
    results, error = execute_query(cursor, query, (index_name, today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")))
    if error:
        output.append(error)
        return

    if len(results) == 2:
        today_price = results[0][1]
        yesterday_price = results[1][1]
        change = today_price - yesterday_price
        percentage_change = (change / yesterday_price) * 100

        if change > 0:
            output.append(f"{index_name}: -> {today_price} 比昨天涨了 {abs(percentage_change):.2f}%。")
        elif change < 0:
            output.append(f"{index_name}: -> {today_price} 比昨天跌了 {abs(percentage_change):.2f}%。")
        else:
            output.append(f"{index_name}: -> {today_price} 与昨天持平。")
    elif len(results) == 1:
        result_date = results[0][0]
        if result_date == today.strftime("%Y-%m-%d"):
            output.append(f"{index_name}: 仅找到今天的数据，无法比较。")
        else:
            output.append(f"{index_name}: 仅找到昨天的数据，无法比较。")
    else:
        output.append(f"{index_name}: 没有找到今天和昨天的数据。")

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
    clickable_font = tkFont.Font(family='Courier', size=20, weight='bold')  # 可点击项的字体
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

    # 解析内容并为每个index_name创建一个可点击的Label
    for line in content.split('\n'):
        if ':' in line:
            index_name, message = line.split(':', 1)
            lbl = tk.Label(scrollable_frame, text=index_name, fg="orange", cursor="hand2", font=clickable_font)
            lbl.pack(anchor='w')
            lbl.bind("<Button-1>", lambda e, idx=index_name: show_message(idx))
            tk.Label(scrollable_frame, text=':' + message, font=text_font).pack(anchor='w')
        else:
            tk.Label(scrollable_frame, text=line, font=text_font).pack(anchor='w')

    container.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

def show_message(index_name):
    """调用 name2chart.py 中的函数以显示财务数据图表"""
    plot_financial_data(index_name)

def quit_app(event=None):
    root.destroy()

def main():
    today = datetime.now()
    output = []  # 用于收集输出信息的列表
    databases = [
        {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks', 'names': ('NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX')},
        {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto', 'names': ('Bitcoin', 'Ether', 'Solana')},
        {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies', 'names': ('DXY', 'CNYEUR', 'USDJPY', 'USDCNY', 'CNYJPY', 'USDARS')},
        {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities', 'names': ('Brent', 'Natural gas', 'Uranium', 'Gold', 'Silver', 'Copper', 'Lithium', 'Soybeans', 'Wheat', 'Cocoa', 'Rice', 'Nickel')}
    ]
    intervals = [600, 360, 240, 120, 60, 24, 12, 6, 3]  # 以月份表示的时间间隔列表
    
    for db_config in databases:
        db_path = db_config['path']
        table_name = db_config['table']
        index_names = db_config['names']
        
        with create_connection(db_path) as conn:
            cursor = conn.cursor()
        
            for index_name in index_names:
                compare_today_yesterday(cursor, table_name, index_name, output, today)
                today_price_query = f"SELECT price FROM {table_name} WHERE date = ? AND name = ?"
                cursor.execute(today_price_query, (datetime.now().strftime("%Y-%m-%d"), index_name))
                result = cursor.fetchone()

                if result:
                    today_price = result[0]
                else:
                    output.append(f"没有找到今天的{index_name}价格。")
                    continue
                
                price_extremes = {}
                for months in intervals:
                    max_price, min_price = get_price_comparison(cursor, table_name, months, index_name, today)
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
                                    output.append(f"创了 {years} 年来的新高！！")
                                else:
                                    output.append(f"创了 {months} 个月来的新高！！")
                            else:  # today_price == max_price
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"逼平 {years} 年来的新高！！")
                                else:
                                    output.append(f"逼平 {months} 个月来的新高！！")
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
                                    output.append(f"{index_name} 创了 {years} 年来的新低！！！")
                                else:
                                    output.append(f"{index_name} 创了 {months} 个月来的新低！！！")
                            else:  # today_price == min_price
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"与 {years} 年来的最低值撞衫！！")
                                else:
                                    output.append(f"与 {months} 个月来的最低值撞衫！！")
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
    create_window(None, final_output)  # 假设没有父窗口

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    main()            # 先运行main函数，确保所有GUI组件都已经初始化
    root.mainloop()   # 启动事件循环，这行代码会在所有窗口关闭后执行结束