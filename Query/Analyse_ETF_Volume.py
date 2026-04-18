import json
import sqlite3
import os
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

SYMBOL_TO_TRACE = "" 
TARGET_DATE = "" 

LOG_FILE_PATH = os.path.join(BASE_PATH, "Downloads", "ETF_Volume_trace_log.txt")

PATHS = {
    "config_dir": os.path.join(BASE_CODING_DIR, 'Financial_System', 'Modules'),
    "db_dir": os.path.join(BASE_CODING_DIR, 'Database'),
    "panel_json": lambda config_dir: os.path.join(config_dir, 'Sectors_panel.json'),
    "earnings_history_json": lambda config_dir: os.path.join(config_dir, 'Earning_History.json'),
    "db_file": lambda db_dir: os.path.join(db_dir, 'Finance.db'),
}

CONFIG_DIR = PATHS["config_dir"]
DB_DIR = PATHS["db_dir"]
DB_FILE = PATHS["db_file"](DB_DIR)
PANEL_JSON_FILE = PATHS["panel_json"](CONFIG_DIR)
EARNING_HISTORY_JSON_FILE = PATHS["earnings_history_json"](CONFIG_DIR)

CONFIG = {
    # ========== 策略4 (ETF_Volume_high 放量突破) 参数 ==========
    "ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS": 12,  # 成交额回溯12个月
    "ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD": 3,    # 成交额排名前3名

    # ========== 策略5 (ETF_Volume_low 触底放量) 参数 ==========
    "ETF_COND_LOW_PRICE_LOOKBACK_MONTHS": 5,       # 最高点回溯5个月
    "ETF_COND_LOW_DROP_THRESHOLD": 0.06,           # 距最高点跌幅
    "ETF_COND_LOW_TURNOVER_MONTHS": 2,             # 成交额回溯2个月
    "ETF_COND_LOW_TURNOVER_RANK_THRESHOLD": 3,     # 成交额排名前3名
}

