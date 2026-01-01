import sqlite3
import json
import os
import shutil
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from collections import OrderedDict

# ==============================================================================
# SECTION: GLOBAL CONFIGURATION & SHARED UTILS
# (所有模块共用的基础配置和工具函数)
# ==============================================================================

# --- 数据库路径 ---
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

# --- 基础文件路径 ---
BLACKLIST_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/blacklist.json'
STOCK_SPLITS_FILE = '/Users/yanzhang/Coding/News/Stock_Splits_next.txt'
ERROR_LOG_FILE = '/Users/yanzhang/Coding/News/Today_error.txt'

# --- 面板与颜色配置 (所有模块都会更新这里) ---
SECTORS_PANEL_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json"
COLORS_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Colors.json'

# --- 备份目录 ---
BACKUP_DIR_MAIN = '/Users/yanzhang/Coding/News/backup/backup'
BACKUP_DIR_ROOT = '/Users/yanzhang/Coding/News/backup'
DOWNLOADS_DIR = "/Users/yanzhang/Downloads"
NEWS_DIR = "/Users/yanzhang/Coding/News"

# --- 黑名单 ---
BLACKLIST_GLOB = set(["YNDX"])

def is_blacklisted(name):
    return name in BLACKLIST_GLOB

def create_connection_shared(db_file):
    return sqlite3.connect(db_file, timeout=60.0)

def log_error_with_timestamp(error_message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] {error_message}\n"

def log_and_print_error(error_message):
    formatted_error_message = log_error_with_timestamp(error_message)
    print(f"注意！ {error_message}")
    with open(ERROR_LOG_FILE, 'a') as error_file:
        error_file.write(formatted_error_message)

def load_blacklist_newlow_shared(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file).get("newlow", [])
    except Exception as e:
        print(f"读取黑名单错误: {e}")
        return []

def load_stock_splits_shared(file_path):
    """加载拆股名单"""
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
    """获取指定股票的最新价格和日期 (所有模块通用)"""
    query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 1"
    cursor.execute(query, (name,))
    return cursor.fetchone()

def update_sectors_panel_json(config_path, updates, blacklist_newlow):
    """更新 Sectors_panel.json (5000, 500, 50 通用)"""
    with open(config_path, 'r', encoding='utf-8') as file:
        data = json.load(file, object_pairs_hook=OrderedDict)

    for category, symbols in updates.items():
        if category in data:
            for symbol in symbols:
                if symbol not in data[category] and symbol not in blacklist_newlow:
                    data[category][symbol] = ""
                    print(f"Panel Update: 将 '{symbol}' 添加到 '{category}'")
                elif symbol in data[category]:
                    pass # 已存在
                else:
                    print(f"Panel Update: '{symbol}' 在黑名单中，跳过")
        else:
            data[category] = {symbol: "" for symbol in symbols if symbol not in blacklist_newlow}

    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def parse_output_generic(output):
    """解析 output 文本，提取 {category: [symbols]}"""
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


# ==============================================================================
# MODULE 1: Analyse_Stocks_5000 (Weekly Logic)
# 对应原文件: Analyse_Stocks_5000.py
# ==============================================================================

PATH_SECTORS_5000 = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_5000.json'

def get_price_comparison_5000(cursor, table_name, interval_weeks, name, validate):
    """5000专用: 按周 (Weeks) 比较价格"""
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
    """5000专用: 解析 Weekly 标签 (Blue Keywords)"""
    updates_color = {}
    lines = output.split('\n')
    for line in lines:
        if not line.strip(): continue
        parts = line.split()
        if len(parts) < 3: continue
        
        symbol = parts[1]
        descriptor = parts[2]
        
        category_list = None
        # 逻辑：检查是否包含 W 且为 6, 8, 10
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
    """5000专用: 颜色更新逻辑 (优先级判断)"""
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
    intervals = [6, 8, 10] # Weeks
    
    valid_tables = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                    "Industrials", "Real_Estate", "Technology", "Utilities"]

    with create_connection_shared(DB_PATH) as conn:
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
        update_color_json_5000(COLORS_JSON_PATH, updates_color)
    else:
        log_and_print_error("[5000] 未检索到符合条件的股票。")


