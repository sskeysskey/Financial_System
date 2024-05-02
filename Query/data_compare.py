import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

@contextmanager
def create_connection(db_file):
    """ 创建到SQLite数据库的连接，并确保正确关闭 """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        yield conn
    except sqlite3.Error as e:
        error_msg = f"数据库连接失败: {e}"
        print(error_msg)
        yield None, error_msg
    finally:
        if conn:
            conn.close()

def get_price_comparison(cursor, table_name, months_back, name, today):
    # 使用 dateutil.relativedelta 计算过去的日期
    yesterday = today - timedelta(days=1)
    day_of_week = yesterday.weekday()  # 周一为0，周日为6

    if day_of_week == 5:  # 昨天是周六
        yesterday = today - timedelta(days=2)  # 取周五
    elif day_of_week == 6:  # 昨天是周日
        yesterday = today - timedelta(days=3)  # 取上周五

    ex_yesterday = yesterday - timedelta(days=1)
    past_date = yesterday - relativedelta(months=months_back)
    
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d"), name))
    return cursor.fetchone()

def execute_query(cursor, query, params):
    """ 执行SQL查询并处理异常 """
    try:
        cursor.execute(query, params)
        return cursor.fetchall(), None
    except sqlite3.DatabaseError as e:
        return None, f"SQL执行错误: {e}"

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
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies', 'names': ('DXY', 'CNYEUR', 'CNYGBP',
            'CNYUSD', 'USDJPY')},
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities', 'names': ('Brent', 'Crude Oil',
            'Natural gas', 'Gold', 'Copper', 'Coffee', 'Cocoa', 'Rice', 'Corn', 'Oat', 'Lean Hogs',
            'Live Cattle', 'Cotton', 'Orange Juice', 'Sugar')},
    ]
    intervals = [600, 360, 240, 120, 60, 24, 12, 6, 3]  # 以月份表示的时间间隔列表
    
    for db_config in databases:
        db_path = db_config['path']
        table_name = db_config['table']
        names = db_config['names']
        
        with create_connection(db_path) as conn:
            cursor = conn.cursor()
        
            for name in names:
                # compare_today_yesterday(cursor, table_name, name, output, today)
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
                                    output.append(f"{name}\n创了 {years} 年来的新高！！")
                                else:
                                    output.append(f"{name}\n创了 {months} 个月来的新高！！")
                            else:  # today_price == max_price
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"{name}\n逼平 {years} 年来的新高！！")
                                else:
                                    output.append(f"{name}\n逼平 {months} 个月来的新高！！")
                        elif abs_diff_ratio <= 3:
                            if abs_diff_ratio <= 1:
                                difference_desc = "仅仅差"
                            elif abs_diff_ratio <= 2:
                                difference_desc = "仅差"
                            else:
                                difference_desc = "差"
                            if months >= 12:
                                years = months // 12
                                output.append(f"{name}\n距 {years} 年最高价 {max_price} {difference_desc} {diff_ratio:.2f}%")
                            else:
                                output.append(f"{name}\n距 {months} 个月最高价 {max_price} {difference_desc} {diff_ratio:.2f}%")
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
                                    output.append(f"{name}\n创了 {years} 年来的新低！！！")
                                else:
                                    output.append(f"{name}\n创了 {months} 个月来的新低！！！")
                            else:  # today_price == min_price
                                if months >= 12:
                                    years = months // 12
                                    output.append(f"{name}\n与 {years} 年来的最低值撞衫！！")
                                else:
                                    output.append(f"{name}\n与 {months} 个月来的最低值撞衫！！")
                        elif abs_diff_ratio <= 3:
                            if abs_diff_ratio <= 1:
                                difference_desc = "仅仅差"
                            elif abs_diff_ratio <= 2:
                                difference_desc = "仅差"
                            else:
                                difference_desc = "差"
                            if months >= 12:
                                years = months // 12
                                output.append(f"{name}\n距 {years} 年最低价 {min_price} {difference_desc} {diff_ratio:.2f}%")
                            else:
                                output.append(f"{name}\n距 {months} 个月最低价 {min_price} {difference_desc} {diff_ratio:.2f}%")
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
    sys.exit()

if __name__ == "__main__":
    main()            # 先运行main函数，确保所有GUI组件都已经初始化
    root.mainloop()   # 启动事件循环，这行代码会在所有窗口关闭后执行结束