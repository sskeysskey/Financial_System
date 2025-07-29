import sqlite3
import json
import os
from datetime import datetime

# --- 1. 定义文件和数据库路径 ---
# 请确保这些路径在您的系统上是正确的
base_path = "/Users/yanzhang/Documents/"
news_path = os.path.join(base_path, "News")
db_path = os.path.join(base_path, "Database")
config_path = os.path.join(base_path, "Financial_System", "Modules")

# 输入文件
earnings_release_file = os.path.join(news_path, "Earnings_Release_next.txt")
sectors_json_file = os.path.join(config_path, "Sectors_All.json")
db_file = os.path.join(db_path, "Finance.db")

# 输出文件
output_file = os.path.join(news_path, "Filter_Earning1.txt")

# --- 2. 可配置参数 ---
# 您可以在这里修改需要查询的最近财报次数
NUM_EARNINGS_TO_CHECK = 2  # <--- 修改点：将2改为可配置的变量

def create_symbol_to_sector_map(json_file_path):
    """
    读取Sectors_All.json文件，并创建一个从股票代码到板块名称的映射。
    这个映射可以让我们通过股票代码快速找到它对应的数据库表名。
    """
    symbol_map = {}
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
            # 遍历每个板块及其中的股票列表
            for sector, symbols in sectors_data.items():
                # 遍历板块中的每个股票代码
                for symbol in symbols:
                    # 创建 "股票代码": "板块名" 的映射
                    symbol_map[symbol] = sector
    except FileNotFoundError:
        print(f"错误: JSON文件未找到 at {json_file_path}")
        return None
    except json.JSONDecodeError:
        print(f"错误: JSON文件格式无效 at {json_file_path}")
        return None
    return symbol_map

def get_symbols_from_release_file(file_path):
    """
    从Earnings_Release_next.txt文件中提取所有股票代码。
    """
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # 去除行首行尾的空白字符并按冒号分割
                parts = line.strip().split(':')
                if parts:
                    # 第一个部分就是股票代码，再次去除空白
                    symbol = parts[0].strip()
                    if symbol:
                        symbols.append(symbol)
    except FileNotFoundError:
        print(f"错误: 财报发布文件未找到 at {file_path}")
    return symbols

def process_stocks():
    """
    主处理函数，执行所有逻辑。
    """
    # --- 2. 加载数据 ---
    print("开始处理...")
    symbols_to_check = get_symbols_from_release_file(earnings_release_file)
    symbol_sector_map = create_symbol_to_sector_map(sectors_json_file)

    if not symbols_to_check or not symbol_sector_map:
        print("错误: 无法加载初始数据（股票列表或板块映射），程序终止。")
        return

    print(f"待检查的股票列表: {symbols_to_check}")
    print(f"配置: 将检查最近 {NUM_EARNINGS_TO_CHECK} 次财报。")
    
    # 用于存储满足条件的股票
    filtered_symbols = []
    
    # --- 3. 连接数据库并处理 ---
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        print("数据库连接成功。")

        # --- 4. 遍历每个待检查的股票 ---
        for symbol in symbols_to_check:
            print(f"\n--- 正在处理股票: {symbol} ---")

            # 步骤A: 获取最近N次财报日期
            # <--- 修改点：使用变量 NUM_EARNINGS_TO_CHECK 来动态设置LIMIT
            cursor.execute(
                "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT ?",
                (symbol, NUM_EARNINGS_TO_CHECK)
            )
            earnings_dates_result = cursor.fetchall()

            # <--- 修改点：检查获取到的财报记录是否足够
            if len(earnings_dates_result) < NUM_EARNINGS_TO_CHECK:
                print(f"信息: {symbol} 在 Earning 表中没有足够的 {NUM_EARNINGS_TO_CHECK} 次财报记录，已跳过。")
                continue
            
            # 将结果从 [(date1,), (date2,)] 转换为 [date1, date2]
            earnings_dates = [item[0] for item in earnings_dates_result]
            print(f"找到财报日期: {earnings_dates}")

            # 步骤B: 查找股票所属的板块/表名
            table_name = symbol_sector_map.get(symbol)
            if not table_name:
                print(f"警告: 在 Sectors_All.json 中未找到 {symbol} 的板块信息，已跳过。")
                continue
            
            print(f"{symbol} 属于板块/表: {table_name}")

            # 步骤C: 查询价格
            # 为防止SQL注入，我们验证表名是否合法（虽然这里是从我们自己的JSON文件读取的，但这是个好习惯）
            # 这里我们假设JSON文件是可信的，直接使用表名
            
            prices = {}
            # 查询所有财报日的收盘价
            for date_str in earnings_dates:
                cursor.execute(
                    f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?',
                    (symbol, date_str)
                )
                price_result = cursor.fetchone()
                if price_result:
                    prices[date_str] = price_result[0]
                else:
                    print(f"警告: 未能在表 {table_name} 中找到 {symbol} 在 {date_str} 的价格。")
            
            # 查询最新收盘价
            cursor.execute(
                f'SELECT price FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1',
                (symbol,)
            )
            latest_price_result = cursor.fetchone()
            if latest_price_result:
                latest_price = latest_price_result[0]
                print(f"最新收盘价: {latest_price}")
            else:
                print(f"警告: 未能在表 {table_name} 中找到 {symbol} 的任何价格数据，已跳过。")
                continue

            # <--- 修改点：确保获取了所有N个财报日的价格
            if len(prices) < NUM_EARNINGS_TO_CHECK:
                print(f"信息: 未能获取 {symbol} 全部 {NUM_EARNINGS_TO_CHECK} 次财报日的完整价格数据，已跳过。")
                continue

            earnings_day_prices = list(prices.values())
            print(f"财报日价格列表: {earnings_day_prices}")

            # 步骤D: 应用过滤条件
            # <--- 修改点：检查最新价是否低于所有N个财报日的价格
            # all() 函数会检查一个可迭代对象中的所有元素是否都为True
            # (latest_price < p for p in earnings_day_prices) 是一个生成器表达式，高效地进行每一次比较
            if all(latest_price < p for p in earnings_day_prices):
                print(f"*** 条件满足: {symbol} 的最新价 {latest_price} 低于所有 {NUM_EARNINGS_TO_CHECK} 次财报日价格。 ***")
                filtered_symbols.append(symbol)
            else:
                print(f"条件不满足: {symbol} 的最新价未低于所有 {NUM_EARNINGS_TO_CHECK} 次财报日价格。")

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        if conn:
            conn.close()
            print("\n数据库连接已关闭。")

    # --- 5. 写入结果到文件 ---
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for symbol in filtered_symbols:
                f.write(f"{symbol}\n")
        print(f"\n处理完成。满足条件的股票已写入到: {output_file}")
        print(f"筛选出的股票列表: {filtered_symbols}")
    except IOError as e:
        print(f"写入文件时发生错误: {e}")

# --- 程序入口 ---
if __name__ == "__main__":
    process_stocks()