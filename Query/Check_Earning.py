import json
import sqlite3
import os

# --- 新增功能函数 ---
def update_json_with_earning_filter(symbols_list, target_json_path):
    """
    将分析结果写入指定的 JSON 文件中的 'Earning_Filter' 组。

    Args:
        symbols_list (list or set): 符合条件的股票代码列表或集合。
        target_json_path (str): 目标 JSON 文件的路径。
    """
    print(f"\n--- 开始更新 JSON 文件: {os.path.basename(target_json_path)} ---")
    
    # 1. 准备要写入的数据
    # 根据需求，将股票列表转换为 {"symbol": "", ...} 格式的字典
    earning_filter_group = {symbol: "" for symbol in sorted(symbols_list)}
    
    try:
        # 2. 读取现有的 JSON 数据
        # 使用 'r+' 模式，如果文件不存在会报错，这符合我们的逻辑，因为我们是更新一个现有结构的文件
        with open(target_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 3. 更新数据
        # 直接对加载的 Python 字典进行操作，覆盖或创建 'Earning_Filter' 键
        data['Earning_Filter'] = earning_filter_group
        # ### 修改点：打印信息时使用 len(symbols_list) ###
        print(f"已将 'Earning_Filter' 组更新为包含 {len(symbols_list)} 个 symbol。")

        # 4. 将更新后的数据写回文件
        # 使用 'w' 模式来完整覆盖旧文件内容
        with open(target_json_path, 'w', encoding='utf-8') as f:
            # indent=4 保持文件格式美观，易于阅读
            # ensure_ascii=False 确保中文字符能被正确写入
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        print(f"成功将更新后的内容写入到: {target_json_path}")

    except FileNotFoundError:
        print(f"错误: 目标 JSON 文件未找到，请检查路径: {target_json_path}")
    except json.JSONDecodeError:
        print(f"错误: 目标 JSON 文件格式不正确，无法解析: {target_json_path}")
    except IOError as e:
        print(f"错误: 读写 JSON 文件时发生错误: {e}")
    except Exception as e:
        print(f"更新 JSON 文件时发生未知错误: {e}")


def analyze_financial_data():
    """
    根据指定规则分析金融数据，并筛选出符合条件的股票代码。
    新功能：
    - 将本次结果与备份文件比对，只将新增的 symbol 写入 news 文件。
    - 用本次的完整结果覆盖更新备份文件。
    - 如果没有新增内容，则不生成 news 文件，并删除旧的 news 文件。
    - (新) 将本次完整结果更新到指定的 JSON 文件中。
    """
    # --- 1. 配置路径 ---
    # 请根据您的实际情况修改这些路径
    # 使用 os.path.expanduser('~') 来获取用户主目录，使得路径更具可移植性
    base_path = os.path.expanduser('~')
    json_file_path = os.path.join(base_path, 'Documents/Financial_System/Modules/Sectors_All.json')
    db_file_path = os.path.join(base_path, 'Documents/Database/Finance.db')
    
    # 将输出路径明确区分为 news 路径和 backup 路径
    news_file_path = '/Users/yanzhang/Documents/News/Earning_Symbols.txt'
    backup_file_path = '/Users/yanzhang/Documents/News/backup/Earning_Symbols.txt'

    # --- 新增路径配置 ---
    # 您提到的 "Sectors_panel_test" 文件路径
    # 注意：您提供的路径指向一个 .py 文件，但其内容是 JSON。
    # 通常不建议用 .py 后缀存储纯数据文件。这里我将其命名为 .json 后缀，这是一个更好的实践。
    # 如果您必须使用 .py 后缀，只需修改文件名即可。
    target_json_for_filter_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'


    # --- 1.1. 确保 backup 目录存在 ---
    # 这是一个好的编程习惯，确保在写入文件前，其所在的目录是存在的
    backup_dir = os.path.dirname(backup_file_path)
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"已创建备份目录: {backup_dir}")

    # --- 2. 定义目标板块 ---
    target_sectors = {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    }

    # --- 3. 加载 JSON 数据 ---
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            all_sectors_data = json.load(f)
    except FileNotFoundError:
        print(f"错误: JSON 文件未找到，请检查路径: {json_file_path}")
        return
    except json.JSONDecodeError:
        print(f"错误: JSON 文件格式不正确: {json_file_path}")
        return

    qualified_symbols = [] # 用于存储所有满足条件的股票代码

    # --- 4. 连接数据库并执行分析 ---
    try:
        # 使用 with 语句确保数据库连接在使用后能被安全关闭
        with sqlite3.connect(db_file_path) as conn:
            cursor = conn.cursor()
            print("数据库连接成功，开始分析...")

            # 遍历 JSON 文件中的每个板块
            for sector_name, symbols in all_sectors_data.items():
                # 如果当前板块不是我们关心的目标板块，则跳过
                if sector_name not in target_sectors:
                    continue
                
                print(f"\n正在处理板块: {sector_name}...")

                if not symbols:
                    print(f"板块 {sector_name} 中没有股票代码，已跳过。")
                    continue

                # 遍历板块中的每一个股票代码
                for symbol in symbols:
                    # a. 从 Earning 表中查找该 symbol 对应的所有日期
                    # ORDER BY date ASC 确保日期按时间顺序排列
                    cursor.execute(
                        "SELECT date FROM Earning WHERE name = ? ORDER BY date ASC",
                        (symbol,)
                    )
                    earning_dates_result = cursor.fetchall()
                    
                    # 将查询结果 (元组列表) 转换为日期字符串列表
                    earning_dates = [row[0] for row in earning_dates_result]

                    # b. 条件1: 检查 Earning 表中记录是否至少有两条
                    if len(earning_dates) < 2:
                        continue # 不满足条件，处理下一个 symbol

                    # c. 根据获取到的日期，去对应的板块表中查询价格
                    # 构造 SQL 查询中的占位符，例如 '?, ?, ?'
                    placeholders = ', '.join(['?'] * len(earning_dates))
                    # SQL 查询语句，表名不能用 ? 参数化，但因为我们是从自己的JSON文件中获取的，所以是安全的
                    query = f"""
                        SELECT date, price 
                        FROM "{sector_name}" 
                        WHERE name = ? AND date IN ({placeholders})
                        ORDER BY date ASC
                    """
                    # 参数包括 symbol 和所有的 earning_dates
                    params = (symbol, *earning_dates)
                    
                    cursor.execute(query, params)
                    price_data = cursor.fetchall()

                    # 如果在板块表中找到的数据量和 Earning 表中的日期数量不匹配，说明数据不完整，跳过
                    if len(price_data) != len(earning_dates):
                        continue

                    prices = [row[1] for row in price_data]

                    # d. 条件2: 检查价格是否持续上升
                    is_continuously_increasing = True
                    for i in range(1, len(prices)):
                        # 如果当前价格不比前一个价格高，则不满足条件
                        if prices[i] <= prices[i-1]:
                            is_continuously_increasing = False
                            break
                    
                    if not is_continuously_increasing:
                        continue # 不满足条件，处理下一个 symbol

                    # e. 如果价格持续上升，则计算平均价并获取最新价
                    # 旧代码: average_price = sum(prices) / len(prices)
                    # <--- 修改点 1: 将计算平均价改为计算财报日价格中的最低价
                    min_price_on_earning_dates = min(prices)

                    # 获取该 symbol 在其板块表中的最新价格
                    latest_price_query = f'SELECT price FROM "{sector_name}" WHERE name = ? ORDER BY date DESC LIMIT 1'
                    cursor.execute(latest_price_query, (symbol,))
                    latest_price_result = cursor.fetchone()

                    if latest_price_result is None:
                        continue # 没有找到最新价格，跳过

                    latest_price = latest_price_result[0]

                    # f. 条件3: 比较最新价是否高于平均价
                    # 旧代码: if latest_price < average_price:
                    # <--- 修改点 2: 比较最新价是否低于财报日的 "最低价"
                    if latest_price < min_price_on_earning_dates:
                        print(f"  [符合条件!] Symbol: {symbol}")
                        print(f"    - Earning 日期数量: {len(earning_dates)}")
                        print(f"    - 价格持续上升: {prices}")
                        # 旧代码 print(f"    - 平均价: {average_price:.2f}")
                        # 旧代码 print(f"    - 最新价: {latest_price:.2f} (高于平均价)")
                        print(f"    - 财报日最低价: {min_price_on_earning_dates:.2f}") # 原为 "平均价"
                        print(f"    - 最新价: {latest_price:.2f} (低于财报日最低价)") # 原为 "高于平均价" (原文此处逻辑有误，应为低于)
                        qualified_symbols.append(symbol)

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return
    except Exception as e:
        print(f"发生未知错误: {e}")
        return

    # --- 5. 处理和写入结果 (### 核心逻辑修改区域 ###) ---
    if not qualified_symbols:
        print("\n分析完成，没有找到任何符合所有条件的股票。")
    else:
        print(f"\n分析完成，共找到 {len(qualified_symbols)} 个符合条件的股票: {sorted(qualified_symbols)}")        


    # --- 5.2. 处理 news 和 backup 文本文件 (保留原有逻辑) ---
    print("\n--- 开始处理 news 和 backup 文本文件 ---")
    backup_symbols = set()
    try:
        with open(backup_file_path, 'r', encoding='utf-8') as f:
            # 使用集合推导式高效地读取所有旧的 symbol
            # .strip() 用于移除每行末尾的换行符和可能的空白
            backup_symbols = {line.strip() for line in f if line.strip()}
        print(f"成功从备份文件加载了 {len(backup_symbols)} 个旧的 symbol。")
    except FileNotFoundError:
        print(f"未找到备份文件: {backup_file_path}。将视作首次运行。")
    except IOError as e:
        print(f"错误: 无法读取备份文件: {e}")
        # 如果无法读取备份，则无法进行比对，直接退出以防数据错乱
        return

    # 5.2 找出本次新增的 symbol
    # 将本次结果也转换为集合，利用集合的差集运算，找出新 symbol
    current_symbols_set = set(qualified_symbols)
    new_symbols = current_symbols_set - backup_symbols

    # 5.3 根据是否有新增 symbol，统一处理 news 文件和 JSON 文件
    if new_symbols:
        print(f"\n发现 {len(new_symbols)} 个新的 symbol，将更新 news 文件和 JSON 文件。")
        
        # (A) 更新 JSON 文件，只写入新增的 symbol
        update_json_with_earning_filter(new_symbols, target_json_for_filter_path)
        
        # (B) 写入 news 文件，也只写入新增的 symbol
        try:
            with open(news_file_path, 'w', encoding='utf-8') as f:
                # 为了保持输出顺序一致，可以对 new_symbols 排序后写入
                for symbol in sorted(list(new_symbols)):
                    f.write(symbol + '\n')
            print(f"新增结果已成功写入到文件: {news_file_path}")
        except IOError as e:
            print(f"错误: 无法写入 news 文件: {e}")
            
    else:
        # 当没有新内容时，检查旧文件是否存在，如果存在则删除
        print("\n与上次相比，没有发现新的符合条件的股票。")
        
        # (A) 清空 JSON 文件中的 Earning_Filter 组
        # 传递一个空列表给函数，它会自动写入一个空的 {}
        update_json_with_earning_filter([], target_json_for_filter_path)
        
        # (B) 删除旧的 news 文件
        try:
            if os.path.exists(news_file_path):
                os.remove(news_file_path)
                print(f"已删除旧的 news 文件，因为本次没有新内容: {news_file_path}")
        except OSError as e:
            # 使用 OSError 捕获与文件系统操作相关的错误
            print(f"错误: 无法删除旧的 news 文件: {e}")

    # 5.4 用本次的完整结果覆盖更新 backup 文件 (### 此处逻辑保持不变 ###)
    # 备份文件必须总是保存当前所有符合条件的 symbol，以便下一次运行时进行正确的比较
    print(f"\n正在用本次扫描到的 {len(qualified_symbols)} 个完整结果更新备份文件...")
    try:
        with open(backup_file_path, 'w', encoding='utf-8') as f:
            # 将本次所有符合条件的 symbol 写入备份文件，为下次比对做准备
            for symbol in sorted(qualified_symbols):
                f.write(symbol + '\n')
        print(f"备份文件已成功更新: {backup_file_path}")
    except IOError as e:
        print(f"错误: 无法更新备份文件: {e}")


if __name__ == '__main__':
    analyze_financial_data()