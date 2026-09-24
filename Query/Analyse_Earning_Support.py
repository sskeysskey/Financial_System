import json
import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# ================= 配置区域 =================
SYMBOL_TO_TRACE = ""
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "SRRK"
# TARGET_DATE = "2026-09-18"

MIN_SUPPORT_DAYS = 6
SUPPORT_THRESHOLD_PCT = 2.6

# ========== SupportLevel_Over 顺延继承配置 ==========
ENABLE_OVER_INHERIT = True
INHERIT_SUFFIX = "延"
INHERIT_ALLOW_GAP = True
INHERIT_GAP_MAX_DAYS = 7
MAX_INHERIT_DAYS = 0
INHERIT_IGNORE_EARNING_DAY = False
# 已掉出目标分组、但昨天仍在 Over 链上的 symbol 会被拉回，且【只允许走顺延】
FORCE_KEEP_OVER_CHAIN = True

# ========== 【新增】Pivot 支撑区 (ZigZag 摆动低点 + 横盘底 + 聚类 + 评分) ==========
ENABLE_PIVOT_ZONE = True
# 融合模式: "legacy"=仅旧逻辑  "zone"=仅支撑区  "union"=并集(推荐)  "intersect"=仅二者共振
HYBRID_MODE = "union"
ZONE_LOOKBACK_DAYS = 270          # 支撑区回看自然日（约9个月）
ZONE_MIN_BARS = 40                # 至少多少根K线才做支撑区分析
ZONE_ATR_WINDOW = 60              # 用最近N根的 TR% 中位数估计波动率
ZONE_ZIGZAG_ATR_MULT = 2.0        # ZigZag 阈值 = ATR% × 倍数
ZONE_ZIGZAG_MIN_PCT = 5.0
ZONE_ZIGZAG_MAX_PCT = 15.0
ZONE_EDGE_BARS = 3                # 窗口起点附近且左侧跌幅未知的低点丢弃
ZONE_BASE_SCAN_BARS = 5           # 横盘底：拐点左右扫描根数
ZONE_BASE_ATR_MULT = 0.6          # 横盘底带宽 = max(MIN, ATR%×倍数)
ZONE_BASE_MIN_PCT = 1.5
ZONE_MIN_WIDTH_PCT = 0.5          # 支撑区最小宽度
ZONE_MAX_WIDTH_PCT = 4.0          # 支撑区最大宽度
ZONE_CLUSTER_ATR_MULT = 0.6       # 聚类容差 = max(MIN, ATR%×倍数)
ZONE_CLUSTER_MIN_PCT = 1.5
ZONE_BREAK_ATR_MULT = 0.3         # 有效跌破容差 = clamp(ATR%×倍数, MIN, MAX)
ZONE_BREAK_MIN_PCT = 0.5
ZONE_BREAK_MAX_PCT = 2.0
ZONE_VOL_SPIKE_RATIO = 1.5        # 拐点附近放量倍数（相对前20日均量）
ZONE_DECAY_FULL_DAYS = 90         # 最后触及90天内不衰减，之后线性衰减到0.6
ZONE_MIN_SCORE = 30               # 低于此分的区不参与判定
ZONE_STRONG_SCORE = 60            # 强支撑：可覆盖旧逻辑的 Over / 可中断顺延
ZONE_OVERRIDE_CONFLICT = True     # 旧逻辑 Over 而强支撑区 Close 时，改判为 Close
ZONE_INTERRUPT_INHERIT = True     # 顺延链上的 symbol 落入强支撑区时中断顺延（不作用于强制拉回的）
ZONE_SUFFIX = "枢"                # 仅支撑区命中的后缀
CONFLUENCE_SUFFIX = "共"          # 新旧逻辑共振的后缀

# ========== 文件路径 ==========
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")
SECTORS_PANEL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")

# ========== symbol 边界匹配 ==========
_SYMBOL_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-^=_")

def _item_matches_symbol(item, symbol):
    if not isinstance(item, str) or not symbol or not item.startswith(symbol):
        return False
    if len(item) == len(symbol):
        return True
    return item[len(symbol)] not in _SYMBOL_CHARS


# =====================================================================
# 【新增】Pivot 支撑区算法
# =====================================================================
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _robust_atr_pct(bars, window):
    """TR% 的中位数，抗跳空异常值"""
    trs = []
    for i in range(1, len(bars)):
        pc = bars[i - 1]["c"]
        h, l = bars[i]["h"], bars[i]["l"]
        if not pc or pc <= 0:
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)) / pc * 100)
    if not trs:
        return None
    return _median(trs[-window:])


