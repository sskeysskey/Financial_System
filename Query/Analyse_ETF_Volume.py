import json
import sqlite3
import os
import re
import datetime

# --- 1. 配置文件和路径 ---
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
BASE_PATH = USER_HOME

# ================= 配置区域 =================
SYMBOL_TO_TRACE = ""
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "AIRR"
# TARGET_DATE = "2026-03-30"

LOG_FILE_PATH = os.path.join(BASE_PATH, "Downloads", "ETF_Volume_trace_log.txt")

PATHS = {
    "config_dir": os.path.join(BASE_CODING_DIR, 'Financial_System', 'Modules'),
    "db_dir": os.path.join(BASE_CODING_DIR, 'Database'),
    "panel_json": lambda config_dir: os.path.join(config_dir, 'Sectors_panel.json'),
    "description_json": lambda config_dir: os.path.join(config_dir, 'description.json'),
    "tags_setting_json": lambda config_dir: os.path.join(config_dir, 'tags_filter.json'),
    "earnings_history_json": lambda config_dir: os.path.join(config_dir, 'Earning_History.json'),
    "db_file": lambda db_dir: os.path.join(db_dir, 'Finance.db'),
}

CONFIG_DIR = PATHS["config_dir"]
DB_DIR = PATHS["db_dir"]
DB_FILE = PATHS["db_file"](DB_DIR)
PANEL_JSON_FILE = PATHS["panel_json"](CONFIG_DIR)
DESCRIPTION_JSON_FILE = PATHS["description_json"](CONFIG_DIR)
TAGS_SETTING_JSON_FILE = PATHS["tags_setting_json"](CONFIG_DIR)
EARNING_HISTORY_JSON_FILE = PATHS["earnings_history_json"](CONFIG_DIR)

CONFIG = {
    # ========== 策略1 (ETF_Volume_high 放量突破) 参数 ==========
    "ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS": 12,  # 成交额回溯12个月
    "ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD": 3,    # 成交额排名前3名

    # ========== 策略2 (ETF_Volume_low 触底放量) 参数 ==========
    "ETF_COND_LOW_PRICE_LOOKBACK_MONTHS": 3,       # 最高点回溯月份
    "ETF_COND_LOW_DROP_THRESHOLD": 0.06,           # 距最高点跌幅 (原逻辑的常规跌幅)
    "ETF_COND_LOW_TURNOVER_MONTHS": 2,             # 成交额回溯月份
    "ETF_COND_LOW_TURNOVER_RANK_THRESHOLD": 3,     # 成交额排名前 N 名

    # ========== 策略2 附加：年度成交额前三 "甲" 标记 参数 ==========
    "ETF_COND_LOW_YEARLY_TURNOVER_LOOKBACK_MONTHS": 12,  # 年度成交额回溯12个月
    "ETF_COND_LOW_YEARLY_TURNOVER_RANK_THRESHOLD": 3,    # 年度成交额排名前3名 -> 标 "甲"

    # ========== 策略3 (ETF 深度回撤) 参数 【新增】 ==========
    "ETF_COND_DEEP_DROP_LOOKBACK_MONTHS": 6,   # 回溯半年 (约 6*30=180 天)
    "ETF_COND_DEEP_DROP_THRESHOLD": 0.35,      # 从区间最高收盘价回撤 >= 35%
    "ETF_COND_DEEP_DROP_MIN_DAYS": 30,         # 区间内至少要有 N 个交易日数据(防新上市误判)
    "ETF_COND_DEEP_DROP_REQUIRE_DOWN": False,  # 是否额外要求 T 日收盘价 < T-1 收盘价
    "ETF_COND_DEEP_DROP_MAX_STALE_DAYS": 15,   # 最新数据距基准日超过 N 天视为停更, 跳过
    "ETF_DEEP_DROP_MARK": "乙",                # 深跌命中在 Panel 备注中的标记
}


