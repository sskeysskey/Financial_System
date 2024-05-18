from datetime import datetime, timedelta
import sqlite3
import json
import shutil  # 在文件最开始导入shutil模块

def copy_database_to_backup():
    source_path = '/Users/yanzhang/Documents/Database/Finance.db'
    destination_path = '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db'
    shutil.copy2(source_path, destination_path)  # 使用copy2来复制文件，并覆盖同名文件
    print(f"文件已从{source_path}复制到{destination_path}。")

def compare_today_yesterday(config_path, output_file):
    # 读取合并后的数据库配置
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    output = []
    for table_name, keywords in config.items():
        for keyword in sorted(keywords):
            db_path = "/Users/yanzhang/Documents/Database/Finance.db"
            
            # 使用 with 语句来管理数据库连接
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                today = datetime.now()
                yesterday = today - timedelta(days=1)
                
                if keyword in {'Bitcoin', 'Ether', 'Solana', 'Binance'}:
                    ex_yesterday = yesterday - timedelta(days=1)
                else:
                    day_of_week = yesterday.weekday()
                    if day_of_week == 0:  # 昨天是周一
                        ex_yesterday = yesterday - timedelta(days=3)  # 取上周五
                    elif day_of_week in {5, 6}:  # 昨天是周六或周日
                        yesterday = yesterday - timedelta(days=(day_of_week - 4))  # 周五
                        ex_yesterday = yesterday - timedelta(days=1)
                    else:
                        ex_yesterday = yesterday - timedelta(days=1)

                query = f"""
                SELECT date, price FROM {table_name} 
                WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                """
                cursor.execute(query, (keyword, yesterday.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d")))
                results = cursor.fetchall()

                if len(results) == 2:
                    yesterday_price = results[0][1]
                    ex_yesterday_price = results[1][1]
                    change = yesterday_price - ex_yesterday_price
                    percentage_change = (change / ex_yesterday_price) * 100
                    change_text = f"{percentage_change:.2f}%"
                    print(f"{keyword}: {change_text}")
                    output.append(f"{keyword}: {change_text}")

    with open(output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
    output_file = '/Users/yanzhang/Documents/News/backup/Compare_Panel.txt'
    compare_today_yesterday(config_path, output_file)
    print(f"{output_file} 已生成。")
    copy_database_to_backup()  # 在程序的最后调用复制数据库的功能