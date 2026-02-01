import os
import json
import sqlite3
import re
import shutil
import sys
from datetime import datetime, timedelta, date
from collections import OrderedDict

# ==============================================================================
# 全局配置 & 依赖检查
# ==============================================================================

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 程序二 (Volume Scanner) 的核心配置 ---
LOOKBACK_YEARS = 0.5  # 1 代表一年, 0.5 代表半年...

# 第三方库依赖
try:
    from wcwidth import wcswidth
    from dateutil.relativedelta import relativedelta
except ImportError as e:
    print(f"缺少必要的库: {e}")
    print("请确保已安装: pip install wcwidth python-dateutil")
    exit(1)

# 获取当前用户的家目录 (例如 /Users/yanzhang)
HOME = USER_HOME

# ==============================================================================
# PART 1: Compare_Combined 逻辑
# ==============================================================================

class ConfigCompare:
    # 基础路径动态化
    BASE_NEWS_DIR = os.path.join(BASE_CODING_DIR, 'News')
    BASE_MODULES_DIR = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules')
    BASE_DB_DIR = os.path.join(BASE_CODING_DIR, 'Database')
    
    # 财报文件路径列表
    EARNINGS_FILES = [
        os.path.join(BASE_NEWS_DIR, 'Earnings_Release_new.txt'),
        os.path.join(BASE_NEWS_DIR, 'Earnings_Release_next.txt'),
        os.path.join(BASE_NEWS_DIR, 'Earnings_Release_third.txt'),
        os.path.join(BASE_NEWS_DIR, 'Earnings_Release_fourth.txt'),
        os.path.join(BASE_NEWS_DIR, 'Earnings_Release_fifth.txt')
    ]
    
    # JSON 配置文件
    COLOR_JSON_PATH = os.path.join(BASE_MODULES_DIR, 'Colors.json')
    SECTORS_ALL_JSON_PATH = os.path.join(BASE_MODULES_DIR, 'Sectors_All.json')
    DESCRIPTION_PATH = os.path.join(BASE_MODULES_DIR, 'description.json')
    GAINER_LOSER_PATH = os.path.join(BASE_MODULES_DIR, 'Gainer_Loser.json')
    
    # 数据库
    DB_PATH = os.path.join(BASE_DB_DIR, 'Finance.db')
    
    # 输出与日志
    ERROR_FILE_PATH = os.path.join(BASE_NEWS_DIR, 'Today_error.txt')
    DIRECTORY_BACKUP = os.path.join(BASE_NEWS_DIR, 'backup/site/')
    
    # Compare_All 输出
    OUTPUT_FILE_ALL = os.path.join(BASE_NEWS_DIR, 'backup/Compare_All.txt')
    ADDITIONAL_OUTPUT_FILE_ALL = os.path.join(BASE_CODING_DIR, 'Website/economics/compare_all.txt')
    
    # Compare_Stocks 输出
    FILE_PATH_TXT_STOCKS = os.path.join(BASE_NEWS_DIR, 'CompareStock.txt')
    
    # Compare_ETFs 输出
    FILE_PATH_ETFS = os.path.join(BASE_NEWS_DIR, 'CompareETFs.txt')

# --- Compare 模块辅助函数 ---

def create_connection_compare(db_file):
    return sqlite3.connect(db_file, timeout=60.0)

