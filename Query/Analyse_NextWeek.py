import sqlite3
import json
import os
import datetime    # 新增

# --- 1. 定义文件和数据库路径 ---
# 请确保这些路径在您的系统上是正确的
base_path = "/Users/yanzhang/Coding/"
news_path = os.path.join(base_path, "News")
db_path = os.path.join(base_path, "Database")
config_path = os.path.join(base_path, "Financial_System", "Modules")
backup_file = os.path.join(news_path, "backup", "NextWeek_Earning.txt")
notification_file = os.path.join(news_path, "notification_earning.txt")  # 新增

# 输入文件
earnings_release_file = os.path.join(news_path, "Earnings_Release_next.txt")
sectors_json_file  = os.path.join(config_path, "Sectors_All.json")
db_file            = os.path.join(db_path, "Finance.db")

# 输出文件
output_file        = os.path.join(news_path, "NextWeek_Earning.txt")

# 黑名单和面板 JSON 路径
blacklist_json_file = os.path.join(config_path, "Blacklist.json")
panel_json_file     = os.path.join(config_path, "Sectors_panel.json")

# --- 2. 可配置参数 ---
NUM_EARNINGS_TO_CHECK = 2  # 查询近 N 次财报
MIN_DROP_PERCENTAGE   = 0.04 # 最新收盘价必须至少比历史财报日价格低 4%

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

