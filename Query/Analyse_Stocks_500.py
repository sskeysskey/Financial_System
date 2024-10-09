import sqlite3
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import OrderedDict

blacklist_glob = set(["YNDX"])  # 使用集合以提高查找效率

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
        '/Users/yanzhang/Documents/News/backup/backup',
        '/Users/yanzhang/Documents/News'
    ]
    timestamp = datetime.now().strftime("%y%m%d")
    file_name = f"NewLow500_{timestamp}.txt"
    output_files = []
    
    for output_dir in output_dirs:
        os.makedirs(output_dir, exist_ok=True)
        output_files.append(os.path.join(output_dir, file_name))
    
    return output_files

def get_price_comparison(cursor, table_name, interval, name, validate):
    today = datetime.now()
    ex_validate = validate - timedelta(days=1)
    
    # 判断interval是否是小数，若是，则按天数计算
    # if interval == 1.5:
    #     days = int(interval * 30)  # 将月份转换为天数
    #     past_date = validate - timedelta(days=days - 1)
    # else:

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
            if 'Y' in year_part:
                continue  # 如果是年份，我们不处理
            if 'M' in year_part:
                months = int(year_part.replace('M', ''))
                if months == 3:
                    category_list = 'cyan_keywords'
                elif months == 6:
                    category_list = 'green_keywords'
                else:
                    continue  # 其他月份不处理

                if category_list in updates_color:
                    if symbol not in updates_color[category_list]:
                        updates_color[category_list].append(symbol)
                else:
                    updates_color[category_list] = [symbol]
    return updates_color

def update_color_json(color_config_path, updates_colors, blacklist_newlow, existing_sectors_panel):
    with open(color_config_path, 'r', encoding='utf-8') as file:
        all_colors = json.load(file)

    # 创建一个新的字典，排除 "red_keywords"
    colors = {k: v for k, v in all_colors.items() if k != "red_keywords"}

    # 创建一个集合，包含所有已存在于 sectors_panel.json 中的 symbol
    existing_symbols = set()
    for category in existing_sectors_panel.values():
        existing_symbols.update(category.keys())

    for category_list, names in updates_colors.items():
        for name in names:
            # 检查该 symbol 是否存在于 colors.json 中的其他分组，且不在 red_keywords 中
            symbol_exists_elsewhere = any(
                name in symbols for group, symbols in colors.items() if group != category_list
            )

            if symbol_exists_elsewhere:
                print(f"Symbol {name} 已存在于Colors其他分组中，跳过添加到 {category_list}")
                continue  # 跳过当前 symbol 的添加

            if name not in colors.get(category_list, []):
                if name in existing_symbols:
                    # 如果 symbol 已存在于 sectors_panel.json 中，打印日志
                    print(f"Symbol {name} 已存在于 sectors_panel.json 中，不添加到 {category_list}")
                else:
                    if category_list in colors:
                        colors[category_list].append(name)
                        print(f"将 '{name}' 添加到Colors已存在的 '{category_list}' 类别中")
                    else:
                        colors[category_list] = [name]
                        print(f"'{name}' 被添加到新的 '{category_list}' 类别中")
    
    # 在写回文件之前，将 "red_keywords" 添加回去
    colors["red_keywords"] = all_colors.get("red_keywords", [])

    try:
        with open(color_config_path, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

def log_and_print_error(error_message):
    formatted_error_message = log_error_with_timestamp(error_message)
    print(f"错误: {error_message}")
    with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
        error_file.write(formatted_error_message)

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
        error_message = f"读取文件 {file_path} 时发生错误: {e}"
        print(error_message)
        formatted_error_message = log_error_with_timestamp(error_message)
        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
            error_file.write(formatted_error_message)
    return stock_splits_symbols

def main():    
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    blacklist_path = '/Users/yanzhang/Documents/Financial_System/Modules/blacklist.json'
    blacklist_newlow = load_blacklist_newlow(blacklist_path)
    
    # 加载拆股文件的symbol列表
    stock_splits_file = '/Users/yanzhang/Documents/News/Stock_Splits_next.txt'
    stock_splits_symbols = load_stock_splits(stock_splits_file)

    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json', 'r') as file:
        data = json.load(file)

    output = []    
    intervals = [6, 3]  # 以月份表示的时间间隔列表

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

                    # 检查是否接近最低价格
                    for interval in intervals:
                        _, min_price = price_extremes.get(interval, (None, None))
                        if min_price is not None and validate_price <= min_price:
                            # 在生成output_line之前，检查name是否在拆股文件中
                            if name in stock_splits_symbols:
                                error_message = f"由于{table_name}的 {name} 存在于拆股文档中，所以不添加入output_500"
                                print(error_message)
                                formatted_error_message = log_error_with_timestamp(error_message)
                                with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                                    error_file.write(formatted_error_message)
                                break  # 跳过此name的处理
                            
                            output_line = f"{table_name} {name} {interval}M_newlow"
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

        # 在更新之前，先读取sectors_panel.json的内容
        with open("/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json", 'r', encoding='utf-8') as file:
            existing_sectors_panel = json.load(file)
    
        updates = parse_output(final_output)
        updates_color = parse_output_color(final_output)

        config_json = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json"
        update_json_data(config_json, updates, blacklist_newlow)

        color_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
        update_color_json(color_json_path, updates_color, blacklist_newlow, existing_sectors_panel)
    else:
        error_message = "analyse_500，没有符合条件的股票被检索出来。"
        log_and_print_error(error_message)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_and_print_error(f"程序执行过程中发生错误: {str(e)}")