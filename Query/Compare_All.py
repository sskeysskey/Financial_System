from datetime import datetime, timedelta
import sqlite3
import json
import re
import os

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

def read_latest_date_info(gainer_loser_path):
    if not os.path.exists(gainer_loser_path):
        return {"gainer": [], "loser": []}

    with open(gainer_loser_path, 'r') as f:
        data = json.load(f)
    latest_date = max(data.keys())
    return latest_date, data[latest_date]

def read_earnings_release(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}

    earnings_companies = {}

    # 修改后的正则表达式
    pattern_colon = re.compile(r'([\w-]+)(?::[\w]+)?\s*:\s*\d+\s*:\s*(\d{4}-\d{2}-\d{2})')

    with open(filepath, 'r') as file:
        for line in file:
            match = pattern_colon.search(line)
            company = match.group(1).strip()
            date = match.group(2)
            day = date.split('-')[2]  # 只取日期的天数
            earnings_companies[company] = day
    return earnings_companies

def compare_today_yesterday(config_path, output_file, gainer_loser_path, earning_file, error_file_path, additional_output_file):
    latest_date, latest_info = read_latest_date_info(gainer_loser_path)
    gainers = latest_info.get("gainer", [])
    losers = latest_info.get("loser", [])
    earnings_data = read_earnings_release(earning_file, error_file_path)

    # 检查 gainer_loser.json 中的日期是否为今天或昨天
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    latest_date = datetime.strptime(latest_date, "%Y-%m-%d").date()
    is_recent = latest_date in (today, yesterday)

    if not os.path.exists(config_path):
        log_error_with_timestamp(f"文件 {config_path} 不存在。", error_file_path)
        return

    with open(config_path, 'r') as f:
        config = json.load(f)
    
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
                        latest_price = float(results[0][1]) if results[0][1] is not None else 0
                        second_latest_price = float(results[1][1]) if results[1][1] is not None else 0
                        change = latest_price - second_latest_price
                        if second_latest_price != 0:
                            percentage_change = (change / second_latest_price) * 100
                            change_text = f"{percentage_change:.2f}%"
                        else:
                            # 处理除以零的情况
                            if latest_price > 0:
                                change_text = "∞%"  # 正无穷
                            elif latest_price < 0:
                                change_text = "-∞%"  # 负无穷
                            else:
                                change_text = "0%"  # 两个价格都为零
                            raise ValueError(f" {table_name} 下的 {keyword}的 second_latest_price 为零")

                        # 检查是否连续两天或三天上涨
                        consecutive_rise = 0
                        consecutive_fall = 0
                        if keyword in config.get(table_name, {}):
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
                                # 检查连续下跌
                                elif (four_day_results[0][1] < four_day_results[1][1] and
                                      four_day_results[1][1] < four_day_results[2][1]):
                                    consecutive_fall = 2
                                    if four_day_results[2][1] < four_day_results[3][1]:
                                        consecutive_fall = 3

                            if consecutive_rise == 2:
                                change_text += "+"
                            elif consecutive_rise == 3:
                                change_text += "++"
                            
                            if consecutive_fall == 2:
                                change_text += "-"
                            elif consecutive_fall == 3:
                                change_text += "--"

                        if is_recent and keyword in gainers:
                            if keyword in earnings_data:
                                output.append(f"{keyword}: {earnings_data[keyword]}财{change_text}涨")
                            else:
                                output.append(f"{keyword}: {change_text}涨")
                        elif is_recent and keyword in losers:
                            if keyword in earnings_data:
                                output.append(f"{keyword}: {earnings_data[keyword]}财{change_text}跌")
                            else:
                                output.append(f"{keyword}: {change_text}跌")
                        else:
                            if keyword in earnings_data:
                                output.append(f"{keyword}: {earnings_data[keyword]}财{change_text}")
                            else:
                                output.append(f"{keyword}: {change_text}")
                    else:
                        raise Exception(f"错误：无法比较{table_name}下的{keyword}，因为缺少必要的数据。")
            except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e))
                with open(error_file_path, 'a') as error_file:
                    error_file.write(formatted_error_message)

    with open(output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

    # 写入额外的输出文件（覆盖已存在的文件）
    with open(additional_output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    output_file = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
    additional_output_file = '/Users/yanzhang/Documents/sskeysskey.github.io/economics/compare_all.txt'
    gainer_loser_path = '/Users/yanzhang/Documents/Financial_System/Modules/Gainer_Loser.json'
    earning_file = '/Users/yanzhang/Documents/News/Earnings_Release_new.txt'
    error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'

    try:
        # 运行主逻辑
        compare_today_yesterday(config_path, output_file, gainer_loser_path, earning_file, error_file_path, additional_output_file)
        print(f"{output_file} 和 {additional_output_file} 已生成。")

    except Exception as e:
        error_message = log_error_with_timestamp(f"未预期的错误: {str(e)}")
        with open(error_file_path, 'a') as error_file:
            error_file.write(error_message)
        print(f"发生错误，详情请查看 {error_file_path}")