def load_blacklist(json_file_path):
    """
    从 Blacklist.json 中加载 'newlow' 黑名单，返回一个 set。
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        newlow = data.get('newlow', [])
        bl_set = set(newlow)
        print(f"成功加载黑名单 'newlow': 共 {len(bl_set)} 个 symbol。")
        return bl_set
    except FileNotFoundError:
        print(f"警告: 未找到黑名单文件: {json_file_path}，将不进行过滤。")
    except json.JSONDecodeError:
        print(f"警告: 黑名单文件格式无效: {json_file_path}，将不进行过滤。")
    except Exception as e:
        print(f"警告: 加载黑名单时发生错误: {e}，将不进行过滤。")
    return set()

def update_json_group(symbols_list, target_json_path, group_name):
    """
    将 symbols_list 写入 target_json_path 的 group_name 分组，
    格式为 { group_name: {symbol1: "", symbol2: "", ...}, ... }
    """
    print(f"\n--- 更新 JSON 文件: {os.path.basename(target_json_path)} 下的组 '{group_name}' ---")
    try:
        with open(target_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误: 目标 JSON 文件未找到: {target_json_path}")
        return
    except json.JSONDecodeError:
        print(f"错误: 目标 JSON 文件格式不正确: {target_json_path}")
        return

    # 构造新的分组
    group_dict = {symbol: "" for symbol in sorted(symbols_list)}
    data[group_name] = group_dict

    try:
        with open(target_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功将 {len(symbols_list)} 个 symbol 写入组 '{group_name}'.")
    except Exception as e:
        print(f"错误: 写入 JSON 文件失败: {e}")

def process_stocks():
    print("开始处理...")
    symbols_to_check = get_symbols_from_release_file(earnings_release_file)
    symbol_sector_map = create_symbol_to_sector_map(sectors_json_file)

    if not symbols_to_check or not symbol_sector_map:
        print("错误: 无法加载初始数据（股票列表或板块映射），程序终止。")
        return

    print(f"待检查的股票列表: {symbols_to_check}")
    print(f"配置: 将检查最近 {NUM_EARNINGS_TO_CHECK} 次财报。")
    
    # 用于存储各策略满足条件的股票
    # 最新收盘价被过去N次财报的最低值还低
    filtered_1 = []
    
    # 过去N次财报都是上升，且收盘价比（N次财报中收盘价最高值）低4%
    filtered_2 = []
    filtered_3 = []    # 新增：策略3

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
                    print(f"警告: 表 {table_name} 中未找到 {symbol} 在 {date_str} 的价格。")
            if len(prices) < NUM_EARNINGS_TO_CHECK:
                print(f"信息: 未能获取 {symbol} 全部 {NUM_EARNINGS_TO_CHECK} 次财报日的完整价格数据，已跳过。")
                continue

            # 查询最新收盘价
            cursor.execute(
                f'SELECT date, price FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1',
                (symbol,)
            )
            latest_row = cursor.fetchone()
            if not latest_row:
                print(f"警告: 未能在 {table_name} 中找到 {symbol} 的任何价格数据，已跳过。")
                continue
            latest_date_str, latest_price = latest_row
            latest_date = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d").date()
            print(f"最新收盘价: {latest_price} （日期: {latest_date_str}）")

            earnings_day_prices = [prices[d] for d in earnings_dates]
            print(f"财报日价格列表 (按日期降序): {earnings_day_prices}")

            threshold = 1 - MIN_DROP_PERCENTAGE

            # 策略 1: 最新价比所有 N 次财报日价格都低至少 4%
            cond1 = all(latest_price < p * threshold for p in earnings_day_prices)
            if cond1:
                print(f"*** [filtered_1] 条件满足: {symbol} 的最新价 {latest_price} 比所有 {NUM_EARNINGS_TO_CHECK} 次财报日收盘价低 {MIN_DROP_PERCENTAGE*100:.0f}%。 ***")
                filtered_1.append(symbol)
            else:
                print(f"[filtered_1] 条件不满足: {symbol}")

            # 策略 2: N 次财报日收盘价递增 && 最新价比最近一次财报价低至少 4%
            # 将 prices 按时间升序排列
            asc_prices = list(reversed(earnings_day_prices))
            increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
            most_recent_er_price = earnings_day_prices[0]  # 第一项是最近一次财报收盘价
            cond2 = increasing and (latest_price < most_recent_er_price * threshold)
            if cond2:
                print(f"*** [filtered_2] 条件满足: {symbol} 的过去 {NUM_EARNINGS_TO_CHECK} 次财报日收盘价递增，且最新价 {latest_price} 比最近一次财报价 {most_recent_er_price} 低 {MIN_DROP_PERCENTAGE*100:.0f}%。 ***")
                filtered_2.append(symbol)
            else:
                print(f"[filtered_2] 条件不满足: {symbol}")

            # --- 策略 3 ---
            # 1) 前 N 次财报日价格递增 (变量 increasing 已在策略2里计算过)
            # 2) 最近两次财报价格涨幅至少 MIN_DROP_PERCENTAGE
            last_er_price = earnings_day_prices[0]
            prev_er_price = earnings_day_prices[1]
            gap_ok = (last_er_price >= prev_er_price * (1 + MIN_DROP_PERCENTAGE))
            if not gap_ok:
                print(
                    f"[filtered_3] 不满足涨幅要求: "
                    f"最近两次财报从 {prev_er_price} 到 {last_er_price}，"
                    f"涨幅 {(last_er_price/prev_er_price-1)*100:.2f}% < {MIN_DROP_PERCENTAGE*100:.0f}%"
                )

            # 3) 最新价 < N 次财报日收盘价最低值
            min_er_price = min(earnings_day_prices)

            # 4) 时间窗口判断：上次财报日期 +3 个月，往前推20天 到 往前推7天
            last_er_date = datetime.datetime.strptime(earnings_dates[0], "%Y-%m-%d").date()
            # 简单加三个月
            m = last_er_date.month + 3
            y = last_er_date.year + (m-1)//12
            m = (m-1)%12 + 1
            day = min(
                last_er_date.day,
                [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,31,30,31,30,31,31,30,31,30,31][m-1]
            )
            next_er_date = datetime.date(y, m, day)

            window_start = next_er_date - datetime.timedelta(days=20)
            window_end   = next_er_date - datetime.timedelta(days=7)

            cond3 = (
                increasing          # 原本的“递增”条件
                and gap_ok          # 新增：最近两次财报至少 MIN_DROP_PERCENTAGE 涨幅
                and latest_price < min_er_price
                and window_start <= latest_date <= window_end
            )
            if cond3:
                print(
                    f"*** [filtered_3] 条件满足: {symbol} 最新价 {latest_price} "
                    f"在窗口 {window_start}—{window_end} 内，低于历史最低 {min_er_price}，"
                    f"且最近两财报涨幅 {(last_er_price/prev_er_price-1)*100:.2f}% ≥ {MIN_DROP_PERCENTAGE*100:.0f}%。 ***"
                )
                filtered_3.append(symbol)
            else:
                print(f"[filtered_3] 条件不满足: {symbol}")

        print("\n数据库处理完成。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")

    # 合并所有策略的结果（去重）
    combined_filtered = list(set(filtered_1 + filtered_2))
    print(f"\n策略结果汇总:")
    print(f"  filtered_1: {filtered_1}")
    print(f"  filtered_2: {filtered_2}")
    print(f"  合并去重后总计: {combined_filtered}")
    print(f"  filtered_3: {filtered_3}")

    # --- 5. 应用黑名单过滤 & 更新 JSON 面板 ---
    print("\n--- 应用黑名单过滤 & 更新 JSON 面板 ---")
    blacklist_set = load_blacklist(blacklist_json_file)
    final_symbols = [s for s in combined_filtered if s not in blacklist_set]
    print(f"去除黑名单后: {final_symbols}")

    # --- 5.1 过滤 MNSPP 表中的无效 pe_ratio ---
    print("\n--- 过滤 MNSPP 表中的无效 pe_ratio ---")
    valid_symbols = []
    conn_m = None
    try:
        conn_m = sqlite3.connect(db_file)
        cursor_m = conn_m.cursor()
        for sym in final_symbols:
            cursor_m.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (sym,))
            row = cursor_m.fetchone()
            pe = row[0] if row else None
            # 过滤掉 "--", "null", "" 或 None
            if pe is not None and str(pe).strip() not in ("--", "null", ""):
                valid_symbols.append(sym)
            else:
                print(f"过滤: {sym} 的 pe_ratio 无效: {pe}")
    except sqlite3.Error as e:
        print(f"MNSPP 查询数据库错误: {e}")
    finally:
        if conn_m:
            conn_m.close()
    final_symbols = valid_symbols
    print(f"经过 pe_ratio 过滤后: {final_symbols}")

    # --- 与 backup 比对，只写新增 ---
    backup_dir = os.path.dirname(backup_file)
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir, exist_ok=True)

    # 读取备份文件（旧的符号集合）
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            old_set = {line.strip() for line in f if line.strip()}
        print(f"已从备份加载 {len(old_set)} 个旧的 symbol。")
    except FileNotFoundError:
        old_set = set()
        print("未找到备份文件，视作首次运行。")

    # 计算“新增”符号
    new_set = set(final_symbols) - old_set
    if new_set:
        print(f"本次新增 {len(new_set)} 个 symbol: {sorted(new_set)}")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for sym in sorted(new_set):
                    f.write(sym + '\n')
            print(f"新增结果已写入: {output_file}")
        except IOError as e:
            print(f"写入 news 文件时错误: {e}")
    else:
        print("本次没有发现新的 symbol。")
        # 如果没有新增且旧 news 文件存在，就删掉它
        if os.path.exists(output_file):
            os.remove(output_file)
            print(f"无新增，已删除旧的 news 文件: {output_file}")

    # --- 3. 更新 JSON 面板（只写新增 new_set） ---
    # 如果 new_set 为空，update_json_group 会写一个空的 {} 过去
    update_json_group(new_set, panel_json_file, "Next_Week")

    # --- 最后，把本次完整 final_symbols 覆盖写回 备份文件 ---
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            for sym in sorted(final_symbols):
                f.write(sym + '\n')
        print(f"备份文件已更新，共 {len(final_symbols)} 个 symbol: {backup_file}")
    except IOError as e:
        print(f"更新备份文件时错误: {e}")

    # --- 写入 notification_earning.txt ---
    # --- 额外：与 backup/notification_earning.txt 对比，只写新增，并更新 backup ---
    backup_notification_file = os.path.join(news_path, "backup", "notification_earning.txt")
    backup_dir = os.path.dirname(backup_notification_file)
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir, exist_ok=True)

    # 读取旧的 notification backup
    try:
        with open(backup_notification_file, 'r', encoding='utf-8') as f:
            old_notif = {line.strip() for line in f if line.strip()}
        print(f"已从备份加载 {len(old_notif)} 个旧的通知 symbol。")
    except FileNotFoundError:
        old_notif = set()
        print("未找到 notification 备份文件，视作首次运行。")

    # 计算新增
    new_notif = set(filtered_3) - old_notif
    if new_notif:
        # 只把新增写入 news 下的 txt（覆盖原 notification_file）
        with open(notification_file, 'w', encoding='utf-8') as f:
            for sym in sorted(new_notif):
                f.write(sym + '\n')
        print(f"本次通知新增 {len(new_notif)} 个 symbol: {sorted(new_notif)}")
    else:
        print("本次没有新增的通知 symbol。")
        # 若旧的 news/notification_earning.txt 存在，则删掉它
        if os.path.exists(notification_file):
            os.remove(notification_file)
            print(f"无新增，已删除旧的通知文件: {notification_file}")

    # --- 更新 sectors_panel.json 中的 Notification 组 ---
    update_json_group(new_notif, panel_json_file, "Notification")

    # 最后，把本次完整的 filtered_3 覆盖写回 backup
    try:
        with open(backup_notification_file, 'w', encoding='utf-8') as f:
            for sym in sorted(filtered_3):
                f.write(sym + '\n')
        print(f"通知备份已更新，共 {len(filtered_3)} 个 symbol: {backup_notification_file}")
    except IOError as e:
        print(f"更新通知备份文件时错误: {e}")

    
# --- 程序入口 ---
if __name__ == "__main__":
    process_stocks()