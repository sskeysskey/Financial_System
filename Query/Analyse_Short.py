import json
import sqlite3
import logging
import os
from wcwidth import wcswidth
from collections import defaultdict
from datetime import datetime, timedelta

# ==========================================
# 1. 配置文件和路径管理
# ==========================================

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# ============ 回测 / 追踪配置 ============
# 如为空，则运行"今天"模式；填入日期（如 "2025-01-15"），则运行回测模式
SYMBOL_TO_TRACE = ""
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "SE"
# TARGET_DATE = "2026-03-05"

# 追踪日志路径
LOG_FILE_PATH = os.path.join(USER_HOME, "Downloads", "OverBuy_trace_log.txt")
# =========================================

# 算法参数配置
CONFIG = {
    "MA_PERIOD": 200,
    "MA_BELOW_MAX_PCT": 0.3,
    "RECENT_DAYS_LOOKBACK": 3,
    "LOOKBACK_MONTHS_LONG": 12,
    "RANK_THRESHOLD_LONG": 2,
    "LOOKBACK_MONTHS_SHORT": 6,
    "RANK_THRESHOLD_SHORT": 1,
    "M_TOP_HEIGHT_TOLERANCE": 0.038,
    "M_TOP_NECK_DEPTH": 0.025,
    "M_TOP_MIN_DAYS_GAP": 3,
    "PUMP_DUMP_THRESHOLD": 0.10,
    "BREAKOUT_TOLERANCE": 0.005,
}

# 动态路径生成
BASE_PATH = USER_HOME
CODING_DIR = BASE_CODING_DIR
MODULES_DIR = os.path.join(CODING_DIR, 'Financial_System', 'Modules')
NEWS_DIR = os.path.join(CODING_DIR, 'News')
DB_DIR = os.path.join(CODING_DIR, 'Database')
DOWNLOADS_DIR = os.path.join(BASE_PATH, 'Downloads')

DESC_FILE = os.path.join(MODULES_DIR, 'description.json')
SECTORS_FILE = os.path.join(MODULES_DIR, 'Sectors_All.json')
PANEL_FILE = os.path.join(MODULES_DIR, 'Sectors_panel.json')
EARNING_HISTORY_FILE = os.path.join(MODULES_DIR, 'Earning_History.json')
OUTPUT_FILE = os.path.join(NEWS_DIR, 'OverBuy.txt')
DB_FILE = os.path.join(DB_DIR, 'Finance.db')
DEBUG_LOG_FILE = os.path.join(DOWNLOADS_DIR, 'OverBuy_debug.log')

# ==========================================
# 2. 日志配置
# ==========================================
LOG_ENABLED = False

logger = logging.getLogger(__name__)
handlers_list = [logging.StreamHandler()]

