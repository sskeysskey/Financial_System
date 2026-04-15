import json
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

# ========== 文件路径 ==========
DB_PATH = "/Users/yanzhang/Coding/Database/Finance.db"
SECTORS_ALL_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
EARNING_HISTORY_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Earning_History.json"
SECTORS_PANEL_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json"

# ========== 加载 JSON 文件 ==========
with open(SECTORS_ALL_PATH, 'r', encoding='utf-8') as f:
    sectors_all = json.load(f)

with open(EARNING_HISTORY_PATH, 'r', encoding='utf-8') as f:
    earning_history = json.load(f)

with open(SECTORS_PANEL_PATH, 'r', encoding='utf-8') as f:
    sectors_panel = json.load(f)

# ========== 需要提取 symbol 的分组 ==========
target_groups = [
    "Short", "Short_W", "Strategy12", "Strategy34", "OverSell_W",
    "PE_Deep", "PE_Deeper", "PE_W", "PE_valid", "PE_invalid",
    "PE_Volume", "PE_Volume_up", "PE_Hot", "PE_Volume_high"
]

# ========== 从目标分组中提取所有唯一 symbol ==========
symbols = set()
for group in target_groups:
    if group in sectors_panel:
        for symbol in sectors_panel[group]:
            symbols.add(symbol)

print(f"共提取 {len(symbols)} 个唯一 symbol: {sorted(symbols)}")

# ========== 连接数据库，构建 symbol -> 表名 映射 ==========
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 从数据库各表中读取所有 name，构建完整映射
symbol_to_table = {}
for table in sectors_all.keys():
    try:
        cursor.execute(f'SELECT DISTINCT name FROM [{table}]')
        for (name,) in cursor.fetchall():
            symbol_to_table[name] = table
    except Exception as e:
        print(f"查询表 [{table}] 出错: {e}")

# ========== 逐个 symbol 分析支撑位 ==========
support_close = {}   # 接近支撑位（最新价 > 支撑位，差值 ≤ 2.6%）
support_over = {}    # 跌破支撑位（最新价 ≤ 支撑位）

earning_close = defaultdict(list)  # 日期 -> symbol列表
earning_over = defaultdict(list)