# --- 2. 辅助与文件操作模块 ---
def update_etf_panel(json_path, etf_vol_high_list, etf_vol_high_notes, etf_vol_low_list, etf_vol_low_notes, log_detail):
    """专门用于更新 ETF 策略的 Panel 文件"""
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

    data['ETF_Volume_high'] = build_group_dict(etf_vol_high_list, etf_vol_high_notes)
    data['ETF_Volume_high_backup'] = build_group_dict(etf_vol_high_list, etf_vol_high_notes)
    
    data['ETF_Volume_low'] = build_group_dict(etf_vol_low_list, etf_vol_low_notes)
    data['ETF_Volume_low_backup'] = build_group_dict(etf_vol_low_list, etf_vol_low_notes)

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail("ETF Panel 文件更新完成。")
    except Exception as e:
        log_detail(f"错误: 写入 Panel JSON 文件失败: {e}")

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail, base_date_str):
    log_detail(f"\n--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    if not symbols_to_add:
        log_detail(f" - 列表为空，跳过写入历史记录。")
        return
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(base_date_str, [])
    updated_symbols = sorted(list(set(existing_symbols) | set(symbols_to_add)))
    
    if not updated_symbols: return
    
    data[group_name][base_date_str] = updated_symbols
    num_added = len(updated_symbols) - len(existing_symbols)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail(f"成功更新历史记录。日期: {base_date_str}, 分组: '{group_name}'. 本次新增 {num_added} 个。")
    except Exception as e:
        log_detail(f"错误: 写入历史记录文件失败: {e}")

def check_turnover_rank(cursor, sector_name, symbol, latest_date_str, latest_turnover, lookback_months, rank_threshold, log_detail, is_tracing):
    try:
        dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - datetime.timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()
    
    valid_data = [(r[0], r[1] * r[2]) for r in rows if r[1] is not None and r[2] is not None]
    if not valid_data: return False
    
    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    top_n_turnovers = [item[1] for item in sorted_data[:rank_threshold]]
    
    is_top_n = False
    if latest_turnover in top_n_turnovers:
        is_top_n = True
    elif len(top_n_turnovers) >= rank_threshold and latest_turnover >= top_n_turnovers[-1]:
        is_top_n = True
    
    if is_tracing:
        log_detail(f"    - 条件 (成交额排名): 回溯{lookback_months}个月，当前成交额: {latest_turnover:,.0f} -> 在前{rank_threshold}名: {is_top_n}")
    
    return is_top_n

# --- 3. 核心逻辑模块 ---
def process_etf_volume_high(db_path, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略4 (ETF_Volume_high - ETF放量突破) ==========")
    turnover_lookback_months = CONFIG.get("ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 12)
    turnover_rank_threshold = CONFIG.get("ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
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
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- 正在检查 ETF {symbol} (策略4) ---")
            
        if target_date_override:
            query = f'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, target_date_override))
        else:
            query = f'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol,))
        
        rows = cursor.fetchall()
        if len(rows) < 2 or None in [rows[0][1], rows[0][2], rows[0][3], rows[1][1]]: continue
            
        latest_date, latest_price, latest_volume, latest_open = rows[0]
        prev_date, prev_price, prev_volume, _ = rows[1]
        latest_turnover = latest_price * latest_volume
        
        cond_price_up = (latest_price > prev_price) and (latest_price > latest_open)
        if not cond_price_up: continue
            
        cond_turnover_12m_top = check_turnover_rank(
            cursor, "ETFs", symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
        )
        
        if cond_price_up and cond_turnover_12m_top:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中-ETF类] 价格上涨 + 12个月成交额Top{turnover_rank_threshold}")
            
    conn.close()
    return sorted(list(set(results)))

def process_etf_volume_low(db_path, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略5 (ETF_Volume_low - ETF触底放量) ==========")
    price_lookback_months = CONFIG.get("ETF_COND_LOW_PRICE_LOOKBACK_MONTHS", 5)
    drop_threshold = CONFIG.get("ETF_COND_LOW_DROP_THRESHOLD", 0.06)
    turnover_lookback_months = CONFIG.get("ETF_COND_LOW_TURNOVER_MONTHS", 2)
    turnover_rank_threshold = CONFIG.get("ETF_COND_LOW_TURNOVER_RANK_THRESHOLD", 3) 
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
    except Exception as e:
        conn.close()
        return []
        
    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- 正在检查 ETF {symbol} (策略5) ---")
            
        try:
            dt = datetime.datetime.strptime(base_date, "%Y-%m-%d")
            start_date_price = dt - datetime.timedelta(days=price_lookback_months * 30)
            start_date_price_str = start_date_price.strftime("%Y-%m-%d")
        except Exception: continue
            
        query = f'SELECT date, price, volume FROM "ETFs" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date DESC'
        cursor.execute(query, (symbol, start_date_price_str, base_date))
        rows = cursor.fetchall()
        
        if len(rows) < 3: continue
            
        latest_date, latest_price, latest_volume = rows[0]
        prev_date, prev_price, prev_volume = rows[1]
        prev_prev_date, prev_prev_price, prev_prev_volume = rows[2]
        
        if None in [latest_price, prev_price, prev_prev_price, latest_volume, prev_volume]: continue
            
        latest_turnover = latest_price * latest_volume
        prev_turnover = prev_price * prev_volume
        
        if latest_price >= prev_price: continue

        valid_prices = [r[1] for r in rows if r[1] is not None]
        max_price = max(valid_prices)
        cond_price_drop = latest_price <= max_price * (1 - drop_threshold)
        if not cond_price_drop: continue
            
        cond_latest_turnover_topN = check_turnover_rank(
            cursor, "ETFs", symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
        )
        
        cond_prev_turnover_topN = False
        cond_prev_down = prev_price < prev_prev_price
        if not cond_latest_turnover_topN:
            cond_prev_turnover_topN = check_turnover_rank(
                cursor, "ETFs", symbol, prev_date, prev_turnover,
                turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
            )
            
        cond_turnover_high_and_down = cond_latest_turnover_topN or (cond_prev_turnover_topN and cond_prev_down)
            
        if cond_price_drop and cond_turnover_high_and_down:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中-ETF类] 跌幅达标 + 阶段巨量且下跌")
            
    conn.close()
    return sorted(list(set(results)))

# --- 4. 主执行流程 ---
def run_etf_logic(log_detail):
    log_detail("ETF 策略程序开始运行...")
    base_date_str = TARGET_DATE if TARGET_DATE else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")

    # 执行策略
    final_etf_volume_high = process_etf_volume_high(DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail)
    final_etf_volume_low = process_etf_volume_low(DB_FILE, TARGET_DATE, SYMBOL_TO_TRACE, log_detail)

    # 简单构建 notes (ETF 默认无后缀，直接映射自身)
    etf_vol_high_notes = {sym: sym for sym in final_etf_volume_high}
    etf_vol_low_notes = {sym: sym for sym in final_etf_volume_low}

    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [策略4] ETF_Volume_high 命中: {len(final_etf_volume_high)} 个")
        log_detail(f"📊 [策略5] ETF_Volume_low 命中: {len(final_etf_volume_low)} 个") 
        log_detail("="*60 + "\n")
        return

    log_detail(f"\n正在写入 Panel 文件...")
    update_etf_panel(PANEL_JSON_FILE, final_etf_volume_high, etf_vol_high_notes, final_etf_volume_low, etf_vol_low_notes, log_detail)

    log_detail(f"\n正在更新 History 文件...")
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_high", final_etf_volume_high, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_low", final_etf_volume_low, log_detail, base_date_str) 

    log_detail("程序运行结束。")

def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将写入: {LOG_FILE_PATH}")
        try:
            with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
                def log_detail_file(message):
                    log_file.write(message + '\n')
                    print(message)
                run_etf_logic(log_detail_file)
        except IOError as e:
            print(f"错误：无法打开或写入日志文件 {LOG_FILE_PATH}: {e}")
    else:
        print("追踪模式未启用。日志仅输出到控制台。")
        def log_detail_console(message):
            print(message)
        run_etf_logic(log_detail_console)

if __name__ == '__main__':
    main()