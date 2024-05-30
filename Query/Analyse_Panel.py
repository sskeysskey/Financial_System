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

def get_price_comparison(cursor, table_name, interval, name, validate):
    today = datetime.now()
    ex_validate = validate - timedelta(days=1)
    
    # 判断interval是否小于1，若是，则按天数计算
    if interval < 1:
        days = int(interval * 30)  # 将月份转换为天数
        past_date = validate - timedelta(days=days - 1)
    else:
        past_date = today - relativedelta(months=int(interval))
    
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), ex_validate.strftime("%Y-%m-%d"), name))
    result = cursor.fetchone()
    if result and (result[0] is not None and result[1] is not None):
        return result
    else:
        return None  # 如果找不到有效数据，则返回None

def get_latest_price_and_date(cursor, table_name, name):
    """获取指定股票的最新价格和日期"""
    query = f"""
    SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 1
    """
    cursor.execute(query, (name,))
    return cursor.fetchone()

def main():
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
                result = get_latest_price_and_date(cursor, table_name, name)
                if result:
                    validate, validate_price = result
                    validate = datetime.strptime(validate, "%Y-%m-%d")
                else:
                    error_message = f"没有找到{name}的历史价格数据。"
                    formatted_error_message = log_error_with_timestamp(error_message)
                    with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                        error_file.write(formatted_error_message)
                    continue
                
                price_extremes = {}
                for interval in intervals:
                    result = get_price_comparison(cursor, table_name, interval, name, validate)
                    try:
                        if result:
                            max_price, min_price = result
                            price_extremes[interval] = (max_price, min_price)
                        else:
                            raise Exception(f"没有足够的历史数据来进行{interval}月的价格比较。")
                    except Exception as e:
                        formatted_error_message = log_error_with_timestamp(str(e))
                        # 将错误信息追加到文件中
                        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                            error_file.write(formatted_error_message)
                        continue  # 处理下一个时间间隔

                # 检查是否接近最高价格
                found_max = False
                close_max = False
                for interval in intervals:
                    if found_max or close_max:
                        break
                    max_price, _ = price_extremes.get(interval, (None, None))
                    if max_price is not None:
                        diff_ratio = (max_price - validate_price) / max_price * 100
                        abs_diff_ratio = abs(diff_ratio)
                        if validate_price >= max_price:
                            found_max = True
                            if validate_price > max_price:
                                if interval >= 12:
                                    years = interval // 12
                                    output.append(f"{name}\n创了 {years} 年来的新高！！")
                                else:
                                    output.append(f"{name}\n创了 {interval} 个月来的新高！！")
                            else:
                                if interval >= 12:
                                    years = interval // 12
                                    output.append(f"{name}\n逼平 {years} 年来的新高！！")
                                else:
                                    output.append(f"{name}\n逼平 {interval} 个月来的新高！！")
                        elif abs_diff_ratio <= 3:
                            if abs_diff_ratio <= 1:
                                difference_desc = "仅仅差"
                            elif abs_diff_ratio <= 2:
                                difference_desc = "仅差"
                            else:
                                difference_desc = "差"
                            if interval >= 12:
                                years = interval // 12
                                output.append(f"{name}\n距 {years} 年最高价 {max_price} {difference_desc} {diff_ratio:.2f}%")
                            else:
                                output.append(f"{name}\n距 {interval} 个月最高价 {max_price} {difference_desc} {diff_ratio:.2f}%")
                            close_max = True

                # 同样的逻辑适用于最低价格检查
                found_min = False
                close_min = False
                for interval in intervals:
                    if found_min or close_min:
                        break
                    _, min_price = price_extremes.get(interval, (None, None))
                    if min_price is not None:
                        diff_ratio = (validate_price - min_price) / min_price * 100
                        abs_diff_ratio = abs(diff_ratio)
                        if validate_price <= min_price:
                            found_min = True
                            if validate_price < min_price:
                                if interval >= 12:
                                    years = interval // 12
                                    output.append(f"{name}\n创了 {years} 年来的新低！！！")
                                else:
                                    output.append(f"{name}\n创了 {interval} 个月来的新低！！！")
                            else:
                                if interval >= 12:
                                    years = interval // 12
                                    output.append(f"{name}\n与 {years} 年来的最低值撞衫！！")
                                else:
                                    output.append(f"{name}\n与 {interval} 个月来的最低值撞衫！！")
                        elif abs_diff_ratio <= 3:
                            if abs_diff_ratio <= 1:
                                difference_desc = "仅仅差"
                            elif abs_diff_ratio <= 2:
                                difference_desc = "仅差"
                            else:
                                difference_desc = "差"
                            if interval >= 12:
                                years = interval // 12
                                output.append(f"{name}\n距 {years} 年最低价 {min_price} {difference_desc} {diff_ratio:.2f}%")
                            else:
                                output.append(f"{name}\n距 {interval} 个月最低价 {min_price} {difference_desc} {diff_ratio:.2f}%")
                            close_min = True

            output.append(f"\n")
            
    final_output = "\n".join(output)
    # 将输出保存到文件
    file_path = '/Users/yanzhang/Documents/News/AnalysePanel.txt'
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(final_output)
    print(f"文件已保存到 {file_path}")

if __name__ == "__main__":
    main()