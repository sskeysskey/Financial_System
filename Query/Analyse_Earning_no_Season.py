import json
import sqlite3
import os

def analyze_financial_data():
    """
    新功能：
    - 将本次结果与备份文件比对，只将新增的 symbol 写入 news 文件。
    - 用本次的完整结果覆盖更新备份文件。
    - 如果没有新增内容，则不生成 news 文件，并删除旧的 news 文件。
    - (新) 将本次完整结果更新到指定的 JSON 文件中。
    - (新) 在写入 panel.json 前，使用 Blacklist.json 进行过滤。
    """
    # --- 1. 配置路径 ---
    # 使用 os.path.expanduser('~') 来获取用户主目录，使得路径更具可移植性
    base_path = os.path.expanduser('~')
    json_file_path = os.path.join(base_path, 'Coding/Financial_System/Modules/Sectors_All.json')
    db_file_path = os.path.join(base_path, 'Coding/Database/Finance.db')
    
    # 将输出路径明确区分为 news 路径和 backup 路径
    news_file_path = '/Users/yanzhang/Coding/News/Filter_Earning.txt'
    backup_file_path = '/Users/yanzhang/Coding/News/backup/Filter_Earning.txt'
    
    target_json_for_filter_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
    blacklist_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Blacklist.json'

    TURNOVER_THRESHOLD = 150_000_000  # 成交额阈值：一亿五千万
    PRICE_DROP_PERCENTAGE = 0.07     # 价格回撤阈值：7%
    RECENT_EARNINGS_COUNT   = 2            # —— 可配置：取最近 N 次财报（原来写死 3，现在改为 2）

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

    # --- 加载黑名单数据 ---
    print("\n--- 开始加载黑名单数据 ---")
    blacklist_newlow_set = set()
    try:
        with open(blacklist_json_path, 'r', encoding='utf-8') as f:
            blacklist_data = json.load(f)
            # 使用 .get('newlow', []) 来安全地获取列表，如果 'newlow' 键不存在，则返回一个空列表
            newlow_list = blacklist_data.get('newlow', [])
            if newlow_list:
                # 将列表转换为集合，以提高后续的查找效率
                blacklist_newlow_set = set(newlow_list)
                print(f"成功加载 {len(blacklist_newlow_set)} 个 symbol 到 'newlow' 黑名单。")
            else:
                print("'newlow' 黑名单为空或不存在。")
    except FileNotFoundError:
        print(f"警告: 黑名单文件未找到，将不进行任何过滤: {blacklist_json_path}")
    except json.JSONDecodeError:
        print(f"警告: 黑名单文件格式不正确，将不进行任何过滤: {blacklist_json_path}")
    except Exception as e:
        print(f"警告: 加载黑名单时发生未知错误，将不进行任何过滤: {e}")


    qualified_symbols = [] # 用于存储所有满足条件的股票代码

    # --- 4. 连接数据库并执行分析 ---
    try:
        # 使用 with 语句确保数据库连接在使用后能被安全关闭
        with sqlite3.connect(db_file_path) as conn:
            cursor = conn.cursor()
            print("\n数据库连接成功，开始分析...")

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
                    
                    # 条件1: 最新财报日价格 > 最近(<=3)财报日均价
                    prices_to_check = prices[-RECENT_EARNINGS_COUNT:]

                    # 2. 必须至少有两个价格点才有比较的意义。
                    if len(prices_to_check) < 2:
                        continue # 数据不足，处理下一个 symbol

                    # 3. 计算这些价格的平均值。
                    average_of_recent_earnings = sum(prices_to_check) / len(prices_to_check)
                    
                    # 4. 获取最新一期的财报日价格（即列表中的最后一个价格）。
                    latest_earning_price = prices_to_check[-1]

                    # 5. 如果最新一期的财报日价格不高于近期均价，则跳过
                    if latest_earning_price <= average_of_recent_earnings:
                        continue # 不满足条件，处理下一个 symbol
                    
                    # 如果代码能执行到这里，说明已满足“最新财报价 > 近期均价”的条件，可以继续下一步分析。

                    # e. 条件满足后，获取财报日最低价和股票最新价，进行下一步判断
                    min_price_on_earning_dates = min(prices)

                    # 获取最新交易日的 价格 和 成交量
                    latest_data_query = f'SELECT price, volume FROM "{sector_name}" WHERE name = ? ORDER BY date DESC LIMIT 1'
                    cursor.execute(latest_data_query, (symbol,))
                    latest_data_result = cursor.fetchone()

                    if latest_data_result is None:
                        continue
                    
                    # 从查询结果中解包得到价格和成交量
                    latest_price, latest_volume = latest_data_result

                    # 条件2: 最新价 < 所有财报日中的最低价
                    # 条件3: 最新价 < 最新财报日价格 * (1 - 7%)
                    price_condition_2 = latest_price <= latest_earning_price * (1 - PRICE_DROP_PERCENTAGE)

                    # if price_condition_1 and price_condition_2:
                    if price_condition_2:
                        
                        # 计算最新成交额
                        latest_turnover = latest_price * latest_volume
                        
                        # 条件4: 最新成交额 >= 1.5亿
                        if latest_turnover >= TURNOVER_THRESHOLD:
                            # 所有条件都满足，才加入列表并打印信息
                            print(f"  [符合所有条件!] Symbol: {symbol}")
                            print(f"    - 最近财报日均价: {average_of_recent_earnings:.2f}, 最新财报日价格: {latest_earning_price:.2f} (价格高于均价 ✅)")
                            print(f"    ---------------------------------")
                            print(f"    - 所有财报日最低价: {min_price_on_earning_dates:.2f}")
                            print(f"    - 最新价比财报日价低至少 {PRICE_DROP_PERCENTAGE:.0%}: {latest_price:.2f} <= {latest_earning_price * (1 - PRICE_DROP_PERCENTAGE):.2f} (✅)")
                            print(f"    - 股票当前最新价: {latest_price:.2f} (低于所有财报日最低价 ✅)")
                            print(f"    ---------------------------------")
                            print(f"    - 最新成交额: {latest_turnover:,.2f} (>= {TURNOVER_THRESHOLD:,.0f} ✅)")
                            qualified_symbols.append(symbol)

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return
    except Exception as e:
        print(f"发生未知错误: {e}")
        return

    # --- 5. 处理和写入结果 ---
    if not qualified_symbols:
        print("\n分析完成，没有找到任何符合所有条件的股票。")
    else:
        print(f"\n分析完成，共找到 {len(qualified_symbols)} 个符合条件的股票: {sorted(qualified_symbols)}")        

    # --- 5.2. 处理 news 和 backup 文本文件 ---
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

    # ### 新增代码块 3: 使用黑名单过滤新增的 symbol ###
    if blacklist_newlow_set:
        # 使用集合的差集运算来移除在黑名单中的 symbol
        filtered_new_symbols = new_symbols - blacklist_newlow_set
        
        # 打印出被过滤掉的 symbol，方便追踪
        removed_by_blacklist = new_symbols - filtered_new_symbols
        if removed_by_blacklist:
            print(f"\n根据 'newlow' 黑名单，已过滤掉 {len(removed_by_blacklist)} 个新增 symbol: {sorted(list(removed_by_blacklist))}")
    else:
        # 如果黑名单为空，则不过滤
        filtered_new_symbols = new_symbols


    # ### 修改点: 使用过滤后的 `filtered_new_symbols` 进行判断和写入 ###
    if filtered_new_symbols:
        print(f"\n发现 {len(filtered_new_symbols)} 个新的、且不在黑名单中的 symbol，将更新 news 文件和 JSON 文件。")
        
        # (A) 更新 JSON 文件，只写入过滤后的新增 symbol
        update_json_with_earning_filter(filtered_new_symbols, target_json_for_filter_path)
        
        # (B) 写入 news 文件，也只写入过滤后的新增 symbol
        try:
            with open(news_file_path, 'w', encoding='utf-8') as f:
                # 为了保持输出顺序一致，可以对 new_symbols 排序后写入
                for symbol in sorted(list(filtered_new_symbols)):
                    f.write(symbol + '\n')
            print(f"新增结果已成功写入到文件: {news_file_path}")
        except IOError as e:
            print(f"错误: 无法写入 news 文件: {e}")
            
    else:
        # 如果没有新的 symbol，或者所有新的 symbol 都在黑名单中
        print("\n与上次相比，没有发现新的、符合条件的股票（或所有新增股票均在黑名单中）。")
        
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

    # 5.4 用本次的完整结果覆盖更新 backup 文件 (逻辑保持不变)
    # 备份文件必须总是保存当前所有符合条件的 symbol (不过滤黑名单)，以便下一次运行时进行正确的比较
    print(f"\n正在用本次扫描到的 {len(qualified_symbols)} 个完整结果更新备份文件...")
    try:
        with open(backup_file_path, 'w', encoding='utf-8') as f:
            # 将本次所有符合条件的 symbol 写入备份文件，为下次比对做准备
            for symbol in sorted(qualified_symbols):
                f.write(symbol + '\n')
        print(f"备份文件已成功更新: {backup_file_path}")
    except IOError as e:
        print(f"错误: 无法更新备份文件: {e}")

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


if __name__ == '__main__':
    analyze_financial_data()