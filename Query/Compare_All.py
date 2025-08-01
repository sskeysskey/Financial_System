from datetime import datetime, timedelta
import sqlite3
import json
import re
import os

def log_error_with_timestamp(error_message, file_path=None):
    """
    记录带时间戳的错误信息

    Args:
        error_message: 错误信息
        file_path: 可选的错误日志文件路径
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    formatted_message = f"[{timestamp}] {error_message}\n"

    if file_path:
        with open(file_path, 'a') as error_file:
            error_file.write(formatted_message)

    return formatted_message

def read_latest_date_info(gainer_loser_path):
    if not os.path.exists(gainer_loser_path):
        return {"gainer": [], "loser": []}

    with open(gainer_loser_path, 'r') as f:
        data = json.load(f)
    latest_date = max(data.keys())
    return latest_date, data[latest_date]

def read_earnings_release(filepath, error_file_path):
    """
    读取一个收益发布文件，将格式 AAPL : BMO : 2025-07-21
    转成 { 'AAPL': {'day':'21','type':'BMO'}, ... }
    """
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}

    earnings_companies = {}
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = [p.strip() for p in line.split(':')]
                # 期望形如 ['VZ', 'BMO', '2025-07-21']
                if len(parts) == 3:
                    company, rel_type, date = parts
                    day = date.split('-')[2]  # 取日
                    earnings_companies[company] = {
                        'day': day,
                        'type': rel_type  # 保存 BMO/AMC/TNS
                    }
    except Exception as e:
        log_error_with_timestamp(f"处理文件 {filepath} 时发生错误: {e}", error_file_path)

    return earnings_companies

def compare_today_yesterday(
    config_path,
    output_file,
    gainer_loser_path,
    earning_file_new,
    earning_file_next,
    error_file_path,
    additional_output_file
):
    # 在函数开头或者合适的位置，先定义一个映射：
    type_map = {
        'BMO': '前',
        'AMC': '后',
        'TNS': '未'
    }

    # 读取 gainer/loser
    latest_date, latest_info = read_latest_date_info(gainer_loser_path)
    gainers = latest_info.get("gainer", [])
    losers = latest_info.get("loser", [])

    # 读取新发布的业绩
    earnings_data = read_earnings_release(earning_file_new, error_file_path)
    # 读取下次发布的业绩，并合并
    earnings_data_next = read_earnings_release(earning_file_next, error_file_path)
    earnings_data.update(earnings_data_next)

    # 检查 gainer_loser.json 中的日期是否为今天或昨天
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    latest_date_date = datetime.strptime(latest_date, "%Y-%m-%d").date()
    is_recent = latest_date_date in (today, yesterday)

    if not os.path.exists(config_path):
        log_error_with_timestamp(f"文件 {config_path} 不存在。", error_file_path)
        return

    with open(config_path, 'r') as f:
        config = json.load(f)

    output = []
    db_path = "/Users/yanzhang/Coding/Database/Finance.db"

    for table_name, keywords in config.items():
        for keyword in sorted(keywords):
            try:
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()

                    # 检查表结构
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = [column[1] for column in cursor.fetchall()]
                    has_volume = 'volume' in columns

                    # 根据是否有 volume 字段调整查询
                    if has_volume:
                        query = f"""
                        SELECT date, price, volume FROM {table_name}
                        WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                        """
                    else:
                        query = f"""
                        SELECT date, price FROM {table_name}
                        WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                        """

                    # 获取最近两个日期
                    query_two_closest_dates = f"""
                    SELECT date FROM {table_name}
                    WHERE name = ? ORDER BY date DESC LIMIT 2
                    """
                    cursor.execute(query_two_closest_dates, (keyword,))
                    dates = cursor.fetchall()

                    if len(dates) < 2:
                        raise Exception(f"错误：无法找到{table_name}下的{keyword}的两个有效数据日期。")

                    latest_db_date = dates[0][0]
                    second_latest_db_date = dates[1][0]

                    cursor.execute(query, (keyword, latest_db_date, second_latest_db_date))
                    results = cursor.fetchall()

                    if len(results) >= 2:
                        latest_price = float(results[0][1] or 0)
                        second_latest_price = float(results[1][1] or 0)

                        latest_volume = 0
                        if has_volume and len(results[0]) > 2:
                            latest_volume = results[0][2] or 0

                        change = latest_price - second_latest_price
                        if second_latest_price != 0:
                            percentage_change = (change / second_latest_price) * 100
                            change_text = f"{percentage_change:.2f}%"
                        else:
                            # 除以零的情况
                            if latest_price > 0:
                                change_text = "∞%"
                            elif latest_price < 0:
                                change_text = "-∞%"
                            else:
                                change_text = "0%"
                            # 这里仍然记录错误
                            raise ValueError(f"{table_name} 下的 {keyword} 的 second_latest_price 为零")

                        if has_volume and latest_volume > 5000000:
                            change_text += '*'

                        # 检查连续涨跌天数（2 或 3 天）
                        consecutive_rise = consecutive_fall = 0
                        query_four_days = f"""
                        SELECT date, price FROM {table_name}
                        WHERE name = ? ORDER BY date DESC LIMIT 4
                        """
                        cursor.execute(query_four_days, (keyword,))
                        four_day_results = cursor.fetchall()
                        if len(four_day_results) == 4:
                            p = [row[1] for row in four_day_results]
                            if p[0] > p[1] > p[2]:
                                consecutive_rise = 2 + (1 if p[2] > p[3] else 0)
                            elif p[0] < p[1] < p[2]:
                                consecutive_fall = 2 + (1 if p[2] < p[3] else 0)

                        if consecutive_rise == 2:
                            change_text += '+'
                        elif consecutive_rise == 3:
                            change_text += '++'
                        if consecutive_fall == 2:
                            change_text += '-'
                        elif consecutive_fall == 3:
                            change_text += '--'

                        # 根据 gainer/loser 和 earnings_data 拼装输出
                        if is_recent and keyword in gainers:
                            suffix = "涨"
                        elif is_recent and keyword in losers:
                            suffix = "跌"
                        else:
                            suffix = ""

                        if keyword in earnings_data:
                            info = earnings_data[keyword]
                            day  = info['day']
                            typ  = info['type']
                            char = type_map.get(typ, '财')   # 默认回落到“财”
                            output.append(f"{keyword}: {day}{char}{change_text}{suffix}")
                        else:
                            output.append(f"{keyword}: {change_text}{suffix}")
                    else:
                        raise Exception(f"错误：无法比较{table_name}下的{keyword}，因为缺少必要的数据。")
            except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e), error_file_path)
                with open(error_file_path, 'a') as error_file:
                    error_file.write(formatted_error_message)

    # 写主输出
    with open(output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

    # 写额外的输出（覆盖）
    with open(additional_output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
    output_file = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
    additional_output_file = '/Users/yanzhang/Coding/Website/economics/compare_all.txt'
    gainer_loser_path = '/Users/yanzhang/Coding/Financial_System/Modules/Gainer_Loser.json'
    earning_file_new = '/Users/yanzhang/Coding/News/Earnings_Release_new.txt'
    earning_file_next = '/Users/yanzhang/Coding/News/Earnings_Release_next.txt'
    error_file_path = '/Users/yanzhang/Coding/News/Today_error.txt'

    try:
        compare_today_yesterday(
            config_path,
            output_file,
            gainer_loser_path,
            earning_file_new,
            earning_file_next,
            error_file_path,
            additional_output_file
        )
        print(f"{output_file} 和 {additional_output_file} 已生成。")
    except Exception as e:
        error_message = log_error_with_timestamp(f"未预期的错误: {e}", error_file_path)
        with open(error_file_path, 'a') as error_file:
            error_file.write(error_message)
        print(f"发生错误，详情请查看 {error_file_path}")