def _zigzag(closes, thr_pct):
    """基于收盘价的 ZigZag，返回已确认的拐点 [('L'|'H', idx), ...]，最后一段未确认的不返回"""
    n = len(closes)
    if n < 3:
        return []
    thr = thr_pct / 100.0
    trend = 0
    hi_idx = lo_idx = 0
    ext = 0
    pivots = []
    for i in range(1, n):
        c = closes[i]
        if trend == 0:
            if c > closes[hi_idx]:
                hi_idx = i
            if c < closes[lo_idx]:
                lo_idx = i
            if hi_idx > lo_idx and closes[hi_idx] >= closes[lo_idx] * (1 + thr):
                pivots.append(('L', lo_idx)); trend = 1; ext = hi_idx
            elif lo_idx > hi_idx and closes[lo_idx] <= closes[hi_idx] * (1 - thr):
                pivots.append(('H', hi_idx)); trend = -1; ext = lo_idx
        elif trend == 1:
            if c > closes[ext]:
                ext = i
            elif c <= closes[ext] * (1 - thr):
                pivots.append(('H', ext)); trend = -1; ext = i
        else:
            if c < closes[ext]:
                ext = i
            elif c >= closes[ext] * (1 + thr):
                pivots.append(('L', ext)); trend = 1; ext = i
    return pivots


def _detect_pivot_zones(bars, latest_dt):
    info = {"atr_pct": None, "zz_thr": None, "break_tol": None, "pivots": [], "zones": []}
    if len(bars) < ZONE_MIN_BARS:
        return info

    closes = [b["c"] for b in bars]
    n = len(bars)
    atr = _robust_atr_pct(bars, ZONE_ATR_WINDOW) or 3.0
    zz = _clamp(ZONE_ZIGZAG_ATR_MULT * atr, ZONE_ZIGZAG_MIN_PCT, ZONE_ZIGZAG_MAX_PCT)
    base_tol = max(ZONE_BASE_MIN_PCT, ZONE_BASE_ATR_MULT * atr)
    cluster_tol = max(ZONE_CLUSTER_MIN_PCT, ZONE_CLUSTER_ATR_MULT * atr)
    break_tol = _clamp(ZONE_BREAK_ATR_MULT * atr, ZONE_BREAK_MIN_PCT, ZONE_BREAK_MAX_PCT)
    info.update({"atr_pct": atr, "zz_thr": zz, "break_tol": break_tol})

    swings = _zigzag(closes, zz)
    pivots = []
    for k, (typ, idx) in enumerate(swings):
        if typ != 'L':
            continue
        prev_h = next((swings[j][1] for j in range(k - 1, -1, -1) if swings[j][0] == 'H'), None)
        next_h = next((swings[j][1] for j in range(k + 1, len(swings)) if swings[j][0] == 'H'), None)
        pc = closes[idx]
        left_start = prev_h if prev_h is not None else 0
        right_end = next_h if next_h is not None else n - 1
        drop = (max(closes[left_start:idx + 1]) - pc) / pc * 100
        bounce = (max(closes[idx:right_end + 1]) - pc) / pc * 100

        if prev_h is None and (idx < ZONE_EDGE_BARS or drop < zz * 0.5):
            continue  # 窗口起点伪低点
        p_dt = datetime.strptime(bars[idx]["d"], "%Y-%m-%d")
        if (latest_dt - p_dt).days < MIN_SUPPORT_DAYS:
            continue  # 与旧逻辑一致：支撑点至少距今 MIN_SUPPORT_DAYS 天

        band_hi = pc * (1 + base_tol / 100)
        band_lo = pc * (1 - break_tol / 100)
        lo_i = max(0, idx - ZONE_BASE_SCAN_BARS)
        hi_i = min(n - 1, idx + ZONE_BASE_SCAN_BARS)
        base_idx = [i for i in range(lo_i, hi_i + 1) if band_lo <= closes[i] <= band_hi]
        if idx not in base_idx:
            base_idx.append(idx)

        v_near = max((bars[j]["v"] or 0) for j in range(max(0, idx - 1), min(n, idx + 2)))
        prev_vs = [bars[j]["v"] for j in range(max(0, idx - 21), max(0, idx - 1)) if bars[j]["v"]]
        avg_v = (sum(prev_vs) / len(prev_vs)) if prev_vs else None
        vol_ratio = (v_near / avg_v) if avg_v else 0.0

        pivots.append({
            "idx": idx, "date": bars[idx]["d"], "close": pc,
            "drop": drop, "bounce": bounce,
            "base_high": max(closes[i] for i in base_idx),
            "base_end": max(base_idx),
            "base_days": len(base_idx),
            "base_dates": (bars[min(base_idx)]["d"], bars[max(base_idx)]["d"]),
            "vol_ratio": vol_ratio,
        })
    info["pivots"] = pivots

    # 聚类
    clusters = []
    for p in sorted(pivots, key=lambda x: x["close"]):
        if clusters and p["close"] <= clusters[-1][0]["close"] * (1 + cluster_tol / 100):
            clusters[-1].append(p)
        else:
            clusters.append([p])

    zones = []
    for members in clusters:
        z_low = min(m["close"] for m in members)
        z_high = max(m["base_high"] for m in members)
        z_high = min(z_high, z_low * (1 + ZONE_MAX_WIDTH_PCT / 100))
        z_high = max(z_high, z_low * (1 + ZONE_MIN_WIDTH_PCT / 100))
        last_idx = max(m["base_end"] for m in members)
        break_level = z_low * (1 - break_tol / 100)
        broken = any(closes[i] < break_level for i in range(last_idx + 1, n))

        touches = len(members)
        avg_bounce = sum(m["bounce"] for m in members) / touches
        max_base = max(m["base_days"] for m in members)
        vol_spike = any(m["vol_ratio"] >= ZONE_VOL_SPIKE_RATIO for m in members)
        age = (latest_dt - datetime.strptime(bars[last_idx]["d"], "%Y-%m-%d")).days
        if age <= ZONE_DECAY_FULL_DAYS:
            decay = 1.0
        else:
            span = max(1, ZONE_LOOKBACK_DAYS - ZONE_DECAY_FULL_DAYS)
            decay = max(0.6, 1.0 - 0.4 * (age - ZONE_DECAY_FULL_DAYS) / span)

        raw = (min(60, 20 * touches)
               + min(30, 10 * avg_bounce / zz)
               + min(15, 3 * max_base)
               + (10 if vol_spike else 0))
        score = min(100.0, raw * decay)

        zones.append({
            "low": z_low, "high": z_high, "break_level": break_level,
            "touches": touches, "dates": sorted(m["date"] for m in members),
            "base_ranges": [m["base_dates"] for m in sorted(members, key=lambda x: x["date"])],
            "avg_bounce": avg_bounce, "max_base": max_base, "vol_spike": vol_spike,
            "age": age, "broken": broken, "score": score,
        })
    info["zones"] = sorted(zones, key=lambda z: -z["low"])
    return info


