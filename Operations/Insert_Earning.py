import sqlite3
import pyperclip
import datetime
import re
import subprocess

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def get_stock_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def parse_stock_data(content, stock_name):
    pattern = rf'{re.escape(stock_name)}.*?:\s*([-]?\d+\.\d+)%'
    match = re.search(pattern, content)
    if match:
        return float(match.group(1))
    return None

# def parse_stock_data(content, stock_name):
#     # 修改正则表达式以匹配百分号
#     pattern = rf'{re.escape(stock_name)}\.10\.\*\.-\s*:\s*([-]?\d+\.\d+%?)' 
#     match = re.search(pattern, content)
#     if match:
#         # 去除百分号并转换为浮点数
#         return float(match.group(1).rstrip('%')) 
#     else:
#         return None

def check_last_record_date(cursor, name, current_date):
    cursor.execute("""
        SELECT date FROM Earning
        WHERE name = ?
        ORDER BY date DESC
        LIMIT 1
    """, (name,))
    result = cursor.fetchone()
    
    if result:
        last_date = datetime.date.fromisoformat(result[0])
        days_difference = (current_date - last_date).days
        return days_difference > 60  # 超过两个月（假设每月30天）
    return True  # 如果没有找到记录，允许插入

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

def insert_data(db_path, date, name, price):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        current_date = datetime.date.fromisoformat(date)
        
        if check_last_record_date(cursor, name, current_date):
            try:
                cursor.execute("""
                    INSERT INTO Earning (date, name, price)
                    VALUES (?, ?, ?)
                """, (date, name, price))
                conn.commit()
                show_alert(f"已成功添加：\n名称 {name}\n日期 {date}\n价格 {price}")
                return True
            except sqlite3.IntegrityError:
                show_alert(f"{name} 在 {date} 的记录已存在。")
        else:
            show_alert(f"{name} 的最新记录距离现在不足两个月，无法添加新数据。")
        return False

def main():
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    file_path = '/Users/yanzhang/Documents/News/CompareStock.txt'
    
    Copy_Command_C()
    # 从剪贴板获取股票名称
    stock_name = pyperclip.paste().strip()
    
    # 获取昨天的日期
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # 读取并解析股票数据
    content = get_stock_data(file_path)
    price = parse_stock_data(content, stock_name)
    
    if price is not None:
        # 尝试插入数据到数据库
        insert_data(db_path, yesterday, stock_name, price)
    else:
        show_alert(f"无法找到 {stock_name} 的数据")

if __name__ == "__main__":
    main()