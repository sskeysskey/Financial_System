import json
import sqlite3
import os
import re
import bisect
import heapq
import datetime

# --- 1. 配置文件和路径 ---
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
BASE_PATH = USER_HOME

# ================= 配置区域 =================
SYMBOL_TO_TRACE = ""
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "BWET"
# TARGET_DATE = "2026-09-25"

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
    # ========== 通用参数 ==========
    "ETF_MAX_STALE_DAYS": 15,          # 【新增】策略1/2/延续/追: 最新数据距基准日超过 N 天视为停更, 跳过 (<=0 关闭)
    "AUTO_CREATE_DB_INDEX": True,      # 【新增】自动为 ETFs(name, date) 建索引 (IF NOT EXISTS, 不改数据)

    # ========== 策略1 (ETF_Volume_high 放量突破) 参数 ==========
    "ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS": 12,  # 成交额回溯12个月
    "ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD": 3,    # 成交额排名前3名

    # ========== 策略1 附加："追" 规则 参数 【新增】 ==========
    "ETF_COND_HIGH_CHASE_LOOKBACK_TRADING_DAYS": 15,  # T日之前 N 个交易日内(不含T日)出现过原始 high 信号
    "ETF_COND_HIGH_CHASE_DROP_THRESHOLD": 0.12,       # 今日收盘较 high 当日收盘下跌 >= 12%
    "ETF_COND_HIGH_CHASE_USE_DB_RECALC": True,        # 信号源①: 用数据库按策略1原规则重算历史 high
    "ETF_COND_HIGH_CHASE_USE_HISTORY": True,          # 信号源②: Earning_History.json 中 ETF_Volume_high (不带追)
    "ETF_HIGH_CHASE_MARK": "追",                      # Panel/History 中的标记

    # ========== 策略2 (ETF_Volume_low 触底放量) 参数 ==========
    "ETF_COND_LOW_PRICE_LOOKBACK_MONTHS": 3,       # 最高点回溯月份
    "ETF_COND_LOW_DROP_THRESHOLD": 0.06,           # 距最高点跌幅 (原逻辑的常规跌幅)
    "ETF_COND_LOW_TURNOVER_MONTHS": 2,             # 成交额回溯月份
    "ETF_COND_LOW_TURNOVER_RANK_THRESHOLD": 3,     # 成交额排名前 N 名

    # ========== 策略2 附加：年度成交额前三 "甲" 标记 参数 ==========
    "ETF_COND_LOW_YEARLY_TURNOVER_LOOKBACK_MONTHS": 12,  # 年度成交额回溯12个月
    "ETF_COND_LOW_YEARLY_TURNOVER_RANK_THRESHOLD": 3,    # 年度成交额排名前3名 -> 标 "甲"

    # ========== 策略3 (ETF 深度回撤) 参数 ==========
    "ETF_COND_DEEP_DROP_LOOKBACK_MONTHS": 6,   # 回溯半年 (约 6*30=180 天)
    "ETF_COND_DEEP_DROP_THRESHOLD": 0.35,      # 从区间最高收盘价回撤 >= 35%
    "ETF_COND_DEEP_DROP_MIN_DAYS": 30,         # 区间内至少要有 N 个交易日数据(防新上市误判)
    "ETF_COND_DEEP_DROP_REQUIRE_DOWN": False,  # 是否额外要求 T 日收盘价 < T-1 收盘价
    "ETF_COND_DEEP_DROP_MAX_STALE_DAYS": 15,   # 最新数据距基准日超过 N 天视为停更, 跳过
    "ETF_DEEP_DROP_MARK": "乙",                # 深跌命中在 Panel 备注中的标记
}


