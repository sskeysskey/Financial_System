import sqlite3
import pyperclip
import datetime
import json
import subprocess
import sys

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def get_table_name_from_symbol(symbol, json_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as file:
        sectors_data = json.load(file)
    
    for table_name, symbols in sectors_data.items():
        if symbol in symbols:
            return table_name
    return None

def get_last_two_prices(cursor, table_name, name):
    query = f"""
        SELECT date, price FROM {table_name}
        WHERE name = ?
        ORDER BY date DESC
        LIMIT 2
    """
    cursor.execute(query, (name,))
    return cursor.fetchall()

def calculate_percentage_change(latest_price, previous_price):
    if previous_price == 0:
        return 0  # 避免除以零
    # 计算百分比变化并保留两位小数
    percentage_change = (latest_price - previous_price) / previous_price * 100
    return round(percentage_change, 2)

def check_last_record_date(cursor, name, current_date):
    cursor.execute("""
        SELECT date, price FROM Earning
        WHERE name = ?
        ORDER BY date DESC
        LIMIT 1
    """, (name,))
    result = cursor.fetchone()
    
    if result:
        last_date = datetime.date.fromisoformat(result[0])
        price = result[1]
        days_difference = (current_date - last_date).days
        if days_difference > 60:
            return False, last_date, price  # 没有近两个月的数据，不允许插入
        else:
            return True, last_date, price  # 返回最新的日期和价格，允许覆盖
    return False, None, None  # 如果没有找到记录，不允许插入

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

def insert_data(db_path, date, name, price):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        current_date = datetime.date.fromisoformat(date)
        
        has_recent_data, last_date, last_price = check_last_record_date(cursor, name, current_date)
        
        if has_recent_data:
            # 执行更新操作
            cursor.execute("""
                UPDATE Earning
                SET price = ?, date = ?
                WHERE name = ? AND date = ?
            """, (price, date, name, last_date.isoformat()))
            
            if cursor.rowcount > 0:
                conn.commit()
                show_alert(f"已成功强制覆盖更新：\n名称 {name}\n日期 {date}\n价格 {price}")
                return True
            else:
                show_alert(f"未找到可更新的记录：{name}")
                return False
        else:
            show_alert(f"{name} 没有近两个月的记录，无法添加新数据。")
            return False

def main(symbol=None):
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    json_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    # 定义允许的表名集合
    ALLOWED_TABLES = {'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical','Technology', 'Energy',
                        'Industrials', 'Consumer_Defensive', 'Utilities', 'Healthcare', 'Financial_Services',
                        'Real_Estate'}
    
    # 如果没有传递 symbol 参数，则从剪贴板中获取symbol
    if symbol is None:
        Copy_Command_C()
        stock_name = pyperclip.paste().strip()  # 从剪贴板获取symbol
    else:
        stock_name = symbol.strip()  # 使用传递进来的symbol
    
    table_name = get_table_name_from_symbol(stock_name, json_file_path)
    
    if not table_name:
        show_alert(f"无法找到 {stock_name} 所属的表")
        return
    
    # 检查表名是否在允许的集合中
    if table_name not in ALLOWED_TABLES:
        show_alert(f"{stock_name} 不是有效的股票代码，无法添加到earning数据库中")
        return
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # 获取该symbol的最新两条价格记录
        records = get_last_two_prices(cursor, table_name, stock_name)
        if len(records) < 2:
            show_alert(f"{stock_name} 没有足够的价格数据来计算变化")
            return
        
        latest_price = records[0][1]
        previous_price = records[1][1]
        
        # 计算百分比变化
        percentage_change = calculate_percentage_change(latest_price, previous_price)
        
        # 获取昨天的日期
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        
        # 尝试将数据覆盖写入到Earning表
        insert_data(db_path, yesterday, stock_name, percentage_change)

if __name__ == "__main__":
    # 如果有传参，则使用传递的参数；如果没有传参，则 symbol = None
    if len(sys.argv) > 1:
        main(sys.argv[1])  # 使用传递的第一个参数作为 symbol
    else:
        main()  # 没有传参时，执行默认行为