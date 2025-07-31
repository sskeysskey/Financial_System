import sqlite3
import pyperclip
import datetime
import json
import subprocess
import sys

# 在文件开头加上
import tkinter as tk

def show_toast(message, duration=2000, bg="green", fg="white"):
    """
    在屏幕中间弹出一个无边框悬浮窗，duration 毫秒后自动销毁。
    bg/fg 分别是背景色和前景色（文字色）。
    """
    # 新建一个顶层窗口
    root = tk.Tk()
    root.overrideredirect(True)           # 去掉标题栏和边框
    root.attributes('-topmost', True)     # 置顶

    root.configure(bg=bg)

    # 文字标签
    label = tk.Label(
        root,
        text=message,
        bg=bg,
        fg=fg,
        font=('Helvetica', 22),
        justify='left',
        anchor='w',
        padx=10,
        pady=5
    )
    label.pack()

    # 计算放在屏幕右下角
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    
    # 水平居中，垂直居中下方偏移 50px
    x = (sw - w) // 2 + 40
    # 换成你想要的偏移量
    y = (sh - h) // 2
    
    root.geometry(f'{w}x{h}+{x}+{y}')

    # duration 毫秒后销毁自己
    root.after(duration, root.destroy)
    root.mainloop()

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
        # 1. 先把字符串补齐到 YYYY-MM-DD
        date_str = result[0]
        parts = date_str.split('-')
        if len(parts) == 3:
            year, month, day = parts
            month = month.zfill(2)
            day   = day.zfill(2)
            date_str = f"{year}-{month}-{day}"
        # 2. 再用 fromisoformat
        last_date = datetime.date.fromisoformat(date_str)
        price = result[1]
        days_difference = (current_date - last_date).days
        if days_difference > 30:
            return True, None, None  # 没有问题，可以插入
        else:
            return False, last_date, price  # 返回最新的日期和价格
    return True, None, None  # 如果没有找到记录，允许插入

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

def insert_data(db_path, date, name, price):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        current_date = datetime.date.fromisoformat(date)
        
        allowed_to_insert, last_date, last_price = check_last_record_date(cursor, name, current_date)
        formatted_price = f"{price:+.2f}%"
        
        if allowed_to_insert:
            try:
                cursor.execute("""
                    INSERT INTO Earning (date, name, price)
                    VALUES (?, ?, ?)
                """, (date, name, price))
                conn.commit()
                # 成功：绿色背景
                show_toast(f"成功！\n\n{formatted_price}", duration=3000)
                return True
            except sqlite3.IntegrityError:
                show_alert(f"{name} 在 {date} 的记录已存在。")
        else:
            if last_date and last_price is not None:
                # show_toast(f"{name} 的最新记录距离现在不足1个月，无法添加新数据。\n"
                #            f"最新记录日期：{last_date}\n\n"
                #            f"价格：{last_price}", duration=3000)
                formatted_last = f"{last_price:+.2f}%"
                # 失败：红色背景
                show_toast(f"失败！\n\n{formatted_last}", duration=4000, bg="red")
            else:
                show_alert(f"{name} 的最新记录距离现在不足1个月，无法添加新数据。")
        return False

def get_user_input():
    # AppleScript代码，弹出输入对话框
    applescript_code = '''
    display dialog "请输入股票代码:" default answer "" buttons {"取消", "确定"} default button "确定"
    '''
    try:
        # 运行 AppleScript 并获取结果
        result = subprocess.run(['osascript', '-e', applescript_code], 
                              capture_output=True, text=True, check=True)
        # 解析返回的结果
        if 'button returned:确定' in result.stdout:
            # 提取用户输入的文本
            user_input = result.stdout.split('text returned:')[1].strip()
            return user_input.upper()  # 转换为大写
        return None
    except subprocess.CalledProcessError:
        return None

def main(symbol=None):
    db_path = '/Users/yanzhang/Coding/Database/Finance.db'
    json_file_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
    # 定义允许的表名集合
    ALLOWED_TABLES = {'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical','Technology', 'Energy',
                        'Industrials', 'Consumer_Defensive', 'Utilities', 'Healthcare', 'Financial_Services',
                        'Real_Estate'}
    
    # 如果没有传递 symbol 参数，则从剪贴板中获取symbol
    if symbol is None:
        Copy_Command_C()
        stock_name = pyperclip.paste()
        
        # 如果剪贴板为空或者内容无效，弹出输入框
        if not stock_name or not stock_name.strip():
            stock_name = get_user_input()
            if not stock_name:  # 如果用户取消输入
                return
    else:
        stock_name = symbol.strip()  # 使用传递进来的symbol
    
    stock_name = stock_name.strip()  # 确保去除首尾空格
    
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
        
        # 尝试将数据插入到Earning表
        insert_data(db_path, yesterday, stock_name, percentage_change)

if __name__ == "__main__":
    # 如果有传参，则使用传递的参数；如果没有传参，则 symbol = None
    if len(sys.argv) > 1:
        main(sys.argv[1])  # 使用传递的第一个参数作为 symbol
    else:
        main()  # 没有传参时，执行默认行为