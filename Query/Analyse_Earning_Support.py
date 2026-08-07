import json
import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# ================= 配置区域 =================
# 如果为空，则运行"今天"模式；如果填入日期（如 "2024-11-03"），则运行回测模式
SYMBOL_TO_TRACE = "" 
TARGET_DATE = "" 

# SYMBOL_TO_TRACE = "BE"
# TARGET_DATE = "2026-05-18"

# 【新增配置项】支撑点距离最新日期的最小天数要求
MIN_SUPPORT_DAYS = 6

# 【新增配置项】支撑位判定阈值（百分比），例如 2.6 代表 2.6%
SUPPORT_THRESHOLD_PCT = 2.6

# ========== 【新增】SupportLevel_Over 顺延继承配置 ==========
# 规则：某天判定为 SupportLevel_Over 后，只要之后收盘价继续比前一日更低，
#       就直接顺延判定为 SupportLevel_Over（不再重算支撑位）；
#       直到某天收盘价不再走低（>= 前一日），链条断开，下次再跌时恢复完整判定逻辑。
ENABLE_OVER_INHERIT = True      # 顺延继承总开关
INHERIT_SUFFIX = "延"            # 顺延命中的标记后缀（写入 Sectors_panel 的 value）
INHERIT_ALLOW_GAP = True        # 允许 history 缺少"前一交易日"key 时向前找最近记录
INHERIT_GAP_MAX_DAYS = 7        # 向前找的最大自然日跨度
MAX_INHERIT_DAYS = 0            # 顺延链条最大连续天数上限（0 = 不限制）
INHERIT_IGNORE_EARNING_DAY = False  # True: 顺延时忽略"最新日为财报日则跳过"的过滤
FORCE_KEEP_OVER_CHAIN = False   # True: 即使 symbol 已掉出目标分组，只要昨天在 Over 链上也强制参与运算

# ========== 文件路径 ==========
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")
SECTORS_PANEL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")


