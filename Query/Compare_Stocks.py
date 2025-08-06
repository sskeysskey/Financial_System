from datetime import datetime, timedelta
import sqlite3
import json
import os
from wcwidth import wcswidth
import re

def pad_display(s: str, width: int, align: str = 'left') -> str:
    """按照真实列宽（CJK=2，ASCII=1）来给 s 补空格到 width 列."""
    cur = wcswidth(s)
    if cur >= width:
        return s
    pad = width - cur
    if align == 'left':
        return s + ' ' * pad
    else:
        return ' ' * pad + s
    
def create_connection(db_file):
    return sqlite3.connect(db_file)

def log_error_with_timestamp(error_message, error_file_path):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(error_file_path, 'a') as error_file:
        error_file.write(f"[{timestamp}] {error_message}\n")

def read_earnings_release(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}

    # BMO→前，AMC→后，TNS→未
    period_map = {'BMO': '前', 'AMC': '后', 'TNS': '未', 'TAS': '未'}

    earnings_companies = {}

    with open(filepath, 'r') as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split(':')]
            # 期望 parts = [symbol, period, date]
            if len(parts) >= 3:
                company = parts[0]
                period = parts[1]
                date_str = parts[-1]

                m = re.match(r'(\d{4})-(\d{2})-(\d{2})$', date_str)
                if m:
                    day = m.group(3)  # “dd”
                    # 映射到“前/后/未”
                    suffix = period_map.get(period)
                    if suffix:
                        earnings_companies[company] = f"{day}{suffix}"
                    else:
                        log_error_with_timestamp(
                            f"第 {line_number} 行未知的 period: '{period}'",
                            error_file_path
                        )
                        # 退而只取 day
                        earnings_companies[company] = day
                else:
                    log_error_with_timestamp(
                        f"第 {line_number} 行日期格式不对: '{date_str}'",
                        error_file_path
                    )
            else:
                log_error_with_timestamp(
                    f"第 {line_number} 行无法解析: '{line}'",
                    error_file_path
                )

    return earnings_companies

def read_gainers_losers(filepath):
    if not os.path.exists(filepath):
        return [], []

    with open(filepath, 'r') as file:
        data = json.load(file)
        
    if not data:
        return [], []

    today_date = datetime.now().strftime("%Y-%m-%d")
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 尝试获取今天的数据
    if today_date in data:
        return data[today_date].get('gainer', []), data[today_date].get('loser', [])
    # 如果今天的数据不存在，尝试获取昨天的数据
    elif yesterday_date in data:
        return data[yesterday_date].get('gainer', []), data[yesterday_date].get('loser', [])
    else:
        return [], []

def get_latest_available_dates(cursor, table_name, name, limit=4):
    query = f"""
    SELECT date FROM {table_name}
    WHERE name = ? 
    ORDER BY date DESC
    LIMIT ?
    """
    cursor.execute(query, (name, limit))
    return cursor.fetchall()

