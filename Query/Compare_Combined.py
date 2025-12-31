import os
import json
import sqlite3
# import csv
import re
from datetime import datetime, timedelta
from wcwidth import wcswidth

# ==========================================
# 通用辅助函数
# ==========================================

def create_connection(db_file):
    return sqlite3.connect(db_file, timeout=60.0)

def log_error_with_timestamp(error_message, file_path=None):
    """
    通用错误记录函数
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    formatted_message = f"[{timestamp}] {error_message}\n"
    if file_path:
        with open(file_path, 'a') as error_file:
            error_file.write(formatted_message)
    return formatted_message

def clean_old_backups(directory, prefix, days=4, exts=None):
    """
    通用清理备份函数
    """
    if exts is None:
        exts = ['.txt'] # 修改：默认只检查 txt，不再检查 csv
        
    # 如果 exts 为空列表（针对 ETFs 的逻辑，它只看前缀），则不检查扩展名
    check_ext = True if exts else False

    now = datetime.now()
    cutoff = now - timedelta(days=days)

    if not os.path.exists(directory):
        return

    for filename in os.listdir(directory):
        name, ext = os.path.splitext(filename)
        
        # 检查前缀
        if not filename.startswith(prefix):
            continue
        
        # 检查后缀（如果需要）
        if check_ext and ext.lower() not in exts:
            continue

        try:
            # 尝试提取日期，假设格式为 prefix_YYMMDD.ext 或 prefixYYMMDD.ext
            # 这里沿用原脚本逻辑：取前缀之后的部分，去掉后缀
            date_part = filename[len(prefix):].split('.')[0]
            # 处理可能的下划线 (比如 CompareStock_230814)
            if date_part.startswith('_'):
                date_part = date_part[1:]
                
            file_date = datetime.strptime(date_part, '%y%m%d')
            file_date = file_date.replace(year=now.year)
            
            if file_date < cutoff:
                file_path = os.path.join(directory, filename)
                os.remove(file_path)
                print(f"删除旧备份文件：{filename}")
        except Exception as e:
            # 文件名格式不符合日期格式，跳过
            pass

# ==========================================
# 模块 1: Compare_All 逻辑
# ==========================================

def read_latest_date_info_all(gainer_loser_path):
    if not os.path.exists(gainer_loser_path):
        return {"gainer": [], "loser": []}
    with open(gainer_loser_path, 'r') as f:
        data = json.load(f)
    latest_date = max(data.keys())
    return latest_date, data[latest_date]

def read_earnings_release_for_all(filepath, error_file_path):
    """
    Compare_All 专用的简易财报读取
    """
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}
    earnings_companies = {}
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = [p.strip() for p in line.split(':')]
                if len(parts) == 3:
                    company, rel_type, date = parts
                    day = date.split('-')[2]
                    earnings_companies[company] = {
                        'day': day,
                        'type': rel_type
                    }
    except Exception as e:
        log_error_with_timestamp(f"处理文件 {filepath} 时发生错误: {e}", error_file_path)
    return earnings_companies

def run_compare_all(
    config_path, output_file, gainer_loser_path,
    earning_file_new, earning_file_next, earning_file_third, earning_file_fourth, earning_file_fifth,
    error_file_path, additional_output_file
):
    print("--- 开始执行: Compare_All ---")
    type_map = {'BMO': '前', 'AMC': '后', 'TNS': '未'}
    
    latest_date, latest_info = read_latest_date_info_all(gainer_loser_path)
    gainers = latest_info.get("gainer", [])
    losers = latest_info.get("loser", [])

    earning_files = [earning_file_new, earning_file_next, earning_file_third, earning_file_fourth, earning_file_fifth]
    earnings_data = {}
    for file_path in earning_files:
        data_from_file = read_earnings_release_for_all(file_path, error_file_path)
        earnings_data.update(data_from_file)

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    try:
        latest_date_date = datetime.strptime(latest_date, "%Y-%m-%d").date()
        is_recent = latest_date_date in (today, yesterday)
    except:
        is_recent = False

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
                with sqlite3.connect(db_path, timeout=60.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = [column[1] for column in cursor.fetchall()]
                    has_volume = 'volume' in columns

                    if has_volume:
                        query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? AND date IN (?, ?) ORDER BY date DESC"
                    else:
                        query = f"SELECT date, price FROM {table_name} WHERE name = ? AND date IN (?, ?) ORDER BY date DESC"

                    query_two_closest_dates = f"SELECT date FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 2"
                    cursor.execute(query_two_closest_dates, (keyword,))
                    dates = cursor.fetchall()

                    if len(dates) < 2:
                        # 静默跳过或记录，原脚本抛出异常
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
                            if latest_price > 0: change_text = "∞%"
                            elif latest_price < 0: change_text = "-∞%"
                            else: change_text = "0%"
                            raise ValueError(f"{table_name} 下的 {keyword} 的 second_latest_price 为零")

                        if has_volume and latest_volume > 5000000:
                            change_text += '*'

                        consecutive_rise = consecutive_fall = 0
                        query_four_days = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 4"
                        cursor.execute(query_four_days, (keyword,))
                        four_day_results = cursor.fetchall()
                        if len(four_day_results) == 4:
                            p = [row[1] for row in four_day_results]
                            if p[0] > p[1] > p[2]:
                                consecutive_rise = 2 + (1 if p[2] > p[3] else 0)
                            elif p[0] < p[1] < p[2]:
                                consecutive_fall = 2 + (1 if p[2] < p[3] else 0)

                        if consecutive_rise == 2: change_text += '+'
                        elif consecutive_rise == 3: change_text += '++'
                        if consecutive_fall == 2: change_text += '-'
                        elif consecutive_fall == 3: change_text += '--'

                        if is_recent and keyword in gainers: suffix = "涨"
                        elif is_recent and keyword in losers: suffix = "跌"
                        else: suffix = ""

                        if keyword in earnings_data:
                            info = earnings_data[keyword]
                            day  = info['day']
                            typ  = info['type']
                            char = type_map.get(typ, '财')
                            output.append(f"{keyword}: {day}{char}{change_text}{suffix}")
                        else:
                            output.append(f"{keyword}: {change_text}{suffix}")
                    else:
                        raise Exception(f"错误：无法比较{table_name}下的{keyword}，因为缺少必要的数据。")
            except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e), error_file_path)
                # 原脚本在这里又写了一次，log函数里也写了一次，这里只打印吧
                # print(f"Compare_All Warning: {e}") 

    with open(output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

    with open(additional_output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')
    
    print(f"Compare_All 完成。生成: {output_file}")


# ==========================================
# 模块 2: Compare_Stocks 逻辑
# ==========================================

def pad_display(s: str, width: int, align: str = 'left') -> str:
    cur = wcswidth(s)
    if cur >= width:
        return s
    pad = width - cur
    if align == 'left':
        return s + ' ' * pad
    else:
        return ' ' * pad + s

def read_earnings_release_for_stocks(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}
    period_map = {'BMO': '前', 'AMC': '后', 'TNS': '未', 'TAS': '未'}
    earnings_companies = {}
    with open(filepath, 'r') as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split(':')]
            if len(parts) >= 3:
                company = parts[0]
                period = parts[1]
                date_str = parts[-1]
                m = re.match(r'(\d{4})-(\d{2})-(\d{2})$', date_str)
                if m:
                    day = m.group(3)
                    suffix = period_map.get(period)
                    if suffix:
                        earnings_companies[company] = f"{day}{suffix}"
                    else:
                        log_error_with_timestamp(f"第 {line_number} 行未知的 period: '{period}'", error_file_path)
                        earnings_companies[company] = day
                else:
                    log_error_with_timestamp(f"第 {line_number} 行日期格式不对: '{date_str}'", error_file_path)
            else:
                log_error_with_timestamp(f"第 {line_number} 行无法解析: '{line}'", error_file_path)
    return earnings_companies

def read_gainers_losers_stocks(filepath):
    if not os.path.exists(filepath):
        return [], []
    with open(filepath, 'r') as file:
        data = json.load(file)
    if not data:
        return [], []
    today_date = datetime.now().strftime("%Y-%m-%d")
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if today_date in data:
        return data[today_date].get('gainer', []), data[today_date].get('loser', [])
    elif yesterday_date in data:
        return data[yesterday_date].get('gainer', []), data[yesterday_date].get('loser', [])
    else:
        return [], []

def get_latest_available_dates(cursor, table_name, name, limit=4):
    query = f"SELECT date FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT ?"
    cursor.execute(query, (name, limit))
    return cursor.fetchall()

def get_prices_available_days(cursor, table_name, name, dates):
    placeholders = ', '.join('?' for _ in dates)
    query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? AND date IN ({placeholders}) ORDER BY date DESC"
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def run_compare_stocks(
    config_path, description_path, blacklist, interested_sectors, db_path,
    earnings_new_path, earnings_next_path, earnings_third_path, earnings_fourth_path, earnings_fifth_path,
    gainers_losers_path, output_path, error_file_path
):
    print("--- 开始执行: Compare_Stocks ---")
    with open(config_path, 'r') as file:
        data = json.load(file)
    with open(description_path, 'r') as file:
        description_data = json.load(file)

    earnings_new = read_earnings_release_for_stocks(earnings_new_path, error_file_path)
    earnings_next = read_earnings_release_for_stocks(earnings_next_path, error_file_path)
    earnings_third = read_earnings_release_for_stocks(earnings_third_path, error_file_path)
    earnings_fourth = read_earnings_release_for_stocks(earnings_fourth_path, error_file_path)
    earnings_fifth = read_earnings_release_for_stocks(earnings_fifth_path, error_file_path)
    gainers, losers = read_gainers_losers_stocks(gainers_losers_path)

    symbol_to_tags = {}
    for item in description_data.get("stocks", []) + description_data.get("etfs", []):
        symbol_to_tags[item["symbol"]] = item.get("tag", [])

    output = []
    with create_connection(db_path) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name not in interested_sectors:
                continue
            for name in names:
                if name in blacklist:
                    continue
                try:
                    date_rows = get_latest_available_dates(cursor, table_name, name)
                    if len(date_rows) < 2:
                        raise ValueError(f"无法找到 {table_name} 下的 {name} 足够的历史数据进行比较。")
                    dates = [r[0] for r in date_rows]
                    prices = get_prices_available_days(cursor, table_name, name, dates)
                    if len(prices) < 2:
                        raise ValueError(f"无法比较 {table_name} 下的 {name}，因为缺少必要的数据。")

                    latest_price, latest_volume = prices[0][1], prices[0][2]
                    prev_price, prev_volume = prices[1][1], prices[1][2]
                    change = latest_price - prev_price
                    percentage_change = (change / prev_price * 100) if prev_price else 0
                    volume_change = latest_volume - prev_volume
                    percentage_volume_change = (volume_change / prev_volume * 100) if prev_volume else 0

                    consecutive_rise = 0
                    if len(prices) >= 3 and prices[0][1] > prices[1][1] > prices[2][1]:
                        consecutive_rise = 2 + (1 if len(prices) >= 4 and prices[2][1] > prices[3][1] else 0)
                    consecutive_fall = 0
                    if len(prices) >= 3 and prices[0][1] < prices[1][1] < prices[2][1]:
                        consecutive_fall = 2 + (1 if len(prices) >= 4 and prices[2][1] < prices[3][1] else 0)

                    output.append((
                        f"{table_name} {name}", percentage_change, latest_volume, percentage_volume_change, consecutive_rise, consecutive_fall
                    ))
                except Exception as e:
                    log_error_with_timestamp(f"{name}: {str(e)}", error_file_path)

    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        # 写 TXT
        with open(output_path, 'w', encoding='utf-8') as txtfile:
            for entry in output:
                sector, company = entry[0].rsplit(' ', 1)
                pct_change, vol, pct_vol_change, cr, cf = entry[1:]
                original = company
                
                # 标注
                if original in earnings_new: company += f".{earnings_new[original]}"
                if original in earnings_next: company += f".{earnings_next[original]}"
                if original in earnings_third: company += f".{earnings_third[original]}"
                if original in earnings_fourth: company += f".{earnings_fourth[original]}"
                if original in earnings_fifth: company += f".{earnings_fifth[original]}"
                
                if vol > 5_000_000: company += '.*'
                if original in gainers: company += '.>'
                elif original in losers: company += '.<'
                
                if cr == 2: company += '.+'
                elif cr == 3: company += '.++'
                if cf == 2: company += '.-'
                elif cf == 3: company += '.--'

                tags = symbol_to_tags.get(original, [])
                tags_str = ', '.join(tags)
                sector_p = pad_display(sector, 25, 'left')
                company_p = pad_display(company, 15, 'left')
                txtfile.write(f"{sector_p}{company_p}: {pct_change:>6.2f}%  {tags_str}\n")
        
        # 顺便写 CSV
        # csv_path = os.path.splitext(output_path)[0] + '.csv'
        # with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        #     writer = csv.writer(csvfile)
        #     writer.writerow(['Sector', 'Company', 'Change(%)', 'Tags'])
        #     for entry in output:
        #         sector, company = entry[0].rsplit(' ', 1)
        #         pct_change, vol, pct_vol_change, cr, cf = entry[1:]
        #         original = company
                
        #         if original in earnings_new: company += f".{earnings_new[original]}"
        #         if original in earnings_next: company += f".{earnings_next[original]}"
        #         if original in earnings_third: company += f".{earnings_third[original]}"
        #         if original in earnings_fourth: company += f".{earnings_fourth[original]}"
        #         if original in earnings_fifth: company += f".{earnings_fifth[original]}"
        #         if vol > 5_000_000: company += '.*'
        #         if original in gainers: company += '.>'
        #         elif original in losers: company += '.<'
        #         if cr == 2: company += '.+'
        #         elif cr == 3: company += '.++'
        #         if cf == 2: company += '.-'
        #         elif cf == 3: company += '.--'
                
        #         tags = symbol_to_tags.get(original, [])
        #         tags_str = ', '.join(tags)
        #         writer.writerow([sector, company, f"{pct_change:.2f}", tags_str])
        
        print(f"Compare_Stocks 完成。生成: {output_path}")
    else:
        log_error_with_timestamp("Compare_Stocks 输出为空。", error_file_path)

# ==========================================
# 模块 3: Compare_ETFs 逻辑
# ==========================================

def get_latest_four_dates_etf(cursor, table_name, name):
    query = f"SELECT date FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 4"
    cursor.execute(query, (name,))
    return cursor.fetchall()

def get_prices_four_days_etf(cursor, table_name, name, dates):
    query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? AND date IN (?, ?, ?, ?) ORDER BY date DESC"
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def run_compare_etfs(config_path, description_path, blacklist, interested_sectors, db_path, output_path, error_file_path):
    print("--- 开始执行: Compare_ETFs ---")
    with open(config_path, 'r') as file:
        data = json.load(file)
    with open(description_path, 'r') as file:
        description_data = json.load(file)

    symbol_to_tags = {}
    for item in description_data.get("stocks", []) + description_data.get("etfs", []):
        symbol_to_tags[item["symbol"]] = item.get("tag", [])

    output = []
    with create_connection(db_path) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name in interested_sectors:
                for name in names:
                    if name in blacklist:
                        continue
                    try:
                        results = get_latest_four_dates_etf(cursor, table_name, name)
                        if len(results) < 4:
                            raise ValueError(f"无法找到 {table_name} 下的 {name} 足够的历史数据进行比较。")
                        dates = [result[0] for result in results]
                        prices = get_prices_four_days_etf(cursor, table_name, name, dates)
                        if len(prices) == 4:
                            latest_price, second_latest_price = prices[0][1], prices[1][1]
                            latest_volume, second_latest_volume = prices[0][2], prices[1][2]
                            change = latest_price - second_latest_price
                            percentage_change = (change / second_latest_price) * 100
                            volume_change = latest_volume - second_latest_volume
                            percentage_volume_change = (volume_change / second_latest_volume) * 100

                            consecutive_rise = 0
                            if prices[0][1] > prices[1][1] and prices[1][1] > prices[2][1]:
                                consecutive_rise = 2
                                if prices[2][1] > prices[3][1]: consecutive_rise = 3
                            
                            consecutive_fall = 0
                            if prices[0][1] < prices[1][1] and prices[1][1] < prices[2][1]:
                                consecutive_fall = 2
                                if prices[2][1] < prices[3][1]: consecutive_fall = 3

                            output.append((f"{table_name} {name}", percentage_change, latest_volume, percentage_volume_change, consecutive_rise, consecutive_fall))
                        else:
                            raise ValueError(f"无法比较 {table_name} 下的 {name}，因为缺少必要的数据。")
                    except Exception as e:
                        log_error_with_timestamp(str(e), error_file_path)

    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        with open(output_path, 'w') as file:
            for line in output:
                sector, company = line[0].rsplit(' ', 1)
                percentage_change, latest_volume, percentage_volume_change, consecutive_rise, consecutive_fall = line[1], line[2], line[3], line[4], line[5]
                
                original_company = company
                if latest_volume > 3000000: company += '.*'
                if consecutive_rise == 2: company += '.+'
                elif consecutive_rise == 3: company += '.++'
                if consecutive_fall == 2: company += '.-'
                elif consecutive_fall == 3: company += '.--'
                
                tags = symbol_to_tags.get(original_company, [])
                tags_str = ', '.join(f'{tag}' for tag in tags)
                
                file.write(f"{company:<10}: {percentage_change:>6.2f}%   {latest_volume:<10} {percentage_volume_change:>7.2f}%   {tags_str}\n")
        print(f"Compare_ETFs 完成。生成: {output_path}")
    else:
        log_error_with_timestamp("ETFs 输出为空。", error_file_path)


# ==========================================
# 主执行逻辑
# ==========================================

if __name__ == '__main__':
    # --- 共享路径配置 ---
    config_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
    description_path = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
    gainer_loser_path = '/Users/yanzhang/Coding/Financial_System/Modules/Gainer_Loser.json'
    db_path = '/Users/yanzhang/Coding/Database/Finance.db'
    
    # 财报文件
    earning_file_new = '/Users/yanzhang/Coding/News/Earnings_Release_new.txt'
    earning_file_next = '/Users/yanzhang/Coding/News/Earnings_Release_next.txt'
    earning_file_third = '/Users/yanzhang/Coding/News/Earnings_Release_third.txt'
    earning_file_fourth = '/Users/yanzhang/Coding/News/Earnings_Release_fourth.txt'
    earning_file_fifth = '/Users/yanzhang/Coding/News/Earnings_Release_fifth.txt'
    
    # 错误日志
    error_file_path = '/Users/yanzhang/Coding/News/Today_error.txt'
    # 备份目录
    directory_backup = '/Users/yanzhang/Coding/News/backup/site/'

    # ----------------------------------------
    # 1. 执行 Compare_All
    # ----------------------------------------
    output_file_all = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
    additional_output_file_all = '/Users/yanzhang/Coding/Website/economics/compare_all.txt'
    
    try:
        run_compare_all(
            config_path, output_file_all, gainer_loser_path,
            earning_file_new, earning_file_next, earning_file_third, earning_file_fourth, earning_file_fifth,
            error_file_path, additional_output_file_all
        )
    except Exception as e:
        print(f"Error in Compare_All: {e}")

    # ----------------------------------------
    # 2. 执行 Compare_Stocks
    # ----------------------------------------
    file_path_txt_stocks = '/Users/yanzhang/Coding/News/CompareStock.txt'
    # file_path_csv_stocks = os.path.splitext(file_path_txt_stocks)[0] + '.csv' # 屏蔽 CSV 路径
    
    blacklist_stocks = []
    interested_sectors_stocks = [
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    ]

    # Stocks 备份逻辑 (仅备份 TXT)
    if os.path.exists(file_path_txt_stocks):
        ts = (datetime.now() - timedelta(days=1)).strftime('%y%m%d')
        d, fn = os.path.split(file_path_txt_stocks)
        name, ext = os.path.splitext(fn)
        new_fn = f"{name}_{ts}{ext}"
        os.rename(file_path_txt_stocks, os.path.join(directory_backup, new_fn))
        print(f"Stock TXT 已备份为: {new_fn}")
    
    # if os.path.exists(file_path_csv_stocks):
    #     ts = (datetime.now() - timedelta(days=1)).strftime('%y%m%d')
    #     d, fn = os.path.split(file_path_csv_stocks)
    #     name, ext = os.path.splitext(fn)
    #     new_fn = f"{name}_{ts}{ext}"
    #     os.rename(file_path_csv_stocks, os.path.join(directory_backup, new_fn))
    #     print(f"Stock CSV 已备份为: {new_fn}")

    try:
        run_compare_stocks(
            config_path, description_path, blacklist_stocks, interested_sectors_stocks, db_path,
            earning_file_new, earning_file_next, earning_file_third, earning_file_fourth, earning_file_fifth,
            gainer_loser_path, file_path_txt_stocks, error_file_path
        )
        # 清理逻辑：只清理 .txt
        clean_old_backups(directory_backup, prefix="CompareStock_", days=4, exts=['.txt'])
    except Exception as e:
        print(f"Error in Compare_Stocks: {e}")

    # ----------------------------------------
    # 3. 执行 Compare_ETFs
    # ----------------------------------------
    file_path_etfs = '/Users/yanzhang/Coding/News/CompareETFs.txt'
    blacklist_etfs = ["ERY","TQQQ","QLD","SOXL","SPXL","SVXY","YINN","CHAU","UVXY",
                "VIXY","VXX","SPXS","SPXU","ZSL","AGQ","SCO","TMF","SOXS",
                "BOIL","TWM","KOLD","TMV"]
    interested_sectors_etfs = ["ETFs"]

    # ETFs 备份逻辑
    if os.path.exists(file_path_etfs):
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%y%m%d')
        directory, filename = os.path.split(file_path_etfs)
        name, extension = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{extension}"
        new_file_path = os.path.join(directory_backup, new_filename)
        os.rename(file_path_etfs, new_file_path)
        print(f"ETF 文件已重命名为: {new_file_path}")

    try:
        run_compare_etfs(
            config_path, description_path, blacklist_etfs, interested_sectors_etfs,
            db_path, file_path_etfs, error_file_path
        )
        # 清理逻辑：只清理 .txt
        clean_old_backups(directory_backup, prefix="CompareETFs_", days=4, exts=['.txt'])
    except Exception as e:
        print(f"Error in Compare_ETFs: {e}")