for symbol in sorted(symbols):
    table = symbol_to_table.get(symbol)
    if not table:
        print(f"⚠️  {symbol} 未在数据库任何表中找到，跳过")
        continue

    try:
        # 1. 获取该 symbol 的最新一条记录 (将 price 改为 low)
        cursor.execute(
            f'SELECT date, price, low FROM [{table}] WHERE name = ? ORDER BY date DESC LIMIT 1',
            (symbol,)
        )
        latest_row = cursor.fetchone()
        # 此时 latest_row 包含 (date, close_price, low_price)
        if not latest_row:
            print(f"⚠️  {symbol} 在表 [{table}] 中无数据，跳过")
            continue

        latest_date, latest_close, latest_low = latest_row # 新增 latest_low

        # 2. 获取最新日期往前 31 天内的历史记录（不含最新当天）
        latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

        # 设定初始回溯天数为 31 天
        lookback_days = 31
        skip_symbol = False # 用于标记是否在61天后依然无效而需要跳过
        
        # 使用循环来处理可能的周期延展逻辑
        while True:
            date_ago = (latest_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            # 获取历史记录，按日期升序排列，方便获取“昨天”的日期
            cursor.execute(
                f'SELECT date, price FROM [{table}] WHERE name = ? AND date >= ? AND date < ? ORDER BY date ASC',
                (symbol, date_ago, latest_date)
            )
            hist_rows = cursor.fetchall()

            if not hist_rows:
                break  # 如果没有数据，跳出循环在外部处理

            # 3. 检查周期内是否有财报日且涨跌幅为正
            # cursor.execute(
            #     '''SELECT date, price FROM Earning 
            #        WHERE name = ? AND date >= ? AND date < ? 
            #        ORDER BY date DESC LIMIT 1''',
            #     (symbol, date_ago, latest_date)
            # )
            # earning_row = cursor.fetchone()

            # support_price = None
            # support_date = None
            # support_type = ""

            # # 如果有财报记录，且财报日当天涨跌幅（price字段） > 0
            # if earning_row and earning_row[1] > 0:
            #     earning_date = earning_row[0]
            #     # 从历史记录中找到财报日当天的收盘价
            #     for r_date, r_price in hist_rows:
            #         if r_date == earning_date:
            #             support_price = r_price
            #             support_date = earning_date
            #             support_type = f"财报支撑({earning_date})"
            #             break
            
            # 如果没有符合条件的财报日，则回退到使用最低价
            # if support_price is None:
            min_date, min_price = min(hist_rows, key=lambda x: x[1])
            support_price = min_price
            support_date = min_date
            support_type = f"最低价支撑({support_date})"

            # 4. 检查是否需要延展周期到 61 天，或者 61 天后依然无效跳过
            # hist_rows[-1][0] 是距离 latest_date 最近的一个交易日（即“昨天”）
            last_trading_day = hist_rows[-1][0]
            
            if support_date == last_trading_day:
                if lookback_days == 31:
                    print(f"  🔄 {symbol}: 支撑点为前一交易日({support_date})，可能处于持续下跌中，将判断周期延展至 61 天")
                    lookback_days = 61
                    continue  # 重新执行 while 循环，使用 61 天的数据
                elif lookback_days == 61:
                    print(f"  ⏭️ {symbol}: 延展至 61 天后，支撑点仍为前一交易日({support_date})，跳过")
                    skip_symbol = True
                    break # 即使是61天依然是前一天，跳出循环并标记跳过
            else:
                break  # 找到了合适的支撑位（非前一交易日），跳出循环

        # 检查是否因为无历史数据或触发了61天跳过逻辑
        if not hist_rows:
            print(f"⚠️  {symbol} {lookback_days}天内无历史数据可比较，跳过")
            continue
        if skip_symbol:
            continue

        # 5. 检查支撑点日期与最新日期的天数差
        support_dt = datetime.strptime(support_date, "%Y-%m-%d")
        days_diff = (latest_dt - support_dt).days
        
        if days_diff < 7:
            print(f"  ⚠️ {symbol}: 支撑点日期({support_date})距最新日期({latest_date})仅 {days_diff} 天，不足7天，视为无效，跳过")
            continue

        # 6. 比较最新最低价与支撑位
        if latest_low > support_price:
            diff_pct = (latest_low - support_price) / support_price * 100
            if diff_pct <= 2.61:
                support_close[symbol] = ""
                earning_close[latest_date].append(symbol)
                print(f"  ✅ {symbol}: SupportLevel_Close "
                    f"(最新最低={latest_low}, 支撑={support_price} [{support_type}], 差={diff_pct:.2f}%)")
        else:
            # 最新价 ≤ 支撑位，即跌破支撑
            
            # ========== 新增逻辑：判断最近一次财报 ==========
            support_val = ""
            
            # # 获取最近一次财报（日期小于等于最新日期）
            # cursor.execute(
            #     '''SELECT date, price FROM Earning 
            #        WHERE name = ? AND date <= ? 
            #        ORDER BY date DESC LIMIT 1''',
            #     (symbol, latest_date)
            # )
            # last_earning = cursor.fetchone()
            
            # # 如果存在财报且财报日涨跌幅为正值
            # if last_earning and last_earning[1] > 0:
            #     last_earning_date = last_earning[0]
                
            #     # 获取该财报日的收盘价
            #     cursor.execute(
            #         f'SELECT price FROM [{table}] WHERE name = ? AND date = ?',
            #         (symbol, last_earning_date)
            #     )
            #     earning_price_row = cursor.fetchone()
                
            #     if earning_price_row:
            #         earning_close_price = earning_price_row[0]
                    
            #         # 计算最新价与财报日收盘价的百分比差值（绝对值）
            #         diff_pct = abs(latest_low - earning_close_price) / earning_close_price * 100
                    
            #         # 如果差值在 2.6% 以内，则加上“财”字
            #         if diff_pct <= 2.6:
            #             support_val = f"{symbol}财"

            support_over[symbol] = support_val
            earning_over[latest_date].append(symbol)
            
            # 打印日志时附带财报条件信息（如果满足）
            # extra_info = f" [符合财报条件: {support_val}]" if support_val else ""
            print(f"  🔻 {symbol}: SupportLevel_Over "
                  f"(最新最低={latest_low}, 支撑={support_price} [{support_type}])")

    except Exception as e:
        print(f"处理 {symbol} 时出错: {e}")

conn.close()

# ========== 更新 Sectors_panel.json ==========
# 清除原内容后写入新结果
sectors_panel["SupportLevel_Close"] = support_close
sectors_panel["SupportLevel_Close_backup"] = support_close.copy()
sectors_panel["SupportLevel_Over"] = support_over
sectors_panel["SupportLevel_Over_backup"] = support_over.copy()

# ========== 更新 Earning_History.json ==========
# SupportLevel_Close（追加日期条目）
if "SupportLevel_Close" not in earning_history:
    earning_history["SupportLevel_Close"] = {}
for date_key, sym_list in earning_close.items():
    earning_history["SupportLevel_Close"][date_key] = sorted(sym_list)

# SupportLevel_Over
if "SupportLevel_Over" not in earning_history:
    earning_history["SupportLevel_Over"] = {}
for date_key, sym_list in earning_over.items():
    earning_history["SupportLevel_Over"][date_key] = sorted(sym_list)

# ========== 写回文件 ======
with open(SECTORS_PANEL_PATH, 'w', encoding='utf-8') as f:
    json.dump(sectors_panel, f, indent=4, ensure_ascii=False)

with open(EARNING_HISTORY_PATH, 'w', encoding='utf-8') as f:
    json.dump(earning_history, f, indent=4, ensure_ascii=False)

print(f"\n===== 完成 =====")
print(f"SupportLevel_Close ({len(support_close)}个): {list(support_close.keys())}")
print(f"SupportLevel_Over  ({len(support_over)}个): {list(support_over.keys())}")