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
    "PE_Deep", "PE_Deeper", "PE_W", "PE_valid", "PE_invalid", "season",
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

        # 2. 获取历史支撑位（31天 -> 可能延展到61天）
        lookback_days = 31
        skip_symbol = False

        while True:
            date_ago = (latest_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            # 获取历史记录，按日期升序排列，方便获取“昨天”的日期
            # 【修改点 1】：将 SELECT date, price 改为 SELECT date, low
            cursor.execute(
                f'SELECT date, low FROM [{table}] WHERE name = ? AND date >= ? AND date < ? ORDER BY date ASC',
                (symbol, date_ago, latest_date)
            )
            hist_rows = cursor.fetchall()

            if not hist_rows:
                break

            min_date, min_low = min(hist_rows, key=lambda x: x[1])
            support_price = min_low
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
                    print(f"  ⏭️ {symbol}: 延展至 61 天后，支撑点仍为前一交易日({support_date})")
                    skip_symbol = True
                    break # 即使是61天依然是前一天，跳出循环并标记跳过
            else:
                break  # 找到了合适的支撑位（非前一交易日），跳出循环

        # ===== Phase 2: 标准支撑位检查 =====
        symbol_categorized = False

        if not hist_rows:
            print(f"⚠️  {symbol} {lookback_days}天内无历史数据可比较")
            # 如果不是61天延展场景，直接跳过
            if lookback_days != 61:
                continue
            # 否则留给 Phase 3 财报回退检查
        elif skip_symbol:
            # 61天后支撑点仍为前一交易日，不直接跳过，留给 Phase 3
            pass
        else:
            support_dt = datetime.strptime(support_date, "%Y-%m-%d")
            days_diff = (latest_dt - support_dt).days

            if days_diff < 8:
                print(f"  ⚠️ {symbol}: 支撑点日期({support_date})距最新日期({latest_date})仅 {days_diff} 天，不足8天，视为无效")
                # 如果不是61天延展场景，直接跳过
                if lookback_days != 61:
                    continue
                # 否则留给 Phase 3
            else:
                # 比较最新收盘价与支撑位
                if latest_close > support_price: # 修改点
                    diff_pct = (latest_close - support_price) / support_price * 100 # 修改点
                    if diff_pct <= 2.6:
                        support_close[symbol] = ""
                        earning_close[latest_date].append(symbol)
                        symbol_categorized = True
                        print(f"  ✅ {symbol}: SupportLevel_Close (最新收盘={latest_close}, 支撑={support_price}, 差={diff_pct:.2f}%)")
                else:
                    # 最新收盘价 ≤ 支撑位，跌破支撑
                    support_over[symbol] = ""
                    earning_over[latest_date].append(symbol)
                    symbol_categorized = True
                    print(f"  🔻 {symbol}: SupportLevel_Over (最新收盘={latest_close}, 支撑={support_price})")

        # ===== Phase 3: 财报支撑回退检查（仅当延展到61天且标准检查未产生结果时） =====
        if not symbol_categorized and lookback_days == 61:
            date_61_ago = (latest_dt - timedelta(days=61)).strftime("%Y-%m-%d")

            # 在61天范围内查找 price 为正值的最近一次财报
            cursor.execute(
                '''SELECT date, price FROM Earning 
                   WHERE name = ? AND date >= ? AND date < ? AND price > 0
                   ORDER BY date DESC LIMIT 1''',
                (symbol, date_61_ago, latest_date)
            )
            earning_row = cursor.fetchone()

            if earning_row:
                earning_date = earning_row[0]

                # 获取该财报日在对应表中的 low 作为支撑位
                cursor.execute(
                    f'SELECT low FROM [{table}] WHERE name = ? AND date = ?',
                    (symbol, earning_date)
                )
                earning_low_row = cursor.fetchone()

                if earning_low_row:
                    earning_support = earning_low_row[0]
                    earning_dt = datetime.strptime(earning_date, "%Y-%m-%d")
                    e_days_diff = (latest_dt - earning_dt).days
                    earning_support_type = f"财报支撑({earning_date})"

                    if e_days_diff < 8:
                        print(f"  ⚠️ {symbol}: 财报日({earning_date})距最新日期仅 {e_days_diff} 天，不足8天，跳过")
                    else:
                        if latest_close > earning_support: # 修改点
                            diff_pct = (latest_close - earning_support) / earning_support * 100 # 修改点
                            if diff_pct <= 2.6:
                                support_close[symbol] = f"{symbol}财"
                                earning_close[latest_date].append(symbol)
                                symbol_categorized = True
                                print(f"  ✅ {symbol}: SupportLevel_Close [财报回退] (最新收盘={latest_close}, 支撑={earning_support}, 差={diff_pct:.2f}%)")
                        else:
                            support_over[symbol] = f"{symbol}财"
                            earning_over[latest_date].append(symbol)
                            symbol_categorized = True
                            print(f"  🔻 {symbol}: SupportLevel_Over [财报回退] (最新收盘={latest_close}, 支撑={earning_support})")

            if not symbol_categorized:
                print(f"  ⏭️ {symbol}: 61天范围内无符合条件的财报支撑，最终跳过")

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

# ========== 写回文件 ==========
with open(SECTORS_PANEL_PATH, 'w', encoding='utf-8') as f:
    json.dump(sectors_panel, f, indent=4, ensure_ascii=False)

with open(EARNING_HISTORY_PATH, 'w', encoding='utf-8') as f:
    json.dump(earning_history, f, indent=4, ensure_ascii=False)

print(f"\n===== 完成 =====")
print(f"SupportLevel_Close ({len(support_close)}个): {list(support_close.keys())}")
print(f"SupportLevel_Over  ({len(support_over)}个): {list(support_over.keys())}")