# --- 2. 辅助与文件操作模块 ---
def get_base_date(target_date_override):
    """统一基准日: 回测用 TARGET_DATE, 实盘用 '昨天'。所有策略必须共用同一个基准日。"""
    if target_date_override:
        return target_date_override
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def _parse_date(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d")


def _stale_days(latest_date_str, base_dt):
    try:
        return (base_dt - _parse_date(latest_date_str)).days
    except Exception:
        return 0


def _is_stale(latest_date_str, base_dt, max_stale_days):
    return max_stale_days > 0 and _stale_days(latest_date_str, base_dt) > max_stale_days


def _is_top_n(value, values, n):
    """value 是否位于 values 的前 n 名 (与原 check_turnover_rank 判定口径一致)"""
    if not values:
        return False
    top = heapq.nlargest(n, values)
    if value in top:
        return True
    return len(top) >= n and value >= top[n - 1]


def _split_hist_symbol(s):
    """把 History 中的 'ABC黑追' 拆成 ('ABC', '黑追')"""
    if not isinstance(s, str):
        return "", ""
    m = re.match(r'^(.*?)([\u4e00-\u9fff]*)$', s.strip())
    if not m:
        return s.strip(), ""
    return m.group(1).strip(), m.group(2)


def _clean_hist_symbol(s):
    """清洗 History 中的符号，去掉末尾的中文标记（如"黑"/"甲"/"乙"/"追"）"""
    return _split_hist_symbol(s)[0]


def _load_json_safe(path, log_detail):
    """
    返回 (data, ok)
      - 文件不存在: ({}, True)   -> 可以安全新建
      - 解析失败:   (None, False) -> 调用方必须中止写入, 防止覆盖掉其它分组
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f), True
    except FileNotFoundError:
        return {}, True
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        log_detail(f"错误: 读取/解析 JSON 失败 ({path}): {e}")
        return None, False


def _atomic_write_json(path, data):
    """原子写: 先写临时文件再替换, 防止写到一半崩溃导致文件损坏"""
    tmp_path = path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def ensure_db_index(db_path, log_detail):
    if not CONFIG.get("AUTO_CREATE_DB_INDEX", True):
        return
    try:
        conn = sqlite3.connect(db_path, timeout=60.0)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_etfs_name_date ON "ETFs"(name, date)')
        conn.commit()
        conn.close()
    except Exception as e:
        log_detail(f"提示: 创建索引失败(不影响运行, 仅影响速度): {e}")


def _get_all_etfs(cursor, log_detail):
    cursor.execute('SELECT DISTINCT name FROM "ETFs"')
    all_etfs = [r[0] for r in cursor.fetchall()]
    log_detail(f"从 ETFs 表中获取 {len(all_etfs)} 个 Symbol。")
    return all_etfs


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
    data, ok = _load_json_safe(json_path, log_detail)
    if not ok:
        log_detail("⛔ Panel 文件解析失败, 为防止覆盖其它分组, 本次不写入 Panel。请先修复该文件。")
        return

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
        _atomic_write_json(json_path, data)
        log_detail("Panel 文件更新完成（ETF 分组）。")
    except Exception as e:
        log_detail(f"错误: 写入 Panel JSON 文件失败: {e}")


def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail, base_date_str):
    log_detail(f"\n--- 更新历史记录: '{group_name}' ---")
    if not symbols_to_add:
        log_detail(" - 列表为空，跳过写入。")
        return

    record_date_str = base_date_str

    data, ok = _load_json_safe(file_path, log_detail)
    if not ok:
        log_detail("⛔ History 文件解析失败, 为防止覆盖历史数据, 本次不写入。请先修复该文件。")
        return

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
        _atomic_write_json(file_path, data)
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
        dt = _parse_date(latest_date_str)
        start_date = dt - datetime.timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()

    valid_data = [(r[0], r[1] * r[2]) for r in rows if r[1] is not None and r[2] is not None]
    if not valid_data:
        return False

    is_top_n = _is_top_n(latest_turnover, [v for _, v in valid_data], rank_threshold)

    if is_tracing:
        top_n_data = sorted(valid_data, key=lambda x: x[1], reverse=True)[:rank_threshold]
        log_detail(f"    - 成交额排名检查: 回溯{lookback_months}个月, 共{len(valid_data)}个交易日")
        top_str = ", ".join([f"[{d}]: {v:,.0f}" for d, v in top_n_data])
        log_detail(f"      前{rank_threshold}名: {top_str}")
        log_detail(f"      当前成交额: {latest_turnover:,.0f} -> 在前{rank_threshold}: {is_top_n}")

    return is_top_n


def get_etf_yearly_turnover_top_symbols(db_path, symbols, base_date, log_detail,
                                        lookback_months=12, rank_threshold=3, symbol_to_trace=""):
    """
    对给定的 ETF 列表，逐个判断其"最新成交额(<=基准日)"是否为过去 lookback_months 个月的前 rank_threshold 名。
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

        # 【修复】统一以基准日为上限, 与其它策略口径一致
        cursor.execute(
            'SELECT date, price, volume FROM "ETFs" WHERE name = ? AND date <= ? '
            'ORDER BY date DESC LIMIT 1',
            (symbol, base_date)
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
def process_etf_volume_high(db_path, base_date, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略1 (ETF_Volume_high - ETF放量突破) ==========")

    turnover_lookback_months = CONFIG.get("ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 12)
    turnover_rank_threshold = CONFIG.get("ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)
    max_stale_days = CONFIG.get("ETF_MAX_STALE_DAYS", 15)

    log_detail(f"基准日期: {base_date}")
    try:
        base_dt = _parse_date(base_date)
    except Exception as e:
        log_detail(f"错误: 基准日期解析失败: {e}")
        return []

    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        all_etfs = _get_all_etfs(cursor, log_detail)
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []

    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- 检查 ETF {symbol} ---")

        # 【修复】实盘模式也以基准日为上限, 避免与策略2/3/History 日期错位
        cursor.execute(
            'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? AND date <= ? '
            'ORDER BY date DESC LIMIT 2',
            (symbol, base_date)
        )
        rows = cursor.fetchall()
        if len(rows) < 2 or rows[0][1] is None or rows[0][2] is None or rows[0][3] is None or rows[1][1] is None:
            if is_tracing: log_detail("    x 交易数据不足")
            continue

        latest_date, latest_price, latest_volume, latest_open = rows[0]
        prev_date, prev_price, prev_volume, _ = rows[1]

        # 【修复】停更数据不再反复产生信号
        if _is_stale(latest_date, base_dt, max_stale_days):
            if is_tracing:
                log_detail(f"    x 数据停更: 最新 {latest_date}, 距基准日 {_stale_days(latest_date, base_dt)} 天")
            continue

        latest_turnover = latest_price * latest_volume

        cond_price_up = (latest_price > prev_price)
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


# --- 策略1 附加【新增】: ETF_Volume_high "追" ---
def process_etf_volume_high_chase(db_path, base_date, history_json_path, exclude_symbols,
                                  symbol_to_trace, log_detail):
    """
    规则：
      1) T 日收盘价 < T-1 收盘价 (今日下跌)
      2) T 日之前的 N 个交易日内 (默认15, 不含T日) 出现过原始 ETF_Volume_high 信号 (不带"追")
         信号来源 (可配置, 默认取并集):
           ① DB 重算: 按策略1原规则 (上涨 + 12个月成交额前3) 逐日重算
           ② History: Earning_History.json -> ETF_Volume_high 中不带"追"的记录
              (日期映射到 <= 该日期的最近交易日, 兼容周末/节假日记录)
      3) T 日收盘价 <= 任一信号日收盘价 × (1 - 12%)
    返回 (results, detail_map)
    """
    lookback_td = CONFIG.get("ETF_COND_HIGH_CHASE_LOOKBACK_TRADING_DAYS", 15)
    drop_threshold = CONFIG.get("ETF_COND_HIGH_CHASE_DROP_THRESHOLD", 0.12)
    use_db = CONFIG.get("ETF_COND_HIGH_CHASE_USE_DB_RECALC", True)
    use_hist = CONFIG.get("ETF_COND_HIGH_CHASE_USE_HISTORY", True)
    chase_mark = CONFIG.get("ETF_HIGH_CHASE_MARK", "追")
    t_months = CONFIG.get("ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 12)
    t_rank = CONFIG.get("ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)
    max_stale_days = CONFIG.get("ETF_MAX_STALE_DAYS", 15)

    log_detail(f"\n========== 开始执行 策略1附加 (ETF_Volume_high '{chase_mark}') ==========")
    log_detail(f"参数: 回溯 {lookback_td} 个交易日 | 较信号日跌幅 >= {drop_threshold:.2%} | "
               f"信号源: DB重算={use_db}, History={use_hist}")
    log_detail(f"基准日期: {base_date}")

    try:
        base_dt = _parse_date(base_date)
    except Exception as e:
        log_detail(f"错误: 基准日期解析失败: {e}")
        return [], {}

    exclude_symbols = set(exclude_symbols or [])

    # ---- 构建 History 索引: symbol -> {date_str} (仅不带"追"的原始信号) ----
    hist_index = {}
    if use_hist:
        data, ok = _load_json_safe(history_json_path, log_detail)
        if ok and data:
            coarse_days = lookback_td * 4 + 30   # 粗过滤, 精确窗口按交易日再判定
            for date_str, syms in (data.get("ETF_Volume_high", {}) or {}).items():
                try:
                    hd = _parse_date(date_str)
                except Exception:
                    continue
                if hd >= base_dt or (base_dt - hd).days > coarse_days:
                    continue
                for raw in syms or []:
                    sym, suffix = _split_hist_symbol(raw)
                    if not sym or chase_mark in suffix:
                        continue   # 带"追"的不作为触发源
                    hist_index.setdefault(sym, set()).add(date_str)
        log_detail(f"History 中近期原始 high 记录涉及 ETF 数: {len(hist_index)}")

    if not use_db and not hist_index:
        log_detail("无可用信号源, 跳过。")
        return [], {}

    # 数据起点: 覆盖 [最早信号日 - 成交额回溯期], 额外留 120 天缓冲给 15 个交易日+节假日
    data_start_str = (base_dt - datetime.timedelta(days=t_months * 30 + 120)).strftime("%Y-%m-%d")

    results, detail_map = [], {}
    stat = {"checked": 0, "stale": 0, "not_down": 0, "no_signal": 0, "drop_not_enough": 0, "hit": 0}

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    try:
        all_etfs = _get_all_etfs(cursor, log_detail)
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return [], {}

    for symbol in all_etfs:
        if symbol in exclude_symbols:
            continue
        if not use_db and symbol not in hist_index:
            continue

        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- [{chase_mark}规则] 检查 ETF {symbol} ---")
        stat["checked"] += 1

        # Step1: 先做轻量的 "今日下跌" 判断, 不满足直接跳过 (避免拉一年数据)
        cursor.execute(
            'SELECT date, price FROM "ETFs" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2',
            (symbol, base_date)
        )
        last2 = cursor.fetchall()
        if len(last2) < 2 or last2[0][1] is None or last2[1][1] is None:
            if is_tracing: log_detail("    x 无当前或前一日价格数据")
            continue

        latest_date, latest_price = last2[0]
        prev_date, prev_price = last2[1]

        if _is_stale(latest_date, base_dt, max_stale_days):
            stat["stale"] += 1
            if is_tracing:
                log_detail(f"    x 数据停更: 最新 {latest_date}, 距基准日 {_stale_days(latest_date, base_dt)} 天")
            continue

        if not (latest_price < prev_price):
            stat["not_down"] += 1
            if is_tracing: log_detail(f"    x T日未下跌 ({latest_price:.4f} >= {prev_price:.4f})")
            continue
        if is_tracing:
            log_detail(f"    - T日下跌: [{prev_date}] {prev_price:.4f} -> [{latest_date}] {latest_price:.4f}")

        # Step2: 拉取一次完整数据, 在内存中完成信号重算
        cursor.execute(
            'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? AND date >= ? AND date <= ? '
            'ORDER BY date ASC',
            (symbol, data_start_str, latest_date)
        )
        rows = cursor.fetchall()
        if not rows or rows[-1][0] != latest_date:
            if is_tracing: log_detail("    x 数据异常, 跳过")
            continue

        dates = [r[0] for r in rows]
        t_idx = len(rows) - 1
        win_start = max(0, t_idx - lookback_td)
        if is_tracing:
            log_detail(f"    - 回溯窗口: [{dates[win_start]} ~ {dates[t_idx - 1] if t_idx >= 1 else '-'}] "
                       f"共 {t_idx - win_start} 个交易日")

        signals = {}  # idx -> 来源描述

        # 信号源① DB 重算 (与策略1口径完全一致)
        if use_db:
            to_dates, to_vals = [], []
            for d, p, v, _o in rows:
                if p is not None and v is not None:
                    to_dates.append(d)
                    to_vals.append(p * v)

            for i in range(max(1, win_start), t_idx):
                d, p, v, o = rows[i]
                pp = rows[i - 1][1]
                if p is None or v is None or o is None or pp is None:
                    continue
                if not (p > pp):
                    continue
                try:
                    s = (_parse_date(d) - datetime.timedelta(days=t_months * 30)).strftime("%Y-%m-%d")
                except Exception:
                    continue
                lo = bisect.bisect_left(to_dates, s)
                hi = bisect.bisect_right(to_dates, d)
                if _is_top_n(p * v, to_vals[lo:hi], t_rank):
                    signals[i] = "DB重算"

        # 信号源② History
        if use_hist and symbol in hist_index:
            for hd in sorted(hist_index[symbol]):
                k = bisect.bisect_right(dates, hd) - 1   # 映射到 <= hd 的最近交易日
                if win_start <= k < t_idx:
                    signals[k] = "DB重算+History" if k in signals else "History"
                elif is_tracing:
                    log_detail(f"    - History 记录 {hd} 不在窗口内 (或映射到T日自身), 忽略")

        if not signals:
            stat["no_signal"] += 1
            if is_tracing: log_detail(f"    x 近 {lookback_td} 个交易日内无原始 high 信号")
            continue

        best = None
        for i in sorted(signals):
            sig_date, sig_price = rows[i][0], rows[i][1]
            if sig_price is None or sig_price <= 0:
                continue
            drop_pct = 1 - latest_price / sig_price
            ok = latest_price <= sig_price * (1 - drop_threshold)
            if is_tracing:
                log_detail(f"    - 信号日 [{sig_date}] ({signals[i]}, {t_idx - i}个交易日前) 收盘 {sig_price:.4f} "
                           f"-> 今日 {latest_price:.4f}, 跌幅 {drop_pct:.2%} = {ok}")
            if ok and (best is None or drop_pct > best["drop_pct"]):
                best = {
                    "signal_date": sig_date,
                    "signal_price": sig_price,
                    "signal_source": signals[i],
                    "days_ago": t_idx - i,
                    "latest_date": latest_date,
                    "latest_price": latest_price,
                    "drop_pct": drop_pct,
                }

        if best is None:
            stat["drop_not_enough"] += 1
            continue

        results.append(symbol)
        detail_map[symbol] = best
        stat["hit"] += 1
        if is_tracing:
            log_detail(f"    ✅ [选中] 今日下跌 + 较 [{best['signal_date']}] 下跌 {best['drop_pct']:.2%} "
                       f">= {drop_threshold:.2%} -> 标记 '{chase_mark}'")

    conn.close()
    results = sorted(set(results))

    log_detail(f"\n--- '{chase_mark}'规则 统计 ---")
    log_detail(f"  检查: {stat['checked']} | 停更: {stat['stale']} | T日未跌: {stat['not_down']} | "
               f"无信号: {stat['no_signal']} | 跌幅不足: {stat['drop_not_enough']} | ✅ 命中: {stat['hit']}")
    for sym in sorted(results, key=lambda s: detail_map[s]["drop_pct"], reverse=True):
        d = detail_map[sym]
        log_detail(f"  {sym:<8} 跌 {d['drop_pct']:>7.2%} | 信号日 [{d['signal_date']}] {d['signal_price']:.4f} "
                   f"({d['signal_source']}, {d['days_ago']}日前) -> [{d['latest_date']}] {d['latest_price']:.4f}")
    log_detail(f"\n'{chase_mark}'规则筛选完成，共命中 {len(results)} 个 ETF: {results}")
    return results, detail_map


# --- 策略2: ETF_Volume_low (ETF触底放量) ---
def process_etf_volume_low(db_path, base_date, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略2 (ETF_Volume_low - ETF触底放量) ==========")

    price_lookback_months = CONFIG.get("ETF_COND_LOW_PRICE_LOOKBACK_MONTHS", 6)
    drop_threshold = CONFIG.get("ETF_COND_LOW_DROP_THRESHOLD", 0.11)
    turnover_lookback_months = CONFIG.get("ETF_COND_LOW_TURNOVER_MONTHS", 3)
    turnover_rank_threshold = CONFIG.get("ETF_COND_LOW_TURNOVER_RANK_THRESHOLD", 2)
    max_stale_days = CONFIG.get("ETF_MAX_STALE_DAYS", 15)

    try:
        base_dt = _parse_date(base_date)
        start_date_price_str = (base_dt - datetime.timedelta(days=price_lookback_months * 30)).strftime("%Y-%m-%d")
    except Exception as e:
        log_detail(f"错误: 基准日期解析失败: {e}")
        return []

    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        all_etfs = _get_all_etfs(cursor, log_detail)
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []

    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- 检查 ETF {symbol} ---")

        query = 'SELECT date, price, volume FROM "ETFs" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date DESC'
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

        if _is_stale(latest_date, base_dt, max_stale_days):
            if is_tracing:
                log_detail(f"    x 数据停更: 最新 {latest_date}, 距基准日 {_stale_days(latest_date, base_dt)} 天")
            continue

        latest_turnover = latest_price * latest_volume
        prev_turnover = prev_price * prev_volume

        cond_latest_down = latest_price < prev_price
        if not cond_latest_down:
            if is_tracing: log_detail(f"    x T日未下跌 ({latest_price:.2f} >= {prev_price:.2f})")
            continue

        valid_prices = [r[1] for r in rows if r[1] is not None]
        max_price = max(valid_prices)

        cond_price_drop = latest_price <= max_price * (1 - drop_threshold)

        if is_tracing:
            drop_pct = (1 - latest_price / max_price) if max_price > 0 else 0
            log_detail(f"    - 条件A (跌幅>{drop_threshold*100}%): 最高 {max_price:.2f}, 当前 {latest_price:.2f}, 跌幅 {drop_pct:.2%} = {cond_price_drop}")

        if not cond_price_drop:
            continue

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


# --- 策略3: ETF 深度回撤 (半年最高收盘价回撤 >= 35%) ---
def process_etf_deep_drop(db_path, base_date, symbol_to_trace, log_detail):
    """
    任何 ETF，在最近 N 个月(默认6个月)内，
    从区间内最高收盘价(price) 回撤到 最新收盘价 的跌幅 >= 阈值(默认35%)，
    即命中，并入 ETF_Volume_low 分组（备注追加 '乙' 标记）。
    """
    lookback_months = CONFIG.get("ETF_COND_DEEP_DROP_LOOKBACK_MONTHS", 6)
    drop_threshold = CONFIG.get("ETF_COND_DEEP_DROP_THRESHOLD", 0.35)
    min_days = CONFIG.get("ETF_COND_DEEP_DROP_MIN_DAYS", 30)
    require_down = CONFIG.get("ETF_COND_DEEP_DROP_REQUIRE_DOWN", False)
    max_stale_days = CONFIG.get("ETF_COND_DEEP_DROP_MAX_STALE_DAYS", 15)

    log_detail(f"\n========== 开始执行 策略3 (ETF_Deep_Drop - 半年深度回撤) ==========")
    log_detail(f"参数: 回溯 {lookback_months} 个月 | 回撤阈值 >= {drop_threshold:.2%} | "
               f"最少交易日 {min_days} | 要求T日下跌={require_down} | 允许数据滞后 {max_stale_days} 天")
    log_detail(f"基准日期: {base_date}")

    try:
        base_dt = _parse_date(base_date)
    except Exception as e:
        log_detail(f"错误: 基准日期解析失败: {e}")
        return [], {}

    start_dt = base_dt - datetime.timedelta(days=lookback_months * 30)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    log_detail(f"回溯区间: [{start_date_str} ~ {base_date}]")

    results = []
    detail_map = {}
    stat = {"total": 0, "no_data": 0, "not_enough_days": 0, "stale": 0,
            "bad_max": 0, "drop_not_enough": 0, "blocked_by_down": 0, "hit": 0}

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        all_etfs = _get_all_etfs(cursor, log_detail)
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

        if _is_stale(latest_date, base_dt, max_stale_days):
            stat["stale"] += 1
            if is_tracing:
                log_detail(f"    x 数据滞后 {_stale_days(latest_date, base_dt)} 天 (最新 {latest_date}), 超过 {max_stale_days} 天, 跳过")
            continue

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
            "max_date": max_date, "max_price": max_price,
            "latest_date": latest_date, "latest_price": latest_price,
            "drop_pct": drop_pct, "days": len(valid_rows),
        }
        if is_tracing:
            log_detail(f"    ✅ [选中] 半年回撤 {drop_pct:.2%} >= {drop_threshold:.2%}")

    conn.close()
    results = sorted(list(set(results)))

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


def process_etf_volume_low_continuation(db_path, base_date, history_json_path, symbol_to_trace, log_detail):
    """
    策略2补充规则（延续信号）：
    检查 ETF 在"基准日期前7天内"是否曾命中 ETF_Volume_low。
    若曾命中，且当前收盘价 < 前一日收盘价，同时当前收盘价 < 任一历史命中日的收盘价，则加入结果。
    """
    log_detail("\n========== 开始执行 策略2补充规则 (ETF_Volume_low 延续) ==========")
    log_detail(f"基准日期: {base_date}")
    max_stale_days = CONFIG.get("ETF_MAX_STALE_DAYS", 15)

    history_data, ok = _load_json_safe(history_json_path, log_detail)
    if not ok or not history_data:
        log_detail("无法加载 History JSON 或为空，跳过。")
        return []

    low_history = history_data.get("ETF_Volume_low", {})
    if not low_history:
        log_detail("ETF_Volume_low 历史记录为空，跳过。")
        return []

    try:
        base_dt = _parse_date(base_date)
        seven_days_ago = base_dt - datetime.timedelta(days=7)
    except Exception as e:
        log_detail(f"日期解析失败: {e}")
        return []

    symbol_history_dates = {}
    for date_str, symbols in low_history.items():
        try:
            hist_dt = _parse_date(date_str)
        except Exception:
            continue
        if hist_dt >= base_dt or hist_dt < seven_days_ago:
            continue
        for raw_sym in symbols:
            sym = _clean_hist_symbol(raw_sym)
            if sym:
                symbol_history_dates.setdefault(sym, []).append(date_str)

    log_detail(f"7天窗口内涉及到的历史 ETF 数: {len(symbol_history_dates)}")

    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    for symbol in sorted(symbol_history_dates):
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- [延续规则] 检查 ETF {symbol} ---")
            log_detail(f"    7天内历史命中日期: {symbol_history_dates[symbol]}")

        cursor.execute(
            'SELECT date, price FROM "ETFs" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2',
            (symbol, base_date)
        )
        rows = cursor.fetchall()
        if len(rows) < 2 or rows[0][1] is None or rows[1][1] is None:
            if is_tracing: log_detail("    x 无当前或前一日价格数据")
            continue

        latest_date, latest_price = rows[0]
        prev_date, prev_price = rows[1]

        if _is_stale(latest_date, base_dt, max_stale_days):
            if is_tracing: log_detail(f"    x 数据停更: 最新 {latest_date}")
            continue

        if latest_price >= prev_price:
            if is_tracing: log_detail(f"    x T日未下跌 ({latest_price:.4f} >= {prev_price:.4f})")
            continue

        hit = False
        for hist_date in sorted(symbol_history_dates[symbol]):
            # 【修复】History 日期可能是周末/节假日, 映射到 <= 该日的最近交易日
            cursor.execute(
                'SELECT date, price FROM "ETFs" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1',
                (symbol, hist_date)
            )
            r = cursor.fetchone()
            if not r or r[1] is None:
                if is_tracing: log_detail(f"    - 历史日期 {hist_date} 无价格数据")
                continue
            real_date, hist_price = r
            if real_date >= latest_date:
                continue  # 映射到T日自身, 不能自己参考自己

            if latest_price < hist_price:
                if is_tracing:
                    log_detail(f"    ✅ [{hist_date}→{real_date}] 历史价 {hist_price:.4f} > "
                               f"当前 {latest_price:.4f}，且今日已下跌，命中")
                hit = True
                break
            elif is_tracing:
                log_detail(f"    - [{hist_date}→{real_date}] 历史价 {hist_price:.4f} <= 当前 {latest_price:.4f}")

        if hit:
            results.append(symbol)

    conn.close()
    results = sorted(list(set(results)))
    log_detail(f"\n策略2补充规则筛选完成，共命中 {len(results)} 个 ETF: {results}")
    return results


# --- 4. 主执行流程 ---
def run_etf_volume_logic(log_detail):
    log_detail("ETF_Volume 多策略程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    base_date_str = get_base_date(TARGET_DATE)
    log_detail(f"统一基准日期: {base_date_str}")

    if TARGET_DATE:
        log_detail(f"\n⚠️ 回测模式, 目标日期: {TARGET_DATE}，不会写入 Panel 和 History。")

    ensure_db_index(DB_FILE, log_detail)

    tag_blacklist = load_tag_settings(TAGS_SETTING_JSON_FILE)
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    deep_mark = CONFIG.get("ETF_DEEP_DROP_MARK", "乙")
    chase_mark = CONFIG.get("ETF_HIGH_CHASE_MARK", "追")

    # ===== 策略1 =====
    final_etf_high_base = process_etf_volume_high(DB_FILE, base_date_str, SYMBOL_TO_TRACE, log_detail)

    # ===== 策略1 附加: 追 =====
    final_etf_high_chase, chase_detail = process_etf_volume_high_chase(
        DB_FILE, base_date_str, EARNING_HISTORY_JSON_FILE,
        final_etf_high_base, SYMBOL_TO_TRACE, log_detail
    )
    chase_set = set(final_etf_high_chase) - set(final_etf_high_base)
    final_etf_high = sorted(set(final_etf_high_base) | chase_set)

    log_detail(f"\n========== ETF_Volume_high 合并结果 ==========")
    log_detail(f"  原策略1: {len(final_etf_high_base)} 个 | '{chase_mark}': {len(chase_set)} 个 "
               f"=> 合并后 {len(final_etf_high)} 个")

    # ===== 策略2 + 延续 + 策略3 =====
    final_etf_low = process_etf_volume_low(DB_FILE, base_date_str, SYMBOL_TO_TRACE, log_detail)
    final_etf_low_cont = process_etf_volume_low_continuation(
        DB_FILE, base_date_str, EARNING_HISTORY_JSON_FILE, SYMBOL_TO_TRACE, log_detail
    )
    final_etf_deep_drop, deep_drop_detail = process_etf_deep_drop(
        DB_FILE, base_date_str, SYMBOL_TO_TRACE, log_detail
    )
    deep_drop_set = set(final_etf_deep_drop)

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

    etf_low_jia_set = get_etf_yearly_turnover_top_symbols(
        DB_FILE, final_etf_low, base_date_str, log_detail,
        CONFIG.get("ETF_COND_LOW_YEARLY_TURNOVER_LOOKBACK_MONTHS", 12),
        CONFIG.get("ETF_COND_LOW_YEARLY_TURNOVER_RANK_THRESHOLD", 3),
        SYMBOL_TO_TRACE
    )

    # 构建备注（黑 / 甲 / 乙 / 追）
    def build_notes(symbols, jia_set=None, deep_set=None, chase=None):
        jia_set = jia_set or set()
        deep_set = deep_set or set()
        chase = chase or set()
        note_map = {}
        for sym in symbols:
            suffix = ""
            if set(symbol_to_tags_map.get(sym, [])).intersection(tag_blacklist):
                suffix += "黑"
            if sym in jia_set:
                suffix += "甲"
            if sym in deep_set:
                suffix += deep_mark
            if sym in chase:
                suffix += chase_mark
            note_map[sym] = f"{sym}{suffix}"
        return note_map

    etf_high_notes = build_notes(final_etf_high, chase=chase_set)
    etf_low_notes = build_notes(final_etf_low, etf_low_jia_set, deep_drop_set)

    if SYMBOL_TO_TRACE:
        log_detail(f"\n{'='*60}")
        log_detail(f"📌 [{SYMBOL_TO_TRACE}] 命中汇总")
        log_detail(f"  策略1 ETF_Volume_high:      {'✅' if SYMBOL_TO_TRACE in final_etf_high_base else '❌'}")
        log_detail(f"  策略1附加 '{chase_mark}':           {'✅' if SYMBOL_TO_TRACE in chase_set else '❌'}")
        if SYMBOL_TO_TRACE in chase_detail:
            c = chase_detail[SYMBOL_TO_TRACE]
            log_detail(f"        └─ 信号日[{c['signal_date']}] {c['signal_price']:.4f} ({c['signal_source']}) -> "
                       f"[{c['latest_date']}] {c['latest_price']:.4f}, 跌 {c['drop_pct']:.2%}")
        log_detail(f"  策略2 ETF_Volume_low:       {'✅' if SYMBOL_TO_TRACE in final_etf_low else '❌'}")
        log_detail(f"  策略3 半年深跌(标'{deep_mark}'):    {'✅' if SYMBOL_TO_TRACE in deep_drop_set else '❌'}")
        if SYMBOL_TO_TRACE in deep_drop_detail:
            d = deep_drop_detail[SYMBOL_TO_TRACE]
            log_detail(f"        └─ 高点[{d['max_date']}] {d['max_price']:.4f} -> "
                       f"最新[{d['latest_date']}] {d['latest_price']:.4f}, 回撤 {d['drop_pct']:.2%}")
        log_detail(f"  年度成交额前三(甲):         {'✅' if SYMBOL_TO_TRACE in etf_low_jia_set else '❌'}")
        log_detail(f"  high 备注: {etf_high_notes.get(SYMBOL_TO_TRACE, '(未命中)')}")
        log_detail(f"  low  备注: {etf_low_notes.get(SYMBOL_TO_TRACE, '(未命中)')}")
        log_detail(f"{'='*60}")

    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 回测模式 (Date: {TARGET_DATE}) - 不写入任何文件")
        log_detail(f"📊 ETF_Volume_high 命中: {len(final_etf_high)} 个")
        log_detail(f"   -> {final_etf_high}")
        log_detail(f"📊 其中标'{chase_mark}': {len(chase_set)} 个 -> {sorted(chase_set)}")
        log_detail(f"📊 ETF_Volume_low  命中: {len(final_etf_low)} 个")
        log_detail(f"   -> {final_etf_low}")
        log_detail(f"📊 其中标'甲'(年度前三): {len(etf_low_jia_set)} 个 -> {sorted(etf_low_jia_set)}")
        log_detail(f"📊 其中标'{deep_mark}'(半年深跌>= "
                   f"{CONFIG.get('ETF_COND_DEEP_DROP_THRESHOLD', 0.35):.0%}): "
                   f"{len(deep_drop_set)} 个 -> {sorted(deep_drop_set)}")
        log_detail(f"📊 Panel high 备注预览: {sorted(etf_high_notes.values())}")
        log_detail(f"📊 Panel low  备注预览: {sorted(etf_low_notes.values())}")
        log_detail("="*60)
        return

    log_detail(f"\n正在写入 Panel 文件...")
    update_panel_etf(PANEL_JSON_FILE, final_etf_high, etf_high_notes,
                     final_etf_low, etf_low_notes, log_detail)

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