def _fmt_zone(z):
    return (f"区间[{z['low']:.2f}~{z['high']:.2f}] 触及{z['touches']}次({','.join(z['dates'])}) "
            f"横盘{z['max_base']}天 均反弹{z['avg_bounce']:.1f}% "
            f"{'放量 ' if z['vol_spike'] else ''}评分={z['score']:.0f}")


def _zone_analyze(cursor, table, symbol, latest_dt, latest_date, latest_close, latest_low, prev_close):
    res = {"cat": None, "zone": None, "mode": "", "diff": None, "info": None}
    start = (latest_dt - timedelta(days=ZONE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    cursor.execute(
        f'SELECT date, price, high, low, volume FROM [{table}] '
        f'WHERE name = ? AND date >= ? AND date < ? ORDER BY date ASC',
        (symbol, start, latest_date)
    )
    bars = []
    for d, c, h, l, v in cursor.fetchall():
        if c is None or c <= 0:
            continue
        h = h if h is not None else c
        l = l if l is not None else c
        bars.append({"d": d, "c": c, "h": max(h, c), "l": min(l, c), "v": v or 0})

    info = _detect_pivot_zones(bars, latest_dt)
    res["info"] = info
    thr = SUPPORT_THRESHOLD_PCT
    close_hits, over_hits = [], []

    for z in info["zones"]:
        if z["broken"] or z["score"] < ZONE_MIN_SCORE:
            continue
        upper = z["high"] * (1 + thr / 100)
        if latest_close >= z["break_level"]:
            if latest_close <= upper:
                if latest_close < z["low"]:
                    mode = "假破容忍"
                elif latest_close <= z["high"]:
                    mode = "区内"
                else:
                    mode = "区上"
                close_hits.append((z, mode, (latest_close - z["low"]) / z["low"] * 100))
            elif latest_low is not None and latest_low <= upper:
                close_hits.append((z, "探底回升", (latest_low - z["low"]) / z["low"] * 100))
        else:
            if prev_close is not None and prev_close >= z["break_level"]:
                over_hits.append((z, "有效跌破", (latest_close - z["low"]) / z["low"] * 100))

    if close_hits:
        z, mode, diff = max(close_hits, key=lambda t: (t[0]["score"], -abs(t[2])))
        res.update({"cat": "close", "zone": z, "mode": mode, "diff": diff})
    elif over_hits:
        z, mode, diff = max(over_hits, key=lambda t: (t[0]["score"], t[0]["low"]))
        res.update({"cat": "over", "zone": z, "mode": mode, "diff": diff})
    return res


def _legacy_hit(legacy, cat, val, msg):
    legacy["cat"] = cat
    legacy["val"] = val
    legacy["msg"] = msg


def run_support_logic(log_detail):
    log_detail("Analyse_Earning_Support 程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    log_detail(f"Pivot 支撑区: {'开启' if ENABLE_PIVOT_ZONE else '关闭'} | 融合模式: {HYBRID_MODE}")

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel 和 History JSON 文件。\n")

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

    target_groups = [
        "Short", "Short_W", "Strategy12", "Strategy34", "OverSell_W",
        "PE_Deep", "PE_Deeper", "PE_W", "PE_valid", "PE_invalid", "season",
        "PE_Volume", "PE_Volume_up", "PE_Hot", "PE_Volume_high"
    ]

    symbols = set()

    if TARGET_DATE:
        log_detail(f"正在从 Earning_History.json 提取 {TARGET_DATE} 的历史数据作为回测起点...")
        for group in target_groups:
            if group in earning_history and TARGET_DATE in earning_history[group]:
                for symbol in earning_history[group][TARGET_DATE]:
                    symbols.add(symbol)
    else:
        log_detail("正在从 Sectors_panel.json 提取最新数据作为运行起点...")
        for group in target_groups:
            if group in sectors_panel:
                for symbol in sectors_panel[group]:
                    symbols.add(symbol)

    over_history = earning_history.get("SupportLevel_Over", {}) or {}

    def _was_over_on(date_str, symbol):
        items = over_history.get(date_str)
        if not items:
            return False
        return any(_item_matches_symbol(it, symbol) for it in items)

    forced_only_symbols = set()
    if ENABLE_OVER_INHERIT and FORCE_KEEP_OVER_CHAIN and over_history:
        try:
            if TARGET_DATE:
                ref_dt = datetime.strptime(TARGET_DATE, "%Y-%m-%d")
                strict_before = True
            else:
                ref_dt = datetime.now()
                strict_before = False
            for d_key, items in over_history.items():
                try:
                    d_dt = datetime.strptime(d_key, "%Y-%m-%d")
                except Exception:
                    continue
                gap = (ref_dt.date() - d_dt.date()).days
                if (gap > 0 if strict_before else gap >= 0) and gap <= INHERIT_GAP_MAX_DAYS:
                    for it in items or []:
                        if isinstance(it, str) and it and it not in symbols:
                            forced_only_symbols.add(it)
            symbols |= forced_only_symbols
            if forced_only_symbols:
                log_detail(f"[顺延] FORCE_KEEP_OVER_CHAIN 额外纳入 {len(forced_only_symbols)} 个仍在 Over 链上的 symbol (仅允许走顺延)")
        except Exception as e:
            log_detail(f"[顺延] 强制纳入 Over 链 symbol 时出错: {e}")

    log_detail(f"共提取 {len(symbols)} 个唯一 symbol")

    if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE not in symbols:
        log_detail(f"⚠️ [警告] 追踪的 Symbol '{SYMBOL_TO_TRACE}' 未在任何目标分组中找到。")
        log_detail(f"   可能原因：")
        log_detail(f"   1. 该 Symbol 在 {TARGET_DATE or '最新日期'} 确实不在这些分组中: {target_groups}")
        log_detail(f"   2. JSON 文件中该日期的数据结构可能缺失。")
        return

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

    def _resolve_inherit_source_date(symbol, table, latest_date, prev_date, is_tracing):
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

    support_close = {}
    support_over = {}
    earning_close = defaultdict(list)
    earning_over = defaultdict(list)
    inherit_hits = []
    zone_only_hits = []
    confluence_hits = []
    override_hits = []
    inherit_interrupts = []

    for symbol in sorted(symbols):
        is_tracing = (symbol == SYMBOL_TO_TRACE)
        is_forced_only = symbol in forced_only_symbols
        table = symbol_to_table.get(symbol)

        if not table:
            if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 未在数据库任何表中找到，跳过")
            continue

        if is_tracing:
            log_detail(f"\n>>> [追踪] 开始分析 {symbol} (所在表: {table})" + (" [仅限顺延: 由 Over 链强制拉回]" if is_forced_only else ""))

        try:
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

            latest_date, latest_close, latest_low = latest_rows[0]
            prev_date, prev_close, prev_low = latest_rows[1]

            cursor.execute('SELECT 1 FROM Earning WHERE name = ? AND date = ?', (symbol, latest_date))
            is_earning_day = cursor.fetchone() is not None

            if latest_close >= prev_close:
                if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 最新收盘价({latest_close}) 未低于前一日收盘价({prev_close})，跳过（Over 顺延链条在此断开）")
                continue

            if is_tracing:
                log_detail(f"  -> 最新交易日: {latest_date}, 收盘价: {latest_close}, 最低价: {latest_low} (前一日收盘: {prev_close})")

            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

            pe_high_tag = ""
            pe_vol_high_history = earning_history.get("PE_Volume_high", {})
            for i in range(21):
                check_date = (latest_dt - timedelta(days=i)).strftime("%Y-%m-%d")
                if check_date in pe_vol_high_history:
                    for item in pe_vol_high_history[check_date]:
                        if _item_matches_symbol(item, symbol) and '甲' in item:
                            pe_high_tag = f" \033[95m[PE_High甲:{check_date}]\033[0m"
                            break
                if pe_high_tag:
                    break

            # ===== 【新增】Pivot 支撑区分析（非财报日才做） =====
            zone_res = None
            if ENABLE_PIVOT_ZONE and not is_earning_day:
                zone_res = _zone_analyze(cursor, table, symbol, latest_dt, latest_date,
                                         latest_close, latest_low, prev_close)
                if is_tracing:
                    zi = zone_res["info"]
                    if zi["atr_pct"] is None:
                        log_detail(f"  [支撑区] 历史K线不足 {ZONE_MIN_BARS} 根，未做分析")
                    else:
                        log_detail(f"  [支撑区] ATR%(中位)={zi['atr_pct']:.2f}% ZigZag阈值={zi['zz_thr']:.2f}% 跌破容差={zi['break_tol']:.2f}%")
                        for p in zi["pivots"]:
                            log_detail(f"    · 摆动低点 {p['date']} close={p['close']} 前跌{p['drop']:.1f}% 后弹{p['bounce']:.1f}% "
                                       f"横盘{p['base_days']}天({p['base_dates'][0]}~{p['base_dates'][1]}) 量比{p['vol_ratio']:.2f}")
                        for z in zi["zones"]:
                            st = "❌已失效" if z["broken"] else ("⚠️低分" if z["score"] < ZONE_MIN_SCORE else "✔有效")
                            log_detail(f"    ▣ {_fmt_zone(z)} {st}")
                        if zone_res["cat"]:
                            log_detail(f"  [支撑区] 判定={zone_res['cat']} 模式={zone_res['mode']} 距区下沿={zone_res['diff']:.2f}%")
                        else:
                            log_detail(f"  [支撑区] 未命中任何支撑区")

            # ===== Phase 0: SupportLevel_Over 顺延继承 =====
            if ENABLE_OVER_INHERIT:
                if is_earning_day and not INHERIT_IGNORE_EARNING_DAY:
                    if is_tracing:
                        log_detail(f"  ⏭️ [顺延] 最新交易日({latest_date})为财报日，按配置不走顺延继承")
                else:
                    src_date, src_reason = _resolve_inherit_source_date(
                        symbol, table, latest_date, prev_date, is_tracing
                    )
                    if (src_date and ZONE_INTERRUPT_INHERIT and not is_forced_only and zone_res
                            and zone_res["cat"] == "close" and zone_res["zone"]["score"] >= ZONE_STRONG_SCORE):
                        inherit_interrupts.append(symbol)
                        log_detail(f"  ⛓️‍💥 {symbol}: 顺延链中断 —— 已跌入强支撑区 {_fmt_zone(zone_res['zone'])}，改走完整判定")
                        src_date = None
                    if src_date:
                        support_over[symbol] = f"{symbol}{INHERIT_SUFFIX}"
                        earning_over[latest_date].append(symbol)
                        inherit_hits.append(symbol)
                        log_detail(
                            f"  ✅🔻 {symbol}: SupportLevel_Over [顺延继承·{src_reason} 源日期={src_date}] "
                            f"(最新收盘={latest_close} < 前收={prev_close}，跳过支撑位重算)"
                            + (" [Over链强制拉回]" if is_forced_only else "") + f"{pe_high_tag}"
                        )
                        continue
                    elif is_tracing:
                        log_detail(f"  -> [顺延] 未命中顺延，走完整判定逻辑")

            if is_forced_only:
                if is_tracing:
                    log_detail(f"  ⏭️ [顺延] {symbol} 为 Over 链强制拉回的 symbol，未命中顺延，不进行完整判定，跳过")
                continue

            if is_earning_day:
                if is_tracing: log_detail(f"⚠️ [追踪] {symbol} 最新交易日({latest_date})恰好为财报日，按规则过滤跳过")
                continue

            # ======== 旧逻辑（结果先写入 legacy，最后统一融合） ========
            legacy = {"cat": None, "val": "", "msg": ""}
            legacy_abort = False

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
                    legacy_abort = True
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
                                legacy_abort = True
                    else:
                        support_date = support_date_close
                        support_price_low = min_close_row[1]
                        support_price_close = min_close_row[2]
                        days_diff = days_diff_close
                        if is_tracing: log_detail(f"  ✅ 切换为收盘价(price)支撑点: {support_date} (Low: {support_price_low}, Close: {support_price_close})")

                if not legacy_abort and (days_diff >= MIN_SUPPORT_DAYS or lookback_days == 61):
                    if days_diff >= MIN_SUPPORT_DAYS:
                        val_suffix = "财" if is_earning_fallback else ""
                        tag_prefix = "[最近财报日Fallback] " if is_earning_fallback else ""
                        plain_val = f"{symbol}{val_suffix}" if val_suffix else ""

                        if latest_close > support_price_close:
                            diff_pct_close = (latest_close - support_price_close) / support_price_close * 100
                            if is_tracing: log_detail(f"  -> 距离支撑位(price)差值: {diff_pct_close:.2f}% (阈值: {SUPPORT_THRESHOLD_PCT}%)")

                            if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                _legacy_hit(legacy, "close", plain_val,
                                    f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[首选Price比较] (最新收盘={latest_close}, 支撑日期={support_date}, 支撑(price)={support_price_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                                symbol_categorized = True
                            else:
                                if is_tracing: log_detail(f"  -> price比较不合格，尝试使用支撑日的最低价(low: {support_price_low})进行二次比较")
                                if latest_close > support_price_low:
                                    diff_pct_low = (latest_close - support_price_low) / support_price_low * 100
                                    if diff_pct_low <= SUPPORT_THRESHOLD_PCT:
                                        _legacy_hit(legacy, "close", plain_val,
                                            f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[二次Low比较] (最新收盘={latest_close}, 支撑日期={support_date}, 支撑(low)={support_price_low}, 差={diff_pct_low:.2f}%){pe_high_tag}")
                                        symbol_categorized = True
                                    else:
                                        if is_tracing: log_detail(f"  ⚠️ 二次Low比较差值 {diff_pct_low:.2f}% 仍超 {SUPPORT_THRESHOLD_PCT}%，尝试使用最新日期的low({latest_low})与支撑日的收盘价({support_price_close})进行三次比较")
                                        if latest_low > support_price_close:
                                            diff_pct_latest_low = (latest_low - support_price_close) / support_price_close * 100
                                            if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                                _legacy_hit(legacy, "close", plain_val,
                                                    f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[三次LatestLow比较] (最新low={latest_low}, 支撑日期={support_date}, 支撑(price)={support_price_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                                symbol_categorized = True
                                            else:
                                                if is_tracing: log_detail(f"  ⚠️ 三次LatestLow比较差值 {diff_pct_latest_low:.2f}% 仍超 {SUPPORT_THRESHOLD_PCT}%，继续执行")
                                        else:
                                            if is_tracing: log_detail(f"  ⚠️ 最新low({latest_low}) 已跌破或等于支撑(price)({support_price_close})，不符合三次比较条件，继续执行")
                                else:
                                    _legacy_hit(legacy, "over", plain_val,
                                        f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}[二次Low比较] (最新收盘={latest_close}, 支撑日期={support_date}, 支撑(low)={support_price_low}){pe_high_tag}")
                                    symbol_categorized = True
                        else:
                            _legacy_hit(legacy, "over", plain_val,
                                f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}(最新收盘={latest_close} <= 支撑(price)={support_price_close}){pe_high_tag}")
                            symbol_categorized = True

            # ===== Phase 2.5: 并行流程 =====
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
                        if latest_close > p_min_close:
                            diff_pct_close = (latest_close - p_min_close) / p_min_close * 100
                            if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                parallel_suffix = f"{round_num}轮"
                                log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Close [首选Price比较] (最新={latest_close}, 支撑日期={p_min_date}, 支撑(price)={p_min_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                            else:
                                if latest_close > p_min_low:
                                    diff_pct_low = (latest_close - p_min_low) / p_min_low * 100
                                    if diff_pct_low <= SUPPORT_THRESHOLD_PCT:
                                        parallel_suffix = f"{round_num}轮"
                                        log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Close [二次Low比较] (最新={latest_close}, 支撑日期={p_min_date}, 支撑(low)={p_min_low}, 差={diff_pct_low:.2f}%){pe_high_tag}")
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
                                    log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Over [二次Low比较] (最新={latest_close}, 支撑日期={p_min_date}, 支撑(low)={p_min_low}){pe_high_tag}")
                        else:
                            parallel_suffix = f"{round_num}轮"
                            log_detail(f"  🔗 {symbol}: 并行流程第{round_num}轮命中 Over (最新={latest_close} <= 支撑(price)={p_min_close}){pe_high_tag}")

                    break

                if round_num > max_rounds:
                    parallel_suffix = f"{max_rounds}轮"
                    if is_tracing: log_detail(f"  ⚠️ {max_rounds}轮延展全部失效(持续下跌创新低)，强行标记后缀={parallel_suffix}")

            # ===== Phase 3: 财报支撑回退检查（61 天 / 91 天两档） =====
            if not legacy_abort and not symbol_categorized and lookback_days == 61:
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

                    e_val = f"{symbol}财{parallel_suffix}"
                    if latest_close > earning_support_close:
                        diff_pct_close = (latest_close - earning_support_close) / earning_support_close * 100
                        if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                            _legacy_hit(legacy, "close", e_val,
                                f"  ✅ {symbol}: SupportLevel_Close [财报回退-{fallback_days}天{parallel_suffix}][首选Price比较] (最新={latest_close}, 财报日={earning_date}, 支撑(price)={earning_support_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                            symbol_categorized = True
                        else:
                            if latest_close > earning_support_low:
                                diff_pct_low = (latest_close - earning_support_low) / earning_support_low * 100
                                if diff_pct_low <= SUPPORT_THRESHOLD_PCT:
                                    _legacy_hit(legacy, "close", e_val,
                                        f"  ✅ {symbol}: SupportLevel_Close [财报回退-{fallback_days}天{parallel_suffix}][二次Low比较] (最新={latest_close}, 财报日={earning_date}, 支撑(low)={earning_support_low}, 差={diff_pct_low:.2f}%){pe_high_tag}")
                                    symbol_categorized = True
                                else:
                                    if latest_low > earning_support_close:
                                        diff_pct_latest_low = (latest_low - earning_support_close) / earning_support_close * 100
                                        if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                            _legacy_hit(legacy, "close", e_val,
                                                f"  ✅ {symbol}: SupportLevel_Close [财报回退-{fallback_days}天{parallel_suffix}][三次LatestLow比较] (最新low={latest_low}, 财报日={earning_date}, 支撑(price)={earning_support_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                            symbol_categorized = True
                                        else:
                                            if is_tracing: log_detail(f"  ⚠️ {fallback_days}天档财报支撑差值(含三次LatestLow)超 {SUPPORT_THRESHOLD_PCT}%，尝试下一档")
                                    else:
                                        if is_tracing: log_detail(f"  ⚠️ {fallback_days}天档财报支撑 最新low({latest_low}) <= 支撑(price)({earning_support_close})，不符合三次比较条件，尝试下一档")
                            else:
                                _legacy_hit(legacy, "over", e_val,
                                    f"  ✅🔻 {symbol}: SupportLevel_Over [财报回退-{fallback_days}天{parallel_suffix}][二次Low比较] (最新={latest_close}, 财报日={earning_date}, 支撑(low)={earning_support_low}){pe_high_tag}")
                                symbol_categorized = True
                    else:
                        _legacy_hit(legacy, "over", e_val,
                            f"  ✅🔻 {symbol}: SupportLevel_Over [财报回退-{fallback_days}天{parallel_suffix}] (最新={latest_close} <= 支撑(price)={earning_support_close}){pe_high_tag}")
                        symbol_categorized = True

                if not symbol_categorized and is_tracing:
                    log_detail(f"  ⏭️ 61/91天范围内均无符合条件的财报支撑")

            # ===== Phase 4: 31天内财报后区间支撑位检查 =====
            if not legacy_abort and not symbol_categorized:
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
                            p4_val = f"{symbol}财区"

                            if latest_close > p4_support_close:
                                diff_pct_close = (latest_close - p4_support_close) / p4_support_close * 100
                                if diff_pct_close <= SUPPORT_THRESHOLD_PCT:
                                    _legacy_hit(legacy, "close", p4_val,
                                        f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[首选Price比较] (最新={latest_close}, 支撑日期={p4_support_date}, 支撑(price)={p4_support_close}, 差={diff_pct_close:.2f}%){pe_high_tag}")
                                    symbol_categorized = True
                                else:
                                    if latest_close > p4_support_low:
                                        diff_pct_low = (latest_close - p4_support_low) / p4_support_low * 100
                                        if diff_pct_low <= SUPPORT_THRESHOLD_PCT:
                                            _legacy_hit(legacy, "close", p4_val,
                                                f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[二次Low比较] (最新={latest_close}, 支撑日期={p4_support_date}, 支撑(low)={p4_support_low}, 差={diff_pct_low:.2f}%){pe_high_tag}")
                                            symbol_categorized = True
                                        else:
                                            if latest_low > p4_support_close:
                                                diff_pct_latest_low = (latest_low - p4_support_close) / p4_support_close * 100
                                                if diff_pct_latest_low <= SUPPORT_THRESHOLD_PCT:
                                                    _legacy_hit(legacy, "close", p4_val,
                                                        f"  ✅ {symbol}: SupportLevel_Close {tag_prefix}[三次LatestLow比较] (最新low={latest_low}, 支撑日期={p4_support_date}, 支撑(price)={p4_support_close}, 差={diff_pct_latest_low:.2f}%){pe_high_tag}")
                                                    symbol_categorized = True
                                                else:
                                                    if is_tracing: log_detail(f"  ⚠️ {tag_prefix}差值超 {SUPPORT_THRESHOLD_PCT}%，无输出")
                                            else:
                                                if is_tracing: log_detail(f"  ⚠️ {tag_prefix}最新low({latest_low}) <= 支撑(price)({p4_support_close})，不符合三次比较条件")
                                    else:
                                        _legacy_hit(legacy, "over", p4_val,
                                            f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}[二次Low比较] (最新={latest_close}, 支撑日期={p4_support_date}, 支撑(low)={p4_support_low}){pe_high_tag}")
                                        symbol_categorized = True
                            else:
                                _legacy_hit(legacy, "over", p4_val,
                                    f"  ✅🔻 {symbol}: SupportLevel_Over {tag_prefix}(最新={latest_close} <= 支撑(price)={p4_support_close}){pe_high_tag}")
                                symbol_categorized = True
                else:
                    if is_tracing: log_detail(f"  ⏭️ 31天内无财报，跳过 Phase 4")

            # ===== 【新增】Phase 5: 新旧逻辑融合 =====
            L = legacy["cat"]
            Z = zone_res["cat"] if (zone_res and ENABLE_PIVOT_ZONE) else None
            zz_obj = zone_res["zone"] if Z else None
            z_strong = bool(zz_obj and zz_obj["score"] >= ZONE_STRONG_SCORE)

            final_cat, final_val, final_msg, kind = None, "", "", ""

            def _zone_msg(prefix=""):
                emoji = "✅" if Z == "close" else "✅🔻"
                name = "SupportLevel_Close" if Z == "close" else "SupportLevel_Over"
                return (f"  {emoji} {symbol}: {name} [枢轴支撑区·{zone_res['mode']}]{prefix} "
                        f"(最新收盘={latest_close}, 最新low={latest_low}, {_fmt_zone(zz_obj)}, "
                        f"距区下沿={zone_res['diff']:.2f}%){pe_high_tag}")

            if HYBRID_MODE == "legacy":
                if L:
                    final_cat, final_val, final_msg, kind = L, legacy["val"], legacy["msg"], "legacy"
            elif HYBRID_MODE == "zone":
                if Z:
                    final_cat, final_val, final_msg, kind = Z, f"{symbol}{ZONE_SUFFIX}", _zone_msg(), "zone"
            elif HYBRID_MODE == "intersect":
                if L and L == Z:
                    final_cat = L
                    final_val = (legacy["val"] or symbol) + CONFLUENCE_SUFFIX
                    final_msg = legacy["msg"] + f"  ➕[枢轴共振 {_fmt_zone(zz_obj)}]"
                    kind = "confluence"
                elif is_tracing and (L or Z):
                    log_detail(f"  ⏭️ [融合-intersect] 旧逻辑={L} 支撑区={Z}，未共振，不输出")
            else:  # union
                if L and Z:
                    if L == Z:
                        final_cat = L
                        final_val = (legacy["val"] or symbol) + CONFLUENCE_SUFFIX
                        final_msg = legacy["msg"] + f"  ➕[枢轴共振 {_fmt_zone(zz_obj)}]"
                        kind = "confluence"
                    elif L == "over" and Z == "close" and ZONE_OVERRIDE_CONFLICT and z_strong:
                        final_cat, final_val, kind = "close", f"{symbol}{ZONE_SUFFIX}", "override"
                        final_msg = _zone_msg("[覆盖旧逻辑Over]")
                    else:
                        final_cat, final_val, final_msg, kind = L, legacy["val"], legacy["msg"], "legacy"
                        log_detail(f"  ⚖️ {symbol}: 新旧冲突(旧={L}, 支撑区={Z} 评分={zz_obj['score']:.0f})，保留旧逻辑结果")
                elif L:
                    final_cat, final_val, final_msg, kind = L, legacy["val"], legacy["msg"], "legacy"
                elif Z:
                    final_cat, final_val, final_msg, kind = Z, f"{symbol}{ZONE_SUFFIX}", _zone_msg(), "zone"

            if final_cat == "close":
                support_close[symbol] = final_val
                earning_close[latest_date].append(symbol)
            elif final_cat == "over":
                support_over[symbol] = final_val
                earning_over[latest_date].append(symbol)

            if final_cat:
                log_detail(final_msg)
                if kind == "zone":
                    zone_only_hits.append(symbol)
                elif kind == "confluence":
                    confluence_hits.append(symbol)
                elif kind == "override":
                    override_hits.append(symbol)
            elif is_tracing:
                log_detail(f"  ⏭️ {symbol}: 新旧逻辑均未命中，最终跳过")

        except Exception as e:
            log_detail(f"处理 {symbol} 时出错: {e}")

    conn.close()

    forced_hits = sorted(s for s in inherit_hits if s in forced_only_symbols)
    if inherit_hits:
        log_detail(f"\n[顺延继承] 本次共 {len(inherit_hits)} 个 symbol 通过顺延直接判定为 Over: {sorted(inherit_hits)}")
        if forced_hits:
            log_detail(f"[顺延继承] 其中 {len(forced_hits)} 个来自 Over 链强制拉回: {forced_hits}")
    if inherit_interrupts:
        log_detail(f"[顺延中断] {len(inherit_interrupts)} 个因跌入强支撑区而中断顺延: {sorted(inherit_interrupts)}")
    if ENABLE_PIVOT_ZONE:
        log_detail(f"[支撑区] 仅支撑区命中({ZONE_SUFFIX}) {len(zone_only_hits)} 个: {sorted(zone_only_hits)}")
        log_detail(f"[支撑区] 新旧共振({CONFLUENCE_SUFFIX}) {len(confluence_hits)} 个: {sorted(confluence_hits)}")
        log_detail(f"[支撑区] 强支撑覆盖旧Over {len(override_hits)} 个: {sorted(override_hits)}")

    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [回测模式] 运行完毕 (Date: {TARGET_DATE})。")
        log_detail(f"📊 SupportLevel_Close 命中: {len(support_close)} 个")
        log_detail(f"📊 SupportLevel_Over  命中: {len(support_over)} 个 (其中顺延继承 {len(inherit_hits)} 个，强制拉回 {len(forced_hits)} 个)")
        log_detail("⚠️ 文件未被修改。")
        log_detail("="*60 + "\n")
    else:
        sectors_panel["SupportLevel_Close"] = support_close
        sectors_panel["SupportLevel_Close_backup"] = support_close.copy()
        sectors_panel["SupportLevel_Over"] = support_over
        sectors_panel["SupportLevel_Over_backup"] = support_over.copy()

        if "SupportLevel_Close" not in earning_history:
            earning_history["SupportLevel_Close"] = {}
        for date_key, sym_list in earning_close.items():
            earning_history["SupportLevel_Close"][date_key] = sorted(set(sym_list))

        if "SupportLevel_Over" not in earning_history:
            earning_history["SupportLevel_Over"] = {}
        for date_key, sym_list in earning_over.items():
            earning_history["SupportLevel_Over"][date_key] = sorted(set(sym_list))

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