import sqlite3
import json
import os
# import sys
import datetime

# --- 1. 定义文件和数据库路径 ---
# 请确保这些路径在您的系统上是正确的
base_path = "/Users/yanzhang/Coding/"
news_path = os.path.join(base_path, "News")
# why_path = os.path.join(news_path, "why.txt")

# # 把所有 print（stdout/stderr）都重定向到 why.txt
# sys.stdout = open(why_path, "w", encoding="utf-8")
# sys.stderr = sys.stdout

db_path = os.path.join(base_path, "Database")
config_path = os.path.join(base_path, "Financial_System", "Modules")
backup_file = os.path.join(news_path, "backup", "NextWeek_Earning.txt")
notification_file = os.path.join(news_path, "notification_earning.txt")
backup_notification_file = os.path.join(news_path, "backup", "notification_earning.txt")

# 输入文件
earnings_release_file = os.path.join(news_path, "Earnings_Release_next.txt")
earnings_release_new_file  = os.path.join(news_path, "Earnings_Release_new.txt")
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
MIN_TURNOVER          = 100_000_000  # 策略3：最新交易日的成交额（price * volume）最少 1 亿
RISE_DROP_PERCENTAGE = 0.07  # 升序时，最新价要比最高 ER 价至少低 7%

def filter_negative_earning_last_month(symbols, db_path):
    """
    剔除掉那些在最近 30 天内有 price < 0 财报的 symbols。
    由原来的 cursor 版改为自主 open/close。
    """
    import datetime, sqlite3
    if not symbols:
        return []

    today = datetime.date.today()
    one_month_ago = today - datetime.timedelta(days=30)
    out = []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for sym in symbols:
        cur.execute(
            "SELECT price FROM Earning WHERE name = ? AND date >= ?",
            (sym, one_month_ago.isoformat())
        )
        rows = cur.fetchall()
        # 如果近 30 天内有负值
        if any(r[0] is not None and r[0] < 0 for r in rows):
            print(f"    - 剔除 {sym}：最近一个月有负值财报 → {[r[0] for r in rows if r[0]<0]}")
        else:
            out.append(sym)

    conn.close()
    return out

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
        # 使用 .get() 安全地获取 'newlow' 键，如果不存在则返回空列表
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
        # 最好用 r+ 模式读取，但为保持健壮性，先读后写
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

# --- 新增：独立的成交额过滤函数 ---
def filter_by_turnover(symbols_to_filter, db_path, symbol_sector_map, min_turnover):
    """
    通过检查最新交易日的成交额来过滤股票列表。
    """
    if not symbols_to_filter:
        return []

    print(f"  - 开始对 {len(symbols_to_filter)} 个 symbol 进行成交额过滤...")
    valid_symbols = []
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for sym in symbols_to_filter:
            table_name = symbol_sector_map.get(sym)
            if not table_name:
                print(f"    - 警告 (成交额过滤): 未找到 {sym} 的板块信息，已跳过。")
                continue

            cursor.execute(
                f'SELECT price, volume FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1',
                (sym,)
            )
            row = cursor.fetchone()
            if row and row[0] is not None and row[1] is not None:
                turnover = row[0] * row[1]
                if turnover >= min_turnover:
                    valid_symbols.append(sym)
                else:
                    print(f"    - 过滤 (成交额不足): {sym} (成交额: {turnover:.0f})")
            else:
                print(f"    - 警告 (成交额过滤): 未找到 {sym} 的最新价格/成交量数据，已跳过。")
    except sqlite3.Error as e:
        print(f"    - 成交额查询数据库错误: {e}")
        return valid_symbols
    finally:
        if conn:
            conn.close()
    
    print(f"  - 成交额过滤后剩余 {len(valid_symbols)} 个 symbol。")
    return valid_symbols


