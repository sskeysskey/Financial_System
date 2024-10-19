import sqlite3
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import OrderedDict

blacklist_glob = ["YNDX"]

def is_blacklisted(name):
    return name in blacklist_glob

def create_connection(db_file):
    conn = sqlite3.connect(db_file)
    return conn

def log_error_with_timestamp(error_message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] {error_message}\n"

def load_blacklist_newlow(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        return data.get("newlow", [])

def create_output_files():
    """创建两个输出文件并返回文件路径"""
    output_dirs = [
        '/Users/yanzhang/Documents/News/backup/backup'
    ]
    timestamp = datetime.now().strftime("%y%m%d")
    file_name = f"NewLow_{timestamp}.txt"
    output_files = []
    
    for output_dir in output_dirs:
        os.makedirs(output_dir, exist_ok=True)
        output_files.append(os.path.join(output_dir, file_name))
    
    return output_files

def write_output_to_file(output, file_path):
    """将 output 写入指定文件"""
    try:
        # 确保目标文件夹存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # 写入文件
        with open(file_path, 'w') as f:
            f.write('\n'.join(output))
        print(f"结果已保存到文件: {file_path}")
    except Exception as e:
        error_message = f"写入文件时发生错误: {e}"
        print(error_message)
        formatted_error_message = log_error_with_timestamp(error_message)
        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
            error_file.write(formatted_error_message)

def get_price_comparison(cursor, table_name, interval, name, validate):
    today = datetime.now()
    ex_validate = validate - timedelta(days=1)
    
    # 判断interval是否小于1，若是，则按天数计算
    if interval < 1:
        days = int(interval * 30)  # 将月份转换为天数
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
    else:
        return None  # 如果找不到有效数据，则返回None

def get_latest_price_and_date(cursor, table_name, name):
    """获取指定股票的最新价格和日期"""
    query = f"""
    SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 1
    """
    cursor.execute(query, (name,))
    return cursor.fetchone()

# 解析final_output，构建更新数据
def parse_output(output):
    updates = {}
    lines = output.split('\n')
    for line in lines:
        if line.strip():  # 添加这个检查，确保不处理空行
            category, symbol, _ = line.split()
            if category in updates:
                updates[category].append(symbol)
            else:
                updates[category] = [symbol]
    return updates

def update_json_data(config_path, updates, blacklist_newlow):
    with open(config_path, 'r', encoding='utf-8') as file:
        data = json.load(file, object_pairs_hook=OrderedDict)

    for category, symbols in updates.items():
        if category in data:
            for symbol in symbols:
                if symbol not in data[category] and symbol not in blacklist_newlow:
                    data[category][symbol] = ""  # 使用新格式写入
                    print(f"将symbol '{symbol}' 添加到Panel文件的类别 '{category}' 中")
                    
                    # 将symbol和category写入文件
                    timestamp = datetime.now().strftime("%y%m%d")
                    file_path = f"/Users/yanzhang/Documents/News/NewLow_{timestamp}.txt"
                    with open(file_path, 'a', encoding='utf-8') as f:
                        f.write(f"{category} {symbol}\n")
                        
                elif symbol in data[category]:
                    print(f"'{symbol}' 已存在于Panel文件的类别 '{category}' 中，跳过")
                else:
                    print(f"'{symbol}' 在黑名单中，跳过")
        else:
            data[category] = {symbol: "" for symbol in symbols if symbol not in blacklist_newlow}

    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def parse_output_color(output):
    updates_color = {}
    lines = output.split('\n')
    for line in lines:
        if line.strip():  # 确保不处理空行
            parts = line.split()
            category = parts[0]
            symbol = parts[1]
            descriptor = parts[2]  # 形如 '1Y_newlow'

            # 解析年数和类型（newhigh或newlow）
            year_part, _ = descriptor.split('_')
            if 'M' in year_part:
                continue  # 如果是月份，我们不处理
            if 'Y' in year_part:
                years = int(year_part.replace('Y', ''))
                if years == 1:
                    category_list = 'white_keywords'
                elif years == 2:
                    category_list = 'yellow_keywords'
                elif years == 5:
                    category_list = 'orange_keywords'
                elif years == 10:
                    category_list = 'black_keywords'
                else:
                    continue  # 其他年份不处理

                if category_list in updates_color:
                    if symbol not in updates_color[category_list]:
                        updates_color[category_list].append(symbol)
                else:
                    updates_color[category_list] = [symbol]
    return updates_color

def update_color_json(color_config_path, updates_colors, blacklist_newlow):
    try:
        with open(color_config_path, 'r', encoding='utf-8') as file:
            all_colors = json.load(file)
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
        return

    # 创建一个新的字典，排除 "red_keywords"
    colors = {k: v for k, v in all_colors.items() if k != "red_keywords"}

    for category_list, names in updates_colors.items():
        for name in names:
            # 检查并移动到正确的分类
            moved = False
            for key in colors:
                if name in colors[key]:
                    if key != category_list:
                        colors[key].remove(name)
                        print(f"将 '{name}' 从 '{key}' 类别中移除")
                        moved = True
                    break
            if name not in colors[category_list]:
                colors[category_list].append(name)
                print(f"将 '{name}' 添加到 '{category_list}' 类别中")
            elif not moved:
                print(f"'{name}' 已经在 '{category_list}' 类别中")

    # 在写回文件之前，将 "red_keywords" 添加回去
    colors["red_keywords"] = all_colors["red_keywords"]

    try:
        with open(color_config_path, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

def load_symbols_from_file(file_path):
    """从文件中读取symbol列表"""
    symbols = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                parts = line.split()
                if len(parts) == 3:  # 确保每行有三个字段
                    symbol = parts[1]  # 提取symbol
                    symbols.add(symbol)
    except Exception as e:
        error_message = f"读取文件 {file_path} 时发生错误: {e}"
        print(error_message)
        formatted_error_message = log_error_with_timestamp(error_message)
        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
            error_file.write(formatted_error_message)
    return symbols

def clean_old_backups(directory, file_patterns, days=7):
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        for prefix, date_position in file_patterns:
            if filename.startswith(prefix):
                try:
                    parts = filename.split('_')
                    # 提取日期部分，并确保只获取日期的最后4位
                    date_str = parts[date_position].split('.')[0][-4:]
                    # 确保日期是按照MMDD格式解析
                    file_date = datetime.strptime(date_str, '%m%d')
                    # 将年份替换为当前年份
                    file_date = file_date.replace(year=now.year)
                    
                    # 如果文件日期早于截止日期，则删除文件
                    if file_date < cutoff:
                        file_path = os.path.join(directory, filename)
                        os.remove(file_path)
                        print(f"删除旧备份文件：{file_path}")
                    break  # 文件已处理，无需检查其他模式
                except Exception as e:
                    print(f"跳过文件：{filename}，原因：{e}")

def load_stock_splits(file_path):
    """从Stock_Splits_next.txt文件中加载symbol列表"""
    stock_splits_symbols = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if ':' in line:
                    symbol = line.split(':')[0]  # 提取冒号前面的symbol
                    stock_splits_symbols.add(symbol.strip())
    except Exception as e:
        print(error_message)
        # error_message = f"读取文件 {file_path} 时发生错误: {e}"
        # formatted_error_message = log_error_with_timestamp(error_message)
        # with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
        #     error_file.write(formatted_error_message)
    return stock_splits_symbols

def main():    
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    backup_directory = '/Users/yanzhang/Documents/News/backup/backup'
    blacklist_path = '/Users/yanzhang/Documents/Financial_System/Modules/blacklist.json'
    blacklist_newlow = load_blacklist_newlow(blacklist_path)
    
    # 加载拆股文件的symbol列表
    stock_splits_file = '/Users/yanzhang/Documents/News/Stock_Splits_next.txt'
    stock_splits_symbols = load_stock_splits(stock_splits_file)
    
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
        data = json.load(file)

    output = []
    output_high = []
    intervals = [120, 60, 24, 13]  # 以月份表示的时间间隔列表
    highintervals = [120]

    # 读取10Y_newhigh.txt文件中的symbol列表
    existing_symbols = load_symbols_from_file('/Users/yanzhang/Documents/News/backup/10Y_newhigh.txt')

    # 遍历JSON中的每个表和股票代码
    for table_name, names in data.items():
        if table_name in ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
                        "Industrials", "Real_Estate", "Technology", "Utilities"]:  # 过滤sector
            with create_connection(db_path) as conn:
                cursor = conn.cursor()
                for name in names:
                    if is_blacklisted(name):
                        print(f"{name} is blacklisted and will be skipped.")
                        continue  # 跳过黑名单中的符号
                    
                    result = get_latest_price_and_date(cursor, table_name, name)
                    if result:
                        validate, validate_price = result
                        validate = datetime.strptime(validate, "%Y-%m-%d")
                    else:
                        error_message = f"没有找到{name}的历史价格数据。"
                        formatted_error_message = log_error_with_timestamp(error_message)
                        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                            error_file.write(formatted_error_message)
                        continue

                    price_extremes = {}
                    for interval in intervals:
                        result = get_price_comparison(cursor, table_name, interval, name, validate)
                        try:
                            if result:
                                max_price, min_price = result
                                price_extremes[interval] = (max_price, min_price)
                            else:
                                raise Exception(f"没有足够的历史数据来进行{table_name}下的{name} {interval}月的价格比较。")
                        except Exception as e:
                            formatted_error_message = log_error_with_timestamp(str(e))
                            # 将错误信息追加到文件中
                            with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                                error_file.write(formatted_error_message)
                            continue  # 处理下一个时间间隔

                    # 检查是否接近最高价格
                    for highinterval in highintervals:
                        max_price, _ = price_extremes.get(highinterval, (None, None))
                        if max_price is not None and validate_price >= max_price:
                            if highinterval >= 12:
                                years = highinterval // 12
                                output_line = f"{table_name} {name} {years}Y_newhigh"
                                output_high.append(output_line)

                    # 检查是否接近最低价格
                    for interval in intervals:
                        _, min_price = price_extremes.get(interval, (None, None))
                        if min_price is not None and validate_price <= min_price:
                            if interval >= 12:
                                # 在生成output_line之前，检查name是否在拆股文件中
                                if name in stock_splits_symbols:
                                    error_message = f"由于{table_name}的 {name} 存在于拆股文档中，所以不添加入output_50"
                                    print(error_message)
                                    formatted_error_message = log_error_with_timestamp(error_message)
                                    with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                                        error_file.write(formatted_error_message)
                                    break  # 跳过此name的处理
                                
                                years = interval // 12
                                output_line = f"{table_name} {name} {years}Y_newlow"
                                print(output_line)
                                output.append(output_line)
                                break  # 只输出最长的时间周期

    if output:
        output_files = create_output_files()
        # 将结果写入所有输出文件
        for output_file in output_files:
            with open(output_file, 'w') as f:
                f.write('\n'.join(output))
            print(f"结果已保存到文件: {output_file}")
        
        final_output = "\n".join(output)

        updates = parse_output(final_output)
        updates_color = parse_output_color(final_output)

        config_json = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json"
        update_json_data(config_json, updates, blacklist_newlow)

        color_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
        update_color_json(color_json_path, updates_color, blacklist_newlow)
    else:
        error_message = "analyse_50，没有符合条件的股票被检索出来。"
        formatted_error_message = log_error_with_timestamp(error_message)
        # 将错误信息追加到文件中
        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
            error_file.write(formatted_error_message)

    if output_high:
        # 过滤掉已经存在于10Y_newhigh.txt文件中的symbol
        filtered_output_high = [
            line for line in output_high
            if line.split()[1] not in existing_symbols
        ]

        if filtered_output_high:  # 只有在有新的symbol时才写入文件
            output_high_file_path = '/Users/yanzhang/Documents/News/10Y_newhigh_new.txt'
            write_output_to_file(filtered_output_high, output_high_file_path)

    # 定义要清理的文件模式
    file_patterns = [
        ("Earnings_Release_next_", -1), # 日期在最后一个下划线后
        ("Economic_Events_next_", -1),
        ("NewLow_", -1),
        ("NewLow500_", -1),
        ("NewLow5000_", -1),
        ("Stock_Splits_next_", -1)
    ]

    # 执行清理旧备份文件的函数
    clean_old_backups(backup_directory, file_patterns)
        
if __name__ == "__main__":
    main()