# ==============================================================================
# MODULE 2: Analyse_Stocks_500 (Monthly Logic)
# 对应原文件: Analyse_Stocks_500.py
# ==============================================================================

PATH_SECTORS_500 = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_500.json'

def get_price_comparison_500(cursor, table_name, interval_months, name, validate):
    """500专用: 按月 (Months) 比较价格"""
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
    """500专用: 解析 Monthly 标签 (Cyan Keywords)"""
    updates_color = {}
    lines = output.split('\n')
    for line in lines:
        if not line.strip(): continue
        parts = line.split()
        if len(parts) < 3: continue
        
        symbol = parts[1]
        descriptor = parts[2]
        
        category_list = None
        # 逻辑：检查是否包含 M 且为 5
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
    """500专用: 颜色更新逻辑"""
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
    intervals = [5] # Months
    
    valid_tables = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                    "Industrials", "Real_Estate", "Technology", "Utilities"]

    with create_connection_shared(DB_PATH) as conn:
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
        update_color_json_500(COLORS_JSON_PATH, updates_color)
    else:
        log_and_print_error("[500] 未检索到符合条件的股票。")


# ==============================================================================
# MODULE 3: Analyse_Stocks_50 (Yearly & Highs Logic)
# 对应原文件: Analyse_Stocks_50.py
# ==============================================================================

PATH_SECTORS_ALL = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
PATH_NEWHIGH_10Y = '/Users/yanzhang/Coding/Financial_System/Modules/10Y_newhigh.json'
PATH_NEWHIGH_OUTPUT = '/Users/yanzhang/Coding/News/10Y_newhigh_stock.txt'
PATH_COMPARE_ALL = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
PATH_DESCRIPTION = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'

def get_price_comparison_50(cursor, table_name, interval, name, validate):
    """50专用: 支持小数 interval (天) 和 整数 interval (月)"""
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
    """50专用: 解析 Yearly 标签 (White/Yellow/Orange/Black)"""
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
    """50专用: 颜色排他性更新"""
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

# --- 50模块专用的辅助函数 ---
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
    intervals = [120, 60, 24, 13] # Months for Lows
    highintervals = [120] # Months for Highs
    existing_highs = load_existing_highs_json_50(PATH_NEWHIGH_10Y)
    
    valid_tables = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                    "Industrials", "Real_Estate", "Technology", "Utilities"]

    with create_connection_shared(DB_PATH) as conn:
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
    
    # Process Low Results
    if output:
        final_output = "\n".join(output)
        updates = parse_output_generic(final_output)
        updates_color = parse_output_color_50(final_output)
        update_sectors_panel_json(SECTORS_PANEL_PATH, updates, blacklist_newlow)
        update_color_json_50(COLORS_JSON_PATH, updates_color)
    else:
        log_and_print_error("[50] 未检索到符合条件的股票 (Lows)。")

    # Process High Results
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


# ==============================================================================
# MODULE 4: Analyse_highlow (Detailed High/Low List Logic)
# 对应原文件: Analyse_highlow.py
# ==============================================================================

HL_OUTPUT_PATH = "/Users/yanzhang/Coding/News/HighLow.txt"
HL_BACKUP_OUTPUT_PATH = "/Users/yanzhang/Coding/News/backup/HighLow.txt"
HL_JSON_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"

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
    """HighLow专用: 获取范围内的所有价格"""
    try:
        query = f'SELECT price FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?'
        cursor.execute(query, (symbol, start_date_str, end_date_str))
        return [row[0] for row in cursor.fetchall() if row[0] is not None]
    except Exception as e:
        print(f"[HL] Warning: Could not query price range for {symbol}. {e}")
        return []