def filter_symbols_by_pe_ratio(symbols_to_filter, db_path):
    """
    通过检查 MNSPP 表中的 pe_ratio 来过滤股票列表。

    Args:
        symbols_to_filter (list): 需要过滤的股票代码列表。
        db_path (str): 数据库文件路径。

    Returns:
        list: 一个只包含具有有效 pe_ratio 的股票的新列表。
    """
    if not symbols_to_filter:
        return []

    print(f"  - 开始对 {len(symbols_to_filter)} 个 symbol 进行 PE Ratio 过滤...")
    valid_symbols = []
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for sym in symbols_to_filter:
            cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (sym,))
            row = cursor.fetchone()
            pe = row[0] if row else None
            # 过滤掉 "--", "null", "", None, 以及大小写不敏感的 "null"
            if pe is not None and str(pe).strip().lower() not in ("--", "null", ""):
                valid_symbols.append(sym)
            else:
                print(f"    - 过滤 (PE Ratio 无效): {sym} (PE: {pe})")
    except sqlite3.Error as e:
        print(f"    - MNSPP 查询数据库错误: {e}")
        # 如果查询失败，返回目前已验证通过的列表，而不是空列表
        return valid_symbols
    finally:
        if conn:
            conn.close()
    
    print(f"  - PE Ratio 过滤后剩余 {len(valid_symbols)} 个 symbol。")
    return valid_symbols


