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
    "ETF_COND_LOW_PRICE_LOOKBACK_MONTHS": 5,       # 最高点回溯月份
    "ETF_COND_LOW_DROP_THRESHOLD": 0.06,           # 距最高点跌幅 (原逻辑的常规跌幅)
    "ETF_COND_LOW_DEEP_DROP_THRESHOLD": 0.195,      # 【新增】距最高点深度跌幅 (无视成交额直接选出)
    "ETF_COND_LOW_TURNOVER_MONTHS": 2,             # 成交额回溯月份
    "ETF_COND_LOW_TURNOVER_RANK_THRESHOLD": 3,     # 成交额排名前 N 名
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
    deep_drop_threshold = CONFIG.get("ETF_COND_LOW_DEEP_DROP_THRESHOLD", 0.20) # 新增：深度跌幅阈值
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
        
        # 计算常规跌幅和深度跌幅
        cond_price_drop = latest_price <= max_price * (1 - drop_threshold)
        cond_deep_drop = latest_price <= max_price * (1 - deep_drop_threshold)

        if is_tracing:
            drop_pct = (1 - latest_price / max_price) if max_price > 0 else 0
            log_detail(f"    - 条件A (跌幅>{drop_threshold*100}%): 最高 {max_price:.2f}, 当前 {latest_price:.2f}, 跌幅 {drop_pct:.2%} = {cond_price_drop}")
            log_detail(f"    - 深度跌幅条件 (>{deep_drop_threshold*100}%): {cond_deep_drop}")

        # 如果连常规跌幅都没达到，直接跳过
        if not cond_price_drop:
            continue

        # 【新增逻辑】如果达到深度跌幅（20%），直接选中，无视成交额要求
        if cond_deep_drop:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中] 深度跌幅达标 (跌幅>={deep_drop_threshold*100}%)，无视成交额")
            continue

        # 如果没有达到深度跌幅，但达到了常规跌幅，则继续检查成交额条件
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


def process_etf_volume_low_continuation(db_path, target_date_override,
                                         history_json_path, symbol_to_trace, log_detail):
    """
    策略2补充规则（延续信号）：
    针对每个ETF，扫描 Earning_History.json 的 ETF_Volume_low 分组，
    检查在"基准日期前一个月内"是否曾经命中过。
    若曾命中，且当前收盘价 < 任一历史命中日的收盘价，则加入结果。
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

    # --- 计算一个月窗口 ---
    try:
        base_dt = datetime.datetime.strptime(base_date, "%Y-%m-%d")
        one_month_ago = base_dt - datetime.timedelta(days=30)
    except Exception as e:
        log_detail(f"日期解析失败: {e}")
        return []

    # --- 构建 symbol -> [历史命中日期] 的索引 ---
    # 范围: [base_date - 30天, base_date)，不含 base_date 自身（避免自己参考自己）
    symbol_history_dates = {}
    for date_str, symbols in low_history.items():
        try:
            hist_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            continue
        if hist_dt >= base_dt:      # 不考虑未来日期和当日
            continue
        if hist_dt < one_month_ago: # 超出一个月窗口
            continue
        for raw_sym in symbols:
            sym = _clean_hist_symbol(raw_sym)
            if sym:
                symbol_history_dates.setdefault(sym, []).append(date_str)

    log_detail(f"一个月窗口内涉及到的历史 ETF 数: {len(symbol_history_dates)}")

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
            log_detail(f"    一月内历史命中日期: {symbol_history_dates[symbol]}")

        # 当前最新收盘价
        cursor.execute(
            f'SELECT date, price FROM "ETFs" WHERE name = ? AND date <= ? '
            f'ORDER BY date DESC LIMIT 1',
            (symbol, base_date)
        )
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None:
            if is_tracing: log_detail("    x 无当前价格数据")
            continue
        latest_date, latest_price = latest_row

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
                               f"当前 {latest_price:.4f}，命中")
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
    """清洗 History 中的符号，去掉末尾的中文标记（如"黑"）"""
    return re.sub(r'[\u4e00-\u9fff]+$', '', s).strip()

# --- 4. 主执行流程 ---
def run_etf_volume_logic(log_detail):
    log_detail("ETF_Volume 双策略程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    base_date_str = TARGET_DATE if TARGET_DATE else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    if TARGET_DATE:
        log_detail(f"\n⚠️ 回测模式, 目标日期: {TARGET_DATE}，不会写入 Panel 和 History。")

    tag_blacklist = load_tag_settings(TAGS_SETTING_JSON_FILE)
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    # 执行策略
    final_etf_high = process_etf_volume_high(DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail)
    final_etf_low = process_etf_volume_low(DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail)

    # ===== 新增：策略2的延续规则 =====
    final_etf_low_cont = process_etf_volume_low_continuation(
        DB_FILE, TARGET_DATE, EARNING_HISTORY_JSON_FILE,
        SYMBOL_TO_TRACE, log_detail
    )
    # 合并去重
    before_merge = len(final_etf_low)
    final_etf_low = sorted(list(set(final_etf_low) | set(final_etf_low_cont)))
    log_detail(f"\n策略2合并后: 原策略 {before_merge} 个 + 延续规则 "
               f"{len(final_etf_low_cont)} 个 => 去重后 {len(final_etf_low)} 个")

    # 构建备注（含黑名单标记）
    def build_notes(symbols):
        note_map = {}
        for sym in symbols:
            suffix = ""
            s_tags = set(symbol_to_tags_map.get(sym, []))
            if s_tags.intersection(tag_blacklist):
                suffix += "黑"
            note_map[sym] = f"{sym}{suffix}"
        return note_map

    etf_high_notes = build_notes(final_etf_high)
    etf_low_notes = build_notes(final_etf_low)

    # 追踪汇总
    if SYMBOL_TO_TRACE:
        log_detail(f"\n{'='*60}")
        log_detail(f"📌 [{SYMBOL_TO_TRACE}] 命中汇总")
        log_detail(f"  策略1 ETF_Volume_high: {'✅' if SYMBOL_TO_TRACE in final_etf_high else '❌'}")
        log_detail(f"  策略2 ETF_Volume_low:  {'✅' if SYMBOL_TO_TRACE in final_etf_low else '❌'}")
        log_detail(f"{'='*60}")

    # 回测模式拦截
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 回测模式 (Date: {TARGET_DATE})")
        log_detail(f"📊 ETF_Volume_high 命中: {len(final_etf_high)} 个")
        log_detail(f"📊 ETF_Volume_low  命中: {len(final_etf_low)} 个")
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