def parse_highlow_backup_hl(filepath):
    """HighLow专用: 解析备份文件"""
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
    """HighLow专用: 写入结果"""
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
        conn = create_connection_shared(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        print(f"[HL] Setup Error: {e}")
        return

    current_run_results = {label: {"Low": [], "High": []} for label in HL_TIME_INTERVALS.keys()}

    # 1. 分析数据
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

    # 2. 对比备份与筛选逻辑
    print("[HL] Reading backup and filtering...")
    backup_data = parse_highlow_backup_hl(HL_BACKUP_OUTPUT_PATH)
    results_for_main = {label: {"Low": [], "High": []} for label in HL_TIME_INTERVALS.keys()}

    # 筛选新增
    for label in HL_TIME_INTERVALS:
        for typ in ["Low", "High"]:
            curr = current_run_results[label][typ]
            old = backup_data.get(label, {}).get(typ, [])
            new_only = [s for s in curr if s not in old]
            results_for_main[label][typ] = new_only

    # ETF 过滤
    short_term = ["[0.5 months]", "[1 months]", "[3 months]"]
    for label, data in results_for_main.items():
        if label in short_term:
            for typ in ["Low", "High"]:
                original = data[typ]
                filtered = [s for s in original if s not in etf_symbols]
                if len(filtered) < len(original):
                    print(f"[HL] Filtered {len(original)-len(filtered)} ETFs from {label} {typ}")
                results_for_main[label][typ] = filtered

    # 3. 写入文件 (级联去重)
    has_new = any(results_for_main[l][t] for l in results_for_main for t in ["Low", "High"])
    if has_new:
        # 倒序级联
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

    # 更新备份
    write_results_hl(current_run_results, HL_BACKUP_OUTPUT_PATH)


# ==============================================================================
# HELPERS: Common Utility Functions for Shared Tasks (Cleanup, Backup)
# ==============================================================================

def _apply_color_updates_with_priority(color_path, updates, priority_map, log_prefix):
    """通用颜色更新辅助函数"""
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
                if new_p <= existing_p: # 注意: 这里 5000/500 使用了 <= (或者 <), 50 使用了排他. 这里统一使用覆盖逻辑
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

def clean_old_backups(directory, file_patterns):
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
    print("\n>>> 执行旧备份清理...")
    patterns_1 = [
        ("Earnings_Release_next_", -1, 13), ("Earnings_Release_third_", -1, 13),
        ("Earnings_Release_fourth_", -1, 13), ("Earnings_Release_fifth_", -1, 13),
        ("Economic_Events_next_", -1, 13), ("ETFs_diff_", -1, 3),
        ("NewLow_", -1, 3), ("NewLow500_", -1, 3), ("NewLow5000_", -1, 3),
        ("Stock_Splits_next_", -1, 3), ("TodayCNH_", -1, 3),
        ("Stock_50_", -1, 3), ("Stock_500_", -1, 3), ("Stock_5000_", -1, 3)
    ]
    clean_old_backups(BACKUP_DIR_MAIN, patterns_1)
    
    patterns_2 = [
        ("article_copier_", -1, 3), ("screener_above_", -1, 3),
        ("screener_below_", -1, 3), ("topetf_", -1, 3),
    ]
    clean_old_backups(BACKUP_DIR_ROOT, patterns_2)

# ==============================================================================
# MAIN ORCHESTRATION
# ==============================================================================

def main():
    print("**********************************************************************")
    print(f"COMBINED ANALYSIS START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("**********************************************************************")

    try:
        # 1. 准备公共数据
        blacklist_newlow = load_blacklist_newlow_shared(BLACKLIST_PATH)
        stock_splits = load_stock_splits_shared(STOCK_SPLITS_FILE)

        # 2. 执行模块 5000 (Weekly)
        run_logic_5000(blacklist_newlow, stock_splits)

        # 3. 执行模块 500 (Monthly)
        run_logic_500(blacklist_newlow, stock_splits)

        # 4. 执行模块 50 (Yearly + 10Y Highs)
        run_logic_50(blacklist_newlow, stock_splits)

        print("\n----------------------------------------")
        print("切换至下一阶段任务 (High/Low Analysis)")
        print("----------------------------------------")

        # 5. 执行模块 HighLow (Detailed Lists)
        run_logic_highlow()

        # 6. 收尾工作 (归档与清理)
        move_files_to_backup_routine()
        clean_backups_routine()

    except Exception as e:
        print(f"\nCRITICAL ERROR in Main Loop: {e}")
        log_and_print_error(f"主程序异常: {e}")

    print("\n**********************************************************************")
    print("所有合并任务执行完毕。")
    print("**********************************************************************")

if __name__ == "__main__":
    main()
