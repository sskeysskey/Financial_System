import sqlite3
from datetime import datetime, timedelta

def create_connection(db_file):
    """ 创建到SQLite数据库的连接 """
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Exception as e:
        print(e)
        return None

def get_price_comparison(cursor, date_back_years, index_name):
    today = datetime.now()
    past_date = today - timedelta(days=365 * date_back_years)
    end_date = today - timedelta(days=1)
    
    query = """
    SELECT MAX(price), MIN(price)
    FROM Stocks WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), index_name))
    result = cursor.fetchone()
    return result if result else (None, None)

def main():
    db_file = '/Users/yanzhang/Stocks.db'
    conn = create_connection(db_file)
    cursor = conn.cursor()
    
    index_names = ["NASDAQ", "S&P 500", "SSE Composite Index", "Shenzhen Index", "Nikkei 225", "S&P BSE SENSEX", "HANG SENG INDEX"]
    intervals = [50, 30, 20, 10, 5, 2, 1, 0.5, 0.25]
    
    for index_name in index_names:
        today_price_query = "SELECT price FROM Stocks WHERE date = ? AND name = ?"
        cursor.execute(today_price_query, (datetime.now().strftime("%Y-%m-%d"), index_name))
        result = cursor.fetchone()

        if result:
            today_price = result[0]
            print(f"Today's {index_name} price: {today_price}")
        else:
            print(f"没有找到今天的{index_name}价格。")
            continue  # 如果没有今天的价格，继续下一个指数的检查

        # 检查最高价格
        found_max = False
        for years in intervals:
            if found_max:
                break
            max_price, _ = get_price_comparison(cursor, years, index_name)
            # print(f"Checking {years} years back: max={max_price}")  # 添加打印语句
            if max_price and today_price > max_price:
                print(f"今天的价格 {today_price} 超过了 {years} 年前的 {index_name} 最高价格 {max_price}")
                found_max = True
        
        # 检查最低价格
        found_min = False
        for years in intervals:
            if found_min:
                break
            _, min_price = get_price_comparison(cursor, years, index_name)
            # print(f"Checking {years} years back: min={min_price}")  # 添加打印语句
            if min_price and today_price < min_price:
                print(f"今天的价格 {today_price} 低于 {years} 年前的 {index_name} 最低价格 {min_price}")
                found_min = True

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()