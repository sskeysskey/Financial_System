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

def main():
    now = datetime.now()
    # 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
    if now.weekday() in (0, 6):
        print("Today is either Sunday or Monday. The script will not run.")
    else:
        # 询问用户是否启用鼠标移动功能
        enable_mouse_movement = create_mouse_prompt()
        
        # 如果用户选择启用鼠标移动，则启动鼠标移动线程
        if enable_mouse_movement:
            mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
            mouse_thread.start()
            print("已启用鼠标随机移动功能")
        else:
            print("未启用鼠标随机移动功能")

        # 读取JSON文件
        with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', 'r') as file:
            stock_groups = json.load(file)

        # 读取symbol_mapping JSON文件
        with open('/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json', 'r') as file:
            symbol_mapping = json.load(file)

        today = now.date()
        yesterday = today - timedelta(days=1)

        # 定义时间范围
        start_date = yesterday.strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

        # 连接到SQLite数据库
        conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
        c = conn.cursor()

        # 定义需要特殊处理的group_name
        special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]

        # for group_name, tickers in stock_groups.items():
        #     data_count = 0  # 初始化计数器
        #     for ticker_symbol in tickers:
        #         try:
        #             # 使用 yfinance 下载股票数据
        #             data = yf.download(ticker_symbol, start=start_date, end=end_date)
        #             if data.empty:
        #                 raise ValueError(f"{group_name} {ticker_symbol}: No price data found for the given date range.")

        #             # 插入数据到相应的表中
        #             table_name = group_name.replace(" ", "_")  # 确保表名没有空格
        #             mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)  # 从映射字典获取名称，如果不存在则使用原始 ticker_symbol
        #             for index, row in data.iterrows():
        #                 date = index.strftime('%Y-%m-%d')
        #                 # date = "2024-06-11"
        #                 if group_name in ["Currencies", "Bonds"]:
        #                     price = round(row['Close'], 4)
        #                 elif group_name in ["Crypto"]:
        #                     price = round(row['Close'], 1)
        #                 elif group_name in ["Commodities"]:
        #                     price = round(row['Close'], 3)
        #                 else:
        #                     price = round(row['Close'], 2)

        #                 if group_name in special_groups:
        #                     c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", (date, mapped_name, price))
        #                 else:
        #                     volume = int(row['Volume'])
        #                     c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", (date, mapped_name, price, volume))
                        
        #                 data_count += 1  # 成功插入一条数据，计数器增加
        #         except Exception as e:
        #             with open('/Users/yanzhang/Documents/News/Today_error1.txt', 'a') as error_file:
        #                 error_file.write(log_error_with_timestamp(str(e)))

        #     # 在完成每个group_name后打印信息
        #     print(f"{group_name} 数据处理完成，总共下载了 {data_count} 条数据。")

        for group_name, tickers in stock_groups.items():
            data_count = 0  # 初始化计数器
            for ticker_symbol in tickers:
                try:
                    # 使用 yfinance 下载股票数据
                    data = yf.download(ticker_symbol, start=start_date, end=end_date)
                    if data.empty:
                        raise ValueError(f"{group_name} {ticker_symbol}: No price data found for the given date range.")

                    # 尝试获取昨天的数据
                    if yesterday in data.index:
                        row = data.loc[yesterday]
                    else:
                        # 如果没有昨天的数据，则使用最新可用的数据
                        row = data.iloc[-1]

                    # 将日期统一设为昨天
                    date = yesterday.strftime('%Y-%m-%d')

                    # 根据不同的group_name处理价格精度
                    if group_name in ["Currencies", "Bonds"]:
                        price = round(row['Close'], 4)
                    elif group_name in ["Crypto"]:
                        price = round(row['Close'], 1)
                    elif group_name in ["Commodities"]:
                        price = round(row['Close'], 3)
                    else:
                        price = round(row['Close'], 2)

                    mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)  # 获取映射名称
                    table_name = group_name.replace(" ", "_")  # 确保表名没有空格

                    if group_name in special_groups:
                        c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", 
                                (date, mapped_name, price))
                    else:
                        volume = int(row['Volume'])
                        c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", 
                                (date, mapped_name, price, volume))
                    
                    data_count += 1  # 成功插入一条数据，计数器增加

                except Exception as e:
                    with open('/Users/yanzhang/Documents/News/Today_error1.txt', 'a') as error_file:
                        error_file.write(log_error_with_timestamp(str(e)))

            # 在完成每个group_name后打印信息
            print(f"{group_name} 数据处理完成，总共下载了 {data_count} 条数据。")

        print("所有数据已成功写入数据库")
        # 提交事务
        conn.commit()
        # 关闭连接
        conn.close()

if __name__ == "__main__":
    main()