# --- 2. 辅助与文件操作模块 ---
def load_tag_settings(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        tag_blacklist = set(settings.get('BLACKLIST_TAGS', []))
        return tag_blacklist
    except Exception:
        return set()


def load_symbol_tags(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        symbol_tag_map = {}
        for item in data.get('stocks', []):
            symbol = item.get('symbol')
            tags = item.get('tag', [])
            if symbol:
                symbol_tag_map[symbol] = tags
        return symbol_tag_map
    except Exception:
        return {}


def update_panel_etf(json_path, etf_high_list, etf_high_notes,
                     etf_low_list, etf_low_notes, log_detail):
    """
    专门用于 ETF_Volume_high / ETF_Volume_low 的写入。
    只写入 ETF 相关的 4 个分组（含 _backup），不影响其他分组。
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    def build_group_dict(symbols, notes):
        result = {}
        for sym in sorted(symbols):
            val = notes.get(sym, "")
            result[sym] = "" if val == sym else val
        return result

    data['ETF_Volume_high'] = build_group_dict(etf_high_list, etf_high_notes)
    data['ETF_Volume_high_backup'] = build_group_dict(etf_high_list, etf_high_notes)
    data['ETF_Volume_low'] = build_group_dict(etf_low_list, etf_low_notes)
    data['ETF_Volume_low_backup'] = build_group_dict(etf_low_list, etf_low_notes)

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail("Panel 文件更新完成（ETF 分组）。")
    except Exception as e:
        log_detail(f"错误: 写入 Panel JSON 文件失败: {e}")


def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail, base_date_str):
    log_detail(f"\n--- 更新历史记录: '{group_name}' ---")
    if not symbols_to_add:
        log_detail(" - 列表为空，跳过写入。")
        return

    record_date_str = base_date_str

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(record_date_str, [])
    combined_symbols = set(existing_symbols) | set(symbols_to_add)
    updated_symbols = sorted(list(combined_symbols))

    if not updated_symbols:
        return

    data[group_name][record_date_str] = updated_symbols
    num_added = len(updated_symbols) - len(existing_symbols)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail(f"成功更新: 日期={record_date_str}, 分组='{group_name}', 新增 {num_added} 个。")
    except Exception as e:
        log_detail(f"错误: 写入历史记录文件失败: {e}")


# --- 3. 核心逻辑模块 ---
def check_turnover_rank(cursor, sector_name, symbol, latest_date_str, latest_turnover,
                        lookback_months, rank_threshold, log_detail, is_tracing):
    """
    检查 latest_turnover 是否是过去 lookback_months 个月内的前 rank_threshold 名
    """
    try:
        dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - datetime.timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()

    valid_data = []
    for r in rows:
        if r[1] is not None and r[2] is not None:
            valid_data.append((r[0], r[1] * r[2]))

    if not valid_data:
        return False

    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    top_n_data = sorted_data[:rank_threshold]
    top_n_turnovers = [item[1] for item in top_n_data]

    is_top_n = False
    if latest_turnover in top_n_turnovers:
        is_top_n = True
    elif len(top_n_turnovers) >= rank_threshold and latest_turnover >= top_n_turnovers[rank_threshold - 1]:
        is_top_n = True

    if is_tracing:
        log_detail(f"    - 成交额排名检查: 回溯{lookback_months}个月, 共{len(valid_data)}个交易日")
        top_str = ", ".join([f"[{d}]: {v:,.0f}" for d, v in top_n_data])
        log_detail(f"      前{rank_threshold}名: {top_str}")
        log_detail(f"      当前成交额: {latest_turnover:,.0f} -> 在前{rank_threshold}: {is_top_n}")

    return is_top_n


def get_etf_yearly_turnover_top_symbols(db_path, symbols, target_date_override, log_detail,
                                        lookback_months=12, rank_threshold=3, symbol_to_trace=""):
    """
    对给定的 ETF 列表，逐个判断其"最新成交额"是否为过去 lookback_months 个月的前 rank_threshold 名。
    返回符合条件的 symbol 集合（用于在 Panel 中追加 "甲" 标记）。
    """
    log_detail(f"\n========== 计算 ETF_Volume_low 的年度成交额前 {rank_threshold} 名 (标记'甲') ==========")
    result = set()
    if not symbols:
        log_detail(" - 输入列表为空，跳过。")
        return result

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    for symbol in symbols:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- [甲标记] 检查 ETF {symbol} ---")

        # 获取最新一天的数据
        if target_date_override:
            cursor.execute(
                'SELECT date, price, volume FROM "ETFs" WHERE name = ? AND date <= ? '
                'ORDER BY date DESC LIMIT 1',
                (symbol, target_date_override)
            )
        else:
            cursor.execute(
                'SELECT date, price, volume FROM "ETFs" WHERE name = ? '
                'ORDER BY date DESC LIMIT 1',
                (symbol,)
            )

        row = cursor.fetchone()
        if not row or row[1] is None or row[2] is None:
            if is_tracing:
                log_detail("    x 无最新成交数据")
            continue

        latest_date, latest_price, latest_volume = row
        latest_turnover = latest_price * latest_volume

        if check_turnover_rank(cursor, "ETFs", symbol, latest_date, latest_turnover,
                               lookback_months, rank_threshold, log_detail, is_tracing):
            result.add(symbol)
            if is_tracing:
                log_detail(f"    ✅ 年度成交额前{rank_threshold} -> 标记 '甲'")

    conn.close()
    log_detail(f"\n年度成交额前 {rank_threshold} 名 (标'甲') 共 {len(result)} 个: {sorted(result)}")
    return result


# --- 策略1: ETF_Volume_high (ETF放量突破) ---
def process_etf_volume_high(db_path, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略1 (ETF_Volume_high - ETF放量突破) ==========")

    turnover_lookback_months = CONFIG.get("ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 12)
    turnover_rank_threshold = CONFIG.get("ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)

    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    log_detail(f"基准日期: {base_date}")

    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
        log_detail(f"从 ETFs 表中获取 {len(all_etfs)} 个 Symbol。")
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []

    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- 检查 ETF {symbol} ---")

        if target_date_override:
            query = f'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, target_date_override))
        else:
            query = f'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol,))

        rows = cursor.fetchall()
        if len(rows) < 2 or rows[0][1] is None or rows[0][2] is None or rows[0][3] is None or rows[1][1] is None:
            if is_tracing: log_detail("    x 交易数据不足")
            continue

        latest_date, latest_price, latest_volume, latest_open = rows[0]
        prev_date, prev_price, prev_volume, _ = rows[1]
        latest_turnover = latest_price * latest_volume

        cond_price_up = (latest_price > prev_price) and (latest_price > latest_open)
        if is_tracing:
            log_detail(f"    - 条件A (今日上涨): {prev_price:.2f} -> {latest_price:.2f} = {cond_price_up}")

        if not cond_price_up:
            continue

        cond_turnover_top = check_turnover_rank(
            cursor, "ETFs", symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold,
            log_detail, is_tracing
        )

        if cond_turnover_top:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中] 上涨 + {turnover_lookback_months}月Top{turnover_rank_threshold}")

    conn.close()
    results = sorted(list(set(results)))
    log_detail(f"\n策略1 筛选完成，共命中 {len(results)} 个 ETF: {results}")
    return results


# --- 策略2: ETF_Volume_low (ETF触底放量) ---
def process_etf_volume_low(db_path, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略2 (ETF_Volume_low - ETF触底放量) ==========")

    price_lookback_months = CONFIG.get("ETF_COND_LOW_PRICE_LOOKBACK_MONTHS", 6)
    drop_threshold = CONFIG.get("ETF_COND_LOW_DROP_THRESHOLD", 0.11)
    turnover_lookback_months = CONFIG.get("ETF_COND_LOW_TURNOVER_MONTHS", 3)
    turnover_rank_threshold = CONFIG.get("ETF_COND_LOW_TURNOVER_RANK_THRESHOLD", 2)

    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
        log_detail(f"从 ETFs 表中获取 {len(all_etfs)} 个 Symbol。")
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []

    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- 检查 ETF {symbol} ---")

        try:
            dt = datetime.datetime.strptime(base_date, "%Y-%m-%d")
            start_date_price = dt - datetime.timedelta(days=price_lookback_months * 30)
            start_date_price_str = start_date_price.strftime("%Y-%m-%d")
        except Exception:
            continue

        query = f'SELECT date, price, volume FROM "ETFs" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date DESC'
        cursor.execute(query, (symbol, start_date_price_str, base_date))
        rows = cursor.fetchall()

        if len(rows) < 3:
            if is_tracing: log_detail("    x 数据不足 3 天")
            continue

        latest_date, latest_price, latest_volume = rows[0]
        prev_date, prev_price, prev_volume = rows[1]
        prev_prev_date, prev_prev_price, prev_prev_volume = rows[2]

        if None in [latest_price, prev_price, prev_prev_price, latest_volume, prev_volume]:
            continue

        latest_turnover = latest_price * latest_volume
        prev_turnover = prev_price * prev_volume

        cond_latest_down = latest_price < prev_price
        if not cond_latest_down:
            if is_tracing: log_detail(f"    x T日未下跌 ({latest_price:.2f} >= {prev_price:.2f})")
            continue

        valid_prices = [r[1] for r in rows if r[1] is not None]
        max_price = max(valid_prices)

        # 计算跌幅
        cond_price_drop = latest_price <= max_price * (1 - drop_threshold)

        if is_tracing:
            drop_pct = (1 - latest_price / max_price) if max_price > 0 else 0
            log_detail(f"    - 条件A (跌幅>{drop_threshold*100}%): 最高 {max_price:.2f}, 当前 {latest_price:.2f}, 跌幅 {drop_pct:.2%} = {cond_price_drop}")

        # 如果连常规跌幅都没达到，直接跳过
        if not cond_price_drop:
            continue

        # 检查成交额条件
        cond_latest_turnover_top = check_turnover_rank(
            cursor, "ETFs", symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
        )

        cond_prev_turnover_top = False
        cond_prev_down = prev_price < prev_prev_price

        if not cond_latest_turnover_top:
            cond_prev_turnover_top = check_turnover_rank(
                cursor, "ETFs", symbol, prev_date, prev_turnover,
                turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
            )

        cond_high_and_down = cond_latest_turnover_top or (cond_prev_turnover_top and cond_prev_down)

        if is_tracing:
            log_detail(f"    - 条件B: T日放量={cond_latest_turnover_top}, T-1放量={cond_prev_turnover_top}, T-1下跌={cond_prev_down} -> {cond_high_and_down}")

        if cond_price_drop and cond_high_and_down:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中] 跌幅达标 + 阶段巨量且下跌")

    conn.close()
    results = sorted(list(set(results)))
    log_detail(f"\n策略2 筛选完成，共命中 {len(results)} 个 ETF: {results}")
    return results


# --- 策略3【新增】: ETF 深度回撤 (半年最高收盘价回撤 >= 35%) ---
def process_etf_deep_drop(db_path, target_date_override, symbol_to_trace, log_detail):
    """
    新规则：任何 ETF，在最近 N 个月(默认6个月)内，
    从区间内最高收盘价(price) 回撤到 最新收盘价 的跌幅 >= 阈值(默认35%)，
    即命中，并入 ETF_Volume_low 分组（备注追加 '乙' 标记）。

    不依赖成交额、不依赖当日涨跌（可通过 CONFIG 开关要求 T 日下跌）。
    """
    lookback_months = CONFIG.get("ETF_COND_DEEP_DROP_LOOKBACK_MONTHS", 6)
    drop_threshold = CONFIG.get("ETF_COND_DEEP_DROP_THRESHOLD", 0.35)
    min_days = CONFIG.get("ETF_COND_DEEP_DROP_MIN_DAYS", 30)
    require_down = CONFIG.get("ETF_COND_DEEP_DROP_REQUIRE_DOWN", False)
    max_stale_days = CONFIG.get("ETF_COND_DEEP_DROP_MAX_STALE_DAYS", 15)

    log_detail(f"\n========== 开始执行 策略3 (ETF_Deep_Drop - 半年深度回撤) ==========")
    log_detail(f"参数: 回溯 {lookback_months} 个月 | 回撤阈值 >= {drop_threshold:.2%} | "
               f"最少交易日 {min_days} | 要求T日下跌={require_down} | 允许数据滞后 {max_stale_days} 天")

    base_date = target_date_override if target_date_override else \
        (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    log_detail(f"基准日期: {base_date}")

    try:
        base_dt = datetime.datetime.strptime(base_date, "%Y-%m-%d")
    except Exception as e:
        log_detail(f"错误: 基准日期解析失败: {e}")
        return [], {}

    start_dt = base_dt - datetime.timedelta(days=lookback_months * 30)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    log_detail(f"回溯区间: [{start_date_str} ~ {base_date}]")

    results = []
    detail_map = {}   # symbol -> dict(详细信息, 便于日志与后续扩展)

    # 统计计数器（用于最终日志汇总）
    stat = {
        "total": 0,
        "no_data": 0,
        "not_enough_days": 0,
        "stale": 0,
        "bad_max": 0,
        "drop_not_enough": 0,
        "blocked_by_down": 0,
        "hit": 0,
    }

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
        log_detail(f"从 ETFs 表中获取 {len(all_etfs)} 个 Symbol。")
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return [], {}

    for symbol in all_etfs:
        stat["total"] += 1
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- [深跌规则] 检查 ETF {symbol} ---")

        cursor.execute(
            'SELECT date, price FROM "ETFs" WHERE name = ? AND date >= ? AND date <= ? '
            'ORDER BY date DESC',
            (symbol, start_date_str, base_date)
        )
        rows = cursor.fetchall()

        valid_rows = [(r[0], r[1]) for r in rows if r[1] is not None]
        if not valid_rows:
            stat["no_data"] += 1
            if is_tracing: log_detail("    x 区间内无有效收盘价数据")
            continue

        if len(valid_rows) < min_days:
            stat["not_enough_days"] += 1
            if is_tracing:
                log_detail(f"    x 区间内仅 {len(valid_rows)} 个交易日, 少于最低要求 {min_days} 天")
            continue

        latest_date, latest_price = valid_rows[0]

        # 数据滞后检查（停更/退市的 ETF 不参与）
        try:
            latest_dt = datetime.datetime.strptime(latest_date, "%Y-%m-%d")
            stale_days = (base_dt - latest_dt).days
        except Exception:
            stale_days = 0
        if max_stale_days > 0 and stale_days > max_stale_days:
            stat["stale"] += 1
            if is_tracing:
                log_detail(f"    x 数据滞后 {stale_days} 天 (最新 {latest_date}), 超过 {max_stale_days} 天, 跳过")
            continue

        # 区间最高收盘价及其日期
        max_date, max_price = max(valid_rows, key=lambda x: x[1])
        if max_price is None or max_price <= 0:
            stat["bad_max"] += 1
            if is_tracing: log_detail("    x 区间最高价异常(<=0)")
            continue

        drop_pct = 1 - (latest_price / max_price)
        cond_deep_drop = latest_price <= max_price * (1 - drop_threshold)

        if is_tracing:
            log_detail(f"    - 区间交易日数: {len(valid_rows)}")
            log_detail(f"    - 区间最高收盘: [{max_date}] {max_price:.4f}")
            log_detail(f"    - 最新收盘:     [{latest_date}] {latest_price:.4f}")
            log_detail(f"    - 回撤幅度: {drop_pct:.2%} (阈值 {drop_threshold:.2%}) = {cond_deep_drop}")

        if not cond_deep_drop:
            stat["drop_not_enough"] += 1
            continue

        # 可选：要求 T 日下跌
        if require_down:
            if len(valid_rows) < 2:
                stat["blocked_by_down"] += 1
                if is_tracing: log_detail("    x 无 T-1 数据, 无法判断当日涨跌")
                continue
            prev_date, prev_price = valid_rows[1]
            if not (latest_price < prev_price):
                stat["blocked_by_down"] += 1
                if is_tracing:
                    log_detail(f"    x T日未下跌 ({latest_price:.4f} >= {prev_price:.4f}), 按配置过滤")
                continue
            if is_tracing:
                log_detail(f"    - T日下跌校验通过: {prev_price:.4f} -> {latest_price:.4f}")

        results.append(symbol)
        stat["hit"] += 1
        detail_map[symbol] = {
            "max_date": max_date,
            "max_price": max_price,
            "latest_date": latest_date,
            "latest_price": latest_price,
            "drop_pct": drop_pct,
            "days": len(valid_rows),
        }
        if is_tracing:
            log_detail(f"    ✅ [选中] 半年回撤 {drop_pct:.2%} >= {drop_threshold:.2%}")

    conn.close()

    results = sorted(list(set(results)))

    # ---- 汇总日志 ----
    log_detail(f"\n--- 策略3 统计 ---")
    log_detail(f"  扫描总数: {stat['total']}")
    log_detail(f"  无数据跳过: {stat['no_data']} | 交易日不足: {stat['not_enough_days']} | 数据停更: {stat['stale']}")
    log_detail(f"  最高价异常: {stat['bad_max']} | 回撤未达标: {stat['drop_not_enough']} | 因T日未跌过滤: {stat['blocked_by_down']}")
    log_detail(f"  ✅ 命中: {stat['hit']}")

    if results:
        log_detail(f"\n--- 策略3 命中明细 (按回撤幅度降序) ---")
        for sym in sorted(results, key=lambda s: detail_map[s]["drop_pct"], reverse=True):
            d = detail_map[sym]
            log_detail(f"  {sym:<8} 回撤 {d['drop_pct']:>7.2%} | 高点 [{d['max_date']}] {d['max_price']:.4f} "
                       f"-> 最新 [{d['latest_date']}] {d['latest_price']:.4f} | 样本 {d['days']} 天")

    log_detail(f"\n策略3 筛选完成，共命中 {len(results)} 个 ETF: {results}")
    return results, detail_map


def process_etf_volume_low_continuation(db_path, target_date_override,
                                         history_json_path, symbol_to_trace, log_detail):
    """
    策略2补充规则（延续信号）：
    针对每个ETF，扫描 Earning_History.json 的 ETF_Volume_low 分组，
    检查在"基准日期前7天内"是否曾经命中过。
    若曾命中，且当前收盘价 < 前一日收盘价，同时当前收盘价 < 任一历史命中日的收盘价，则加入结果。
    """
    log_detail("\n========== 开始执行 策略2补充规则 (ETF_Volume_low 延续) ==========")

    base_date = target_date_override if target_date_override else \
        (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    log_detail(f"基准日期: {base_date}")

    # --- 读取 History ---
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log_detail(f"无法加载 History JSON: {e}")
        return []

    low_history = history_data.get("ETF_Volume_low", {})
    if not low_history:
        log_detail("ETF_Volume_low 历史记录为空，跳过。")
        return []

    # --- 计算7天窗口 ---
    try:
        base_dt = datetime.datetime.strptime(base_date, "%Y-%m-%d")
        seven_days_ago = base_dt - datetime.timedelta(days=7)
    except Exception as e:
        log_detail(f"日期解析失败: {e}")
        return []

    # --- 构建 symbol -> [历史命中日期] 的索引 ---
    # 范围: [base_date - 7天, base_date)，不含 base_date 自身（避免自己参考自己）
    symbol_history_dates = {}
    for date_str, symbols in low_history.items():
        try:
            hist_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            continue
        if hist_dt >= base_dt:      # 不考虑未来日期和当日
            continue
        if hist_dt < seven_days_ago: # 超出7天窗口
            continue
        for raw_sym in symbols:
            sym = _clean_hist_symbol(raw_sym)
            if sym:
                symbol_history_dates.setdefault(sym, []).append(date_str)

    log_detail(f"7天窗口内涉及到的历史 ETF 数: {len(symbol_history_dates)}")

    # --- 逐个 ETF 检查价格 ---
    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []

    for symbol in all_etfs:
        if symbol not in symbol_history_dates:
            continue

        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- [延续规则] 检查 ETF {symbol} ---")
            log_detail(f"    7天内历史命中日期: {symbol_history_dates[symbol]}")

        # 获取当前最新收盘价和前一日收盘价
        cursor.execute(
            f'SELECT date, price FROM "ETFs" WHERE name = ? AND date <= ? '
            f'ORDER BY date DESC LIMIT 2',
            (symbol, base_date)
        )
        rows = cursor.fetchall()
        if len(rows) < 2 or rows[0][1] is None or rows[1][1] is None:
            if is_tracing: log_detail("    x 无当前或前一日价格数据")
            continue

        latest_date, latest_price = rows[0]
        prev_date, prev_price = rows[1]

        # 检查是否低于前一日收盘价
        if latest_price >= prev_price:
            if is_tracing: log_detail(f"    x T日未下跌 ({latest_price:.4f} >= {prev_price:.4f})")
            continue

        # 逐一比较每个历史日期的价格
        hit = False
        for hist_date in symbol_history_dates[symbol]:
            cursor.execute(
                f'SELECT price FROM "ETFs" WHERE name = ? AND date = ?',
                (symbol, hist_date)
            )
            r = cursor.fetchone()
            if not r or r[0] is None:
                if is_tracing: log_detail(f"    - 历史日期 {hist_date} 无价格数据")
                continue
            hist_price = r[0]

            if latest_price < hist_price:
                if is_tracing:
                    log_detail(f"    ✅ [{hist_date}] 历史价 {hist_price:.4f} > "
                               f"当前 {latest_price:.4f}，且今日已下跌，命中")
                hit = True
                break
            else:
                if is_tracing:
                    log_detail(f"    - [{hist_date}] 历史价 {hist_price:.4f} <= "
                               f"当前 {latest_price:.4f}")

        if hit:
            results.append(symbol)

    conn.close()
    results = sorted(list(set(results)))
    log_detail(f"\n策略2补充规则筛选完成，共命中 {len(results)} 个 ETF: {results}")
    return results


def _clean_hist_symbol(s):
    """清洗 History 中的符号，去掉末尾的中文标记（如"黑"/"甲"/"乙"）"""
    return re.sub(r'[\u4e00-\u9fff]+$', '', s).strip()


# --- 4. 主执行流程 ---
def run_etf_volume_logic(log_detail):
    log_detail("ETF_Volume 多策略程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    base_date_str = TARGET_DATE if TARGET_DATE else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    if TARGET_DATE:
        log_detail(f"\n⚠️ 回测模式, 目标日期: {TARGET_DATE}，不会写入 Panel 和 History。")

    tag_blacklist = load_tag_settings(TAGS_SETTING_JSON_FILE)
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    deep_mark = CONFIG.get("ETF_DEEP_DROP_MARK", "乙")

    # 执行策略
    final_etf_high = process_etf_volume_high(DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail)
    final_etf_low = process_etf_volume_low(DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail)

    # ===== 策略2的延续规则 =====
    final_etf_low_cont = process_etf_volume_low_continuation(
        DB_FILE, TARGET_DATE, EARNING_HISTORY_JSON_FILE,
        SYMBOL_TO_TRACE, log_detail
    )

    # ===== 新增：策略3 半年深度回撤 (>=35%) =====
    final_etf_deep_drop, deep_drop_detail = process_etf_deep_drop(
        DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail
    )
    deep_drop_set = set(final_etf_deep_drop)

    # 合并去重
    before_merge = len(final_etf_low)
    merged = set(final_etf_low) | set(final_etf_low_cont) | deep_drop_set
    only_deep = sorted(deep_drop_set - set(final_etf_low) - set(final_etf_low_cont))
    final_etf_low = sorted(list(merged))

    log_detail(f"\n========== ETF_Volume_low 合并结果 ==========")
    log_detail(f"  原策略2: {before_merge} 个")
    log_detail(f"  延续规则: {len(final_etf_low_cont)} 个")
    log_detail(f"  深跌规则(策略3): {len(deep_drop_set)} 个 (其中仅由深跌规则新增: {len(only_deep)} 个)")
    if only_deep:
        log_detail(f"  仅深跌新增清单: {only_deep}")
    log_detail(f"  => 去重合并后共 {len(final_etf_low)} 个")

    # ===== 计算 ETF_Volume_low 中 "年度成交额前三" 的标 "甲" 集合 =====
    etf_low_jia_set = get_etf_yearly_turnover_top_symbols(
        DB_FILE, final_etf_low, TARGET_DATE, log_detail,
        CONFIG.get("ETF_COND_LOW_YEARLY_TURNOVER_LOOKBACK_MONTHS", 12),
        CONFIG.get("ETF_COND_LOW_YEARLY_TURNOVER_RANK_THRESHOLD", 3),
        SYMBOL_TO_TRACE
    )

    # 构建备注（含黑名单标记 / 甲标记 / 乙标记）
    def build_notes(symbols, jia_set=None, deep_set=None):
        if jia_set is None:
            jia_set = set()
        if deep_set is None:
            deep_set = set()
        note_map = {}
        for sym in symbols:
            suffix = ""
            s_tags = set(symbol_to_tags_map.get(sym, []))
            if s_tags.intersection(tag_blacklist):
                suffix += "黑"
            if sym in jia_set:
                suffix += "甲"
            if sym in deep_set:
                suffix += deep_mark
            note_map[sym] = f"{sym}{suffix}"
        return note_map

    etf_high_notes = build_notes(final_etf_high)
    etf_low_notes = build_notes(final_etf_low, etf_low_jia_set, deep_drop_set)

    # 追踪汇总
    if SYMBOL_TO_TRACE:
        log_detail(f"\n{'='*60}")
        log_detail(f"📌 [{SYMBOL_TO_TRACE}] 命中汇总")
        log_detail(f"  策略1 ETF_Volume_high:      {'✅' if SYMBOL_TO_TRACE in final_etf_high else '❌'}")
        log_detail(f"  策略2 ETF_Volume_low:       {'✅' if SYMBOL_TO_TRACE in final_etf_low else '❌'}")
        log_detail(f"  策略3 半年深跌(标'{deep_mark}'):    {'✅' if SYMBOL_TO_TRACE in deep_drop_set else '❌'}")
        if SYMBOL_TO_TRACE in deep_drop_detail:
            d = deep_drop_detail[SYMBOL_TO_TRACE]
            log_detail(f"        └─ 高点[{d['max_date']}] {d['max_price']:.4f} -> "
                       f"最新[{d['latest_date']}] {d['latest_price']:.4f}, 回撤 {d['drop_pct']:.2%}")
        log_detail(f"  年度成交额前三(甲):         {'✅' if SYMBOL_TO_TRACE in etf_low_jia_set else '❌'}")
        log_detail(f"  最终备注: {etf_low_notes.get(SYMBOL_TO_TRACE, etf_high_notes.get(SYMBOL_TO_TRACE, '(未命中)'))}")
        log_detail(f"{'='*60}")

    # 回测模式拦截
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 回测模式 (Date: {TARGET_DATE}) - 不写入任何文件")
        log_detail(f"📊 ETF_Volume_high 命中: {len(final_etf_high)} 个")
        log_detail(f"   -> {final_etf_high}")
        log_detail(f"📊 ETF_Volume_low  命中: {len(final_etf_low)} 个")
        log_detail(f"   -> {final_etf_low}")
        log_detail(f"📊 其中标'甲'(年度前三): {len(etf_low_jia_set)} 个 -> {sorted(etf_low_jia_set)}")
        log_detail(f"📊 其中标'{deep_mark}'(半年深跌>= "
                   f"{CONFIG.get('ETF_COND_DEEP_DROP_THRESHOLD', 0.35):.0%}): "
                   f"{len(deep_drop_set)} 个 -> {sorted(deep_drop_set)}")
        log_detail(f"📊 Panel 备注预览: {sorted(etf_low_notes.values())}")
        log_detail("="*60)
        return

    # 写入 Panel
    log_detail(f"\n正在写入 Panel 文件...")
    update_panel_etf(PANEL_JSON_FILE, final_etf_high, etf_high_notes,
                     final_etf_low, etf_low_notes, log_detail)

    # 写入 History
    log_detail(f"\n正在更新 History 文件...")
    history_high = sorted(list(etf_high_notes.values()))
    history_low = sorted(list(etf_low_notes.values()))
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_high", history_high, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_low", history_low, log_detail, base_date_str)

    log_detail("程序运行结束。")


def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志: {LOG_FILE_PATH}")
        try:
            with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
                def log_detail_file(message):
                    log_file.write(message + '\n')
                    print(message)
                run_etf_volume_logic(log_detail_file)
        except IOError as e:
            print(f"错误：无法写入日志文件: {e}")
    else:
        print("追踪模式未启用。")
        def log_detail_console(message):
            print(message)
        run_etf_volume_logic(log_detail_console)


if __name__ == '__main__':
    main()