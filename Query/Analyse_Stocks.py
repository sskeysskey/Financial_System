import sqlite3
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

blacklist_glob = ["YNDX"]

def is_blacklisted(name):
    return name in blacklist_glob

def create_connection(db_file):
    conn = None
    conn = sqlite3.connect(db_file)
    return conn

def log_error_with_timestamp(error_message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] {error_message}\n"

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

def main():    
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
        data = json.load(file)

    output = []
    output1 = []
    intervals = [120, 60, 24, 13]  # 以月份表示的时间间隔列表

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
                    found_min = False
                    for interval in intervals:
                        if found_min:
                            break
                        _, min_price = price_extremes.get(interval, (None, None))
                        if min_price is not None and validate_price <= min_price:
                            found_min = True
                            if validate_price <= min_price:
                                if interval >= 12:
                                    years = interval // 12
                                    output1.append(f"{table_name} {name} {years}Y_newlow")
    final_output1 = "\n".join(output1)

    # 解析final_output1，构建更新数据
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
                        # continue  # 不需要放入任何颜色分类，就用continue
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
        with open(color_config_path, 'r', encoding='utf-8') as file:
            colors = json.load(file)
        
        for category_list, names in updates_colors.items():
            for name in names:
                # 检查并移动到正确的分类
                for key in colors:
                    if name in colors[key]:
                        if key != category_list:
                            colors[key].remove(name)
                        break
                if name not in colors[category_list] and name not in blacklist_newlow:
                    colors[category_list].append(name)

        with open(color_config_path, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)

    if final_output1.strip():  # 检查final_output1是否为空
        updates = parse_output(final_output1)
        updates_color = parse_output_color(final_output1)
        # 黑名单列表
        blacklist_newlow = ["SIRI", "BBD", "BILL", "TAP", "STVN", "LSXMK",
        "TAK", "CSAN", "CIG", "TLK", "LBTYK", "ABEV",
        "TD", "DAY", "RHI", "OTEX", "ZI", "APA", "LU", "FIVE", "ORAN",
        "MGA", "MTN", "NGG", "NFE", "DBX", "ELP", "YUMC", "EBR", "LI",
        "CMCSA", "WBD", "MAT", "ZK", "BEN", "GGB", "BIDU", "PARA", "LVS",
        "ETSY", "GXO", "ZM", "CAE", "PKX", "TU", "XRAY", "ESLT", "VIPS",
        "ALAB", "LEA", "SOLV", "RCI"
        ]

        config_json = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json"
        update_json_data(config_json, updates, blacklist_newlow)
        print("Sectors_Panel.json文件已成功更新！")

        color_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
        update_color_json(color_json_path, updates_color, blacklist_newlow)
        print("Colors.json文件已成功更新！")
    else:
        error_message = "final_output1为空，无法进行更新操作。"
        formatted_error_message = log_error_with_timestamp(error_message)
        # 将错误信息追加到文件中
        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
            error_file.write(formatted_error_message)

if __name__ == "__main__":
    main()