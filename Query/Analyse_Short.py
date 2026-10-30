import json
import sqlite3
import logging
import os
import re
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

# SYMBOL_TO_TRACE = "WELL"
# TARGET_DATE = "2026-10-07"

# 追踪日志路径
LOG_FILE_PATH = os.path.join(USER_HOME, "Downloads", "OverBuy_trace_log.txt")
# =========================================

# 算法参数配置
CONFIG = {
    "MA_PERIOD": 150,
    "RECENT_DAYS_LOOKBACK": 1,
    "LOOKBACK_MONTHS_LONG": 12,
    "RANK_THRESHOLD_LONG": 3,
    "M_TOP_HEIGHT_TOLERANCE": 0.038,
    "M_TOP_NECK_DEPTH": 0.025,
    "M_TOP_MIN_DAYS_GAP": 3,

    # ---------- [新增] Short类 "追" 捞回规则 ----------
    "CHASE_ENABLED": True,                 # 总开关
    "CHASE_SOURCE_GROUPS": ["Short", "Short_W"],   # [新增] 哪些分组的原生命中可作为锚点
    "CHASE_LOOKBACK_TRADING_DAYS": 20,     # 在锚点(原生Short_W)之后多少个交易日内有效
    "CHASE_MIN_DROP_PCT": 0.031,            # 收盘价需比锚点日收盘价低超过该比例
    "CHASE_SUFFIX": "追",                  # 非原生(捞回)标识
    # ---------- [新增] ETF 特殊规则 ----------
    "ETF_RELAXED_ENABLED": True,          # ETF 特殊规则总开关
    "ETF_SECTOR_NAME": "ETFs",            # ETF 所在板块名
    "ETF_CHASE_MIN_DROP_PCT": 0.035,   # None=不限回落幅度；0=收盘需低于锚点；0.035=回落需>3.5%
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
TAGS_SETTING_JSON_FILE = os.path.join(MODULES_DIR, 'tags_filter.json')
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

try:
    with open(TAGS_SETTING_JSON_FILE, 'r', encoding='utf-8') as f:
        tags_settings = json.load(f)
    hot_tags_t = set(tags_settings.get('HOT_TAGS_T', []))
    logger.info('Loaded HOT_TAGS_T')
except Exception as e:
    logger.error(f"Failed to load TAGS_SETTING_JSON_FILE: {e}")
    hot_tags_t = set()

# ==========================================
# 4.1 [性能] 启动时一次性建立索引，避免每个 symbol 线性扫描
# ==========================================
_SYMBOL_SECTOR_MAP = {}
for _sec, _syms in sectors_data.items():
    for _s in _syms:
        _SYMBOL_SECTOR_MAP.setdefault(_s, _sec)      # 先匹配者优先，与原逻辑一致

_SYMBOL_TAGS_MAP = {}
for _item in desc_data.get('stocks', []):
    _SYMBOL_TAGS_MAP.setdefault(_item.get('symbol'), _item.get('tag', []))
for _item in desc_data.get('etfs', []):
    _SYMBOL_TAGS_MAP.setdefault(_item.get('symbol'), _item.get('tag', []))

# ==========================================
# 5. 辅助函数
# ==========================================
def fmt_drop_thr(v):
    """把回落阈值格式化成可读文字。None 或 -inf 表示不限。"""
    if v is None or v == float('-inf'):
        return "不限"
    return f"> {v * 100:.2f}%"

def clean_symbol(symbol_with_suffix):
    """
    清洗函数：只保留开头的连续字母。
    用于处理 Earning_History.json 中带中文后缀的 symbol（如 'TRV抄底追' -> 'TRV'）。
    """
    if not symbol_with_suffix:
        return ""
    match = re.match(r'([A-Za-z]+)', symbol_with_suffix)
    if match:
        return match.group(1).upper()
    return symbol_with_suffix


def calc_ma(cursor, sector, symbol, ma_period, target_date=None):
    """
    [修复] 直接计算 MA 值（仅用于显示）。数据不足返回 0.0。
    原 check_ma_breakout 在价格不处于区间时返回 0，导致输出恒为 MA=0.00。
    """
    try:
        if target_date:
            cursor.execute(
                f'SELECT price FROM "{sector}" WHERE name = ? AND date <= ? '
                f'ORDER BY date DESC LIMIT ?', (symbol, target_date, ma_period))
        else:
            cursor.execute(
                f'SELECT price FROM "{sector}" WHERE name = ? '
                f'ORDER BY date DESC LIMIT ?', (symbol, ma_period))
        prices = [float(r[0]) for r in cursor.fetchall() if r[0] is not None]
        if len(prices) < ma_period:
            return 0.0
        return sum(prices) / ma_period
    except Exception as e:
        logger.error(f"[{symbol}] calc_ma error: {e}")
        return 0.0


def update_earning_history_json_b(file_path, group_name, symbols_to_add, base_date_str=None):
    """
    更新 Earning_History.json 文件。
    base_date_str: 指定记录日期（回测模式下由外部传入，否则默认昨天）。
    """
    if not symbols_to_add:
        return

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
    if cur < 0:
        cur = len(s)
    if cur >= width:
        return s
    pad = width - cur
    return s + ' ' * pad if align == 'left' else ' ' * pad + s


def get_symbol_sector(symbol):
    return _SYMBOL_SECTOR_MAP.get(symbol, "Unknown")


def get_symbol_info(symbol):
    tags = _SYMBOL_TAGS_MAP.get(symbol, [])
    has_blacklist = any(tag in BLACKLIST_TAGS for tag in tags)
    return {'has_blacklist': has_blacklist, 'tags': tags}


# ==========================================
# 5.1 [新增] "追"（Short_W 捞回）相关函数
# ==========================================
def build_native_chase_anchors(history_data, base_date):
    """
    从 Earning_History.json 的 CHASE_SOURCE_GROUPS（Short / Short_W）分组中提取【原生】命中记录，作为"追"的锚点。
    返回: {symbol: [(date_str, group), ...]}  按日期降序
    - 带"追"后缀的记录一律忽略，防止"追"生"追"的连锁传播。
    - 晚于 base_date 的记录忽略（回测时防止使用未来数据）。
    - 同一 symbol 同一天在两个分组都有记录时，Short_W 优先。
    """
    suffix = CONFIG["CHASE_SUFFIX"]
    anchors = defaultdict(dict)          # symbol -> {date_str: group}
    for group in CONFIG.get("CHASE_SOURCE_GROUPS", ["Short", "Short_W"]):
        for date_str, items in history_data.get(group, {}).items():
            if date_str > base_date:
                continue
            for item in items:
                if suffix and suffix in item:
                    continue
                sym = clean_symbol(item)
                if not sym:
                    continue
                prev = anchors[sym].get(date_str)
                if prev is None or group == "Short_W":
                    anchors[sym][date_str] = group
    return {
        sym: sorted(d.items(), key=lambda x: x[0], reverse=True)
        for sym, d in anchors.items()
    }


def find_chase_anchor(rows, anchor_items, min_drop=None):
    """
    min_drop: 自定义最小回落比例；
              None  -> 使用 CONFIG["CHASE_MIN_DROP_PCT"]（股票默认）
              float('-inf') -> 不检查回落幅度（ETF 宽松模式）
    """
    if not anchor_items or len(rows) < 2:
        return None

    date_curr, price_curr = rows[0][0], rows[0][1]
    price_prev = rows[1][1]
    if price_curr is None or price_prev is None:
        return None
    price_curr, price_prev = float(price_curr), float(price_prev)
    if not (price_curr < price_prev):          # 下跌检查（保留）
        return None

    lookback = CONFIG["CHASE_LOOKBACK_TRADING_DAYS"]
    if min_drop is None:
        min_drop = CONFIG["CHASE_MIN_DROP_PCT"]
    window = rows[1:lookback + 1]

    best = None
    for a, grp in anchor_items:
        if a >= date_curr:                  # 锚点必须严格早于当前交易日
            continue
        matched = next((r for r in window if r[0] <= a and r[1] is not None), None)
        if matched is None:
            continue
        anchor_price = float(matched[1])
        if anchor_price <= 0:
            continue
        drop = (anchor_price - price_curr) / anchor_price
        if drop <= min_drop:
            continue
        if (best is None
                or drop > best[2]
                or (drop == best[2] and grp == "Short_W" and best[3] != "Short_W")):
            best = (matched[0], anchor_price, drop, grp)
    return best


def evaluate_bottom_fishing(cursor, sector, symbol, tags, price_curr, latest_earning_date,
                            is_tracing, log_detail):
    """抄底判定：命中热点标签 或 最新价 > 最近财报日收盘价。"""
    if set(tags).intersection(hot_tags_t):
        return True
    if latest_earning_date:
        cursor.execute(f'SELECT price FROM "{sector}" WHERE name = ? AND date = ?',
                       (symbol, latest_earning_date))
        e_row = cursor.fetchone()
        if e_row and e_row[0] is not None:
            earning_price = float(e_row[0])
            if earning_price > 0 and price_curr > earning_price:
                if is_tracing:
                    log_detail(f"    ✓ [财报抄底检查] 满足条件：最新价({price_curr}) > 财报日收盘价({earning_price})")
                return True
    return False


# ==========================================
# 6. 核心策略函数
# ==========================================

def check_turnover_rank(cursor, sector_name, symbol, latest_date_str, latest_turnover, lookback_months, rank_threshold):
    """检查 latest_turnover 是否是过去 lookback_months 个月内的前 rank_threshold 名。"""
    try:
        dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()

    turnovers = [float(r[1]) * float(r[2]) for r in rows if r[1] is not None and r[2] is not None]
    if not turnovers:
        return False

    top_n = sorted(turnovers, reverse=True)[:rank_threshold]
    if latest_turnover in top_n:
        return True
    if len(top_n) >= rank_threshold and latest_turnover >= top_n[rank_threshold - 1]:
        return True
    return False


def check_double_top(cursor, symbol, sector, target_date=None):
    """检查是否形成 M 形态（双峰）。target_date 限制查询上界。"""
    try:
        price_tolerance = CONFIG.get("M_TOP_HEIGHT_TOLERANCE", 0.038)
        min_depth = CONFIG.get("M_TOP_NECK_DEPTH", 0.025)
        min_days_gap = CONFIG.get("M_TOP_MIN_DAYS_GAP", 3)

        if target_date:
            cursor.execute(f"""
                SELECT date, price FROM "{sector}"
                WHERE name = ? AND date <= ?
                ORDER BY date DESC LIMIT 60
            """, (symbol, target_date))
        else:
            cursor.execute(f"""
                SELECT date, price FROM "{sector}"
                WHERE name = ?
                ORDER BY date DESC LIMIT 60
            """, (symbol,))

        rows = cursor.fetchall()
        if len(rows) < 15:
            return False

        rows = rows[::-1]
        prices = [float(r[1]) for r in rows]

        curr_price = prices[-1]
        p2 = prices[-2]
        prev2_price = prices[-3]

        if not (p2 > prev2_price and p2 > curr_price):
            return False

        idx2 = len(prices) - 2
        start_search_index = idx2 - min_days_gap

        for i in range(start_search_index, 0, -1):
            p1 = prices[i]
            idx1 = i

            if not (p1 > prices[i - 1] and p1 > prices[i + 1]):
                continue

            diff_pct = abs(p1 - p2) / max(p1, p2)
            if diff_pct > price_tolerance:
                continue

            period_high = max(prices[idx1: idx2 + 1])
            peak_max = max(p1, p2)
            if period_high > peak_max * 1.001:
                continue

            valley_prices = prices[idx1 + 1: idx2]
            if not valley_prices:
                continue

            avg_peak = (p1 + p2) / 2
            valley_depth = (avg_peak - min(valley_prices)) / avg_peak
            if valley_depth < min_depth:
                continue

            return True

        return False

    except Exception as e:
        logger.error(f'[{symbol}] check_double_top error: {e}')
        return False


def get_latest_earnings_date(cursor, symbol, target_date=None):
    """
    获取该 symbol 的最近财报日（<= target_date）。
    [修复] 查不到时返回 None，不再用 datetime.now() 伪造日期（回测时会产生错误数据）。
    """
    try:
        if target_date:
            cursor.execute(
                'SELECT date FROM Earning WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1',
                (symbol, target_date))
        else:
            cursor.execute(
                'SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1',
                (symbol,))
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.error(f"[{symbol}] Error querying latest earnings date: {e}")
    return None


# ==========================================
# 7. 主执行逻辑（封装为函数，支持回测）
# ==========================================

def run_short_logic(log_detail):
    log_detail("Analyse_Short 程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    base_date = TARGET_DATE if TARGET_DATE else (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel、History JSON 和 TXT 文件。")

    # 初始化分组（每次运行前清空）
    panel_data['Short'] = {}
    short_group = panel_data['Short']
    panel_data['Short_backup'] = {}
    short_backup_group = panel_data['Short_backup']
    panel_data['Short_W'] = {}
    short_w_group = panel_data['Short_W']
    panel_data['Short_W_backup'] = {}
    short_w_backup_group = panel_data['Short_W_backup']

    # [新增] 预构建原生 Short_W 锚点索引（一次性）
    chase_enabled = CONFIG.get("CHASE_ENABLED", False)
    chase_suffix = CONFIG["CHASE_SUFFIX"]
    chase_anchors = build_native_chase_anchors(earning_history_data, base_date) if chase_enabled else {}
    if chase_enabled:
        log_detail(f"[追] 已启用：来源分组={CONFIG['CHASE_SOURCE_GROUPS']}, "
           f"窗口={CONFIG['CHASE_LOOKBACK_TRADING_DAYS']}个交易日, "
           f"股票回落{fmt_drop_thr(CONFIG['CHASE_MIN_DROP_PCT'])}, "
           f"ETF回落{fmt_drop_thr(CONFIG['ETF_CHASE_MIN_DROP_PCT'])}, "
           f"可用锚点股票数={len(chase_anchors)}")

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

    symbols = list(dict.fromkeys(symbols))      # 去重并保持顺序，结果可复现
    log_detail(f"开始扫描 {len(symbols)} 个 symbols（基准日期: {base_date}）...")

    # 一次取足两类规则所需的行数
    fetch_limit = max(CONFIG["RECENT_DAYS_LOOKBACK"],
                      CONFIG["CHASE_LOOKBACK_TRADING_DAYS"] if chase_enabled else 0) + 1

    for symbol in symbols:
        is_tracing = (symbol == SYMBOL_TO_TRACE)
        try:
            # --- A. 基础信息与标签过滤 ---
            symbol_info = get_symbol_info(symbol)
            sector = get_symbol_sector(symbol)
            tags_str = ", ".join(symbol_info['tags']) if symbol_info['tags'] else "无标签"

            if sector == "Unknown":
                if is_tracing:
                    log_detail(f"    x [过滤] {symbol} 未找到所属板块，跳过。")
                continue

            if len(WHITELIST_TAGS) > 0:
                if not any(tag in WHITELIST_TAGS for tag in symbol_info['tags']):
                    if is_tracing:
                        log_detail(f"    x [过滤] {symbol} 不在白名单中，跳过。")
                    continue
            elif symbol_info['has_blacklist']:
                if is_tracing:
                    log_detail(f"    x [过滤] {symbol} 命中黑名单标签 ({tags_str})，跳过。")
                continue

            if is_tracing:
                log_detail(f"\n--- 正在检查 {symbol} (sector: {sector}) ---")
                log_detail(f"    基准日期: {base_date}, 标签: {tags_str}")

            # --- A1. 财报日当天过滤 ---
            latest_earning_date = get_latest_earnings_date(cursor, symbol, target_date=base_date)
            if latest_earning_date == base_date:
                if is_tracing:
                    log_detail(f"    x [过滤] {symbol} 的最新财报日正好是当前基准日 ({base_date})，跳过。")
                continue

            # --- A2. MA 仅用于显示 ---
            ma_value = calc_ma(cursor, sector, symbol, CONFIG["MA_PERIOD"], target_date=base_date)

            # --- B. 获取最近交易数据（降序） ---
            cursor.execute(
                f'SELECT date, price, volume FROM "{sector}" '
                f'WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT {fetch_limit}',
                (symbol, base_date))
            rows = cursor.fetchall()

            if len(rows) < 2:
                if is_tracing:
                    log_detail(f"    x [失败] 数据不足 2 天，跳过。")
                continue

            date_curr, price_curr, vol_curr = rows[0]
            date_prev, price_prev, vol_prev = rows[1]
            if price_curr is None or price_prev is None or vol_curr is None:
                continue
            price_curr, price_prev = float(price_curr), float(price_prev)

            current_turnover = price_curr * float(vol_curr)
            if is_tracing:
                log_detail(f"    最新: {date_curr} 价格={price_curr}, 成交量={vol_curr}, 成交额={current_turnover:,.0f}")
                log_detail(f"    前一日: {date_prev} 价格={price_prev}")

            # --- C. 基础门槛 1: N 天内任意一天下跌 ---
            lookback = CONFIG["RECENT_DAYS_LOOKBACK"]
            n_pairs = min(lookback, len(rows) - 1)
            any_drop = any(
                rows[i][1] is not None and rows[i + 1][1] is not None
                and float(rows[i][1]) < float(rows[i + 1][1])
                for i in range(n_pairs)
            )
            if is_tracing:
                log_detail(f"    - 下跌检查: {any_drop}")
            if not any_drop:
                if is_tracing:
                    log_detail(f"    x [失败] 最近 N 天内未发生下跌，跳过。")
                continue

            # --- D0. [新增] ETF 特殊规则：有锚点 + 下跌 即可，跳过成交额检查 ---
            etf_chase_info = None
            if (chase_enabled
                    and CONFIG.get("ETF_RELAXED_ENABLED")
                    and sector == CONFIG["ETF_SECTOR_NAME"]):
                etf_min_drop = CONFIG.get("ETF_CHASE_MIN_DROP_PCT")
                if etf_min_drop is None:
                    etf_min_drop = float('-inf')
                etf_chase_info = find_chase_anchor(
                    rows, chase_anchors.get(symbol, []), min_drop=etf_min_drop)
                if is_tracing:
                    log_detail(f"    - [ETF特殊规则] 锚点结果: {etf_chase_info}")

            # --- D. 基础门槛 2: 成交额排名检查（原生命中） ---
            is_hit_base = False
            hit_reason = ""
            for i in range(n_pairs):
                day_date, day_price, day_vol = rows[i]
                _, prev_price_i, prev_vol_i = rows[i + 1]

                if day_price is None or prev_price_i is None or day_vol is None or prev_vol_i is None:
                    continue

                day_price = float(day_price)
                prev_price_i = float(prev_price_i)
                if day_price >= prev_price_i:
                    continue

                day_turnover = day_price * float(day_vol)
                prev_turnover = prev_price_i * float(prev_vol_i)

                if day_turnover <= prev_turnover:
                    if is_tracing:
                        log_detail(f"    - [成交额检查] {day_date} 成交额({day_turnover:,.0f}) 未上涨 (前一日: {prev_turnover:,.0f})，跳过。")
                    continue

                date_suffix = f"({day_date})" if i > 0 else ""
                if check_turnover_rank(cursor, sector, symbol, day_date, day_turnover,
                                       CONFIG["LOOKBACK_MONTHS_LONG"], CONFIG["RANK_THRESHOLD_LONG"]):
                    is_hit_base = True
                    hit_reason = f"1年内Top{CONFIG['RANK_THRESHOLD_LONG']}天量{date_suffix}"
                    if is_tracing:
                        log_detail(f"    ✓ [命中] {hit_reason}")
                    break
                elif is_tracing:
                    log_detail(f"    - [成交额检查] {day_date} 成交额={day_turnover:,.0f} 未进入排名门槛。")

            # --- D2. [新增] 原生未命中 -> 尝试"追"（绕过成交额门槛） ---
            chase_info = None
            if not is_hit_base:
                is_etf = (chase_enabled
                    and CONFIG.get("ETF_RELAXED_ENABLED")
                    and sector == CONFIG["ETF_SECTOR_NAME"])
                if chase_enabled:
                    if is_etf:
                        chase_info = etf_chase_info          # ETF 只用自己的规则
                    else:
                        chase_info = find_chase_anchor(rows, chase_anchors.get(symbol, []))
                    if is_tracing:
                        thr = CONFIG["ETF_CHASE_MIN_DROP_PCT"] if is_etf else CONFIG["CHASE_MIN_DROP_PCT"]
                        if chase_info:
                            log_detail(f"    ✓ [追] 锚点 {chase_info[0]} (来自 {chase_info[3]}) 收盘={chase_info[1]}, "
                                    f"当前={price_curr}, 回落 {chase_info[2] * 100:.2f}% "
                                    f"(阈值 {fmt_drop_thr(thr)})")
                        else:
                            log_detail(f"    - [追] 未满足（无有效原生锚点 / 回落不足 / 非下跌日）。 "
                                    f"阈值 {fmt_drop_thr(thr)}，已知锚点: {chase_anchors.get(symbol, [])}")
                if not chase_info:
                    if is_tracing:
                        log_detail(f"    x [失败] 成交额排名未达标且不满足'追'条件，跳过。")
                    continue
                hit_reason = (f"{chase_suffix}[{chase_info[3]}锚点{chase_info[0]} 回落{chase_info[2] * 100:.2f}%]")
                if etf_chase_info:
                    hit_reason = "ETF宽松-" + hit_reason

            # --- E. 分流逻辑 ---
            is_bottom_fishing = evaluate_bottom_fishing(
                cursor, sector, symbol, symbol_info['tags'], price_curr,
                latest_earning_date, is_tracing, log_detail)

            if chase_info:
                # "追"：归入锚点所在分组（Short 或 Short_W），symbol 后缀加标识
                tag_text = f"{symbol}{'抄底' if is_bottom_fishing else ''}{chase_suffix}"
                chase_group = chase_info[3]
                if chase_group == "Short_W":
                    short_w_group[symbol] = tag_text
                    short_w_backup_group[symbol] = tag_text
                    final_short_w_symbols.append(tag_text)
                    group_tag = "[Short_W]"
                else:
                    short_group[symbol] = tag_text
                    short_backup_group[symbol] = tag_text
                    final_short_symbols.append(tag_text)
                    group_tag = "[Short]"
                logger.info(f'[{symbol}] Hit {chase_group} (chase): {hit_reason}')
                if is_tracing:
                    log_detail(f"    ✅ [选中-{chase_group}-追] {hit_reason}" + (" (包含抄底条件)" if is_bottom_fishing else ""))
            else:
                note_val = f"{symbol}抄底" if is_bottom_fishing else ""
                history_val = f"{symbol}抄底" if is_bottom_fishing else symbol

                is_double_top = check_double_top(cursor, symbol, sector, target_date=base_date)
                if is_tracing:
                    log_detail(f"    - M头检查: {is_double_top}")

                if is_double_top:
                    short_w_group[symbol] = note_val
                    short_w_backup_group[symbol] = note_val
                    final_short_w_symbols.append(history_val)
                    group_tag = "[Short_W]"
                    logger.info(f'[{symbol}] Hit Short_W: {hit_reason} + M-Top')
                    if is_tracing:
                        log_detail(f"    ✅ [选中-Short_W] {hit_reason} + M头形态" + (" (包含抄底条件)" if is_bottom_fishing else ""))
                else:
                    short_group[symbol] = note_val
                    short_backup_group[symbol] = note_val
                    final_short_symbols.append(history_val)
                    group_tag = "[Short]"
                    logger.info(f'[{symbol}] Hit Short: {hit_reason}')
                    if is_tracing:
                        log_detail(f"    ✅ [选中-Short] {hit_reason}" + (" (包含抄底条件)" if is_bottom_fishing else ""))

            sector_disp = pad_display(sector, 20, 'left')
            symbol_disp = pad_display(symbol, 5, 'left')
            pct_change = (price_curr - price_prev) / price_prev * 100 if price_prev else 0.0
            sector_outputs[sector_disp].append({
                'text': f"{sector_disp} {symbol_disp} {pct_change:.2f}% MA{CONFIG['MA_PERIOD']}={ma_value:.2f} {group_tag} {hit_reason}: {tags_str}",
                'change_percent': abs(current_turnover)
            })

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

    # ======== 正常模式 ========
    log_detail("OverBuy Scan Result (Down + High Turnover)")
    log_detail(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    log_detail("=" * 60)
    for sector in sorted(sector_outputs.keys()):
        for output in sorted(sector_outputs[sector], key=lambda x: x['change_percent'], reverse=True):
            log_detail(output['text'])

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
        run_short_logic(print)


if __name__ == '__main__':
    main()