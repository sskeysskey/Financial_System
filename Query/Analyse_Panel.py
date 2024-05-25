import sqlite3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def create_connection(db_file):
    """ 创建数据库连接 """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Exception as e:
        print(e)
    return conn

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

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
    result = cursor.fetchone()
    if result and (result[0] is not None and result[1] is not None):
        return result
    else:
        return None  # 如果找不到有效数据，则返回None

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
        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Indices', 'names': ('NASDAQ',
            'S&P500', 'Shanghai', 'Shenzhen', 'Nikkei', 'India', 'HANGSENG', 'Russell', 'VIX', 'Brazil', 'Russian')},

        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto', 'names': ('Bitcoin',
            'Ether', 'Solana', 'Binance')},

        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies', 'names': ('DXY',
            'USDCNY', 'USDJPY', 'CNYEUR', 'GBPCNY', 'USDARS')},

        {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities', 'names': ('Brent',
            'CrudeOil', 'Naturalgas', 'Gold', 'Copper', 'Coffee', 'Cocoa', 'Rice', 'Corn', 'Oat', 'LeanHogs',
            'LiveCattle', 'Cotton', 'OrangeJuice', 'Sugar', 'Silver', 'Soybean')},
    ]
    intervals = [600, 360, 240, 120, 60, 24, 12, 6, 3]  # 以月份表示的时间间隔列表
    
    for db_config in databases:
        db_path = db_config['path']
        table_name = db_config['table']
        names = db_config['names']
        
        with create_connection(db_path) as conn:
            cursor = conn.cursor()
        
            for name in names:
                today_price_query = f"SELECT price FROM {table_name} WHERE date = ? AND name = ?"
                cursor.execute(today_price_query, (real_today.strftime("%Y-%m-%d"), name))
                result = cursor.fetchone()
                try:
                    if result:
                        today_price = result[0]
                    else:
                        raise Exception(f"没有找到今天的{name}价格。")
                except Exception as e:
                    formatted_error_message = log_error_with_timestamp(str(e))
                    # 将错误信息追加到文件中
                    with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                        error_file.write(formatted_error_message)
                
                price_extremes = {}
                for months in intervals:
                    result = get_price_comparison(cursor, table_name, months, name, today)
                    try:
                        if result:
                            max_price, min_price = result
                            price_extremes[months] = (max_price, min_price)
                        else:
                            raise Exception(f"没有足够的历史数据来进行{months}月的价格比较。")
                    except Exception as e:
                        formatted_error_message = log_error_with_timestamp(str(e))
                        # 将错误信息追加到文件中
                        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                            error_file.write(formatted_error_message)

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
    file_path = '/Users/yanzhang/Documents/News/AnalysePanel.txt'  # 您可以修改这个路径到您想要保存的目录
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(final_output)
    print(f"文件已保存到 {file_path}")

if __name__ == "__main__":
    main()