def get_prices_available_days(cursor, table_name, name, dates):
    placeholders = ', '.join('?' for _ in dates)
    query = f"""
    SELECT date, price, volume FROM {table_name}
    WHERE name = ? AND date IN ({placeholders})
    ORDER BY date DESC
    """
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def compare_today_yesterday(config_path,
                            description_path,
                            blacklist,
                            interested_sectors,
                            db_path,
                            earnings_new_path,
                            earnings_next_path,
                            gainers_losers_path,
                            output_path,
                            error_file_path):
    # 读取配置和描述
    with open(config_path, 'r') as file:
        data = json.load(file)
    with open(description_path, 'r') as file:
        description_data = json.load(file)

    # 读取两份财报文件
    earnings_new = read_earnings_release(earnings_new_path, error_file_path)
    earnings_next = read_earnings_release(earnings_next_path, error_file_path)

    gainers, losers = read_gainers_losers(gainers_losers_path)

    # 构建 symbol -> tags 映射
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
                    log_error_with_timestamp(f"跳过黑名单中的股票: {name}", error_file_path)
                    continue
                try:
                    # 获取最新可用的日期列表
                    date_rows = get_latest_available_dates(cursor, table_name, name)
                    if len(date_rows) < 2:
                        raise ValueError(f"无法找到 {table_name} 下的 {name} 足够的历史数据进行比较。")
                    dates = [r[0] for r in date_rows]
                    prices = get_prices_available_days(cursor, table_name, name, dates)
                    if len(prices) < 2:
                        raise ValueError(f"无法比较 {table_name} 下的 {name}，因为缺少必要的数据。")

                    # 计算价格及成交量变化
                    latest_price, latest_volume = prices[0][1], prices[0][2]
                    prev_price, prev_volume = prices[1][1], prices[1][2]
                    change = latest_price - prev_price
                    percentage_change = (change / prev_price * 100) if prev_price else 0
                    volume_change = latest_volume - prev_volume
                    percentage_volume_change = (volume_change / prev_volume * 100) if prev_volume else 0

                    # 连续涨跌
                    consecutive_rise = 0
                    if len(prices) >= 3 and prices[0][1] > prices[1][1] > prices[2][1]:
                        consecutive_rise = 2 + (1 if len(prices) >= 4 and prices[2][1] > prices[3][1] else 0)
                    consecutive_fall = 0
                    if len(prices) >= 3 and prices[0][1] < prices[1][1] < prices[2][1]:
                        consecutive_fall = 2 + (1 if len(prices) >= 4 and prices[2][1] < prices[3][1] else 0)

                    output.append((
                        f"{table_name} {name}",
                        percentage_change,
                        latest_volume,
                        percentage_volume_change,
                        consecutive_rise,
                        consecutive_fall
                    ))
                except Exception as e:
                    log_error_with_timestamp(str(e), error_file_path)

    # 生成输出文件
    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        with open(output_path, 'w') as file:
            for entry in output:
                sector, company = entry[0].rsplit(' ', 1)
                pct_change, vol, pct_vol_change, cr, cf = entry[1:]
                original = company

                # 来自 earnings_new 的标注
                if original in earnings_new:
                    company += f".{earnings_new[original]}"
                # 来自 earnings_next 的标注
                if original in earnings_next:
                    company += f".{earnings_next[original]}"

                # 大成交量标记
                if vol > 5_000_000:
                    company += '.*'
                # 涨跌家数标记
                if original in gainers:
                    company += '.>'
                elif original in losers:
                    company += '.<'

                # 连续涨跌标记
                if cr == 2:
                    company += '.+'
                elif cr == 3:
                    company += '.++'
                if cf == 2:
                    company += '.-'
                elif cf == 3:
                    company += '.--'

                # 标签
                tags = symbol_to_tags.get(original, [])
                tags_str = ', '.join(tags)

                # 按「25 列」补齐 sector，按「15 列」补齐 company
                sector_p = pad_display(sector, 25, 'left')
                company_p = pad_display(company, 15, 'left')
                file.write(f"{sector_p}{company_p}: {pct_change:>6.2f}%  {tags_str}\n")

        print(f"{output_path} 已生成。")
    else:
        log_error_with_timestamp("输出为空，无法进行保存文件操作。", error_file_path)

def clean_old_backups(directory, prefix="CompareStock_", days=4):
    """删除备份目录中超过指定天数的文件"""
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    for filename in os.listdir(directory):
        if not filename.startswith(prefix):
            continue
        try:
            date_str = filename.split('_')[-1].split('.')[0]
            file_date = datetime.strptime(date_str, '%y%m%d').replace(year=now.year)
            if file_date < cutoff:
                os.remove(os.path.join(directory, filename))
                print(f"删除旧备份文件：{filename}")
        except Exception as e:
            print(f"跳过文件：{filename}，原因：{e}")

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
    description_path = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
    blacklist = []
    interested_sectors = [
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    ]
    file_path = '/Users/yanzhang/Coding/News/CompareStock.txt'
    directory_backup = '/Users/yanzhang/Coding/News/backup/site/'
    error_file_path = '/Users/yanzhang/Coding/News/Today_error.txt'

    # 备份并重命名昨日的 CompareStock.txt
    if os.path.exists(file_path):
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%y%m%d')
        directory, filename = os.path.split(file_path)
        name, ext = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{ext}"
        new_file_path = os.path.join(directory_backup, new_filename)
        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
    else:
        print("文件不存在")

    compare_today_yesterday(
        config_path,
        description_path,
        blacklist,
        interested_sectors,
        '/Users/yanzhang/Coding/Database/Finance.db',
        '/Users/yanzhang/Coding/News/Earnings_Release_new.txt',
        '/Users/yanzhang/Coding/News/Earnings_Release_next.txt',
        '/Users/yanzhang/Coding/Financial_System/Modules/Gainer_Loser.json',
        file_path,
        error_file_path
    )

    clean_old_backups(directory_backup)