def process_stocks():
    print("开始处理...")
    # 读取两个来源的 symbol
    symbols_next = get_symbols_from_release_file(earnings_release_file)
    symbols_new  = get_symbols_from_release_file(earnings_release_new_file)
    
    # symbols_to_check = sorted(set(symbols_next + symbols_new))
    
    # 合并，同时去重，但保留第一次出现的顺序
    combined = symbols_next + symbols_new
    symbols_to_check = list(dict.fromkeys(combined))
    
    # symbols_to_check = get_symbols_from_release_file(earnings_release_file)
    
    symbol_sector_map = create_symbol_to_sector_map(sectors_json_file)

    if not symbols_to_check or not symbol_sector_map:
        print("错误: 无法加载初始数据，程序终止。")
        return

    print(f"待检查的股票列表: {symbols_to_check}")
    print(f"配置: 将检查最近 {NUM_EARNINGS_TO_CHECK} 次财报。")
    
    # 策略1：最新收盘价被过去N次财报的最低值还低
    filtered_1 = []
    
    # 策略2：过去N次财报都是上升，且收盘价比（N次财报中收盘价最高值）低4%，且最近一次的财报日期要和最新收盘价日期间隔不少于7天
    filtered_2 = []

    filtered_2_5 = []     # 新增：策略2.5

    # 策略3：最新价 < 过去N次财报最低价，且交易日落在下次财报前7~20天窗口
    filtered_3 = []    # 新增：策略3

    filtered_3_5 = []     # 新增：策略3.5
    # 策略 4(1)： 最近N次财报的收盘价要递增，最近一次财报必须是从系统日期往前数一个月内
    # 策略 4(1)： 且该symbol从earning表中读到的price值必须为正，且最新财报日一周后的收盘价比最新财报日前后(±2天内)的最高收盘价低超过4%
    filtered_4 = []

    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        print("数据库连接成功。")

        # -----------------------------
        # 第一遍: 只对 next.txt 中的 symbols 跑 策略1 和 策略2
        # -----------------------------
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

            # 查询最新收盘价及成交量
            cursor.execute(
                f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1',
                (symbol,)
            )
            latest_row = cursor.fetchone()
            if not latest_row:
                print(f"警告: 未能在 {table_name} 中找到 {symbol} 的任何价格/成交量数据，已跳过。")
                continue
            latest_date_str, latest_price, latest_volume = latest_row
            latest_date = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d").date()
            
            # --- 修改点: 保留成交额计算和打印，但从条件判断中移除 ---
            # turnover = latest_price * latest_volume if latest_price and latest_volume else 0
            # turnover_ok = turnover >= MIN_TURNOVER
            # print(f"最新收盘价: {latest_price} ({latest_date_str})，成交额: {turnover:.0f}" + ("" if turnover_ok else f" ← 注意: 未达 {MIN_TURNOVER}"))

            earnings_day_prices = [prices[d] for d in earnings_dates]
            threshold = 1 - MIN_DROP_PERCENTAGE

            # 策略 1: 最新价比所有 N 次财报日价格都低至少 4%，自动剔除了那些在最近 30 天内有负值财报记录的股票
            cond1 = all(latest_price < p * threshold for p in earnings_day_prices)
            if cond1:
                print(f"*** [filtered_1] 条件满足: {symbol} 的最新价 {latest_price} 比所有 {NUM_EARNINGS_TO_CHECK} 次财报日收盘价低 {MIN_DROP_PERCENTAGE*100:.0f}%。 ***")
                filtered_1.append(symbol)
            else:
                print(f"[filtered_1] 条件不满足: {symbol}")

            # 策略 2: N 次财报日收盘价递增 && 最新价比最近一次财报价低至少 4%，且最近一次的财报日期要和最新收盘价日期间隔不少于7天，自动剔除了那些在最近 30 天内有负值财报记录的股票
            # 将 prices 按时间升序排列
            asc_prices = list(reversed(earnings_day_prices))
            increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
            most_recent_er_price = earnings_day_prices[0]  # 第一项是最近一次财报收盘价
            # —— 新增：计算最近一次财报日到最新交易日的天数差 —— 
            last_er_date = datetime.datetime.strptime(earnings_dates[0], "%Y-%m-%d").date()
            days_since_er = (latest_date - last_er_date).days
            date_ok = days_since_er >= 7
            if not date_ok:
                print(f"    - 跳过策略2: 最新交易日({latest_date_str})距最近财报日({earnings_dates[0]})仅 {days_since_er} 天 (<7天)")

            # --- 修改点: 移除 turnover_ok ---
            cond2 = increasing and (latest_price < most_recent_er_price * threshold) and date_ok
            if cond2:
                print(f"*** [filtered_2] 条件满足: {symbol} 的过去 {NUM_EARNINGS_TO_CHECK} 次财报日收盘价递增，且最新价 {latest_price} 比最近一次财报价 {most_recent_er_price} 低 {MIN_DROP_PERCENTAGE*100:.0f}%。 ***")
                filtered_2.append(symbol)
            else:
                print(f"[filtered_2] 条件不满足: {symbol}")

            # 策略 2.5 过去N次财报保持上升，且最近的4次财报里至少有一次财报的收盘价要比该symbol的最新收盘价高7%以上
            # ① 取最近4次财报日期
            cursor.execute(
                "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 4",
                (symbol,)
            )
            dates4 = [r[0] for r in cursor.fetchall()]
            if len(dates4) == 4:
                # ② 取这4次的收盘价
                prices4 = []
                for d in dates4:
                    cursor.execute(
                        f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?',
                        (symbol, d)
                    )
                    r = cursor.fetchone()
                    if r:
                        prices4.append(r[0])
                if len(prices4) == 4:
                    # 检查前 N 次是否递增
                    asc_N = list(reversed(prices4))[:NUM_EARNINGS_TO_CHECK]
                    increasing_N = all(asc_N[i] < asc_N[i+1] for i in range(len(asc_N)-1))
                    # 检查 4 次里是否有一次 > 最新价 × 1.07
                    any_high = any(p > latest_price * 1.07 for p in prices4)
                    # --- 修改点: 移除 turnover_ok ---
                    if increasing_N and any_high and date_ok:
                        print(f"*** [filtered_2_5] 条件满足: {symbol} ***")
                        filtered_2_5.append(symbol)

        # --- 第二遍: 全表扫描 Earning，跑 策略3, 3.5 和 4 ---
        cursor.execute("SELECT DISTINCT name FROM Earning")
        all_symbols = [row[0] for row in cursor.fetchall()]
        print(f"\n策略3/3.5/4 全库扫描 {len(all_symbols)} 个 symbol…")
        
        # --- 新增：为策略4的日期检查预先计算好阈值 ---
        today = datetime.date.today()
        one_month_ago = today - datetime.timedelta(days=30)

        for symbol in all_symbols:
            # (为减少输出，可以注释掉下面的打印)
            # print(f"\n--- [S3/S4] 处理 {symbol} ---")
            # 1) 拿最近 N 次财报日期
            cursor.execute(
                "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT ?",
                (symbol, NUM_EARNINGS_TO_CHECK)
            )
            dates = [r[0] for r in cursor.fetchall()]
            if len(dates) < NUM_EARNINGS_TO_CHECK:
                print("  跳过: 财报次数不足")
                continue

            # 2) 找板块表名
            table_name = symbol_sector_map.get(symbol)
            if not table_name:
                print("  跳过: 无板块映射")
                continue

            # 3) 查询 N 次财报日价格
            prices = {}
            for d in dates:
                cursor.execute(
                    f'SELECT price FROM "{table_name}" WHERE name=? AND date=?',
                    (symbol, d)
                )
                r = cursor.fetchone()
                if r: prices[d] = r[0]
            if len(prices) < NUM_EARNINGS_TO_CHECK:
                print("  跳过: 财报价不全")
                continue
            earnings_day_prices = [prices[d] for d in dates]

            # 4) 查询最新价+量
            cursor.execute(
                f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1',
                (symbol,)
            )
            r = cursor.fetchone()
            if not r:
                print("  跳过: 无最新日数据")
                continue
            latest_date_str, latest_price, latest_volume = r
            latest_date = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d").date()
            
            # --- 修改点: 保留成交额计算，但从条件判断中移除 ---
            # turnover = latest_price * latest_volume if latest_price and latest_volume else 0
            # turnover_ok = turnover >= MIN_TURNOVER # 这行不再是必须的，但保留也无妨

            last_er_date = datetime.datetime.strptime(dates[0], "%Y-%m-%d").date()
            asc_prices = list(reversed(earnings_day_prices))

            # --- 策略3 ---
            min_er_price = min(earnings_day_prices)
            m = last_er_date.month + 3
            y = last_er_date.year + (m-1)//12
            m = (m-1)%12 + 1
            day = min(
                last_er_date.day,
                [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,
                31,30,31,30,31,31,30,31,30,31][m-1]
            )
            next_er = datetime.date(y, m, day)
            window_start = next_er - datetime.timedelta(days=20)
            window_end   = next_er - datetime.timedelta(days=7)
            
            if asc_prices[0] < asc_prices[1]:
                # 上升：最新收盘价要比最高 ER 价低至少 7%
                price_ok = latest_price < max(asc_prices) * (1 - RISE_DROP_PERCENTAGE)
            else:
                # 非升序：两次 ER 收盘价差距至少 4%
                diff = abs(asc_prices[1] - asc_prices[0])
                price_ok = diff >= asc_prices[0] * MIN_DROP_PERCENTAGE                

            # 最终合成 cond3：新价格规则 + 时间窗口
            cond3 = (
                price_ok
                and latest_price < min_er_price
                and window_start <= latest_date <= window_end
            )
            if cond3:
                filtered_3.append(symbol)
                print("  [filtered_3] ✓ (最终通过)")
            else:
                print("  [filtered_3] × (未通过)")

            # --- 策略3.5: 过去N次财报保持上升，且最近的4次财报里至少有一次财报的收盘价要比该symbol的最新收盘价高7%以上
            if asc_prices[0] < asc_prices[1]:
                # ① 取最近4次财报日期
                cursor.execute(
                    "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 4",
                    (symbol,)
                )
                dates4 = [r[0] for r in cursor.fetchall()]
                if len(dates4) == 4:
                    # ② 取这4次的收盘价
                    prices4 = []
                    for d in dates4:
                        cursor.execute(
                            f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?',
                            (symbol, d)
                        )
                        r = cursor.fetchone()
                        if r: prices4.append(r[0])
                    if len(prices4) == 4:
                        any_high = any(p > latest_price * 1.07 for p in prices4)
                        # 与策略3其余条件相同：turnover_ok, window_start ≤ latest_date ≤ window_end
                        if any_high and (window_start <= latest_date <= window_end):
                            print(f"  [filtered_3_5] ✓ {symbol} 通过：前{NUM_EARNINGS_TO_CHECK}次递增 + 4次中有价 > 最新价×1.07")
                            filtered_3_5.append(symbol)
            
            # --- 新增：策略4 ---
            # 规则1: 最近N次财报收盘价递增
            s4_increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
            
            # 规则2: 最近一次财报在过去一个月内
            s4_recent_er = last_er_date >= one_month_ago
            
            # 规则3: Earning表中的price为正
            cursor.execute("SELECT price FROM Earning WHERE name = ? AND date = ?", (symbol, dates[0]))
            earning_record_price_row = cursor.fetchone()
            s4_positive_earning = earning_record_price_row and earning_record_price_row[0] is not None and earning_record_price_row[0] > 0
            
            # 只有在满足以上基本条件和成交额条件时，才进行最复杂的价格查询
            if s4_increasing and s4_recent_er and s4_positive_earning:
                # 1) 日期窗口：最近财报日后5~11天
                window_start = last_er_date + datetime.timedelta(days=5)
                window_end   = last_er_date + datetime.timedelta(days=11)
                date_in_window = window_start <= latest_date <= window_end

                # 2) 取财报日前后±2天的最高价
                start_range = last_er_date - datetime.timedelta(days=2)
                end_range   = last_er_date + datetime.timedelta(days=2)
                cursor.execute(
                    f'SELECT MAX(price) FROM "{table_name}" '
                    "WHERE name = ? AND date BETWEEN ? AND ?",
                    (symbol, start_range.isoformat(), end_range.isoformat())
                )
                max_row = cursor.fetchone()
                max_price_around_er = max_row[0] if max_row and max_row[0] is not None else None

                # 3) 取倒数第二次财报收盘价
                second_er_price = None
                if len(earnings_day_prices) >= 2:
                    second_er_price = earnings_day_prices[1]

                # 4) 根据市值选择跌幅阈值 X
                cursor.execute("SELECT market_cap FROM MNSPP WHERE symbol = ?", (symbol,))
                mcap_row = cursor.fetchone()
                mcap = mcap_row[0] if mcap_row else None
                MARKETCAP_THRESHOLD = 50_000_000_000  # 500亿
                drop_large = 0.04  # ≥500亿 用4%
                drop_small = 0.07  # <500亿 用7%
                drop_pct = drop_large if mcap and mcap >= MARKETCAP_THRESHOLD else drop_small

                # A 条件：在窗口内 且 最新价 < max_price_around_er * (1 - drop_pct)
                cond_A = (
                    date_in_window
                    and max_price_around_er is not None
                    and latest_price < max_price_around_er * (1 - drop_pct)
                )
                # B 条件：最新价 < 倒数第二次财报收盘价
                cond_B = (second_er_price is not None and latest_price < second_er_price)

                if cond_A or cond_B:
                    print(f"*** [filtered_4] {symbol} 通过："
                          f"日期窗{window_start}~{window_end}, 最新价{latest_price:.2f}, "
                          f"X={drop_pct*100:.0f}%, max_ER_price={max_price_around_er}, "
                          f"2nd_ER_price={second_er_price} ***")
                    filtered_4.append(symbol)

        print("\n数据库处理完成。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")

    # --- 新增: 过滤最新交易日 == 最新财报日 的 symbol ---
    def filter_by_date_mismatch(symbols_list):
        """
        去除掉那些“最新交易日日期”与“最新财报日日期”相同的 symbol
        """
        filtered = []
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        for sym in symbols_list:
            # 1) 拿最新一条财报日期
            cur.execute(
                "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1",
                (sym,)
            )
            row_er = cur.fetchone()
            if not row_er:
                # 没有财报记录，保留（或按你需求也可以直接跳过）
                filtered.append(sym)
                continue
            latest_er_date = row_er[0]

            # 2) 拿最新一条交易日期
            table_name = symbol_sector_map.get(sym)
            if not table_name:
                filtered.append(sym)
                continue
            cur.execute(
                f'SELECT date FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1',
                (sym,)
            )
            row_tr = cur.fetchone()
            if not row_tr:
                filtered.append(sym)
                continue
            latest_tr_date = row_tr[0]

            # 3) 比较
            if latest_tr_date == latest_er_date:
                print(f"跳过 {sym}：最新交易日({latest_tr_date}) == 最新财报日({latest_er_date})")
            else:
                filtered.append(sym)

        conn.close()
        return filtered

    # --- 结果汇总与共享过滤流程 ---
    
    # 1. 汇总初步结果
    final_symbols = sorted(set(filtered_1 + filtered_2 + filtered_2_5))
    final_notification_list = sorted(set(filtered_3 + filtered_3_5 + filtered_4))

    print(f"\n策略结果汇总 (过滤前):")
    print(f"  主列表找到: {len(final_symbols)} 个")
    print(f"  通知列表找到: {len(final_notification_list)} 个")

    # 2. 过滤最近一个月有负值财报的
    print("\n--- 2. 额外过滤：最近一个月有负值财报 → 剔除 ---")
    # 只有主列表需要进行负值财报过滤
    final_symbols = filter_negative_earning_last_month(final_symbols, db_file)
    
    # 3. 应用黑名单过滤
    print("\n--- 3. 应用黑名单过滤 ---")
    blacklist_set = load_blacklist(blacklist_json_file)
    final_symbols = [s for s in final_symbols if s not in blacklist_set]
    final_notification_list = [s for s in final_notification_list if s not in blacklist_set]
    print(f"黑名单过滤后，主列表剩余: {len(final_symbols)} 个, 通知列表剩余: {len(final_notification_list)} 个")

    # --- 4. 新增：过滤低成交额股票 ---
    print("\n--- 4. 过滤低成交额股票 ---")
    final_symbols = filter_by_turnover(final_symbols, db_file, symbol_sector_map, MIN_TURNOVER)
    final_notification_list = filter_by_turnover(final_notification_list, db_file, symbol_sector_map, MIN_TURNOVER)

    # 5. 过滤无效 PE Ratio
    print("\n--- 5. 过滤无效 PE Ratio ---")
    final_symbols = filter_symbols_by_pe_ratio(final_symbols, db_file)
    final_notification_list = filter_symbols_by_pe_ratio(final_notification_list, db_file)

    # 6. 过滤“最新交易日 == 最新财报日”
    print("\n--- 6. 过滤：剔除“最新交易日 == 最新财报日” 的股票 ---")
    final_symbols = filter_by_date_mismatch(final_symbols)
    final_notification_list = filter_by_date_mismatch(final_notification_list)

    print("\n--- 所有过滤完成后的最终结果 ---")
    print(f"主列表最终数量: {len(final_symbols)} - {final_symbols}")
    print(f"通知列表最终数量: {len(final_notification_list)} - {final_notification_list}")
    
    # # --- 7. 处理主列表的输出 ---
    # print("\n--- 7. 处理主列表输出 ---")
    # backup_dir = os.path.dirname(backup_file)
    # if not os.path.exists(backup_dir): os.makedirs(backup_dir, exist_ok=True)
    # try:
    #     with open(backup_file, 'r', encoding='utf-8') as f:
    #         old_set = {line.strip() for line in f if line.strip()}
    #     print(f"已从主列表备份加载 {len(old_set)} 个旧 symbol。")
    # except FileNotFoundError:
    #     old_set = set()
    #     print("未找到主列表备份文件，视作首次运行。")

    # # 计算“新增”符号
    # new_set = set(final_symbols) - old_set
    # if new_set:
    #     print(f"主列表本次新增 {len(new_set)} 个 symbol: {sorted(new_set)}")
    #     try:
    #         with open(output_file, 'w', encoding='utf-8') as f:
    #             for sym in sorted(new_set):
    #                 f.write(sym + '\n')
    #         print(f"新增结果已写入: {output_file}")
    #     except IOError as e:
    #         print(f"写入 news 文件时错误: {e}")
    # else:
    #     print("本次没有发现新的 symbol。")
    #     # 如果没有新增且旧 news 文件存在，就删掉它
    #     if os.path.exists(output_file):
    #         os.remove(output_file)
    #         print(f"无新增，已删除旧的 news 文件: {output_file}")

    # --- 3. 更新 JSON 面板（只写新增 new_set） ---
    # 如果 new_set 为空，update_json_group 会写一个空的 {} 过去
    update_json_group(final_symbols, panel_json_file, "Next_Week")

    # --- 最后，把本次完整 final_symbols 覆盖写回 备份文件 ---
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            # ### 修改点: 备份文件保存的是当前所有符合条件的 symbol (过滤后) ###
            for sym in sorted(final_symbols):
                f.write(sym + '\n')
        print(f"主列表备份文件已更新，共 {len(final_symbols)} 个 symbol: {backup_file}")
    except IOError as e:
        print(f"更新主列表备份文件时错误: {e}")

    # # --- 8. 处理通知列表的输出 ---
    # # (这部分无变化, 除了变量名 final_notification_list)
    # print("\n--- 8. 处理通知列表输出 ---")
    # backup_dir = os.path.dirname(backup_notification_file)
    # if not os.path.exists(backup_dir):
    #     os.makedirs(backup_dir, exist_ok=True)

    # # 读取旧的 notification backup
    # try:
    #     with open(backup_notification_file, 'r', encoding='utf-8') as f:
    #         old_notif = {line.strip() for line in f if line.strip()}
    #     print(f"已从通知备份加载 {len(old_notif)} 个旧 symbol。")
    # except FileNotFoundError:
    #     old_notif = set()
    #     print("未找到通知备份文件，视作首次运行。")

    # # --- 修改：使用最终的通知列表来计算新增部分 ---
    # new_notif = set(final_notification_list) - old_notif
    # if new_notif:
    #     print(f"通知列表本次新增 {len(new_notif)} 个 symbol: {sorted(new_notif)}")
    #     with open(notification_file, 'w', encoding='utf-8') as f:
    #         for sym in sorted(new_notif):
    #             f.write(sym + '\n')
    # else:
    #     print("本次没有新增的通知 symbol。")
    #     # 若旧的 news/notification_earning.txt 存在，则删掉它
    #     if os.path.exists(notification_file):
    #         os.remove(notification_file)
    #         print(f"无新增，已删除旧的通知文件: {notification_file}")

    # ### 修改点: 使用 new_notif (仅新增部分) 更新 JSON 面板 ###
    update_json_group(final_notification_list, panel_json_file, "Notification")

    # 最后，把本次完整的 filtered_3 覆盖写回 backup
    try:
        with open(backup_notification_file, 'w', encoding='utf-8') as f:
            # --- 修改：备份最终的完整通知列表 ---
            for sym in sorted(final_notification_list):
                f.write(sym + '\n')
        print(f"通知备份已更新，共 {len(final_notification_list)} 个 symbol: {backup_notification_file}")
    except IOError as e:
        print(f"更新通知备份文件时错误: {e}")

# --- 程序入口 ---
if __name__ == "__main__":
    process_stocks()