def run_support_logic(log_detail):
    log_detail("Analyse_Earning_Support 程序开始运行...")
    if SYMBOL_TO_TRACE: 
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    
    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel 和 History JSON 文件。\n")

    # ========== 加载 JSON 文件 ==========
    try:
        with open(SECTORS_ALL_PATH, 'r', encoding='utf-8') as f:
            sectors_all = json.load(f)
        with open(EARNING_HISTORY_PATH, 'r', encoding='utf-8') as f:
            earning_history = json.load(f)
        with open(SECTORS_PANEL_PATH, 'r', encoding='utf-8') as f:
            sectors_panel = json.load(f)
    except Exception as e:
        log_detail(f"加载 JSON 文件失败: {e}")
        return

    # ========== 需要提取 symbol 的分组 ==========
    target_groups = [
        "Short", "Short_W", "Strategy12", "Strategy34", "OverSell_W",
        "PE_Deep", "PE_Deeper", "PE_W", "PE_valid", "PE_invalid", "season",
        "PE_Volume", "PE_Volume_up", "PE_Hot", "PE_Volume_high"
    ]

    # ========== 从目标分组中提取所有唯一 symbol ==========
    symbols = set()
    
    if TARGET_DATE:
        # 回测模式：从 earning_history 中按 TARGET_DATE 提取
        log_detail(f"正在从 Earning_History.json 提取 {TARGET_DATE} 的历史数据作为回测起点...")
        for group in target_groups:
            if group in earning_history and TARGET_DATE in earning_history[group]:
                for symbol in earning_history[group][TARGET_DATE]:
                    symbols.add(symbol)
    else:
        # 正常模式：从 sectors_panel 中提取最新数据
        log_detail("正在从 Sectors_panel.json 提取最新数据作为运行起点...")
        for group in target_groups:
            if group in sectors_panel:
                for symbol in sectors_panel[group]:
                    symbols.add(symbol)

    # ========== 【新增】Over 顺延继承所需的历史索引 ==========
    over_history = earning_history.get("SupportLevel_Over", {}) or {}

    def _was_over_on(date_str, symbol):
        """判断某个日期该 symbol 是否被判定为 SupportLevel_Over"""
        items = over_history.get(date_str)
        if not items:
            return False
        for it in items:
            if not isinstance(it, str):
                continue
            # history 里存的是纯 symbol，这里做宽松匹配以兼容带后缀的写法
            if it == symbol or it.startswith(symbol):
                return True
        return False

    # 【可选】把仍在 Over 链条上的 symbol 强行拉回运算池
    if ENABLE_OVER_INHERIT and FORCE_KEEP_OVER_CHAIN and over_history:
        try:
            ref_date = TARGET_DATE if TARGET_DATE else max(over_history.keys())
            ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
            added = 0
            for d_key, items in over_history.items():
                try:
                    d_dt = datetime.strptime(d_key, "%Y-%m-%d")
                except Exception:
                    continue
                if 0 <= (ref_dt - d_dt).days <= INHERIT_GAP_MAX_DAYS:
                    for it in items:
                        if isinstance(it, str) and it and it not in symbols:
                            symbols.add(it)
                            added += 1
            if added:
                log_detail(f"[顺延] FORCE_KEEP_OVER_CHAIN 已额外纳入 {added} 个仍在 Over 链上的 symbol")
        except Exception as e:
            log_detail(f"[顺延] 强制纳入 Over 链 symbol 时出错: {e}")

    log_detail(f"共提取 {len(symbols)} 个唯一 symbol")

    # ========== 追踪校验 ==========
    if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE not in symbols:
        log_detail(f"⚠️ [警告] 追踪的 Symbol '{SYMBOL_TO_TRACE}' 未在任何目标分组中找到。")
        log_detail(f"   可能原因：")
        log_detail(f"   1. 该 Symbol 在 {TARGET_DATE or '最新日期'} 确实不在这些分组中: {target_groups}")
        log_detail(f"   2. JSON 文件中该日期的数据结构可能缺失。")
        return

    # ========== 连接数据库，构建 symbol -> 表名 映射 ==========
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    symbol_to_table = {}
    for table in sectors_all.keys():
        try:
            cursor.execute(f'SELECT DISTINCT name FROM [{table}]')
            for (name,) in cursor.fetchall():
                symbol_to_table[name] = table
        except Exception as e:
            log_detail(f"查询表 [{table}] 出错: {e}")

    # ========== 【新增】继承来源日定位（含缺口校验 + 链长限制） ==========
    def _resolve_inherit_source_date(symbol, table, latest_date, prev_date, is_tracing):
        """
        返回 (source_date, reason) —— source_date 为 None 表示不满足顺延条件。
        1) 优先精确匹配"上一交易日"；
        2) 若 history 缺少该 key 且允许缺口，则向前找最近有记录的日期，
           并校验从该日到最新日的每个交易日收盘价都在逐日下跌；
        3) 若设置了 MAX_INHERIT_DAYS，则限制连续 Over 天数。
        """
        source_date = None
        reason = ""

        if _was_over_on(prev_date, symbol):
            source_date = prev_date
            reason = "前一交易日"
        elif INHERIT_ALLOW_GAP:
            latest_dt_local = datetime.strptime(latest_date, "%Y-%m-%d")
            candidates = []
            for d_key in over_history.keys():
                try:
                    d_dt = datetime.strptime(d_key, "%Y-%m-%d")
                except Exception:
                    continue
                gap = (latest_dt_local - d_dt).days
                if 0 < gap <= INHERIT_GAP_MAX_DAYS and _was_over_on(d_key, symbol):
                    candidates.append(d_key)
            if candidates:
                cand = max(candidates)
                # 校验 cand -> latest_date 之间收盘价逐日下跌
                cursor.execute(
                    f'SELECT date, price FROM [{table}] WHERE name = ? AND date >= ? AND date <= ? ORDER BY date ASC',
                    (symbol, cand, latest_date)
                )
                rows = cursor.fetchall()
                ok = len(rows) >= 2
                for i in range(1, len(rows)):
                    if rows[i][1] >= rows[i - 1][1]:
                        ok = False
                        break
                if ok:
                    source_date = cand
                    reason = f"缺口继承(跨{len(rows) - 1}个交易日,收盘价逐日下跌)"
                elif is_tracing:
                    log_detail(f"  ⛔ [顺延] 找到 {cand} 的 Over 记录，但期间收盘价非逐日下跌，放弃继承")

        if not source_date:
            return None, ""

        # 链长限制
        if MAX_INHERIT_DAYS and MAX_INHERIT_DAYS > 0:
            cursor.execute(
                f'SELECT date FROM [{table}] WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT ?',
                (symbol, source_date, MAX_INHERIT_DAYS + 2)
            )
            back_dates = [r[0] for r in cursor.fetchall()]
            streak = 0
            for d in back_dates:
                if _was_over_on(d, symbol):
                    streak += 1
                else:
                    break
            if streak >= MAX_INHERIT_DAYS:
                if is_tracing:
                    log_detail(f"  ⛔ [顺延] 已连续 Over {streak} 天，达到上限 {MAX_INHERIT_DAYS}，本次改走完整判定逻辑")
                return None, ""

        return source_date, reason

    # ========== 逐个 symbol 分析支撑位 ==========
    support_close = {}   # 接近支撑位（最新价 > 支撑位，差值 ≤ SUPPORT_THRESHOLD_PCT）
    support_over = {}    # 跌破支撑位（最新价 ≤ 支撑位）

    earning_close = defaultdict(list)  # 日期 -> symbol列表
    earning_over = defaultdict(list)

    inherit_hits = []    # 【新增】记录本次顺延命中的 symbol

    for symbol in sorted(symbols):
        is_tracing = (symbol == SYMBOL_TO_TRACE)
        table = symbol_to_table.get(symbol)
        
        if not table:
            if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 未在数据库任何表中找到，跳过")
            continue

        if is_tracing: log_detail(f"\n>>> [追踪] 开始分析 {symbol} (所在表: {table})")

        try:
            # 1. 获取该 symbol 的最新两条记录 (包含前一交易日，用于判断收盘价是否下跌)
            if TARGET_DATE:
                cursor.execute(
                    f'SELECT date, price, low FROM [{table}] WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2',
                    (symbol, TARGET_DATE)
                )
            else:
                cursor.execute(
                    f'SELECT date, price, low FROM [{table}] WHERE name = ? ORDER BY date DESC LIMIT 2',
                    (symbol,)
                )
                
            latest_rows = cursor.fetchall()
            
            if not latest_rows or len(latest_rows) < 2:
                if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 在目标日期前数据不足两条，跳过")
                continue

            # 提取最新一日和前一日的数据
            latest_date, latest_close, latest_low = latest_rows[0]
            prev_date, prev_close, prev_low = latest_rows[1]

            # [新增] 检查 latest_date 是否为财报日
            cursor.execute('SELECT 1 FROM Earning WHERE name = ? AND date = ?', (symbol, latest_date))
            is_earning_day = cursor.fetchone() is not None

            # 新增条件：最新收盘价必须低于前一日收盘价
            if latest_close >= prev_close:
                if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 最新收盘价({latest_close}) 未低于前一日收盘价({prev_close})，跳过（Over 顺延链条在此断开）")
                continue

            if is_tracing: 
                log_detail(f"  -> 最新交易日: {latest_date}, 收盘价: {latest_close}, 最低价: {latest_low} (前一日收盘: {prev_close})")

            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

            # ========== 【往前推20天扫描 PE_Volume_high (带'甲')】 ==========
            pe_high_tag = ""
            pe_vol_high_history = earning_history.get("PE_Volume_high", {})
            for i in range(21): 
                check_date = (latest_dt - timedelta(days=i)).strftime("%Y-%m-%d")
                if check_date in pe_vol_high_history:
                    for item in pe_vol_high_history[check_date]:
                        if item.startswith(symbol) and '甲' in item:
                            pe_high_tag = f" \033[95m[PE_High甲:{check_date}]\033[0m"
                            break
                if pe_high_tag:
                    break
            # ======================================================================

            # ===== 【新增】Phase 0: SupportLevel_Over 顺延继承 =====
            # 能走到这里说明 latest_close < prev_close（今天收盘更低）。
            # 若"上一交易日"该 symbol 已被判定为 Over，则直接顺延判定为 Over，跳过所有支撑位计算。
            if ENABLE_OVER_INHERIT:
                if is_earning_day and not INHERIT_IGNORE_EARNING_DAY:
                    if is_tracing:
                        log_detail(f"  ⏭️ [顺延] 最新交易日({latest_date})为财报日，按配置不走顺延继承")
                else:
                    src_date, src_reason = _resolve_inherit_source_date(
                        symbol, table, latest_date, prev_date, is_tracing
                    )
                    if src_date:
                        support_over[symbol] = f"{symbol}{INHERIT_SUFFIX}"
                        earning_over[latest_date].append(symbol)
                        inherit_hits.append(symbol)
                        log_detail(
                            f"  ✅🔻 {symbol}: SupportLevel_Over [顺延继承·{src_reason} 源日期={src_date}] "
                            f"(最新收盘={latest_close} < 前收={prev_close}，跳过支撑位重算){pe_high_tag}"
                        )
                        continue
                    elif is_tracing:
                        log_detail(f"  -> [顺延] 前一交易日({prev_date})无 Over 记录，走完整判定逻辑")
            # ======================================================

            # [原逻辑] 最新交易日为财报日则过滤跳过
            if is_earning_day:
                if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 最新交易日({latest_date})恰好为财报日，按规则过滤跳过")
                continue

            # 2. 获取历史支撑位（31天 -> 可能延展到61天）
            lookback_days = 31
            skip_symbol = False

            while True:
                date_ago = (latest_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

                cursor.execute(
                    f'SELECT date, low, price FROM [{table}] WHERE name = ? AND date >= ? AND date < ? ORDER BY date ASC',
                    (symbol, date_ago, latest_date)
                )
                hist_rows = cursor.fetchall()

                if not hist_rows:
                    if is_tracing: log_detail(f"  -> {lookback_days}天内无历史数据")
                    break

                sorted_rows = sorted(hist_rows, key=lambda x: x[1])
                
                min_row = sorted_rows[0]
                second_min_row = sorted_rows[1] if len(sorted_rows) > 1 else None
                third_min_row = sorted_rows[2] if len(sorted_rows) > 2 else None

                support_date = min_row[0]
                support_price_low = min_row[1]
                support_price_close = min_row[2]
                
                last_trading_day = hist_rows[-1][0]

                if is_tracing: 
                    log_detail(f"  -> {lookback_days}天内最低点: {support_date} (Low: {support_price_low}, Close: {support_price_close}) | 前一交易日: {last_trading_day}")
                    if second_min_row:
                        log_detail(f"  -> {lookback_days}天内【次低点】: {second_min_row[0]} (Low: {second_min_row[1]}, Close: {second_min_row[2]})")
                    if third_min_row:
                        log_detail(f"  -> {lookback_days}天内【第三低】: {third_min_row[0]} (Low: {third_min_row[1]}, Close: {third_min_row[2]})")

                # 4. 检查是否需要延展周期
                if support_date == last_trading_day:
                    if lookback_days == 31:
                        if is_tracing: log_detail(f"  🔄 支撑点为前一交易日，可能处于持续下跌中，延展至 61 天")
                        lookback_days = 61
                        continue
                    elif lookback_days == 61:
                        if is_tracing: log_detail(f"  ⏭️ 延展至 61 天后，支撑点仍为前一交易日，标记为跳过基础检查")
                        skip_symbol = True
                        break
                else:
                    break

            # ===== Phase 2: 标准支撑位检查 =====
            symbol_categorized = False
            is_earning_fallback = False

            if not hist_rows:
                if lookback_days != 61:
                    continue
            elif skip_symbol:
                pass
            else:
                support_dt = datetime.strptime(support_date, "%Y-%m-%d")
                days_diff = (latest_dt - support_dt).days

                if days_diff < MIN_SUPPORT_DAYS:
                    if is_tracing: log_detail(f"  ⚠️ 支撑点(low)距离最新日期仅 {days_diff} 天，不足{MIN_SUPPORT_DAYS}天，尝试使用收盘价(price)寻找支撑点...")
                    
                    min_close_row = min(hist_rows, key=lambda x: x[2])
                    support_date_close = min_close_row[0]
                    support_dt_close = datetime.strptime(support_date_close, "%Y-%m-%d")
                    days_diff_close = (latest_dt - support_dt_close).days
                    
                    if days_diff_close < MIN_SUPPORT_DAYS:
                        if is_tracing: log_detail(f"  ⚠️ 收盘价(price)支撑点距离最新日期也仅 {days_diff_close} 天，视为无效")
                        
                        if is_tracing: log_detail(f"  -> 尝试使用最近财报日的 low 和 price 作为支撑点...")
                        cursor.execute(
                            '''SELECT date FROM Earning 
                               WHERE name = ? AND date < ?
                               ORDER BY date DESC LIMIT 1''',
                            (symbol, latest_date)
                        )
                        recent_earning_row = cursor.fetchone()
                        earning_fallback_success = False
                        
                        if recent_earning_row:
                            recent_e_date = recent_earning_row[0]
                            recent_e_dt = datetime.strptime(recent_e_date, "%Y-%m-%d")
                            recent_e_days_diff = (latest_dt - recent_e_dt).days
                            
                            if recent_e_days_diff >= MIN_SUPPORT_DAYS:
                                cursor.execute(
                                    f'SELECT low, price FROM [{table}] WHERE name = ? AND date = ?',
                                    (symbol, recent_e_date)
                                )
                                recent_e_price_row = cursor.fetchone()
                                if recent_e_price_row:
                                    support_date = recent_e_date
                                    support_price_low = recent_e_price_row[0]
                                    support_price_close = recent_e_price_row[1]
                                    days_diff = recent_e_days_diff
                                    earning_fallback_success = True
                                    is_earning_fallback = True
                                    if is_tracing: log_detail(f"  ✅ 切换为最近财报日支撑点: {support_date} (Low: {support_price_low}, Close: {support_price_close})")
                                else:
                                    if is_tracing: log_detail(f"  ⚠️ 最近财报日({recent_e_date})在表 [{table}] 中无价格数据")
                            else:
                                if is_tracing: log_detail(f"  ⚠️ 最近财报日({recent_e_date})距离最新日期仅 {recent_e_days_diff} 天，不足{MIN_SUPPORT_DAYS}天")
                        else:
                            if is_tracing: log_detail(f"  ⚠️ 未找到该 symbol 的历史财报记录")
                            
                        if not earning_fallback_success:
                            if lookback_days != 61:
                                continue
                    else:
                        support_date = support_date_close
                        support_price_low = min_close_row[1]
                        support_price_close = min_close_row[2]
                        days_diff = days_diff_close
                        if is_tracing: log_detail(f"  ✅ 切换为收盘价(price)支撑点: {support_date} (Low: {support_price_low}, Close: {support_price_close})")

                if days_diff >= MIN_SUPPORT_DAYS or lookback_days == 61:
                    if days_diff >= MIN_SUPPORT_DAYS:
                        val_suffix = "财" if is_earning_fallback else ""
                        tag_prefix = "[最近财报日Fallback] " if is_earning_fallback else ""
                        
                        if latest_close > support_price_low:
                            diff_pct = (latest_close - support_price_low) / support_price_low * 100
                            if is_tracing: log_detail(f"  -> 距离支撑位(low)差值: {diff_pct:.2f}% (阈值: {SUPPORT_THRESHOLD_PCT}%)")
                            
                            if diff_pct <= SUPPORT_THRESHOLD_PCT:
                                support_close[symbol] = f"{symbol}{val_suffix}" if val_suffix else ""
                                earning_close[latest_date].append(symbol)
                                symbol_categorized = True
                                log_detail(f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}(最新收盘={latest_close}, 支撑日期={support_date}, 支撑(low)={support_price_low}, 差={diff_pct:.2f}%){pe_high_tag}")
                            else:
                                if is_tracing: log_detail(f"  -> low比较不合格，尝试使用支撑日的收盘价({support_price_close})进行二次比较")
                                if latest_close > support_price_close:
                                    diff_pct_close = (latest_close - support_price_close) / support_price_close * 100
                                    if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                        support_close[symbol] = f"{symbol}{val_suffix}" if val_suffix else ""
                                        earning_close[latest_date].append(symbol)
                                        symbol_categorized = True
                                        log_detail(f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[二次Price比较] (最新收盘={latest_close}, 支撑日期={support_date}, 支撑(price)={support_price_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                                    else:
                                        if is_tracing: log_detail(f"  ⚠️ 二次Price比较差值 {diff_pct_close:.2f}% 仍超 {SUPPORT_THRESHOLD_PCT}%，尝试使用最新日期的low({latest_low})与支撑日的收盘价({support_price_close})进行三次比较")
                                        
                                        if latest_low > support_price_close:
                                            diff_pct_latest_low = (latest_low - support_price_close) / support_price_close * 100
                                            if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                                support_close[symbol] = f"{symbol}{val_suffix}" if val_suffix else ""
                                                earning_close[latest_date].append(symbol)
                                                symbol_categorized = True
                                                log_detail(f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[三次LatestLow比较] (最新low={latest_low}, 支撑日期={support_date}, 支撑(price)={support_price_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                            else:
                                                if is_tracing: log_detail(f"  ⚠️ 三次LatestLow比较差值 {diff_pct_latest_low:.2f}% 仍超 {SUPPORT_THRESHOLD_PCT}%，继续执行")
                                        else:
                                            if is_tracing: log_detail(f"  ⚠️ 最新low({latest_low}) 已跌破或等于支撑(price)({support_price_close})，不符合三次比较条件，继续执行")
                                else:
                                    support_over[symbol] = f"{symbol}{val_suffix}" if val_suffix else ""
                                    earning_over[latest_date].append(symbol)
                                    symbol_categorized = True
                                    log_detail(f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}[二次Price比较] (最新收盘={latest_close}, 支撑日期={support_date}, 支撑(price)={support_price_close}){pe_high_tag}")
                        else:
                            support_over[symbol] = f"{symbol}{val_suffix}" if val_suffix else ""
                            earning_over[latest_date].append(symbol)
                            symbol_categorized = True
                            log_detail(f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}(最新收盘={latest_close}, 支撑日期={support_date}, 支撑(low)={support_price_low}){pe_high_tag}")

            # ===== Phase 2.5: 并行流程 —— 继续向前延展寻找非"昨天"的最低点 =====
            parallel_suffix = ""
            if skip_symbol:
                round_num = 3
                max_rounds = 12

                while round_num <= max_rounds:
                    p_days = 31 * round_num
                    p_date_ago = (latest_dt - timedelta(days=p_days)).strftime("%Y-%m-%d")

                    cursor.execute(
                        f'SELECT date, low, price FROM [{table}] '
                        f'WHERE name = ? AND date >= ? AND date < ? ORDER BY date ASC',
                        (symbol, p_date_ago, latest_date)
                    )
                    p_rows = cursor.fetchall()

                    if not p_rows:
                        if is_tracing: log_detail(f"  ⏹️ 第{round_num}轮({p_days}天)无历史数据，并行流程结束")
                        break

                    p_min_row = min(p_rows, key=lambda x: x[1])
                    p_min_date = p_min_row[0]
                    p_min_low = p_min_row[1]
                    p_min_close = p_min_row[2] 
                    
                    p_last_trading_day = p_rows[-1][0]

                    if p_min_date == p_last_trading_day:
                        if is_tracing: log_detail(f"  🔁 第{round_num}轮({p_days}天)支撑点仍为前一交易日，继续延展")
                        round_num += 1
                        continue

                    p_support_dt = datetime.strptime(p_min_date, "%Y-%m-%d")
                    p_days_diff = (latest_dt - p_support_dt).days

                    if p_days_diff < MIN_SUPPORT_DAYS:
                        if is_tracing: log_detail(f"  ⚠️ 第{round_num}轮支撑点(low)距最新日期仅 {p_days_diff} 天，尝试使用收盘价(price)寻找支撑点...")
                        
                        p_min_close_row = min(p_rows, key=lambda x: x[2])
                        p_min_date_close = p_min_close_row[0]
                        p_support_dt_close = datetime.strptime(p_min_date_close, "%Y-%m-%d")
                        p_days_diff_close = (latest_dt - p_support_dt_close).days
                        
                        if p_days_diff_close < MIN_SUPPORT_DAYS:
                            if is_tracing: log_detail(f"  ⚠️ 第{round_num}轮收盘价(price)支撑点距最新日期也仅 {p_days_diff_close} 天，并行流程放弃")
                            break
                        else:
                            p_min_date = p_min_date_close
                            p_min_low = p_min_close_row[1]
                            p_min_close = p_min_close_row[2]
                            p_days_diff = p_days_diff_close
                            if is_tracing: log_detail(f"  ✅ 第{round_num}轮切换为收盘价(price)支撑点: {p_min_date} (Low: {p_min_low}, Close: {p_min_close})")

                    if p_days_diff >= MIN_SUPPORT_DAYS:
                        if latest_close > p_min_low:
                            diff_pct = (latest_close - p_min_low) / p_min_low * 100
                            if diff_pct <= SUPPORT_THRESHOLD_PCT:
                                parallel_suffix = f"{round_num}轮"
                                log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Close (最新={latest_close}, 支撑日期={p_min_date}, 支撑(low)={p_min_low}, 差={diff_pct:.2f}%){pe_high_tag}")
                            else:
                                if latest_close > p_min_close:
                                    diff_pct_close = (latest_close - p_min_close) / p_min_close * 100
                                    if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                        parallel_suffix = f"{round_num}轮"
                                        log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Close [二次Price比较] (最新={latest_close}, 支撑日期={p_min_date}, 支撑(price)={p_min_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                                    else:
                                        if latest_low > p_min_close:
                                            diff_pct_latest_low = (latest_low - p_min_close) / p_min_close * 100
                                            if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                                parallel_suffix = f"{round_num}轮"
                                                log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Close [三次LatestLow比较] (最新low={latest_low}, 支撑日期={p_min_date}, 支撑(price)={p_min_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                            else:
                                                if is_tracing: log_detail(f"  ⚠️ 第{round_num}轮 Close(含三次LatestLow) 差值超 {SUPPORT_THRESHOLD_PCT}%，并行无输出")
                                        else:
                                            if is_tracing: log_detail(f"  ⚠️ 第{round_num}轮 最新low({latest_low}) <= 支撑(price)({p_min_close})，不符合三次比较条件，并行无输出")
                                else:
                                    parallel_suffix = f"{round_num}轮"
                                    log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Over [二次Price比较] (最新={latest_close}, 支撑日期={p_min_date}, 支撑(price)={p_min_close}){pe_high_tag}")
                        else:
                            parallel_suffix = f"{round_num}轮"
                            log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Over (最新={latest_close}, 支撑日期={p_min_date}, 支撑(low)={p_min_low}){pe_high_tag}")

                    break
                
                if round_num > max_rounds:
                    parallel_suffix = f"{max_rounds}轮"
                    if is_tracing: log_detail(f"  ⚠️ {max_rounds}轮延展全部失效(持续下跌创新低)，强行标记后缀={parallel_suffix}")

            # ===== Phase 3: 财报支撑回退检查（61 天 / 91 天两档） =====
            if not symbol_categorized and lookback_days == 61:
                if is_tracing: log_detail(f"  -> 进入 Phase 3: 财报支撑回退检查")
                
                for fallback_days in (61, 91):
                    if symbol_categorized: break

                    date_N_ago = (latest_dt - timedelta(days=fallback_days)).strftime("%Y-%m-%d")

                    cursor.execute(
                        '''SELECT date, price FROM Earning 
                           WHERE name = ? AND date >= ? AND date < ?
                           ORDER BY date DESC LIMIT 1''',
                        (symbol, date_N_ago, latest_date)
                    )
                    earning_row = cursor.fetchone()

                    if not earning_row:
                        if is_tracing: log_detail(f"  ⏭️ {fallback_days}天范围内无符合条件的财报，尝试下一档")
                        continue

                    earning_date = earning_row[0]

                    cursor.execute(
                        f'SELECT low, price FROM [{table}] WHERE name = ? AND date = ?',
                        (symbol, earning_date)
                    )
                    earning_low_row = cursor.fetchone()

                    if not earning_low_row:
                        if is_tracing: log_detail(f"  ⚠️ 财报日({earning_date})无 low 数据，尝试下一档")
                        continue

                    earning_support_low = earning_low_row[0]
                    earning_support_close = earning_low_row[1] 
                    earning_dt = datetime.strptime(earning_date, "%Y-%m-%d")
                    e_days_diff = (latest_dt - earning_dt).days

                    if e_days_diff < MIN_SUPPORT_DAYS:
                        if is_tracing: log_detail(f"  ⚠️ 财报日({earning_date})距最新日期仅 {e_days_diff} 天，尝试下一档")
                        continue

                    if latest_close > earning_support_low:
                        diff_pct = (latest_close - earning_support_low) / earning_support_low * 100
                        if diff_pct <= SUPPORT_THRESHOLD_PCT:
                            support_close[symbol] = f"{symbol}财{parallel_suffix}"
                            earning_close[latest_date].append(symbol)
                            symbol_categorized = True
                            log_detail(f"  ✅ {symbol}: SupportLevel_Close [财报回退-{fallback_days}天{parallel_suffix}] (最新={latest_close}, 财报日={earning_date}, 支撑(low)={earning_support_low}, 差={diff_pct:.2f}%){pe_high_tag}")
                        else:
                            if latest_close > earning_support_close:
                                diff_pct_close = (latest_close - earning_support_close) / earning_support_close * 100
                                if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                    support_close[symbol] = f"{symbol}财{parallel_suffix}"
                                    earning_close[latest_date].append(symbol)
                                    symbol_categorized = True
                                    log_detail(f"  ✅ {symbol}: SupportLevel_Close [财报回退-{fallback_days}天{parallel_suffix}][二次Price比较] (最新={latest_close}, 财报日={earning_date}, 支撑(price)={earning_support_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                                else:
                                    if latest_low > earning_support_close:
                                        diff_pct_latest_low = (latest_low - earning_support_close) / earning_support_close * 100
                                        if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                            support_close[symbol] = f"{symbol}财{parallel_suffix}"
                                            earning_close[latest_date].append(symbol)
                                            symbol_categorized = True
                                            log_detail(f"  ✅ {symbol}: SupportLevel_Close [财报回退-{fallback_days}天{parallel_suffix}][三次LatestLow比较] (最新low={latest_low}, 财报日={earning_date}, 支撑(price)={earning_support_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                        else:
                                            if is_tracing: log_detail(f"  ⚠️ {fallback_days}天档财报支撑差值(含三次LatestLow)超 {SUPPORT_THRESHOLD_PCT}%，尝试下一档")
                                    else:
                                        if is_tracing: log_detail(f"  ⚠️ {fallback_days}天档财报支撑 最新low({latest_low}) <= 支撑(price)({earning_support_close})，不符合三次比较条件，尝试下一档")
                            else:
                                support_over[symbol] = f"{symbol}财{parallel_suffix}"
                                earning_over[latest_date].append(symbol)
                                symbol_categorized = True
                                log_detail(f"  ✅🔻 {symbol}: SupportLevel_Over [财报回退-{fallback_days}天{parallel_suffix}][二次Price比较] (最新={latest_close}, 财报日={earning_date}, 支撑(price)={earning_support_close}){pe_high_tag}")
                    else:
                        support_over[symbol] = f"{symbol}财{parallel_suffix}"
                        earning_over[latest_date].append(symbol)
                        symbol_categorized = True
                        log_detail(f"  ✅🔻 {symbol}: SupportLevel_Over [财报回退-{fallback_days}天{parallel_suffix}] (最新={latest_close}, 财报日={earning_date}, 支撑(low)={earning_support_low}){pe_high_tag}")

                if not symbol_categorized and is_tracing:
                    log_detail(f"  ⏭️ 61/91天范围内均无符合条件的财报支撑，最终跳过")

            # ===== Phase 4: 31天内财报后区间支撑位检查 =====
            if not symbol_categorized:
                if is_tracing: log_detail(f"  -> 进入 Phase 4: 31天内财报后区间支撑检查")
                
                date_31_ago = (latest_dt - timedelta(days=31)).strftime("%Y-%m-%d")
                
                cursor.execute(
                    '''SELECT date FROM Earning 
                       WHERE name = ? AND date >= ? AND date < ?
                       ORDER BY date DESC LIMIT 1''',
                    (symbol, date_31_ago, latest_date)
                )
                recent_e_row = cursor.fetchone()
                
                if recent_e_row:
                    recent_e_date = recent_e_row[0]
                    if is_tracing: log_detail(f"  -> 发现31天内财报日: {recent_e_date}，开始在该区间寻找支撑点")
                    
                    cursor.execute(
                        f'SELECT date, low, price FROM [{table}] WHERE name = ? AND date >= ? AND date < ? ORDER BY date ASC',
                        (symbol, recent_e_date, latest_date)
                    )
                    p4_rows = cursor.fetchall()
                    
                    if p4_rows:
                        p4_min_row = min(p4_rows, key=lambda x: x[1])
                        p4_support_date = p4_min_row[0]
                        p4_support_low = p4_min_row[1]
                        p4_support_close = p4_min_row[2]
                        
                        p4_support_dt = datetime.strptime(p4_support_date, "%Y-%m-%d")
                        p4_days_diff = (latest_dt - p4_support_dt).days
                        
                        if p4_days_diff < MIN_SUPPORT_DAYS:
                            if is_tracing: log_detail(f"  ⚠️ 区间支撑点(low)距最新日期仅 {p4_days_diff} 天，尝试使用收盘价(price)寻找支撑点...")
                            
                            p4_min_close_row = min(p4_rows, key=lambda x: x[2])
                            p4_support_date_close = p4_min_close_row[0]
                            p4_support_dt_close = datetime.strptime(p4_support_date_close, "%Y-%m-%d")
                            p4_days_diff_close = (latest_dt - p4_support_dt_close).days
                            
                            if p4_days_diff_close < MIN_SUPPORT_DAYS:
                                if is_tracing: log_detail(f"  ⚠️ 区间收盘价(price)支撑点距最新日期也仅 {p4_days_diff_close} 天，Phase 4 放弃")
                            else:
                                p4_support_date = p4_support_date_close
                                p4_support_low = p4_min_close_row[1]
                                p4_support_close = p4_min_close_row[2]
                                p4_days_diff = p4_days_diff_close
                                if is_tracing: log_detail(f"  ✅ 切换为收盘价(price)支撑点: {p4_support_date} (Low: {p4_support_low}, Close: {p4_support_close})")
                        
                        if p4_days_diff >= MIN_SUPPORT_DAYS:
                            tag_prefix = "[31天财报区间] "
                            val_suffix = "财区"
                            
                            if latest_close > p4_support_low:
                                diff_pct = (latest_close - p4_support_low) / p4_support_low * 100
                                if diff_pct <= SUPPORT_THRESHOLD_PCT:
                                    support_close[symbol] = f"{symbol}{val_suffix}"
                                    earning_close[latest_date].append(symbol)
                                    symbol_categorized = True
                                    log_detail(f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}(最新={latest_close}, 支撑日期={p4_support_date}, 支撑(low)={p4_support_low}, 差={diff_pct:.2f}%){pe_high_tag}")
                                else:
                                    if latest_close > p4_support_close:
                                        diff_pct_close = (latest_close - p4_support_close) / p4_support_close * 100
                                        if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                            support_close[symbol] = f"{symbol}{val_suffix}"
                                            earning_close[latest_date].append(symbol)
                                            symbol_categorized = True
                                            log_detail(f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[二次Price比较] (最新={latest_close}, 支撑日期={p4_support_date}, 支撑(price)={p4_support_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                                        else:
                                            if latest_low > p4_support_close:
                                                diff_pct_latest_low = (latest_low - p4_support_close) / p4_support_close * 100
                                                if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                                    support_close[symbol] = f"{symbol}{val_suffix}"
                                                    earning_close[latest_date].append(symbol)
                                                    symbol_categorized = True
                                                    log_detail(f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[三次LatestLow比较] (最新low={latest_low}, 支撑日期={p4_support_date}, 支撑(price)={p4_support_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                                else:
                                                    if is_tracing: log_detail(f"  ⚠️ {tag_prefix}差值超 {SUPPORT_THRESHOLD_PCT}%，无输出")
                                            else:
                                                if is_tracing: log_detail(f"  ⚠️ {tag_prefix}最新low({latest_low}) <= 支撑(price)({p4_support_close})，不符合三次比较条件")
                                    else:
                                        support_over[symbol] = f"{symbol}{val_suffix}"
                                        earning_over[latest_date].append(symbol)
                                        symbol_categorized = True
                                        log_detail(f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}[二次Price比较] (最新={latest_close}, 支撑日期={p4_support_date}, 支撑(price)={p4_support_close}){pe_high_tag}")
                            else:
                                support_over[symbol] = f"{symbol}{val_suffix}"
                                earning_over[latest_date].append(symbol)
                                symbol_categorized = True
                                log_detail(f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}(最新={latest_close}, 支撑日期={p4_support_date}, 支撑(low)={p4_support_low}){pe_high_tag}")
                else:
                    if is_tracing: log_detail(f"  ⏭️ 31天内无财报，跳过 Phase 4")

        except Exception as e:
            log_detail(f"处理 {symbol} 时出错: {e}")

    conn.close()

    # ========== 结果汇总与文件写入 ==========
    if inherit_hits:
        log_detail(f"\n[顺延继承] 本次共 {len(inherit_hits)} 个 symbol 通过顺延直接判定为 Over: {sorted(inherit_hits)}")

    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [回测模式] 运行完毕 (Date: {TARGET_DATE})。")
        log_detail(f"📊 SupportLevel_Close 命中: {len(support_close)} 个")
        log_detail(f"📊 SupportLevel_Over  命中: {len(support_over)} 个 (其中顺延继承 {len(inherit_hits)} 个)")
        log_detail("⚠️ 文件未被修改。")
        log_detail("="*60 + "\n")
    else:
        # 更新 Sectors_panel.json
        sectors_panel["SupportLevel_Close"] = support_close
        sectors_panel["SupportLevel_Close_backup"] = support_close.copy()
        sectors_panel["SupportLevel_Over"] = support_over
        sectors_panel["SupportLevel_Over_backup"] = support_over.copy()

        # 更新 Earning_History.json
        if "SupportLevel_Close" not in earning_history:
            earning_history["SupportLevel_Close"] = {}
        for date_key, sym_list in earning_close.items():
            earning_history["SupportLevel_Close"][date_key] = sorted(set(sym_list))

        if "SupportLevel_Over" not in earning_history:
            earning_history["SupportLevel_Over"] = {}
        for date_key, sym_list in earning_over.items():
            earning_history["SupportLevel_Over"][date_key] = sorted(set(sym_list))

        # 写回文件
        with open(SECTORS_PANEL_PATH, 'w', encoding='utf-8') as f:
            json.dump(sectors_panel, f, indent=4, ensure_ascii=False)

        with open(EARNING_HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(earning_history, f, indent=4, ensure_ascii=False)

        log_detail(f"\n===== 完成 =====")
        log_detail(f"SupportLevel_Close ({len(support_close)}个): {list(support_close.keys())}")
        log_detail(f"SupportLevel_Over  ({len(support_over)}个): {list(support_over.keys())}")
        log_detail(f"其中 顺延继承 命中 {len(inherit_hits)} 个: {sorted(inherit_hits)}")


def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将仅输出到控制台。")
    else:
        print("追踪模式未启用。日志将仅输出到控制台。")
        
    def log_detail_console(message):
        print(message)
        
    run_support_logic(log_detail_console)


if __name__ == '__main__':
    main()