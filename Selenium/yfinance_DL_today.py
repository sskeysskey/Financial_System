import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta
import pyautogui
import random
import time
import threading
import sys
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QDesktopWidget

def create_mouse_prompt():
    """创建询问是否启用鼠标移动的弹窗"""
    # 确保只创建一个QApplication实例
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # 创建消息框
    msg_box = QMessageBox()
    msg_box.setWindowTitle("功能选择")
    msg_box.setText("是否启用鼠标随机移动防止黑屏功能？")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg_box.setDefaultButton(QMessageBox.No)
    
    # 设置窗口标志，使其始终显示在最前面
    msg_box.setWindowFlags(msg_box.windowFlags() | 
                          Qt.WindowStaysOnTopHint | 
                          Qt.WindowActive)
    
    # 移动到屏幕中心
    center = QDesktopWidget().availableGeometry().center()
    msg_box.move(center.x() - msg_box.width() // 2,
                 center.y() - msg_box.height() // 2)
    
    # 激活窗口
    msg_box.show()
    msg_box.activateWindow()
    msg_box.raise_()
    
    # 显示对话框并获取结果
    result = msg_box.exec_()
    
    # 转换结果为布尔值
    return result == QMessageBox.Yes

def move_mouse_periodically():
    """鼠标随机移动功能"""
    while True:
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = pyautogui.size()
            
            # 随机生成目标位置，避免移动到屏幕边缘
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            
            # 缓慢移动鼠标到随机位置
            pyautogui.moveTo(x, y, duration=1)
            
            # 等待30-60秒再次移动
            time.sleep(random.randint(30, 60))
            
        except Exception as e:
            print(f"鼠标移动出错: {str(e)}")
            time.sleep(30)

def log_error_with_timestamp(error_message):
    """错误日志记录"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

def ensure_directory_exists(filepath):
    """确保目录存在，如果不存在则创建"""
    import os
    directory = os.path.dirname(filepath)
    if not os.path.exists(directory):
        os.makedirs(directory)

def write_error_log(error_message, filepath):
    """写入错误日志的安全方法"""
    try:
        ensure_directory_exists(filepath)
        with open(filepath, 'a', encoding='utf-8') as error_file:
            error_file.write(error_message)
        return True
    except Exception as e:
        print(f"写入错误日志失败: {str(e)}")
        return False

def get_price_format(group_name: str) -> int:
    """根据组名决定价格小数位数"""
    if group_name in ["Currencies", "Bonds"]:
        return 4
    elif group_name == "Crypto":
        return 1
    elif group_name == "Commodities":
        return 3
    else:
        return 2

def download_and_process_data(ticker_symbol, start_date, end_date, group_name, c, symbol_mapping, yesterday_date, special_groups, error_log_path):
    """尝试下载和处理数据的函数"""
    try:
        data = yf.download(ticker_symbol, start=start_date, end=end_date, auto_adjust=True)
        if data.empty:
            return False, 0
        
        data_count = 0
        table_name = group_name.replace(" ", "_")
        mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)
        decimal_places = get_price_format(group_name)
        
        for index, row in data.iterrows():
            date = yesterday_date
            # 使用.iloc[0]来获取Series的值
            price = round(float(row['Close'].iloc[0]), decimal_places)

            if group_name in special_groups:
                c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", 
                        (date, mapped_name, price))
            else:
                # 使用.iloc[0]来获取Series的值
                volume = int(row['Volume'].iloc[0])
                c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", 
                        (date, mapped_name, price, volume))
            
            data_count += 1
        
        return True, data_count

    except Exception as e:
        error_message = log_error_with_timestamp(f"{group_name} {ticker_symbol}: {str(e)}")
        write_error_log(error_message, error_log_path)
        return False, 0

def main():
    now = datetime.now()
    # 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
    if now.weekday() in (0, 6):
        print("Today is either Sunday or Monday. The script will not run.")
        return

    enable_mouse_movement = create_mouse_prompt()
    
    if enable_mouse_movement:
        mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
        mouse_thread.start()
        print("已启用鼠标随机移动功能")
    else:
        print("未启用鼠标随机移动功能")

    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', 'r') as file:
        stock_groups = json.load(file)

    with open('/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json', 'r') as file:
        symbol_mapping = json.load(file)

    today = now.date()
    yesterday = today - timedelta(days=1)
    ex_yesterday = yesterday - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # 定义三种不同的日期范围配置
    date_ranges = [
        (yesterday.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')),
        (today.strftime('%Y-%m-%d'), tomorrow.strftime('%Y-%m-%d')),
        (ex_yesterday.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d'))
    ]

    conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
    c = conn.cursor()

    # 定义需要特殊处理的group_name
    special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]
    total_data_count = 0

    ERROR_LOG_PATH = '/Users/yanzhang/Documents/News/Today_error1.txt'
    
    for group_name, tickers in stock_groups.items():
        data_count = 0
        for ticker_symbol in tickers:
            success = False
            
            for start_date, end_date in date_ranges:
                try:
                    print(f"尝试下载 {ticker_symbol} 的数据，日期范围: {start_date} 到 {end_date}")
                    success, current_count = download_and_process_data(
                        ticker_symbol, start_date, end_date, group_name, c,
                        symbol_mapping, yesterday.strftime('%Y-%m-%d'), special_groups,
                        ERROR_LOG_PATH
                    )
                    
                    if success:
                        print(f"成功插入 {current_count}条 {ticker_symbol} 的数据")
                        data_count += current_count
                        break  # 如果成功，退出日期范围循环
                
                except Exception as e:
                    error_message = log_error_with_timestamp(f"未预期的错误 {group_name} {ticker_symbol}: {str(e)}")
                    write_error_log(error_message, ERROR_LOG_PATH)
                    continue

            if not success:
                error_message = log_error_with_timestamp(f"无法获取 {ticker_symbol} 的数据，所有日期范围都已尝试")
                write_error_log(error_message, ERROR_LOG_PATH)
                print(f"无法获取 {ticker_symbol} 的数据，所有日期范围都已尝试")

        if data_count > 0:
            print(f"{group_name} 数据处理完成，总共下载了 {data_count} 条数据。")
        
        total_data_count += data_count

    if total_data_count == 0:
        print("没有数据被写入数据库")
    else:
        print(f"共有 {total_data_count} 个数据成功写入数据库")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()