if LOG_ENABLED:
    os.makedirs(os.path.dirname(DEBUG_LOG_FILE), exist_ok=True)
    handlers_list.append(logging.FileHandler(DEBUG_LOG_FILE, encoding='utf-8'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=handlers_list,
    force=True
)
logger.disabled = False

# ==========================================
# 3. 标签过滤配置
# ==========================================
# BLACKLIST_TAGS = [
#     "赋能半导体", "黄金", "白银", "贵金属", "卫星",
#     "国防", "军工", "生物制药", "铝", "铜", "仿制药", "卡车运输"
# ]
BLACKLIST_TAGS = []
WHITELIST_TAGS = []

# ==========================================
# 4. 数据加载（模块级只读，不影响回测）
# ==========================================

try:
    with open(DESC_FILE, 'r', encoding='utf-8') as f:
        desc_data = json.load(f)
    logger.info('Loaded DESC_FILE')
except Exception as e:
    logger.error(f"Failed to load DESC_FILE: {e}")
    desc_data = {}

try:
    with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
        sectors_data = json.load(f)
    logger.info(f'Loaded SECTORS_FILE with {len(sectors_data)} sectors')
except Exception as e:
    logger.error(f"Failed to load SECTORS_FILE: {e}")
    sectors_data = {}

try:
    with open(PANEL_FILE, 'r', encoding='utf-8') as f:
        panel_data = json.load(f)
    logger.info('Loaded PANEL_FILE')
except FileNotFoundError:
    panel_data = {}
    logger.warning("PANEL_FILE not found, initializing empty.")

try:
    with open(EARNING_HISTORY_FILE, 'r', encoding='utf-8') as f:
        earning_history_data = json.load(f)
    logger.info('Loaded EARNING_HISTORY_FILE for global lookup')
except (FileNotFoundError, json.JSONDecodeError):
    earning_history_data = {}
    logger.warning("EARNING_HISTORY_FILE not found or empty, creating empty lookup dict.")

# ==========================================
# 5. 辅助函数
# ==========================================

def check_ma_breakout(cursor, sector, symbol, ma_period=200, target_date=None):
    """
    检查当前收盘价是否处于 MA200 下方（兼容多日回溯 & 回测日期限制）。
    """
    try:
        limit_rows = ma_period + 10
        # [回测] 限制查询日期上界
        if target_date:
            cursor.execute(f"""
                SELECT price FROM "{sector}"
                WHERE name = ? AND date <= ?
                ORDER BY date DESC
                LIMIT ?
            """, (symbol, target_date, limit_rows))
        else:
            cursor.execute(f"""
                SELECT price FROM "{sector}"
                WHERE name = ?
                ORDER BY date DESC
                LIMIT ?
            """, (symbol, limit_rows))

        rows = cursor.fetchall()
        if len(rows) < ma_period + 1:
            return False, 0

        prices = [float(r[0]) for r in rows][::-1]

        ma_today = sum(prices[-ma_period:]) / ma_period
        price_today = prices[-1]

        tolerance = CONFIG.get("BREAKOUT_TOLERANCE", 0)
        lower_bound = ma_today * (1 - tolerance)
        upper_bound = ma_today * (1 - CONFIG.get("MA_BELOW_MAX_PCT", 0.15))

        if upper_bound <= price_today < lower_bound:
            return True, ma_today

        return False, 0
    except Exception as e:
        logger.error(f"[{symbol}] MA Breakout check error: {e}")
        return False, 0


def update_earning_history_json_b(file_path, group_name, symbols_to_add, base_date_str=None):
    """
    更新 Earning_History.json 文件。
    base_date_str: 指定记录日期（回测模式下由外部传入，否则默认昨天）。
    """
    if not symbols_to_add:
        return

    # [回测兼容] 优先使用传入的日期，否则用昨天
    record_date_str = base_date_str if base_date_str else (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    logger.info(f"--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")

    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(record_date_str, [])
    combined_symbols = sorted(list(set(existing_symbols) | set(symbols_to_add)))
    data[group_name][record_date_str] = combined_symbols

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"成功更新历史记录 '{group_name}'。日期: {record_date_str}, 总计 {len(combined_symbols)} 个。")
    except Exception as e:
        logger.error(f"错误: 写入历史记录文件失败: {e}")


def pad_display(s: str, width: int, align: str = 'left') -> str:
    cur = wcswidth(s)
    if cur >= width:
        return s
    pad = width - cur
    return s + ' ' * pad if align == 'left' else ' ' * pad + s


def get_symbol_sector(symbol):
    for sector, symbols in sectors_data.items():
        if symbol in symbols:
            return sector
    return "Unknown"


def get_symbol_info(symbol):
    for stock in desc_data.get('stocks', []):
        if stock['symbol'] == symbol:
            tags = stock.get('tag', [])
            has_blacklist = any(tag in BLACKLIST_TAGS for tag in tags)
            return {'has_blacklist': has_blacklist, 'tags': tags}

    for etf in desc_data.get('etfs', []):
        if etf['symbol'] == symbol:
            tags = etf.get('tag', [])
            has_blacklist = any(tag in BLACKLIST_TAGS for tag in tags)
            return {'has_blacklist': has_blacklist, 'tags': tags}

    return {'has_blacklist': False, 'tags': []}


# ==========================================
# 6. 核心策略函数
# ==========================================

def check_turnover_rank(cursor, sector_name, symbol, latest_date_str, latest_turnover, lookback_months, rank_threshold):
    """
    检查 latest_turnover 是否是过去 lookback_months 个月内的前 rank_threshold 名。
    （latest_date_str 本身已被上层函数通过 target_date 限制，此处无需额外处理）
    """
    try:
        dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()

    valid_data = []
    for r in rows:
        if r[1] is not None and r[2] is not None:
            turnover = r[1] * r[2]
            valid_data.append((r[0], turnover))

    if not valid_data:
        return False

    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    top_n_data = sorted_data[:rank_threshold]
    top_n_turnovers = [item[1] for item in top_n_data]

    if latest_turnover in top_n_turnovers:
        return True
    elif len(top_n_turnovers) >= rank_threshold and latest_turnover >= top_n_turnovers[rank_threshold - 1]:
        return True

    return False


def check_double_top(cursor, symbol, sector, target_date=None):
    """
    检查是否形成 M 形态（双峰）。[回测] 新增 target_date 参数限制查询上界。
    """
    try:
        price_tolerance = CONFIG.get("M_TOP_HEIGHT_TOLERANCE", 0.038)
        min_depth = CONFIG.get("M_TOP_NECK_DEPTH", 0.025)
        min_days_gap = CONFIG.get("M_TOP_MIN_DAYS_GAP", 3)

        # [回测] 限制查询日期上界，同时修复原代码中 sector 缺少引号的问题
        if target_date:
            cursor.execute(f"""
                SELECT date, price
                FROM "{sector}"
                WHERE name = ? AND date <= ?
                ORDER BY date DESC
                LIMIT 60
            """, (symbol, target_date))
        else:
            cursor.execute(f"""
                SELECT date, price
                FROM "{sector}"
                WHERE name = ?
                ORDER BY date DESC
                LIMIT 60
            """, (symbol,))

        rows = cursor.fetchall()

        if len(rows) < 15:
            return False

        rows = rows[::-1]  # 转正序
        prices = [float(r[1]) for r in rows]

        curr_price = prices[-1]
        p2 = prices[-2]
        prev2_price = prices[-3]

        if not (p2 > prev2_price and p2 > curr_price):
            return False

        idx2 = len(prices) - 2
        start_search_index = idx2 - min_days_gap

        found_pattern = False

        for i in range(start_search_index, 0, -1):
            p1 = prices[i]
            idx1 = i

            if not (p1 > prices[i - 1] and p1 > prices[i + 1]):
                continue

            diff_pct = abs(p1 - p2) / max(p1, p2)
            if diff_pct > price_tolerance:
                continue

            period_prices = prices[idx1: idx2 + 1]
            period_high = max(period_prices)
            peak_max = max(p1, p2)

            if period_high > peak_max * 1.001:
                continue

            valley_prices = prices[idx1 + 1: idx2]
            if not valley_prices:
                continue

            min_valley = min(valley_prices)
            avg_peak = (p1 + p2) / 2

            valley_depth = (avg_peak - min_valley) / avg_peak
            if valley_depth < min_depth:
                continue

            found_pattern = True
            break

        return found_pattern

    except Exception as e:
        logger.error(f'[{symbol}] check_double_top error: {e}')
        return False


def get_latest_earnings_date(cursor, symbol, target_date=None):
    """
    从数据库的 Earning 表中获取该 symbol 的最近财报日。
    [回测] 新增 target_date 参数，防止查到"未来"财报。
    """
    try:
        if target_date:
            cursor.execute(
                'SELECT date FROM Earning WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1',
                (symbol, target_date)
            )
        else:
            cursor.execute(
                'SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1',
                (symbol,)
            )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.error(f"[{symbol}] Error querying latest earnings date: {e}")

    fallback_date = datetime.now() - timedelta(days=CONFIG.get("EARNINGS_LOOKBACK_DAYS", 90))
    return fallback_date.strftime('%Y-%m-%d')


def check_pump_dump_top(cursor, sector, symbol, latest_date_str, latest_price, earnings_date_str):
    """
    检索从最近财报日到最新日期之间，是否在 Short 或 Short_W 中出现过。
    （latest_date_str 已由上层函数通过 target_date 限制，内部 < latest_date_str 条件自然排除未来数据）
    """
    threshold = CONFIG.get("PUMP_DUMP_THRESHOLD", 0.10)
    hit_dates = []

    for group in ["Short", "Short_W"]:
        if group not in earning_history_data:
            continue

        for date_str, symbols_list in earning_history_data[group].items():
            if earnings_date_str <= date_str < latest_date_str:
                if symbol in symbols_list:
                    hit_dates.append(date_str)

    if not hit_dates:
        return False, ""

    for past_date in hit_dates:
        try:
            cursor.execute(f'SELECT price FROM "{sector}" WHERE name = ? AND date = ?', (symbol, past_date))
            row = cursor.fetchone()
            if row and row[0] is not None:
                past_price = float(row[0])
                if past_price > 0 and (latest_price - past_price) / past_price >= threshold:
                    return True, f"较{past_date}信号日大涨{((latest_price - past_price) / past_price) * 100:.1f}%"
        except Exception as e:
            logger.error(f"[{symbol}] Error querying past price for {past_date}: {e}")
            continue

    return False, ""


# ==========================================
# 7. 主执行逻辑（封装为函数，支持回测）
# ==========================================

def run_short_logic(log_detail):
    log_detail("Analyse_Short 程序开始运行...")

    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    # 确定基准日期
    base_date = TARGET_DATE if TARGET_DATE else (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel、History JSON 和 TXT 文件。")

    # 初始化分组（每次运行前清空，防止上次数据残留）
    panel_data['Short'] = {}
    short_group = panel_data['Short']
    panel_data['Short_backup'] = {}
    short_backup_group = panel_data['Short_backup']
    panel_data['Short_W'] = {}
    short_w_group = panel_data['Short_W']
    panel_data['Short_W_backup'] = {}
    short_w_backup_group = panel_data['Short_W_backup']

    conn = sqlite3.connect(DB_FILE, timeout=60.0)
    cursor = conn.cursor()

    sector_outputs = defaultdict(list)
    final_short_symbols = []
    final_short_w_symbols = []

    TARGET_SECTORS = [
        'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Technology', 'Energy',
        'Industrials', 'Consumer_Defensive', 'Communication_Services',
        'Financial_Services', 'Healthcare', 'Utilities', "ETFs",
    ]

    symbols = []
    for sec_name in TARGET_SECTORS:
        if sec_name in sectors_data:
            symbols.extend(sectors_data[sec_name])
        else:
            logger.warning(f"Sector '{sec_name}' not found in SECTORS_FILE.")
    symbols = list(set(symbols))

    log_detail(f"开始扫描 {len(symbols)} 个 symbols（基准日期: {base_date}）...")

    for symbol in symbols:
        is_tracing = (symbol == SYMBOL_TO_TRACE)

        try:
            # --- A. 基础信息与标签过滤 ---
            symbol_info = get_symbol_info(symbol)
            sector = get_symbol_sector(symbol)
            tags_str = ", ".join(symbol_info['tags']) if symbol_info['tags'] else "无标签"

            if len(WHITELIST_TAGS) > 0:
                has_whitelist_tag = any(tag in WHITELIST_TAGS for tag in symbol_info['tags'])
                if not has_whitelist_tag:
                    if is_tracing:
                        log_detail(f"    x [过滤] {symbol} 不在白名单中，跳过。")
                    continue
            else:
                if symbol_info['has_blacklist']:
                    if is_tracing:
                        log_detail(f"    x [过滤] {symbol} 命中黑名单标签 ({tags_str})，跳过。")
                    continue

            if is_tracing:
                log_detail(f"\n--- 正在检查 {symbol} (sector: {sector}) ---")
                log_detail(f"    基准日期: {base_date}, 标签: {tags_str}")

            # --- A2. 进阶门槛：必须跌破 MA200 ---
            # [回测] 传入 base_date 限制 MA 计算范围
            is_ma_break, ma_value = check_ma_breakout(cursor, sector, symbol, CONFIG["MA_PERIOD"], target_date=base_date)
            if not is_ma_break:
                if is_tracing:
                    log_detail(f"    x [失败] MA{CONFIG['MA_PERIOD']} 破位检查未通过。(MA={ma_value:.2f})")
                continue

            if is_tracing:
                log_detail(f"    ✓ [通过] MA{CONFIG['MA_PERIOD']} 破位，MA={ma_value:.2f}")

            # --- B. 获取最近 N+1 天交易数据 ---
            # [回测] 加入 AND date <= base_date 限制，防止穿越
            _lookback = CONFIG["RECENT_DAYS_LOOKBACK"]
            query = (f'SELECT date, price, volume FROM "{sector}" '
                     f'WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT {_lookback + 1}')
            cursor.execute(query, (symbol, base_date))
            rows = cursor.fetchall()

            if len(rows) < 2:
                if is_tracing:
                    log_detail(f"    x [失败] 数据不足 2 天，跳过。")
                continue

            date_curr, price_curr, vol_curr = rows[0]
            date_prev, price_prev, vol_prev = rows[1]

            if price_curr is None or price_prev is None or vol_curr is None:
                continue

            current_turnover = price_curr * vol_curr

            if is_tracing:
                log_detail(f"    最新: {date_curr} 价格={price_curr}, 成交量={vol_curr}, 成交额={current_turnover:,.0f}")
                log_detail(f"    前一日: {date_prev} 价格={price_prev}")

            # --- D2. 砸顶检查（无需下跌即可触发）---
            # [回测] 传入 base_date 限制财报日查询范围
            earnings_date_str = get_latest_earnings_date(cursor, symbol, target_date=base_date)

            is_pump_dump = False
            pd_reason = ""
            if earnings_date_str:
                is_pump_dump, pd_reason = check_pump_dump_top(
                    cursor, sector, symbol, date_curr, price_curr, earnings_date_str
                )

            if is_tracing:
                log_detail(f"    - 砸顶检查: {is_pump_dump}" + (f" ({pd_reason})" if is_pump_dump else ""))

            # --- C. 基础门槛 1: N 天内任意一天下跌即通过 ---
            any_drop_in_5days = any(
                rows[i][1] is not None and rows[i + 1][1] is not None
                and float(rows[i][1]) < float(rows[i + 1][1])
                for i in range(min(CONFIG["RECENT_DAYS_LOOKBACK"], len(rows) - 1))
            )

            if is_tracing:
                log_detail(f"    - 下跌检查: {any_drop_in_5days} (砸顶豁免: {is_pump_dump})")

            if not is_pump_dump and not any_drop_in_5days:
                if is_tracing:
                    log_detail(f"    x [失败] 未下跌且非砸顶，跳过。")
                continue

            # --- D. 基础门槛 2: 成交额排名检查 ---
            is_hit_base = False
            hit_reason = ""

            for i in range(min(CONFIG["RECENT_DAYS_LOOKBACK"], len(rows) - 1)):
                day_date, day_price, day_vol = rows[i]
                _, prev_price_i, _ = rows[i + 1]

                if day_price is None or prev_price_i is None or day_vol is None:
                    continue

                day_price = float(day_price)
                prev_price_i = float(prev_price_i)

                if day_price >= prev_price_i:
                    continue

                day_turnover = day_price * float(day_vol)
                date_suffix = f"({day_date})" if i > 0 else ""

                if check_turnover_rank(cursor, sector, symbol, day_date, day_turnover,
                                       CONFIG["LOOKBACK_MONTHS_LONG"], CONFIG["RANK_THRESHOLD_LONG"]):
                    is_hit_base = True
                    hit_reason = f"1年内Top{CONFIG['RANK_THRESHOLD_LONG']}天量{date_suffix}"
                    if is_tracing:
                        log_detail(f"    ✓ [命中] {hit_reason}")
                    break

                elif check_turnover_rank(cursor, sector, symbol, day_date, day_turnover,
                                         CONFIG["LOOKBACK_MONTHS_SHORT"], CONFIG["RANK_THRESHOLD_SHORT"]):
                    is_hit_base = True
                    hit_reason = f"半年内Top{CONFIG['RANK_THRESHOLD_SHORT']}天量{date_suffix}"
                    if is_tracing:
                        log_detail(f"    ✓ [命中] {hit_reason}")
                    break

            if is_tracing and not is_hit_base and not is_pump_dump:
                log_detail(f"    x [失败] 成交额排名未达标，跳过。")

            # 砸顶强制纳入
            if is_pump_dump:
                is_hit_base = True
                if hit_reason:
                    hit_reason += f" & 砸顶({pd_reason})"
                else:
                    hit_reason = f"砸顶({pd_reason})"

            # --- E. 分流逻辑 ---
            if is_hit_base:
                is_double_top = False
                if not is_pump_dump:
                    # [回测] 传入 base_date 限制 M 头查询范围
                    is_double_top = check_double_top(cursor, symbol, sector, target_date=base_date)

                if is_tracing:
                    log_detail(f"    - M头检查: {is_double_top}")

                if is_pump_dump:
                    panel_val = f"{symbol}砸顶"
                    short_group[symbol] = panel_val
                    short_backup_group[symbol] = panel_val
                    final_short_symbols.append(panel_val)
                    group_tag = "[Short砸顶]"
                    logger.info(f'[{symbol}] Hit Short(Pump Dump): {hit_reason}')
                    if is_tracing:
                        log_detail(f"    ✅ [选中-Short砸顶] {hit_reason}")

                elif is_double_top:
                    short_w_group[symbol] = ""
                    short_w_backup_group[symbol] = ""
                    final_short_w_symbols.append(symbol)
                    group_tag = "[Short_W]"
                    logger.info(f'[{symbol}] Hit Short_W: {hit_reason} + M-Top')
                    if is_tracing:
                        log_detail(f"    ✅ [选中-Short_W] {hit_reason} + M头形态")

                else:
                    short_group[symbol] = ""
                    short_backup_group[symbol] = ""
                    final_short_symbols.append(symbol)
                    group_tag = "[Short]"
                    logger.info(f'[{symbol}] Hit Short: {hit_reason}')
                    if is_tracing:
                        log_detail(f"    ✅ [选中-Short] {hit_reason}")

                sector_disp = pad_display(sector, 20, 'left')
                symbol_disp = pad_display(symbol, 5, 'left')
                pct_change = (price_curr - price_prev) / price_prev * 100

                output_line = {
                    'text': f"{sector_disp} {symbol_disp} {pct_change:.2f}% MA{CONFIG['MA_PERIOD']}={ma_value:.2f} {group_tag} {hit_reason}: {tags_str}",
                    'change_percent': abs(current_turnover)
                }
                sector_outputs[sector_disp].append(output_line)

        except Exception as e:
            logger.error(f'[{symbol}] Error: {e}')
            if is_tracing:
                log_detail(f"    ✗ [异常] {symbol} 处理时发生错误: {e}")
            continue

    conn.close()
    logger.info('DB connection closed')

    # ======== 回测安全拦截：只打印结果，不写任何文件 ========
    if TARGET_DATE:
        log_detail("\n" + "=" * 60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [Short]   命中 {len(final_short_symbols)} 个: {sorted(final_short_symbols)}")
        log_detail(f"📊 [Short_W] 命中 {len(final_short_w_symbols)} 个: {sorted(final_short_w_symbols)}")
        log_detail("=" * 60)
        log_detail("本次运行未写入任何文件。")
        return

    # ======== 正常模式：写入 TXT、History、Panel ========
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as output_file:
        output_file.write("OverBuy Scan Result (Down + High Turnover)\n")
        output_file.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
        output_file.write("=" * 60 + "\n")
        for sector in sorted(sector_outputs.keys()):
            sorted_outputs = sorted(sector_outputs[sector], key=lambda x: x['change_percent'], reverse=True)
            for output in sorted_outputs:
                output_file.write(output['text'] + '\n')
        logger.info(f'Wrote txt output to {OUTPUT_FILE}')

    if final_short_symbols:
        update_earning_history_json_b(EARNING_HISTORY_FILE, "Short", final_short_symbols, base_date_str=base_date)
    if final_short_w_symbols:
        update_earning_history_json_b(EARNING_HISTORY_FILE, "Short_W", final_short_w_symbols, base_date_str=base_date)

    with open(PANEL_FILE, 'w', encoding='utf-8') as f:
        json.dump(panel_data, f, ensure_ascii=False, indent=4)
        logger.info(f'Updated panel file {PANEL_FILE}')

    log_detail("程序运行结束。")


# ==========================================
# 8. 入口函数
# ==========================================

def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将写入: {LOG_FILE_PATH}")
        try:
            with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
                def log_detail_file(message):
                    log_file.write(message + '\n')
                    print(message)
                run_short_logic(log_detail_file)
        except IOError as e:
            print(f"错误：无法打开或写入日志文件 {LOG_FILE_PATH}: {e}")
    else:
        print("追踪模式未启用。日志仅输出到控制台。")
        def log_detail_console(message):
            print(message)
        run_short_logic(log_detail_console)


if __name__ == '__main__':
    main()