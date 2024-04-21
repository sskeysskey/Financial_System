import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
from datetime import datetime, timedelta

def create_connection(db_file):
    """ 创建到SQLite数据库的连接 """
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Exception as e:
        print(e)
        return None

def get_price_comparison(cursor, table_name, months_back, index_name, today):
    past_date = today - timedelta(days=30 * months_back)  # 使用月份计算过去的时间
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
    cursor.execute(query, (index_name, today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")))
    results = cursor.fetchall()

    if len(results) == 2:
        today_price = results[0][1]
        yesterday_price = results[1][1]
        change = today_price - yesterday_price
        percentage_change = (change / yesterday_price) * 100

        if change > 0:
            output.append(f"{index_name}: 比昨天涨了 {abs(percentage_change):.2f}%。")
        elif change < 0:
            output.append(f"{index_name}: 比昨天跌了 {abs(percentage_change):.2f}%。")
        else:
            output.append(f"{index_name}: 与昨天持平。")
    elif len(results) == 1:
        output.append(f"{index_name}: 仅找到昨天的数据，无法比较。")
    else:
        output.append(f"{index_name}: 没有找到今天和昨天的数据。")

def create_window(parent, content):
    top = tk.Toplevel(parent)
    top.bind('<Escape>', quit_app)  # 在新创建的窗口上也绑定 ESC 键

    # 定义字体、窗口设置等
    text_font = tkFont.Font(family='Courier', size=18, weight='bold')  # 你可以根据需要调整字体样式和大小

    # 窗口居中显示，先计算居中位置再显示窗口内容
    top.update_idletasks()  # 更新窗口状态
    w = top.winfo_screenwidth()  # 获取屏幕宽度
    h = top.winfo_screenheight()  # 获取屏幕高度
    size = (800, 600)  # 假设或计算所需窗口大小
    x = w/2 - size[0]/2
    y = h/2 - size[1]/2
    top.geometry("%dx%d+%d+%d" % (size[0], size[1], x, y))

    # 创建文本区域并显示内容
    text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=50, height=30, font=text_font)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')

def quit_app(event=None):
    root.destroy()

def main():
    today = datetime.now()
    output = []  # 用于收集输出信息的列表
    databases = [
        {'path': '/Users/yanzhang/Stocks.db', 'table': 'Stocks', 'names': ('NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX')},
        {'path': '/Users/yanzhang/Crypto.db', 'table': 'Crypto', 'names': ('Bitcoin', 'Ether', 'Binance', 'Bitcoin Cash', 'Solana', 'Monero', 'Litecoin')}
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

                # 检查最高价格
                found_max = False
                for months in intervals:
                    if found_max:
                        break
                    max_price, _ = get_price_comparison(cursor, table_name, months, index_name, today)
                    if max_price and today_price > max_price:
                        if months >= 12:
                            years = months // 12
                            output.append(f"创了 {years} 年来的新高！！")
                        else:
                            output.append(f"创了 {months} 个月来的新高！！")
                        found_max = True

                if not found_max:
                    close_max = False
                    for months in intervals:
                        if close_max:
                            break
                        max_price, _ = get_price_comparison(cursor, table_name, months, index_name, today)
                        diff_ratio = (max_price - today_price) / max_price * 100
                        abs_diff_ratio = abs(diff_ratio)
                        if abs_diff_ratio <= 3:
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

                # 检查最低价格
                found_min = False
                for months in intervals:
                    if found_min:
                        break
                    _, min_price = get_price_comparison(cursor, table_name, months, index_name, today)
                    if min_price and today_price < min_price:
                        if months >= 12:
                            years = months // 12
                            output.append(f"{index_name} 创了 {years} 年来的新低！！！")
                        else:
                            output.append(f"{index_name} 创了 {months} 个月来的新低！！！")
                        found_min = True

                if not found_min:
                    close_min = False
                    for months in intervals:
                        if close_min:
                            break
                        _, min_price = get_price_comparison(cursor, table_name, months, index_name, today)
                        diff_ratio = (today_price - min_price) / min_price * 100
                        abs_diff_ratio = abs(diff_ratio)
                        if abs_diff_ratio <= 3:
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
            # conn.close()
    final_output = "\n".join(output)
    create_window(None, final_output)  # 假设没有父窗口

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    main()            # 先运行main函数，确保所有GUI组件都已经初始化
    root.mainloop()   # 启动事件循环，这行代码会在所有窗口关闭后执行结束