def log_error_compare(error_message, file_path=None):
    """通用错误记录函数 (Compare版)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    formatted_message = f"[{timestamp}] {error_message}\n"
    if file_path:
        with open(file_path, 'a') as error_file:
            error_file.write(formatted_message)
    return formatted_message

def clean_backups_compare(directory, prefix, days=4, exts=None):
    """通用清理备份函数 (Compare版)"""
    if exts is None:
        exts = ['.txt'] 
        
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
        
        # 检查后缀
        if check_ext and ext.lower() not in exts:
            continue

        try:
            # 尝试提取日期
            date_part = filename[len(prefix):].split('.')[0]
            if date_part.startswith('_'):
                date_part = date_part[1:]
                
            file_date = datetime.strptime(date_part, '%y%m%d')
            file_date = file_date.replace(year=now.year)
            
            if file_date < cutoff:
                file_path = os.path.join(directory, filename)
                os.remove(file_path)
                print(f"删除旧备份文件：{filename}")
        except Exception as e:
            pass

def pad_display(s: str, width: int, align: str = 'left') -> str:
    cur = wcswidth(s)
    if cur >= width:
        return s
    pad = width - cur
    if align == 'left':
        return s + ' ' * pad
    else:
        return ' ' * pad + s

def parse_earnings_release(file_path):
    symbols = set()
    try:
        with open(file_path, 'r') as file:
            for line in file:
                parts = line.strip().split(':')
                if parts and parts[0].strip():
                    symbols.add(parts[0].strip())
    except FileNotFoundError:
        print(f"文件未找到: {file_path}")
    except Exception as e:
        print(f"读取文件时发生错误 ({file_path}): {e}")
    return symbols

# --- Compare 核心逻辑函数 ---

def run_update_colors():
    print("--- 开始执行: Update Colors ---")
    
    earnings_symbols = set()
    for path in ConfigCompare.EARNINGS_FILES:
        earnings_symbols |= parse_earnings_release(path)

    try:
        with open(ConfigCompare.SECTORS_ALL_JSON_PATH, 'r', encoding='utf-8') as file:
            sectors_data = json.load(file)
            economics_symbols = set(sectors_data.get('Economics', []))
    except Exception as e:
        print(f"读取 Sectors_All 错误: {e}")
        economics_symbols = set()

    try:
        with open(ConfigCompare.COLOR_JSON_PATH, 'r', encoding='utf-8') as file:
            colors = json.load(file)
    except Exception as e:
        print(f"读取 Colors 错误: {e}")
        colors = {}

    if 'red_keywords' not in colors:
        colors['red_keywords'] = []

    existing_reds = set(colors.get('red_keywords', []))
    kept_keywords = existing_reds & economics_symbols
    final_keywords = list(kept_keywords)
    
    for symbol in earnings_symbols:
        if symbol and symbol not in final_keywords:
            final_keywords.append(symbol)
            
    colors['red_keywords'] = final_keywords

    try:
        with open(ConfigCompare.COLOR_JSON_PATH, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)
        print(f"Update Colors 完成。已更新: {ConfigCompare.COLOR_JSON_PATH}")
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

def read_latest_date_info_all(gainer_loser_path):
    if not os.path.exists(gainer_loser_path):
        return None, {"gainer": [], "loser": []}
    with open(gainer_loser_path, 'r') as f:
        data = json.load(f)
    if not data:
        return None, {"gainer": [], "loser": []}
    latest_date = max(data.keys())
    return latest_date, data[latest_date]

def read_earnings_release_for_all(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_compare(f"文件 {filepath} 不存在。", error_file_path)
        return {}
    earnings_companies = {}
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = [p.strip() for p in line.split(':')]
                if len(parts) == 3:
                    company, rel_type, date = parts
                    
                    # 假设日期格式为 YYYY-MM-DD
                    date_parts = date.split('-')
                    if len(date_parts) >= 3:
                        # 提取 月(索引1) 和 日(索引2) 拼接，例如 '12' + '21' = '1221'
                        day = f"{date_parts[1]}{date_parts[2]}"
                    else:
                        # 防止格式不对导致报错，保留原逻辑或原样返回
                        day = date_parts[-1] 

                    earnings_companies[company] = {
                        'day': day,
                        'type': rel_type
                    }
    except Exception as e:
        log_error_compare(f"处理文件 {filepath} 时发生错误: {e}", error_file_path)
    return earnings_companies

def run_compare_all():
    print("--- 开始执行: Compare_All ---")
    type_map = {'BMO': '前', 'AMC': '后', 'TNS': '未'}
    
    latest_date, latest_info = read_latest_date_info_all(ConfigCompare.GAINER_LOSER_PATH)
    gainers = latest_info.get("gainer", []) if isinstance(latest_info, dict) else []
    losers = latest_info.get("loser", []) if isinstance(latest_info, dict) else []
    
    earnings_data = {}
    for file_path in ConfigCompare.EARNINGS_FILES:
        data_from_file = read_earnings_release_for_all(file_path, ConfigCompare.ERROR_FILE_PATH)
        earnings_data.update(data_from_file)

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    is_recent = False
    if latest_date:
        try:
            latest_date_date = datetime.strptime(latest_date, "%Y-%m-%d").date()
            is_recent = latest_date_date in (today, yesterday)
        except:
            is_recent = False

    if not os.path.exists(ConfigCompare.SECTORS_ALL_JSON_PATH):
        return

    with open(ConfigCompare.SECTORS_ALL_JSON_PATH, 'r') as f:
        config_data = json.load(f)

    output = []
    
    for table_name, keywords in config_data.items():
        for keyword in sorted(keywords):
            try:
                with sqlite3.connect(ConfigCompare.DB_PATH, timeout=60.0) as conn:
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
                        continue # Skip silently if not enough data
                    
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
            except Exception as e:
                log_error_compare(str(e), ConfigCompare.ERROR_FILE_PATH)

    with open(ConfigCompare.OUTPUT_FILE_ALL, 'w') as file:
        for line in output:
            file.write(line + '\n')
            
    if ConfigCompare.ADDITIONAL_OUTPUT_FILE_ALL:
        try:
            with open(ConfigCompare.ADDITIONAL_OUTPUT_FILE_ALL, 'w') as file:
                for line in output:
                    file.write(line + '\n')
        except Exception as e:
             print(f"Warning: 无法写入额外路径 {ConfigCompare.ADDITIONAL_OUTPUT_FILE_ALL}: {e}")
    print(f"Compare_All 完成。生成: {ConfigCompare.OUTPUT_FILE_ALL}")

def read_earnings_release_for_stocks(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_compare(f"文件 {filepath} 不存在。", error_file_path)
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
                    # 修改为提取 月(group 2) + 日(group 3)
                    day = f"{m.group(2)}{m.group(3)}" 
                    suffix = period_map.get(period)
                    if suffix:
                        earnings_companies[company] = f"{day}{suffix}"
                    else:
                        log_error_compare(f"第 {line_number} 行未知的 period: '{period}'", error_file_path)
                        earnings_companies[company] = day
                else:
                    log_error_compare(f"第 {line_number} 行日期格式不对: '{date_str}'", error_file_path)
            else:
                log_error_compare(f"第 {line_number} 行无法解析: '{line}'", error_file_path)
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

def run_compare_stocks(blacklist, interested_sectors):
    print("--- 开始执行: Compare_Stocks ---")
    with open(ConfigCompare.SECTORS_ALL_JSON_PATH, 'r') as file:
        data = json.load(file)
    with open(ConfigCompare.DESCRIPTION_PATH, 'r') as file:
        description_data = json.load(file)

    earnings_maps = []
    for fpath in ConfigCompare.EARNINGS_FILES:
        earnings_maps.append(read_earnings_release_for_stocks(fpath, ConfigCompare.ERROR_FILE_PATH))
    
    earnings_new, earnings_next, earnings_third, earnings_fourth, earnings_fifth = earnings_maps
    gainers, losers = read_gainers_losers_stocks(ConfigCompare.GAINER_LOSER_PATH)
    
    symbol_to_tags = {}
    for item in description_data.get("stocks", []) + description_data.get("etfs", []):
        symbol_to_tags[item["symbol"]] = item.get("tag", [])
        
    output = []
    with create_connection_compare(ConfigCompare.DB_PATH) as conn:
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
                        continue
                    dates = [r[0] for r in date_rows]
                    prices = get_prices_available_days(cursor, table_name, name, dates)
                    if len(prices) < 2:
                        continue

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
                    log_error_compare(f"{name}: {str(e)}", ConfigCompare.ERROR_FILE_PATH)

    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        with open(ConfigCompare.FILE_PATH_TXT_STOCKS, 'w', encoding='utf-8') as txtfile:
            for entry in output:
                sector, company = entry[0].rsplit(' ', 1)
                pct_change, vol, pct_vol_change, cr, cf = entry[1:]
                original = company
                
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
        print(f"Compare_Stocks 完成。生成: {ConfigCompare.FILE_PATH_TXT_STOCKS}")
    else:
        log_error_compare("Compare_Stocks 输出为空。", ConfigCompare.ERROR_FILE_PATH)

def get_latest_four_dates_etf(cursor, table_name, name):
    query = f"SELECT date FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 4"
    cursor.execute(query, (name,))
    return cursor.fetchall()

def get_prices_four_days_etf(cursor, table_name, name, dates):
    query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? AND date IN (?, ?, ?, ?) ORDER BY date DESC"
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def run_compare_etfs(blacklist, interested_sectors):
    print("--- 开始执行: Compare_ETFs ---")
    with open(ConfigCompare.SECTORS_ALL_JSON_PATH, 'r') as file:
        data = json.load(file)
    with open(ConfigCompare.DESCRIPTION_PATH, 'r') as file:
        description_data = json.load(file)
        
    symbol_to_tags = {}
    for item in description_data.get("stocks", []) + description_data.get("etfs", []):
        symbol_to_tags[item["symbol"]] = item.get("tag", [])
        
    output = []
    with create_connection_compare(ConfigCompare.DB_PATH) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name in interested_sectors:
                for name in names:
                    if name in blacklist:
                        continue
                    try:
                        results = get_latest_four_dates_etf(cursor, table_name, name)
                        if len(results) < 4:
                            continue
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
                    except Exception as e:
                        log_error_compare(str(e), ConfigCompare.ERROR_FILE_PATH)
    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        with open(ConfigCompare.FILE_PATH_ETFS, 'w') as file:
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
        print(f"Compare_ETFs 完成。生成: {ConfigCompare.FILE_PATH_ETFS}")
    else:
        log_error_compare("ETFs 输出为空。", ConfigCompare.ERROR_FILE_PATH)

def execute_compare_process():
    """Compare 模块的总入口"""
    print("\n" + "="*50)
    print("STEP 1: 执行 Compare_Combined 逻辑")
    print("="*50)

    # 1. 更新颜色
    run_update_colors()
    print("\n" + "-"*30 + "\n")

    # 2. 执行 Compare_All
    try:
        run_compare_all()
    except Exception as e:
        print(f"Error in Compare_All: {e}")

    # 3. 执行 Compare_Stocks
    blacklist_stocks = []
    interested_sectors_stocks = [
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    ]
    
    if os.path.exists(ConfigCompare.FILE_PATH_TXT_STOCKS):
        ts = (datetime.now() - timedelta(days=1)).strftime('%y%m%d')
        d, fn = os.path.split(ConfigCompare.FILE_PATH_TXT_STOCKS)
        name, ext = os.path.splitext(fn)
        new_fn = f"{name}_{ts}{ext}"
        try:
            if not os.path.exists(ConfigCompare.DIRECTORY_BACKUP):
                os.makedirs(ConfigCompare.DIRECTORY_BACKUP)
            os.rename(ConfigCompare.FILE_PATH_TXT_STOCKS, os.path.join(ConfigCompare.DIRECTORY_BACKUP, new_fn))
            print(f"Stock TXT 已备份为: {new_fn}")
        except OSError as e:
            print(f"备份失败: {e}")

    try:
        run_compare_stocks(blacklist_stocks, interested_sectors_stocks)
        clean_backups_compare(ConfigCompare.DIRECTORY_BACKUP, prefix="CompareStock_", days=4, exts=['.txt'])
    except Exception as e:
        print(f"Error in Compare_Stocks: {e}")

    # 4. 执行 Compare_ETFs
    blacklist_etfs = ["ERY","TQQQ","QLD","SOXL","SPXL","SVXY","YINN","CHAU","UVXY",
                "VIXY","VXX","SPXS","SPXU","ZSL","AGQ","SCO","TMF","SOXS",
                "BOIL","TWM","KOLD","TMV"]
    interested_sectors_etfs = ["ETFs"]
    
    if os.path.exists(ConfigCompare.FILE_PATH_ETFS):
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%y%m%d')
        directory, filename = os.path.split(ConfigCompare.FILE_PATH_ETFS)
        name, extension = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{extension}"
        try:
            if not os.path.exists(ConfigCompare.DIRECTORY_BACKUP):
                os.makedirs(ConfigCompare.DIRECTORY_BACKUP)
            new_file_path = os.path.join(ConfigCompare.DIRECTORY_BACKUP, new_filename)
            os.rename(ConfigCompare.FILE_PATH_ETFS, new_file_path)
            print(f"ETF 文件已重命名为: {new_file_path}")
        except OSError as e:
            print(f"备份失败: {e}")

    try:
        run_compare_etfs(blacklist_etfs, interested_sectors_etfs)
        clean_backups_compare(ConfigCompare.DIRECTORY_BACKUP, prefix="CompareETFs_", days=4, exts=['.txt'])
    except Exception as e:
        print(f"Error in Compare_ETFs: {e}")

# ==============================================================================
# PART 2: Analyse_Combined 逻辑
# ==============================================================================

# --- 全局路径配置 (Analyse) 动态化 ---
DB_PATH_ANALYSE = os.path.join(BASE_CODING_DIR, 'Database/Finance.db')
BLACKLIST_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/blacklist.json')
STOCK_SPLITS_FILE = os.path.join(BASE_CODING_DIR, 'News/Stock_Splits_next.txt')
ERROR_LOG_FILE_ANALYSE = os.path.join(BASE_CODING_DIR, 'News/Today_error.txt')

SECTORS_PANEL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System/Modules/Sectors_panel.json")
COLORS_JSON_PATH_ANALYSE = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/Colors.json')

BACKUP_DIR_MAIN = os.path.join(BASE_CODING_DIR, 'News/backup/backup')
BACKUP_DIR_ROOT = os.path.join(BASE_CODING_DIR, 'News/backup')
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

BLACKLIST_GLOB = set(["YNDX"])

# --- Analyse 模块辅助函数 ---

def is_blacklisted(name):
    return name in BLACKLIST_GLOB

def create_connection_analyse(db_file):
    return sqlite3.connect(db_file, timeout=60.0)

def log_error_analyse(error_message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] {error_message}\n"

def log_and_print_error(error_message):
    formatted_error_message = log_error_analyse(error_message)
    print(f"注意！ {error_message}")
    with open(ERROR_LOG_FILE_ANALYSE, 'a') as error_file:
        error_file.write(formatted_error_message)

def load_blacklist_newlow_shared(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file).get("newlow", [])
    except Exception as e:
        print(f"读取黑名单错误: {e}")
        return []

def load_stock_splits_shared(file_path):
    stock_splits_symbols = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if ':' in line:
                    symbol = line.split(':')[0]
                    stock_splits_symbols.add(symbol.strip())
    except Exception as e:
        print(f"读取拆股文件错误 (非致命): {e}")
    return stock_splits_symbols

def get_latest_price_and_date_shared(cursor, table_name, name):
    query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 1"
    cursor.execute(query, (name,))
    return cursor.fetchone()

def update_sectors_panel_json(config_path, updates, blacklist_newlow):
    with open(config_path, 'r', encoding='utf-8') as file:
        data = json.load(file, object_pairs_hook=OrderedDict)
    for category, symbols in updates.items():
        if category in data:
            for symbol in symbols:
                if symbol not in data[category] and symbol not in blacklist_newlow:
                    data[category][symbol] = ""
                    print(f"Panel Update: 将 '{symbol}' 添加到 '{category}'")
                elif symbol in data[category]:
                    pass
                else:
                    print(f"Panel Update: '{symbol}' 在黑名单中，跳过")
        else:
            data[category] = {symbol: "" for symbol in symbols if symbol not in blacklist_newlow}
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def parse_output_generic(output):
    updates = {}
    lines = output.split('\n')
    for line in lines:
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                category = parts[0]
                symbol = parts[1]
                if category in updates:
                    updates[category].append(symbol)
                else:
                    updates[category] = [symbol]
    return updates

def _apply_color_updates_with_priority(color_path, updates, priority_map, log_prefix):
    try:
        with open(color_path, 'r', encoding='utf-8') as file:
            all_colors = json.load(file)
    except: return
    colors = {k: v for k, v in all_colors.items() if k != "red_keywords"}
    symbol_to_color = {}
    for color, symbols in colors.items():
        for s in symbols: symbol_to_color[s] = color
    for cat, names in updates.items():
        if cat not in priority_map: continue
        new_p = priority_map[cat]
        for name in names:
            existing_color = symbol_to_color.get(name)
            if existing_color:
                existing_p = priority_map.get(existing_color, float('inf'))
                if new_p <= existing_p:
                    if name in colors[existing_color]:
                        colors[existing_color].remove(name)
                        if not colors[existing_color]: del colors[existing_color]
                    if cat not in colors: colors[cat] = []
                    colors[cat].append(name)
                    symbol_to_color[name] = cat
                    print(f"[{log_prefix} Color] '{name}' 从 '{existing_color}' 移动到 '{cat}'")
            else:
                if cat not in colors: colors[cat] = []
                colors[cat].append(name)
                symbol_to_color[name] = cat
                print(f"[{log_prefix} Color] '{name}' 添加到 '{cat}'")
    colors["red_keywords"] = all_colors.get("red_keywords", [])
    with open(color_path, 'w', encoding='utf-8') as f:
        json.dump(colors, f, ensure_ascii=False, indent=4)

def clean_backups_analyse(directory, file_patterns):
    if not os.path.exists(directory): return
    now = datetime.now()
    for filename in os.listdir(directory):
        for prefix, date_pos, retention in file_patterns:
            if filename.startswith(prefix):
                try:
                    cutoff = now.replace(hour=0,minute=0,second=0,microsecond=0) - timedelta(days=retention)
                    parts = filename.split('_')
                    date_part = parts[date_pos]
                    date_str = date_part.split('.')[0][-6:] if '.' in date_part else date_part[-6:]
                    file_date = datetime.strptime(date_str, '%y%m%d').replace(hour=0,minute=0,second=0,microsecond=0)
                    
                    if file_date < cutoff:
                        os.remove(os.path.join(directory, filename))
                        print(f"删除旧备份: {filename}")
                    break
                except: pass

# --- Analyse 核心逻辑模块 ---

# 1. Analyse 5000 (Weekly)
PATH_SECTORS_5000 = os.path.join(HOME, 'Coding/Financial_System/Modules/Sectors_5000.json')

def get_price_comparison_5000(cursor, table_name, interval_weeks, name, validate):
    ex_validate = validate - timedelta(days=1)
    past_date = validate - timedelta(weeks=interval_weeks)
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), ex_validate.strftime("%Y-%m-%d"), name))
    result = cursor.fetchone()
    if result and (result[0] is not None and result[1] is not None):
        return result
    return None

def parse_output_color_5000(output):
    updates_color = {}
    lines = output.split('\n')
    for line in lines:
        if not line.strip(): continue
        parts = line.split()
        if len(parts) < 3: continue
        symbol = parts[1]
        descriptor = parts[2]
        category_list = None
        if 'W' in descriptor:
            week_part, _ = descriptor.split('_')
            try:
                weeks = int(week_part.replace('W', ''))
                if weeks in [6, 8, 10]:
                    category_list = 'blue_keywords'
            except ValueError:
                continue
        if category_list:
            if category_list in updates_color:
                if symbol not in updates_color[category_list]:
                    updates_color[category_list].append(symbol)
            else:
                updates_color[category_list] = [symbol]
    return updates_color

def update_color_json_5000(color_config_path, updates_colors):
    color_priority = {
        'black_keywords': 1, 'orange_keywords': 2, 'yellow_keywords': 3,
        'white_keywords': 4, 'blue_keywords': 5 
    }
    _apply_color_updates_with_priority(color_config_path, updates_colors, color_priority, "5000")

def run_logic_5000(blacklist_newlow, stock_splits_symbols):
    print("\n" + "="*40)
    print(">>> 正在执行: Analyse_Stocks_5000 (Weekly)")
    print("="*40)
    with open(PATH_SECTORS_5000, 'r') as file:
        data = json.load(file)
    output = []
    intervals = [6, 8, 10]
    valid_tables = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                    "Industrials", "Real_Estate", "Technology", "Utilities"]
    with create_connection_analyse(DB_PATH_ANALYSE) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name not in valid_tables: continue
            for name in names:
                if is_blacklisted(name): continue
                result = get_latest_price_and_date_shared(cursor, table_name, name)
                if not result:
                    log_and_print_error(f"[5000] 无历史数据: {name}")
                    continue
                validate_str, validate_price = result
                validate = datetime.strptime(validate_str, "%Y-%m-%d")
                price_extremes = {}
                for interval in intervals:
                    res = get_price_comparison_5000(cursor, table_name, interval, name, validate)
                    if res:
                        price_extremes[interval] = res
                for interval in intervals:
                    _, min_price = price_extremes.get(interval, (None, None))
                    if min_price is not None and validate_price <= min_price:
                        if name in stock_splits_symbols:
                            log_and_print_error(f"[5000] {name} 在拆股名单中，跳过。")
                            break
                        output_line = f"{table_name} {name} {interval}W_newlow"
                        print(f"[5000 Output] {output_line}")
                        output.append(output_line)
                        break
    if output:
        final_output = "\n".join(output)
        updates = parse_output_generic(final_output)
        update_sectors_panel_json(SECTORS_PANEL_PATH, updates, blacklist_newlow)
        updates_color = parse_output_color_5000(final_output)
        update_color_json_5000(COLORS_JSON_PATH_ANALYSE, updates_color)

# 2. Analyse 500 (Monthly)
PATH_SECTORS_500 = os.path.join(HOME, 'Coding/Financial_System/Modules/Sectors_500.json')

def get_price_comparison_500(cursor, table_name, interval_months, name, validate):
    ex_validate = validate - timedelta(days=1)
    past_date = validate - relativedelta(months=int(interval_months))
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), ex_validate.strftime("%Y-%m-%d"), name))
    result = cursor.fetchone()
    if result and (result[0] is not None and result[1] is not None):
        return result
    return None

def parse_output_color_500(output):
    updates_color = {}
    lines = output.split('\n')
    for line in lines:
        if not line.strip(): continue
        parts = line.split()
        if len(parts) < 3: continue
        symbol = parts[1]
        descriptor = parts[2]
        category_list = None
        if 'M' in descriptor:
            try:
                months = int(descriptor.split('_')[0].replace('M', ''))
                if months == 5:
                    category_list = 'cyan_keywords'
            except ValueError:
                continue
        if category_list:
            if category_list in updates_color:
                if symbol not in updates_color[category_list]:
                    updates_color[category_list].append(symbol)
            else:
                updates_color[category_list] = [symbol]
    return updates_color

def update_color_json_500(color_config_path, updates_colors):
    color_priority = {
        'black_keywords': 1, 'orange_keywords': 2, 'yellow_keywords': 3,
        'white_keywords': 4, 'cyan_keywords': 5
    }
    _apply_color_updates_with_priority(color_config_path, updates_colors, color_priority, "500")

def run_logic_500(blacklist_newlow, stock_splits_symbols):
    print("\n" + "="*40)
    print(">>> 正在执行: Analyse_Stocks_500 (Monthly)")
    print("="*40)
    with open(PATH_SECTORS_500, 'r') as file:
        data = json.load(file)
    output = []
    intervals = [5]
    valid_tables = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                    "Industrials", "Real_Estate", "Technology", "Utilities"]
    with create_connection_analyse(DB_PATH_ANALYSE) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name not in valid_tables: continue
            for name in names:
                if is_blacklisted(name): continue
                result = get_latest_price_and_date_shared(cursor, table_name, name)
                if not result:
                    log_and_print_error(f"[500] 无历史数据: {name}")
                    continue
                validate_str, validate_price = result
                validate = datetime.strptime(validate_str, "%Y-%m-%d")
                price_extremes = {}
                for interval in intervals:
                    res = get_price_comparison_500(cursor, table_name, interval, name, validate)
                    if res:
                        price_extremes[interval] = res
                for interval in intervals:
                    _, min_price = price_extremes.get(interval, (None, None))
                    if min_price is not None and validate_price <= min_price:
                        if name in stock_splits_symbols:
                            log_and_print_error(f"[500] {name} 在拆股名单中，跳过。")
                            break
                        output_line = f"{table_name} {name} {interval}M_newlow"
                        print(f"[500 Output] {output_line}")
                        output.append(output_line)
                        break
    if output:
        final_output = "\n".join(output)
        updates = parse_output_generic(final_output)
        update_sectors_panel_json(SECTORS_PANEL_PATH, updates, blacklist_newlow)
        updates_color = parse_output_color_500(final_output)
        update_color_json_500(COLORS_JSON_PATH_ANALYSE, updates_color)
    else:
        log_and_print_error("[500] 未检索到符合条件的股票。")

# 3. Analyse 50 (Yearly & Highs)
PATH_SECTORS_ALL = os.path.join(HOME, 'Coding/Financial_System/Modules/Sectors_All.json')
PATH_NEWHIGH_10Y = os.path.join(HOME, 'Coding/Financial_System/Modules/10Y_newhigh.json')
PATH_NEWHIGH_OUTPUT = os.path.join(HOME, 'Coding/News/10Y_newhigh_stock.txt')
PATH_COMPARE_ALL = os.path.join(HOME, 'Coding/News/backup/Compare_All.txt')
PATH_DESCRIPTION = os.path.join(HOME, 'Coding/Financial_System/Modules/description.json')

def get_price_comparison_50(cursor, table_name, interval, name, validate):
    today = datetime.now()
    ex_validate = validate - timedelta(days=1)
    if interval < 1:
        days = int(interval * 30)
        past_date = validate - timedelta(days=days - 1)
    else:
        past_date = today - relativedelta(months=int(interval))
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), ex_validate.strftime("%Y-%m-%d"), name))
    result = cursor.fetchone()
    if result and (result[0] is not None and result[1] is not None):
        return result
    return None

def parse_output_color_50(output):
    updates_color = {}
    lines = output.split('\n')
    for line in lines:
        if line.strip():
            parts = line.split()
            if len(parts) < 3: continue
            symbol = parts[1]
            descriptor = parts[2]
            if 'Y' in descriptor:
                try:
                    years = int(descriptor.split('_')[0].replace('Y', ''))
                    category_list = None
                    if years == 1: category_list = 'white_keywords'
                    elif years == 2: category_list = 'yellow_keywords'
                    elif years == 5: category_list = 'orange_keywords'
                    elif years == 10: category_list = 'black_keywords'
                    
                    if category_list:
                        if category_list in updates_color:
                            if symbol not in updates_color[category_list]:
                                updates_color[category_list].append(symbol)
                        else:
                            updates_color[category_list] = [symbol]
                except ValueError:
                    continue
    return updates_color

def update_color_json_50(color_config_path, updates_colors):
    try:
        with open(color_config_path, 'r', encoding='utf-8') as file:
            all_colors = json.load(file)
    except Exception as e:
        print(f"读取Colors文件错误: {e}")
        return
    colors = {k: v for k, v in all_colors.items() if k != "red_keywords"}
    for category_list, names in updates_colors.items():
        for name in names:
            moved = False
            for key in colors:
                if name in colors[key]:
                    if key != category_list:
                        colors[key].remove(name)
                        print(f"[50 Color] 将 '{name}' 从 '{key}' 移除")
                        moved = True
                    break
            if category_list not in colors:
                colors[category_list] = []
            if name not in colors[category_list]:
                colors[category_list].append(name)
                print(f"[50 Color] 将 '{name}' 添加到 '{category_list}'")
            elif not moved:
                print(f"[50 Color] '{name}' 已在 '{category_list}' 中")
    colors["red_keywords"] = all_colors.get("red_keywords", [])
    try:
        with open(color_config_path, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入Colors文件错误: {e}")

def load_existing_highs_json_50(file_path):
    highs_map = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'stocks' in data and isinstance(data.get('stocks'), list):
            for stock_group in data['stocks']:
                if isinstance(stock_group, dict):
                    for symbol, price_str in stock_group.items():
                        try:
                            highs_map[symbol] = float(price_str)
                        except: pass
    except: return {}
    return highs_map

def read_compare_all_50(file_path):
    compare_data = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' in line:
                    symbol, data = line.strip().split(':', 1)
                    compare_data[symbol.strip()] = data.strip()
    except: pass
    return compare_data

def load_tags_map_50(file_path):
    tag_map = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for section in ['stocks', 'etfs']:
            for item in data.get(section, []):
                symbol = item.get('symbol')
                tags = item.get('tag', [])
                if symbol and tags:
                    tag_map[symbol] = ','.join(tags)
    except Exception as e:
        print(f"读取description.json错误: {e}")
    return tag_map

def process_high_data_output_50(input_lines, compare_data, tag_map):
    processed_lines = []
    for line in input_lines:
        parts = line.split()
        new_line = ""
        symbol = ""
        if len(parts) >= 4:
            sector, symbol, price_str = parts[0], parts[1], parts[-1]
            compare_info = compare_data.get(symbol, '')
            if compare_info: new_line = f"{sector} {symbol} {compare_info} {price_str}"
            else: new_line = f"{sector} {symbol} {price_str}"
        
        if new_line and symbol:
            tags = tag_map.get(symbol, '')
            if tags: final_line = f"{new_line} {tags}"
            else: final_line = new_line
            processed_lines.append(final_line)
    return processed_lines

def run_logic_50(blacklist_newlow, stock_splits_symbols):
    print("\n" + "="*40)
    print(">>> 正在执行: Analyse_Stocks_50 (All Sectors & Highs)")
    print("="*40)
    with open(PATH_SECTORS_ALL, 'r') as file:
        data = json.load(file)
    output = []
    output_high = []
    intervals = [120, 60, 24, 13]
    highintervals = [120]
    existing_highs = load_existing_highs_json_50(PATH_NEWHIGH_10Y)
    
    valid_tables = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                    "Industrials", "Real_Estate", "Technology", "Utilities"]
    with create_connection_analyse(DB_PATH_ANALYSE) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name not in valid_tables: continue
            for name in names:
                if is_blacklisted(name): continue
                result = get_latest_price_and_date_shared(cursor, table_name, name)
                if not result:
                    log_and_print_error(f"[50] 无历史数据: {name}")
                    continue
                validate_str, validate_price = result
                validate = datetime.strptime(validate_str, "%Y-%m-%d")
                price_extremes = {}
                for interval in intervals:
                    res = get_price_comparison_50(cursor, table_name, interval, name, validate)
                    if res:
                        price_extremes[interval] = res
                
                # Check New Highs
                for highinterval in highintervals:
                    max_price, _ = price_extremes.get(highinterval, (None, None))
                    if max_price is not None and validate_price >= max_price:
                        if highinterval >= 12:
                            years = highinterval // 12
                            output_line = f"{table_name} {name} {years}Y_newhigh {validate_price}"
                            output_high.append(output_line)
                # Check New Lows
                for interval in intervals:
                    _, min_price = price_extremes.get(interval, (None, None))
                    if min_price is not None and validate_price <= min_price:
                        if interval >= 12:
                            if name in stock_splits_symbols:
                                log_and_print_error(f"[50] {name} 在拆股名单中，跳过。")
                                break
                            years = interval // 12
                            output_line = f"{table_name} {name} {years}Y_newlow"
                            print(f"[50 Output] {output_line}")
                            output.append(output_line)
                            break
    
    if output:
        final_output = "\n".join(output)
        updates = parse_output_generic(final_output)
        updates_color = parse_output_color_50(final_output)
        update_sectors_panel_json(SECTORS_PANEL_PATH, updates, blacklist_newlow)
        update_color_json_50(COLORS_JSON_PATH_ANALYSE, updates_color)
    else:
        log_and_print_error("[50] 未检索到符合条件的股票 (Lows)。")

    if output_high:
        compare_data = read_compare_all_50(PATH_COMPARE_ALL)
        tag_map = load_tags_map_50(PATH_DESCRIPTION)
        filtered_highs = []
        for line in output_high:
            parts = line.split()
            if len(parts) >= 4:
                symbol = parts[1]
                try: current_price = float(parts[3])
                except: current_price = float('inf')
                old_price = existing_highs.get(symbol)
                if (old_price is None) or (current_price > old_price):
                    filtered_highs.append(line)
        if filtered_highs:
            processed = process_high_data_output_50(filtered_highs, compare_data, tag_map)
            try:
                os.makedirs(os.path.dirname(PATH_NEWHIGH_OUTPUT), exist_ok=True)
                with open(PATH_NEWHIGH_OUTPUT, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(processed))
                print(f"[50] 新高数据已保存: {PATH_NEWHIGH_OUTPUT}")
            except Exception as e:
                print(f"[50] 写入新高文件错误: {e}")

# 4. Analyse HighLow
HL_OUTPUT_PATH = os.path.join(BASE_CODING_DIR, "News/HighLow.txt")
HL_BACKUP_OUTPUT_PATH = os.path.join(BASE_CODING_DIR, "News/backup/HighLow.txt")
HL_JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System/Modules/Sectors_All.json")
HL_TIME_INTERVALS = {
    "[0.5 months]": relativedelta(days=-15),
    "[1 months]":   relativedelta(months=-1),
    "[3 months]":   relativedelta(months=-3),
    "[6 months]":   relativedelta(months=-6),
    "[1Y]":         relativedelta(years=-1),
    "[2Y]":         relativedelta(years=-2),
    "[5Y]":         relativedelta(years=-5)
}

def get_prices_in_range_hl(cursor, table_name, symbol, start_date_str, end_date_str):
    try:
        query = f'SELECT price FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?'
        cursor.execute(query, (symbol, start_date_str, end_date_str))
        return [row[0] for row in cursor.fetchall() if row[0] is not None]
    except Exception as e:
        print(f"[HL] Warning: Could not query price range for {symbol}. {e}")
        return []

def parse_highlow_backup_hl(filepath):
    parsed_data = {label: {"Low": [], "High": []} for label in HL_TIME_INTERVALS.keys()}
    current_label = None
    current_type = None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.startswith("[") and line.endswith("]"):
                    current_label = line
                    if current_label not in parsed_data: parsed_data[current_label] = {"Low": [], "High": []}
                    current_type = None
                elif line.lower() == "low:": current_type = "Low"
                elif line.lower() == "high:": current_type = "High"
                elif current_label and current_type:
                    symbols = [s.replace("(new)", "").strip() for s in line.split(',') if s.strip()]
                    parsed_data[current_label][current_type].extend(symbols)
    except FileNotFoundError: pass
    return parsed_data

def write_results_hl(results_data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, 'w', encoding='utf-8') as outfile:
            for label, data in results_data.items():
                if not data["Low"] and not data["High"]: continue
                outfile.write(f"{label}\n")
                outfile.write("Low:\n" + (", ".join(data["Low"]) + "\n" if data["Low"] else "\n"))
                outfile.write("High:\n" + (", ".join(data["High"]) + "\n" if data["High"] else "\n"))
                if label != list(results_data.keys())[-1]: outfile.write("\n")
        print(f"[HL] 成功写入: {filepath}")
    except Exception as e:
        print(f"[HL] 写入错误: {e}")

def run_logic_highlow():
    print("\n" + "="*40)
    print(">>> 正在执行: Analyse_highlow (Detailed High/Low List)")
    print("="*40)
    target_categories = ["Bonds", "Currencies", "Crypto", "Indices", "Commodities", "ETFs", "Economics"]
    try:
        with open(HL_JSON_PATH, 'r', encoding='utf-8') as f:
            all_sectors = json.load(f)
        etf_symbols = set(all_sectors.get("ETFs", []))
        conn = create_connection_analyse(DB_PATH_ANALYSE)
        cursor = conn.cursor()
    except Exception as e:
        print(f"[HL] Setup Error: {e}")
        return
    current_run_results = {label: {"Low": [], "High": []} for label in HL_TIME_INTERVALS.keys()}
    
    for category in target_categories:
        if category not in all_sectors: continue
        symbols = all_sectors[category]
        if not symbols: continue
        print(f"[HL] Processing {category}...")
        for symbol in symbols:
            latest = get_latest_price_and_date_shared(cursor, category, symbol)
            if not latest: continue
            try:
                latest_date_str, latest_price = latest
                latest_date_obj = date.fromisoformat(latest_date_str)
            except: continue
            if latest_price is None: continue
            for label, time_delta in HL_TIME_INTERVALS.items():
                start_date = (latest_date_obj + time_delta).isoformat()
                prices = get_prices_in_range_hl(cursor, category, symbol, start_date, latest_date_str)
                if len(prices) < 2: continue
                min_p, max_p = min(prices), max(prices)
                if latest_price == min_p:
                    if symbol not in current_run_results[label]["Low"]:
                        current_run_results[label]["Low"].append(symbol)
                if latest_price == max_p:
                    if symbol not in current_run_results[label]["High"]:
                        current_run_results[label]["High"].append(symbol)
    if conn: conn.close()
    
    print("[HL] Reading backup and filtering...")
    backup_data = parse_highlow_backup_hl(HL_BACKUP_OUTPUT_PATH)
    results_for_main = {label: {"Low": [], "High": []} for label in HL_TIME_INTERVALS.keys()}
    
    for label in HL_TIME_INTERVALS:
        for typ in ["Low", "High"]:
            curr = current_run_results[label][typ]
            old = backup_data.get(label, {}).get(typ, [])
            new_only = [s for s in curr if s not in old]
            results_for_main[label][typ] = new_only
            
    short_term = ["[0.5 months]", "[1 months]", "[3 months]"]
    for label, data in results_for_main.items():
        if label in short_term:
            for typ in ["Low", "High"]:
                original = data[typ]
                filtered = [s for s in original if s not in etf_symbols]
                if len(filtered) < len(original):
                    print(f"[HL] Filtered {len(original)-len(filtered)} ETFs from {label} {typ}")
                results_for_main[label][typ] = filtered

    has_new = any(results_for_main[l][t] for l in results_for_main for t in ["Low", "High"])
    if has_new:
        filtered_results = {l: d for l, d in results_for_main.items() if d["Low"] or d["High"]}
        rev_filtered = OrderedDict(reversed(list(filtered_results.items())))
        cascade = OrderedDict()
        seen_low, seen_high = set(), set()
        
        for label, data in rev_filtered.items():
            new_l = [s for s in data["Low"] if s not in seen_low]
            new_h = [s for s in data["High"] if s not in seen_high]
            if new_l or new_h:
                cascade[label] = {"Low": new_l, "High": new_h}
                seen_low.update(new_l)
                seen_high.update(new_h)
        if cascade:
            write_results_hl(cascade, HL_OUTPUT_PATH)
    else:
        print("[HL] No new symbols found.")
    write_results_hl(current_run_results, HL_BACKUP_OUTPUT_PATH)

def move_files_to_backup_routine():
    print("\n>>> 执行文件归档备份...")
    try:
        os.makedirs(BACKUP_DIR_ROOT, exist_ok=True)
        if os.path.exists(DOWNLOADS_DIR):
            for filename in os.listdir(DOWNLOADS_DIR):
                if (filename.startswith("screener_") and filename.endswith(".txt")) or \
                   (filename.startswith("topetf_") and filename.endswith(".csv")):
                    src = os.path.join(DOWNLOADS_DIR, filename)
                    dst = os.path.join(BACKUP_DIR_ROOT, filename)
                    if os.path.isfile(src):
                        try:
                            shutil.move(src, dst)
                            print(f"归档: {filename}")
                        except: pass
        specific = os.path.join(NEWS_DIR, "screener_sectors.txt")
        if os.path.isfile(specific):
            try:
                shutil.move(specific, os.path.join(BACKUP_DIR_ROOT, "screener_sectors.txt"))
                print("归档: screener_sectors.txt")
            except: pass
    except: pass

def clean_backups_routine():
    print("\n>>> 执行旧备份清理 (Analyse Routine)...")
    patterns_1 = [
        ("Earnings_Release_next_", -1, 13), ("Earnings_Release_third_", -1, 13),
        ("Earnings_Release_fourth_", -1, 13), ("Earnings_Release_fifth_", -1, 13),
        ("Economic_Events_next_", -1, 13), ("ETFs_diff_", -1, 3),
        ("NewLow_", -1, 3), ("NewLow500_", -1, 3), ("NewLow5000_", -1, 3),
        ("Stock_Splits_next_", -1, 3), ("TodayCNH_", -1, 3),
        ("Stock_50_", -1, 3), ("Stock_500_", -1, 3), ("Stock_5000_", -1, 3)
    ]
    clean_backups_analyse(BACKUP_DIR_MAIN, patterns_1)
    
    patterns_2 = [
        ("article_copier_", -1, 3), ("screener_above_", -1, 3),
        ("screener_below_", -1, 3), ("topetf_", -1, 3),
    ]
    clean_backups_analyse(BACKUP_DIR_ROOT, patterns_2)

def execute_analyse_process():
    """Analyse 模块的总入口"""
    print("\n" + "="*50)
    print("STEP 2: 执行 Analyse_Combined 逻辑")
    print("="*50)

    try:
        blacklist_newlow = load_blacklist_newlow_shared(BLACKLIST_PATH)
        stock_splits = load_stock_splits_shared(STOCK_SPLITS_FILE)
        
        run_logic_5000(blacklist_newlow, stock_splits)
        run_logic_500(blacklist_newlow, stock_splits)
        run_logic_50(blacklist_newlow, stock_splits)
        
        print("\n----------------------------------------")
        print("切换至下一阶段任务 (High/Low Analysis)")
        print("----------------------------------------")
        
        run_logic_highlow()
        move_files_to_backup_routine()
        clean_backups_routine()
    except Exception as e:
        print(f"\nCRITICAL ERROR in Analyse Main Loop: {e}")
        log_and_print_error(f"主程序异常: {e}")

# ==============================================================================
# PART 3: Volume_High_Scanner 逻辑
# ==============================================================================

# --- Volume Scanner 辅助函数 ---

def format_volume_scanner(vol):
    """将成交量数值转换为 K, M, B 格式"""
    if not vol:
        return "0"
    try:
        vol = float(vol)
    except ValueError:
        return str(vol)
        
    if vol >= 1_000_000_000:
        return f"{vol / 1_000_000_000:.2f}B"
    elif vol >= 1_000_000:
        return f"{vol / 1_000_000:.2f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.2f}K"
    else:
        return f"{int(vol)}"

def load_json_scanner(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取 JSON 失败 {filepath}: {e}")
        return {}

def load_compare_info_scanner(filepath):
    """读取 Compare_All.txt 获取涨跌幅和财报信息"""
    info_map = {}
    if not os.path.exists(filepath):
        return info_map
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':', 1)
                if len(parts) == 2:
                    info_map[parts[0].strip()] = parts[1].strip()
    except Exception as e:
        print(f"读取 Compare_All 失败: {e}")
    return info_map

def load_tags_scanner(filepath):
    """读取 description.json 获取中文标签"""
    tag_map = {}
    data = load_json_scanner(filepath)
    # 遍历 stocks 和 etfs (虽然主要针对 stocks)
    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            symbol = item.get('symbol')
            tags = item.get('tag', [])
            if symbol and tags:
                tag_map[symbol] = ','.join(tags)
    return tag_map

def get_blacklist_scanner(filepath):
    data = load_json_scanner(filepath)
    return set(data.get("newlow", []))

def load_latest_earnings_scanner(db_path):
    """
    从 Earning 表中获取每只股票最新的财报日期。
    返回字典: {'PDD': '2024-08-26', 'AAPL': '2024-08-01', ...}
    """
    earnings_map = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 使用 GROUP BY 和 MAX(date) 直接获取每个 symbol 最新的日期
        query = "SELECT name, MAX(date) FROM Earning GROUP BY name"
        cursor.execute(query)
        rows = cursor.fetchall()
        for name, date_str in rows:
            if name and date_str:
                earnings_map[name] = date_str
        conn.close()
        print(f"已加载 {len(earnings_map)} 条最新财报日期信息。")
    except Exception as e:
        print(f"读取 Earning 表失败 (可能表不存在): {e}")
    return earnings_map

def run_volume_high_scanner():
    """Volume Scanner 的主入口"""
    print("\n" + "="*50)
    print("STEP 3: 执行 Volume_High_Scanner 逻辑")
    print("="*50)
    
    # 配置路径
    DB_PATH = os.path.join(BASE_CODING_DIR, 'Database/Finance.db')
    SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/Sectors_All.json')
    COMPARE_ALL_PATH = os.path.join(BASE_CODING_DIR, 'News/backup/Compare_All.txt')
    DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/description.json')
    BLACKLIST_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/blacklist.json')

    OUTPUT_FILENAME = f'{LOOKBACK_YEARS}Y_volume_high.txt'
    OUTPUT_FILE = os.path.join(BASE_CODING_DIR, f'News/{OUTPUT_FILENAME}')

    TARGET_SECTORS = [
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    ]

    print(f"--- 开始筛选 {LOOKBACK_YEARS} 年内成交量创新高的股票 ---")
    print(f"--- 过滤条件: 若今日为财报发布日，则跳过 ---")
    
    # 1. 加载基础数据
    sectors_data = load_json_scanner(SECTORS_ALL_PATH)
    compare_map = load_compare_info_scanner(COMPARE_ALL_PATH)
    tags_map = load_tags_scanner(DESCRIPTION_PATH)
    blacklist = get_blacklist_scanner(BLACKLIST_PATH)
    
    # 加载最新财报日期
    latest_earnings_map = load_latest_earnings_scanner(DB_PATH)
    
    results = []
    skipped_count = 0
    
    # 2. 连接数据库
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        print(f"无法连接数据库: {e}")
        return

    # 3. 遍历板块和股票
    for table_name in TARGET_SECTORS:
        if table_name not in sectors_data:
            continue
            
        symbols = sectors_data[table_name]
        print(f"正在扫描板块: {table_name} ({len(symbols)} 个代码)...")
        
        for name in symbols:
            if name in blacklist:
                continue
                
            try:
                # A. 获取最新一天的成交量和日期
                query_latest = f"SELECT date, volume FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 1"
                cursor.execute(query_latest, (name,))
                latest_row = cursor.fetchone()
                
                if not latest_row or not latest_row[1]:
                    continue
                    
                latest_date_str, latest_volume = latest_row
                latest_volume = float(latest_volume)
                
                # 如果成交量太小（例如停牌或极不活跃），可以过滤，这里设为0
                if latest_volume <= 0:
                    continue

                # --- 过滤逻辑：检查是否撞上财报日 ---
                if name in latest_earnings_map:
                    if latest_date_str == latest_earnings_map[name]:
                        skipped_count += 1
                        continue
                # ---------------------------------------

                # B. 计算 N 年前的日期
                try:
                    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")
                    # 支持小数年份
                    start_date = latest_date - relativedelta(years=int(LOOKBACK_YEARS), months=int((LOOKBACK_YEARS % 1) * 12))
                    start_date_str = start_date.strftime("%Y-%m-%d")
                except ValueError:
                    continue
                
                # C. 查询过去 N 年内的最大成交量
                query_max = f"SELECT MAX(volume) FROM {table_name} WHERE name = ? AND date >= ? AND date <= ?"
                cursor.execute(query_max, (name, start_date_str, latest_date_str))
                max_vol_row = cursor.fetchone()
                
                if max_vol_row and max_vol_row[0] is not None:
                    max_volume_period = float(max_vol_row[0])
                    
                    # D. 判断是否新高
                    if latest_volume >= max_volume_period:
                        # 组装数据
                        vol_str = format_volume_scanner(latest_volume)
                        info_str = compare_map.get(name, "")
                        tags_str = tags_map.get(name, "")
                        
                        line_parts = [table_name, name]
                        if info_str:
                            line_parts.append(info_str)
                        
                        line_parts.append(vol_str)
                        
                        if tags_str:
                            line_parts.append(tags_str)
                            
                        results.append(" ".join(line_parts))
                        
            except Exception as e:
                continue

    conn.close()

    # 4. 写入文件
    if results:
        try:
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(results))
            print("\n" + "="*50)
            print(f"成功！已生成文件: {OUTPUT_FILE}")
            print(f"筛选条件: 过去 {LOOKBACK_YEARS} 年内成交量新高 (已剔除财报日)")
            print(f"因财报日剔除数量: {skipped_count}")
            print(f"最终筛选出: {len(results)} 只股票")
            print("="*50)
        except Exception as e:
            print(f"写入文件失败: {e}")
    else:
        print(f"未找到符合条件的股票 (因财报日剔除: {skipped_count})。")

# ==============================================================================
# 主入口
# ==============================================================================
if __name__ == "__main__":
    print("************************************************************************")
    print(f"FULL SYSTEM START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("************************************************************************")

    # 执行第一部分 (Compare)
    execute_compare_process()

    # 执行第二部分 (Analyse)
    execute_analyse_process()
    
    # 执行第三部分 (Volume Scanner)
    run_volume_high_scanner()

    print("\n************************************************************************")
    print("所有任务执行完毕 (Compare + Analyse + VolumeScanner)。")
    print("************************************************************************")