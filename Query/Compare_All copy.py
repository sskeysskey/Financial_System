from datetime import datetime, timedelta
import sqlite3
import json
import shutil  # 在文件最开始导入shutil模块

def copy_database_to_backup():
    source_path = '/Users/yanzhang/Documents/Database/Finance.db'
    destination_path = '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db'
    shutil.copy2(source_path, destination_path)  # 使用copy2来复制文件，并覆盖同名文件
    print(f"文件已从{source_path}复制到{destination_path}。")

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

def read_latest_date_info(gainer_loser_path):
    with open(gainer_loser_path, 'r') as f:
        data = json.load(f)
    latest_date = max(data.keys())
    return data[latest_date]

def read_earningsymbol_from_file(file_path):
    symbols = set()
    with open(file_path, 'r') as f:
        for line in f:
            symbol = line.split(':')[0].strip()
            symbols.add(symbol)
    return symbols

def compare_today_yesterday(config_path, output_file, gainer_loser_path, earning_file, sector_panel_path):
    latest_info = read_latest_date_info(gainer_loser_path)
    gainers = latest_info.get("gainer", [])
    losers = latest_info.get("loser", [])
    symbols = read_earningsymbol_from_file(earning_file)

    with open(config_path, 'r') as f:
        config = json.load(f)
    
    with open(sector_panel_path, 'r') as f:
        panel_json = json.load(f)
    
    output = []
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    
    for table_name, keywords in config.items():
        for keyword in sorted(keywords):
            try:
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()

                    query_two_closest_dates = f"""
                    SELECT date FROM {table_name}
                    WHERE name = ? ORDER BY date DESC LIMIT 2
                    """
                    cursor.execute(query_two_closest_dates, (keyword,))
                    results = cursor.fetchall()

                    if len(results) < 2:
                        raise Exception(f"错误：无法找到{table_name}下的{keyword}的两个有效数据日期。")

                    latest_date = results[0][0]
                    second_latest_date = results[1][0]

                    query = f"""
                    SELECT date, price FROM {table_name} 
                    WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                    """
                    cursor.execute(query, (keyword, latest_date, second_latest_date))
                    results = cursor.fetchall()

                    if len(results) == 2:
                        latest_price = results[0][1]
                        second_latest_price = results[1][1]
                        change = latest_price - second_latest_price
                        percentage_change = (change / second_latest_price) * 100
                        change_text = f"{percentage_change:.2f}%"

                        # 检查是否连续两天或三天上涨
                        consecutive_rise = 0
                        if keyword in panel_json.get(table_name, {}):
                            query_four_days = f"""
                            SELECT date, price FROM {table_name} 
                            WHERE name = ? ORDER BY date DESC LIMIT 4
                            """
                            cursor.execute(query_four_days, (keyword,))
                            four_day_results = cursor.fetchall()
                            if len(four_day_results) == 4:
                                if (four_day_results[0][1] > four_day_results[1][1] and 
                                    four_day_results[1][1] > four_day_results[2][1]):
                                    consecutive_rise = 2
                                    if four_day_results[2][1] > four_day_results[3][1]:
                                        consecutive_rise = 3
                            
                            if consecutive_rise == 2:
                                change_text += "+"
                            elif consecutive_rise == 3:
                                change_text += "++"

                        if keyword in gainers:
                            if keyword in symbols:
                                output.append(f"{keyword}: 财{change_text}涨")
                            else:
                                output.append(f"{keyword}: {change_text}涨")
                        elif keyword in losers:
                            if keyword in symbols:
                                output.append(f"{keyword}: 财{change_text}跌")
                            else:
                                output.append(f"{keyword}: {change_text}跌")
                        else:
                            if keyword in symbols:
                                output.append(f"{keyword}: 财{change_text}")
                            else:
                                output.append(f"{keyword}: {change_text}")
                    else:
                        raise Exception(f"错误：无法比较{table_name}下的{keyword}，因为缺少必要的数据。")
            except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e))
                with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                    error_file.write(formatted_error_message)

    with open(output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    output_file = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
    gainer_loser_path = '/Users/yanzhang/Documents/Financial_System/Modules/Gainer_Loser.json'
    earning_file = '/Users/yanzhang/Documents/News/Earnings_Release_new.txt'
    sector_panel_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
    compare_today_yesterday(config_path, output_file, gainer_loser_path, earning_file, sector_panel_path)
    print(f"{output_file} 已生成。")
    copy_database_to_backup()