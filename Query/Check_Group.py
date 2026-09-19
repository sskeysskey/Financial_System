#「转折」条目太多：把 TURN_MIN_DROP 改成 2（只看 4→2、5→3 这类硬转折），或 TURN_MIN_STREAK 改 4，或 TURN_RECENT_DAYS 改 1（只看最新交易日）。
#「转折」条目太少 / 漏掉你例子那种：把 TURN_MAX_GAP 调到 3（容忍中间连续 2 天无记录），TURN_RECENT_DAYS 调到 5。
# 想把“信号彻底消失”也抓出来：TURN_ALLOW_DROP_TO_ZERO = True（会明显变多，建议同时把 TURN_MIN_STREAK 提到 4）。
# 星级门槛：在 _score_turning() 末尾改 4.5 / 3.5 / 2.5。
# 关键项名单：直接改 TURN_LEVEL2_KEYS / TURN_LEVEL3_KEYS 即可。
#
# ★ 新增「持仓」分组（放在转折之前）：
#   - 数据来源 Modules/firstrade_positions.json（Chrome 插件 + bridge_server.py 落盘）
#   - 支持三种排序，点击表头按钮切换，同一按钮再点一次切换升/降序：
#       A-Z（代码）｜盈亏%（gainloss）｜成本（cost）
#   - 在该分组里点开图表后，Chart_input_single 的左右键就按这个排序在持仓内循环
#   - 按 R 键重新读取 firstrade_positions.json（不用重启）

import sys
import json
import os
import sqlite3
import re
import subprocess
from collections import OrderedDict, defaultdict

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QLabel, QFrame, QMenu,
    QInputDialog, QMessageBox
)
from PyQt6.QtGui import QCursor, QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

# 外部绘图函数
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
from Chart_input_single import plot_financial_data

# ★ 持仓读取层
try:
    from ft_quotes import load_all_positions, position_num, fmt_money
    FT_POS_OK = True
except Exception as _e:
    print(f"[FT] 加载 ft_quotes 失败（持仓分组不可用）: {_e}")
    FT_POS_OK = False
    def load_all_positions(): return {}, {}
    def position_num(rec, *keys): return None
    def fmt_money(s): return str(s)

try:
    from ft_watchlist_add import (add_symbol_async, watchlist_groups,
                                  choose_group_dialog, last_group, save_last_group,
                                  notify_mac)
    FT_WL_ADD_OK = True
except Exception as _e:
    print(f"[FT] 加载 ft_watchlist_add 失败（加自选不可用）: {_e}")
    FT_WL_ADD_OK = False
    def watchlist_groups(): return []
    def choose_group_dialog(*a, **k): return None
    def last_group(): return ""
    def save_last_group(g): pass
    def notify_mac(*a, **k): pass
    def add_symbol_async(*a, **k): return None

# ----------------------------------------------------------------------
# 常量 / 全局配置
# ----------------------------------------------------------------------
MAX_ITEMS_PER_COLUMN = 9
SYMBOL_WIDGET_FIXED_WIDTH = 220

CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")
COLORS_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Colors.json")
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")

# ---------- 持仓分组排序配置 ----------
HOLD_SORT_MODES = [('alpha', 'A-Z'), ('gainloss', '盈亏%'), ('cost', '成本')]
HOLD_SORT_LABEL = dict(HOLD_SORT_MODES)
HOLD_SORT_KEYS = {
    'gainloss': ('gainloss', 'gainlossPercent', 'gainloss_amount'),
    'cost': ('cost', 'totalCost', 'market_value'),
}
HOLD_DEFAULT_DESC = {'alpha': False, 'gainloss': True, 'cost': True}

# 52周新低判定：以下板块内的 symbol 视为符合 52week_low 筛选
WEEK52_LOW_SECTORS = {
    "Basic_Materials", "Real_Estate", "Energy", "Technology",
    "Consumer_Cyclical", "Utilities", "Consumer_Defensive",
    "Industrials", "Communication_Services", "Financial_Services",
    "Healthcare"
}

# ======================================================================
# 多组共振 —— 信号强度评估配置
# ======================================================================
IGNORE_GROUPS = {"_Tag_Blacklist", "no_season"}

HIGH_WEIGHT_CATEGORIES = {           # 红色：高权重
    "PE_Volume", "Short", "Short_W", "PE_Volume_high",
    "SupportLevel_Over", "PE_Deeper", "PE_Deep"
}
MEDIUM_WEIGHT_CATEGORIES = {         # 橙色：中权重
    "PE_Volume_up", "PE_W", "SupportLevel_Close", "PE_Hot",
    "OverSell_W", "season"
}

LOOKBACK_TRADING_DAYS = 120   # 稀有度回看窗口（交易日）
MIN_HISTORY_DAYS = 5          # 历史样本少于该值 → 视为“极少出现”

BADGE_TEXT = {0: "", 1: "★", 2: "★★", 3: "🔥★★★"}
BADGE_NAME = {0: "常态", 1: "值得一看", 2: "罕见/高质量", 3: "极罕见且极强"}

# ======================================================================
# “转折”检测配置
# ======================================================================
TURN_MIN_STREAK = 3
TURN_MIN_DROP = 1
TURN_MAX_GAP = 2
TURN_RECENT_DAYS = 3
TURN_ALLOW_DROP_TO_ZERO = False
TURN_REQUIRE_NO_RECOVERY = True

TURN_LEVEL2_KEYS = {
    "PE_Volume", "SupportLevel_Over", "Short", "PE_Volume_high", "PE_Deep"
}
TURN_LEVEL3_KEYS = {
    "PE_Volume", "SupportLevel_Over", "SupportLevel_Close", "Short", "Short_W",
    "PE_Volume_high", "PE_Deep", "PE_valid", "PE_invalid", "PE_Deeper", "season"
}

TURN_BADGE = {0: "⤵", 1: "⤵★", 2: "⤵★★", 3: "⤵🔥★★★"}
TURN_NAME = {0: "一般转折", 1: "值得一看", 2: "较强转折", 3: "极强转折"}

# ======================================================================
# 分组过滤 & 日期规范化
# ======================================================================
EXCLUDE_BACKUP_GROUPS = True
MAX_STALE_DAYS = 0
COLLAPSE_FAMILIES = False

GROUP_FAMILIES = [
    {"PE_low", "PE_lower", "PE_lowest"},
    {"PE_Deep", "PE_Deeper"},
    {"Short", "Short_W"},
    {"SupportLevel_Close", "SupportLevel_Over"},
    {"PE_Volume", "PE_Volume_up", "PE_Volume_high"},
    {"ETF_Volume_high", "ETF_Volume_low", "ETF_low"},
]

_DATE_RE = re.compile(r"^(\d{4})\D+(\d{1,2})\D+(\d{1,2})")


def norm_date(s):
    """把 2025-1-9 / 2025/1/9 / 20250109 统一成 '2025-01-09'，用于排序"""
    s = str(s).strip()
    m = _DATE_RE.match(s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    return "-".join(m.groups()) if m else s


def is_valid_group(name):
    if name in IGNORE_GROUPS:
        return False
    if EXCLUDE_BACKUP_GROUPS and name.endswith("_backup"):
        return False
    return True


def build_date_universe(history_data):
    """返回 (全局交易日降序列表, {date: 距今第几个交易日})"""
    dates = set()
    for g, dm in (history_data or {}).items():
        if not is_valid_group(g) or not isinstance(dm, dict):
            continue
        dates.update(dm.keys())
    ordered = sorted(dates, key=norm_date, reverse=True)
    return ordered, {d: i for i, d in enumerate(ordered)}


def collapse_family(groups):
    """同族分组合并成 1 项（可选）"""
    if not COLLAPSE_FAMILIES:
        return set(groups)
    out = set()
    for g in groups:
        fam = next((f for f in GROUP_FAMILIES if g in f), None)
        out.add("|".join(sorted(fam)) if fam else g)
    return out


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SymbolManager:
    def __init__(self, symbol_list):
        self.update_symbols(symbol_list)

    def update_symbols(self, symbol_list):
        self.symbols = list(OrderedDict.fromkeys(symbol_list))
        self.current_index = -1

    def next_symbol(self):
        if not self.symbols: return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols: return None
        self.current_index = (self.current_index - 1 + len(self.symbols)) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        try:
            self.current_index = self.symbols.index(symbol)
        except ValueError:
            pass

    def current_symbol(self):
        if self.symbols and 0 <= self.current_index < len(self.symbols):
            return self.symbols[self.current_index]
        return None

    def reset(self):
        self.current_index = -1


# ----------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------
def clean_ticker(symbol):
    """清洗 Symbol，去除中文后缀等，仅保留前面的字母和横杠"""
    match = re.search(r"^([A-Za-z-]+)", symbol)
    return match.group(1) if match else symbol


def split_symbol_suffix(raw):
    """把 'AAPL抄底黑' 拆成 ('AAPL', '抄底黑')"""
    base = clean_ticker(raw)
    suffix = raw[len(base):] if raw.startswith(base) else ""
    return base.upper(), suffix


def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)


def load_text_data(path):
    data = {}
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                key, value = map(str.strip, line.split(':', 1))
                cleaned_key = key.split()[-1]
                data[cleaned_key] = value.split(',')[0].strip() if ',' in value else value
    return data


def load_52week_low_symbols(path):
    """从 Sectors_panel.json 中读取指定板块下的 symbol，作为 52week_low 集合"""
    symbols = set()
    data = load_json(path)
    for sector in WEEK52_LOW_SECTORS:
        for sym in data.get(sector, {}).keys():
            symbols.add(clean_ticker(sym).upper())
    return symbols


def fetch_mnspp_data_from_db(db_path, symbol):
    """从数据库获取财务数据"""
    if not os.path.exists(db_path):
        return "N/A", None, "N/A", "--"
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?", (symbol,))
            result = cursor.fetchone()
            return result if result else ("N/A", None, "N/A", "--")
    except Exception as e:
        print(f"查询财务数据出错: {e}")
        return "N/A", None, "N/A", "--"


def execute_external_script(script_type, keyword):
    script_configs = {
        'similar':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Search_Similar_Tag.py'),
        'tags':     os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'futu':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'earning':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Check_Earning_history.py'),
        'highlow':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Check_HighLow.py'),
    }
    script_path = script_configs.get(script_type)
    if not script_path: return
    try:
        if script_type in ['futu']:
            subprocess.Popen(['osascript', script_path, keyword])
        else:
            subprocess.Popen([sys.executable, script_path, keyword])
    except Exception as e:
        print(f"执行脚本错误: {e}")


# ======================================================================
# 多组共振（次数统计）
# ======================================================================
def calculate_frequency_data(history_data, week52_low_symbols=None, verbose=False):
    if week52_low_symbols is None:
        week52_low_symbols = set()

    pe_chaodi_sources = {"PE_Null"}

    dates_desc, pos = build_date_universe(history_data)
    if not dates_desc:
        return []
    global_latest = dates_desc[0]

    symbol_groups = defaultdict(set)
    symbol_detail = defaultdict(list)
    symbols_with_chaodi = set()

    for group, date_map in (history_data or {}).items():
        if not is_valid_group(group) or not isinstance(date_map, dict) or not date_map:
            continue
        latest = max(date_map.keys(), key=norm_date)
        lag = pos.get(latest, 10 ** 9)
        if lag > MAX_STALE_DAYS:
            if verbose:
                print(f"[skip-stale] {group} 最新={latest} 落后 {lag} 交易日")
            continue
        for raw in (date_map.get(latest) or []):
            base, suf = split_symbol_suffix(raw)
            if "抄底" in raw:
                symbols_with_chaodi.add(base)
            symbol_groups[base].add(group)
            symbol_detail[base].append((group, latest, raw))

    for sym in list(symbol_groups.keys()):
        if sym in week52_low_symbols:
            symbol_groups[sym].add("52week_low")

    count_to_symbols = defaultdict(list)
    for sym, groups in symbol_groups.items():
        eff = set(groups)
        if sym in symbols_with_chaodi:
            eff -= pe_chaodi_sources
        eff = collapse_family(eff)
        count = len(eff)
        if count < 2:
            continue
        count_to_symbols[count].append(sym)

    if verbose:
        print(f"[共振] 全局最新交易日={global_latest}")
        for sym in sorted(symbol_groups):
            print(f"  {sym}: {sorted(symbol_groups[sym])}")

    return [{'count': c, 'symbols': sorted(count_to_symbols[c])}
            for c in sorted(count_to_symbols, reverse=True)]


# ======================================================================
# Earning_History 索引 & 信号强度评估
# ======================================================================
def build_symbol_history_index(history_data):
    sym_items = defaultdict(dict)
    all_dates = set()
    for group, date_map in (history_data or {}).items():
        if not is_valid_group(group) or not isinstance(date_map, dict):
            continue
        for date_str, symbols in date_map.items():
            if not isinstance(symbols, list):
                continue
            all_dates.add(date_str)
            for raw in symbols:
                sym, suf = split_symbol_suffix(raw)
                sym_items[sym].setdefault(date_str, []).append((group, suf))
    return {'sym_items': sym_items,
            'sorted_dates': sorted(all_dates, key=norm_date, reverse=True)}


def get_today_items(history_data):
    today_items = defaultdict(list)
    dates_desc, pos = build_date_universe(history_data)
    if not dates_desc:
        return today_items
    for group, date_map in (history_data or {}).items():
        if not is_valid_group(group) or not isinstance(date_map, dict) or not date_map:
            continue
        latest = max(date_map.keys(), key=norm_date)
        if pos.get(latest, 10 ** 9) > MAX_STALE_DAYS:
            continue
        for raw in (date_map.get(latest) or []):
            sym, suf = split_symbol_suffix(raw)
            today_items[sym].append((group, suf))
    return today_items


def category_color(cat, suffix):
    """返回 'red' / 'orange' / 'blue'"""
    if cat == "PE_Volume_high":
        return 'red' if (suffix and '甲' in suffix) else 'orange'
    if cat in HIGH_WEIGHT_CATEGORIES:
        return 'red'
    if cat in MEDIUM_WEIGHT_CATEGORIES:
        return 'orange'
    return 'blue'


def compute_rarity(sym_date_items, sorted_dates, today, n_today):
    idx = sorted_dates.index(today) if today in sorted_dates else -1
    window = sorted_dates[idx + 1: idx + 1 + LOOKBACK_TRADING_DAYS] if idx >= 0 \
        else sorted_dates[:LOOKBACK_TRADING_DAYS]

    counts = []
    for d in window:
        items = sym_date_items.get(d)
        if items:
            counts.append(len({c for c, _ in items}))

    active = len(counts)
    if active < MIN_HISTORY_DAYS:
        return (3.0 if n_today >= 3 else 2.0), 0.0, active, 0

    ge = sum(1 for c in counts if c >= n_today)
    p = ge / active
    typical = sorted(counts)[active // 2]

    if p <= 0.05:
        r = 3.0
    elif p <= 0.15:
        r = 2.5
    elif p <= 0.30:
        r = 2.0
    elif p <= 0.50:
        r = 1.0
    else:
        r = 0.0
    return r, p, active, typical


def compute_quality(today_items):
    colors = [category_color(c, s) for c, s in today_items]
    total = len(colors)
    if total == 0:
        return 0.0, 0, 0, 0, 0.0
    red = colors.count('red')
    orange = colors.count('orange')
    blue = colors.count('blue')
    purity = (red + orange) / total

    if purity >= 0.999:
        q = 2.0 if red >= 2 else (1.5 if red == 1 else 1.0)
    elif purity >= 0.6:
        q = 0.5
    else:
        q = 0.0
    return q, red, orange, blue, purity


def detect_bonus_markers(sym_date_items, sorted_dates, today, today_items):
    purple, red_mark, notes = 0, 0, []
    if today not in sorted_dates:
        return purple, red_mark, notes

    idx = sorted_dates.index(today)
    prev15 = sorted_dates[idx + 1: idx + 16]
    prev5 = sorted_dates[idx + 1: idx + 6]
    prev1 = sorted_dates[idx + 1] if idx + 1 < len(sorted_dates) else None

    def cats_on(d):
        return {c for c, _ in sym_date_items.get(d, [])}

    def has_jia(d):
        return any(c == "PE_Volume_high" and s and '甲' in s
                   for c, s in sym_date_items.get(d, []))

    today_cats = {c for c, _ in today_items}

    if today_cats & {"SupportLevel_Close", "SupportLevel_Over"}:
        hits = [d for d in prev15 if "PE_Volume" in cats_on(d)]
        if hits:
            purple += 1
            notes.append(f"紫｜SupportLevel + 近15日PE_Volume({hits[0]})")

    if "PE_W" in today_cats and prev1:
        pcats = cats_on(prev1)
        if pcats & {"PE_Hot", "PE_Volume"}:
            purple += 1
            notes.append("紫｜PE_W 接力(前日 Hot/Volume)")
        if pcats & {"Short", "Short_W"}:
            purple += 1
            notes.append("紫｜PE_W 接力(前日 Short)")

    if any(c == "PE_Volume_high" and s and '甲' in s for c, s in today_items):
        if any(has_jia(d) for d in prev15):
            red_mark += 1
            notes.append("红｜15日内重复 PE_Volume_high(甲)")

    if "Short" in today_cats and any(has_jia(d) for d in prev5):
        red_mark += 1
        notes.append("红｜一周内曾 PE_Volume_high(甲)")

    if (today_cats & {"Short", "Short_W"}) and \
       any(c == "PE_Volume_high" and s and '抄底' in s for c, s in today_items):
        red_mark += 1
        notes.append("红｜当日 抄底 + Short")

    return purple, red_mark, notes


def evaluate_symbol_signal(sym, resonance_count, index, today_items_map, week52_low_symbols):
    sym_date_items = index['sym_items'].get(sym, {})
    sorted_dates = index['sorted_dates']
    today = sorted_dates[0] if sorted_dates else None

    raw_items = today_items_map.get(sym, [])
    dedup = {}
    for c, s in raw_items:
        if c not in dedup or (s and not dedup[c]):
            dedup[c] = s
    today_items = sorted(dedup.items())
    n_today = len(today_items) if today_items else resonance_count

    rarity, p, active_days, typical = compute_rarity(sym_date_items, sorted_dates, today, n_today)
    quality, red, orange, blue, purity = compute_quality(today_items)
    purple_cnt, red_cnt, notes = detect_bonus_markers(sym_date_items, sorted_dates, today, today_items)

    bonus = min(purple_cnt, 2) * 0.5 + min(red_cnt, 2) * 0.5
    if sym in week52_low_symbols:
        bonus += 0.5
        notes.append("橙｜处于52周新低板块")
    bonus = min(bonus, 2.0)

    score = rarity + quality + bonus

    if score >= 4.5:
        level = 3
    elif score >= 3.5:
        level = 2
    elif score >= 2.0:
        level = 1
    else:
        level = 0

    if today_items and purity < 0.5 and level > 0:
        level -= 1

    cat_desc = "、".join(
        f"{c}{('[' + s + ']') if s else ''}({category_color(c, s)})" for c, s in today_items
    ) or "无当日明细"

    if active_days >= MIN_HISTORY_DAYS:
        hist_desc = (f"近{active_days}个有记录交易日：中位数 {typical} 组；"
                     f"历史上 ≥{n_today} 组的天数占比 {p*100:.0f}%")
    else:
        hist_desc = f"历史样本仅 {active_days} 天（几乎不出现）"

    reason = (
        f"【{sym}】共振 {resonance_count} 组  评级：{BADGE_TEXT[level] or '—'} ({BADGE_NAME[level]})\n"
        f"总分 {score:.1f} = 稀有度 {rarity:.1f} + 质量 {quality:.1f} + 加成 {bonus:.1f}\n"
        f"── 历史基线 ──\n{hist_desc}\n"
        f"── 今日构成 ──\n红 {red} / 橙 {orange} / 蓝 {blue}（红橙占比 {purity*100:.0f}%）\n{cat_desc}\n"
    )
    if notes:
        reason += "── 额外标记 ──\n" + "\n".join(notes)

    return {'level': level, 'score': score, 'badge': BADGE_TEXT[level], 'reason': reason.strip()}


# ======================================================================
# “转折”检测
# ======================================================================
def _fmt_day_items(items):
    dedup = {}
    for c, s in items:
        if c not in dedup or (s and not dedup[c]):
            dedup[c] = s
    return "、".join(f"{c}{('[' + s + ']') if s else ''}" for c, s in sorted(dedup.items()))


def _turn_key_hits(cats, cnt):
    if cnt <= 2:
        hits = cats & TURN_LEVEL2_KEYS
        return hits, len(hits) >= 1
    hits = cats & TURN_LEVEL3_KEYS
    return hits, len(hits) >= 2


def _score_turning(rec, week52_low_symbols):
    notes = []
    score = 0.0

    score += min(rec['drop'], 3) * 1.0
    notes.append(f"跌幅 {rec['drop']} 档 → +{min(rec['drop'], 3) * 1.0:.1f}")

    extra_streak = min(max(rec['streak'] - TURN_MIN_STREAK, 0), 3)
    if extra_streak:
        score += extra_streak * 0.5
        notes.append(f"平台期 {rec['streak']} 天(超出基准 {extra_streak} 天) → +{extra_streak * 0.5:.1f}")

    kb = min(rec['key_max'], 3) * 0.4
    score += kb
    notes.append(f"平台期单日关键项最多 {rec['key_max']} 个 → +{kb:.1f}")

    if rec['plateau_red']:
        score += 0.5
        notes.append("平台期含红色高权重分组 → +0.5")

    if rec['symbol'] in week52_low_symbols:
        score += 0.5
        notes.append("处于52周新低板块 → +0.5")

    if rec['to_n'] == 0:
        score += 0.5
        notes.append("信号完全消失(0项) → +0.5")

    if score >= 4.5:
        level = 3
    elif score >= 3.5:
        level = 2
    elif score >= 2.5:
        level = 1
    else:
        level = 0
    return score, level, notes


def detect_turning_points(index, week52_low_symbols):
    sym_items = index['sym_items']
    sorted_dates = index['sorted_dates']
    if not sorted_dates:
        return []

    pos = {d: i for i, d in enumerate(sorted_dates)}
    recent = set(sorted_dates[:min(TURN_RECENT_DAYS, len(sorted_dates))])
    results = []

    for sym, date_map in sym_items.items():
        rec_dates = sorted(date_map.keys(), key=lambda d: pos.get(d, 10 ** 9))
        if len(rec_dates) < TURN_MIN_STREAK:
            continue
        cats_of = {d: {c for c, _ in date_map[d]} for d in rec_dates}
        cnt_of = {d: len(cats_of[d]) for d in rec_dates}

        candidates = []
        if TURN_ALLOW_DROP_TO_ZERO:
            newest = rec_dates[0]
            p = pos.get(newest)
            if p is not None and p >= 1:
                zero_day = sorted_dates[p - 1]
                if zero_day in recent:
                    candidates.append((zero_day, 0, 0))
        for i, d in enumerate(rec_dates):
            if d not in recent:
                break
            candidates.append((d, cnt_of[d], i + 1))

        best = None
        for d, m, p_start in candidates:
            if TURN_REQUIRE_NO_RECOVERY:
                newer = [x for x in rec_dates if pos[x] < pos[d]]
                if any(cnt_of[x] > m for x in newer):
                    continue

            plateau = []
            prev = d
            j = p_start
            while j < len(rec_dates):
                cd = rec_dates[j]
                if pos[cd] - pos[prev] > TURN_MAX_GAP:
                    break
                cnt = cnt_of[cd]
                if cnt <= m or cnt < 2:
                    break
                hits, ok = _turn_key_hits(cats_of[cd], cnt)
                if not ok:
                    break
                plateau.append((cd, cnt, len(hits)))
                prev = cd
                j += 1

            if len(plateau) < TURN_MIN_STREAK:
                continue

            counts = [c for _, c, _ in plateau]
            from_n = min(counts)
            drop = from_n - m
            if drop < TURN_MIN_DROP:
                continue

            plateau_red = any(
                any(category_color(c, s) == 'red' for c, s in date_map[pd])
                for pd, _, _ in plateau
            )

            rec = {
                'symbol': sym,
                'date': d,
                'to_n': m,
                'from_n': from_n,
                'from_max': max(counts),
                'drop': drop,
                'streak': len(plateau),
                'key_max': max(k for _, _, k in plateau),
                'plateau': plateau,
                'plateau_red': plateau_red,
                'drop_items': _fmt_day_items(date_map.get(d, [])) or "（当日无任何记录）",
            }
            best = rec
            break

        if not best:
            continue

        score, level, notes = _score_turning(best, week52_low_symbols)
        best['score'] = score
        best['level'] = level
        best['badge'] = TURN_BADGE[level]

        plateau_lines = "\n".join(
            f"  {pd} ({c}项)：{_fmt_day_items(sym_items[sym].get(pd, []))}"
            for pd, c, _ in reversed(best['plateau'])
        )
        best['reason'] = (
            f"【{sym}】转折：平台 {best['from_n']}"
            f"{'~' + str(best['from_max']) if best['from_max'] != best['from_n'] else ''} 项 × "
            f"{best['streak']} 天  →  {best['to_n']} 项（减少 {best['drop']} 档）\n"
            f"评级：{best['badge']} ({TURN_NAME[level]})  总分 {score:.1f}\n"
            f"── 打分明细 ──\n" + "\n".join(notes) + "\n"
            f"── 平台期（旧→新）──\n{plateau_lines}\n"
            f"── 转折日 {best['date']} ({best['to_n']}项) ──\n  {best['drop_items']}"
        )
        results.append(best)

    results.sort(key=lambda r: (-r['score'], -r['drop'], r['symbol']))
    return results


# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------
class GroupWindow(QMainWindow):
    wl_done = pyqtSignal(dict)          # 工作线程 → 主线程 的结果通道

    def __init__(self, keyword_colors, sector_data, compare_data, json_data, earning_history_data):
        super().__init__()
        self.keyword_colors = keyword_colors
        self.sector_data = sector_data
        self.compare_data = compare_data
        self.json_data = json_data
        self.earning_history_data = earning_history_data

        # 用于 Symbol 检索定位的控件映射：{ 'AAPL': [(container, button), ...], ... }
        self.symbol_widgets_map = defaultdict(list)

        # ===== 共振 =====
        self.week52_low_symbols = load_52week_low_symbols(CONFIG_PATH)
        self.resonance_data = calculate_frequency_data(self.earning_history_data, self.week52_low_symbols)

        self.history_index = build_symbol_history_index(self.earning_history_data)
        self.today_items_map = get_today_items(self.earning_history_data)
        self.latest_date = self.history_index['sorted_dates'][0] if self.history_index['sorted_dates'] else ""

        self.symbol_marks = {}
        for item in self.resonance_data:
            for sym in item['symbols']:
                try:
                    self.symbol_marks[sym] = evaluate_symbol_signal(
                        sym, item['count'], self.history_index,
                        self.today_items_map, self.week52_low_symbols
                    )
                except Exception as e:
                    print(f"评估 {sym} 失败: {e}")
                    self.symbol_marks[sym] = {'level': 0, 'score': 0.0, 'badge': '', 'reason': ''}
            item['symbols'] = sorted(item['symbols'],
                                     key=lambda s: (-self.symbol_marks[s]['score'], s))

        # ===== 转折 =====
        try:
            self.turning_data = detect_turning_points(self.history_index, self.week52_low_symbols)
        except Exception as e:
            print(f"转折检测失败: {e}")
            self.turning_data = []

        self.list_turning = [r['symbol'] for r in self.turning_data]
        self.list_resonance = [sym for item in self.resonance_data for sym in item['symbols']]

        # ===== ★ 持仓 =====
        self.positions = {}
        self.positions_meta = {}
        self.hold_sort_mode = 'alpha'
        self.hold_sort_desc = HOLD_DEFAULT_DESC['alpha']
        self._hold_widget_refs = []
        self.load_positions_data()
        self.list_holdings = self._sorted_holdings()

        # ===== 导航作用域 =====
        main_list = self.list_turning + self.list_resonance
        if main_list:
            self.active_source = 'main'
            self.symbol_manager = SymbolManager(main_list)
        else:
            self.active_source = 'holdings'
            self.symbol_manager = SymbolManager(self.list_holdings)

        self.init_ui()

    # ==================================================================
    # 持仓数据
    # ==================================================================
    def load_positions_data(self):
        try:
            pos, meta = load_all_positions()
        except Exception as e:
            print(f"[FT] 读取持仓失败: {e}")
            pos, meta = {}, {}
        clean = {}
        for k, v in (pos or {}).items():
            sym = str(k).strip().upper()
            if sym and isinstance(v, dict):
                clean[sym] = v
        self.positions = clean
        self.positions_meta = meta or {}

    def _sorted_holdings(self):
        syms = list(self.positions.keys())
        mode, desc = self.hold_sort_mode, self.hold_sort_desc
        if mode == 'alpha':
            syms.sort(reverse=desc)
            return syms
        keys = HOLD_SORT_KEYS.get(mode, ('gainloss',))

        def sort_key(s):
            v = position_num(self.positions.get(s, {}), *keys)
            missing = v is None
            val = 0.0 if missing else float(v)
            # 无数据的一律排最后；其余按方向排，最后用代码兜底保证稳定
            return (1 if missing else 0, -val if desc else val, s)

        syms.sort(key=sort_key)
        return syms

    def reload_positions(self):
        self.load_positions_data()
        self._apply_sort()
        ts = self.positions_meta.get('updated_at_str', '')
        self.statusBar().showMessage(
            f"已重新读取持仓：{len(self.positions)} 只 ｜ 数据时间 {ts or '未知'}", 8000)

    # ------------------------------------------------------------------
    def init_ui(self):
        self.setWindowTitle("持仓 / 多组共振 / 转折")
        self.setGeometry(100, 100, 1600, 1000)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        legend = QLabel(
            "【持仓】读取 firstrade_positions.json；点上方按钮切换排序（同一按钮再点一次切升/降序），"
            "排序结果决定图表里左右键的浏览顺序；按 R 键重新读盘。\n"
            "【共振】🔥★★★ 极罕见且信号极强（红框）｜ ★★ 罕见/高质量（黄框）｜ ★ 值得一看（蓝框）｜ 无标记 = 常态（灰框）\n"
            f"【转折】连续 ≥{TURN_MIN_STREAK} 天保持多项关键信号后，突然减项（如 4项→2项 / 2项→1项）；"
            "按钮上的 4→2 表示“平台4项 → 当日2项”，鼠标悬停可看平台期逐日明细。"
            f"  只显示最近 {TURN_RECENT_DAYS} 个交易日内发生的转折。"
        )
        legend.setStyleSheet("color:#9AA5B1; font-size:14px; padding:6px 10px;")
        legend.setWordWrap(True)
        layout.addWidget(legend)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        content = QWidget()
        self.scroll_area.setWidget(content)
        main_lay = QHBoxLayout(content)

        self._build_holdings_section(main_lay)       # ★ 持仓放最前
        self._build_turning_section(main_lay)
        self._build_resonance_sections(main_lay)
        main_lay.addStretch(1)

        # 快捷键
        QShortcut(QKeySequence(Qt.Key.Key_Slash), self).activated.connect(self.show_search_dialog)
        QShortcut(QKeySequence(Qt.Key.Key_A), self).activated.connect(self.add_current_to_watchlist)
        QShortcut(QKeySequence(Qt.Key.Key_R), self).activated.connect(self.reload_positions)
        self.wl_done.connect(self._on_wl_done)
        self.statusBar().showMessage(
            "提示：/ 搜索 ｜ a 加自选 ｜ R 重新读取持仓 ｜ 右键卡片有更多操作", 8000)

        self.apply_stylesheet()

    # ==================================================================
    # ★ 持仓分组
    # ==================================================================
    def _build_holdings_section(self, main_lay):
        self.hold_container = QWidget()
        v = QVBoxLayout(self.hold_container)
        v.setContentsMargins(10, 0, 10, 0)

        self.hold_title = QLabel("")
        self.hold_title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        self.hold_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.hold_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.sort_buttons = {}
        for mode, label in HOLD_SORT_MODES:
            b = QPushButton(label)
            b.setFixedWidth(74)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _=False, m=mode: self.on_sort_clicked(m))
            self.sort_buttons[mode] = b
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.hold_body = QHBoxLayout()
        v.addLayout(self.hold_body)
        v.addStretch(1)

        main_lay.addWidget(self.hold_container)
        self._add_separator(main_lay)

        self._refresh_holdings_body()
        self._update_hold_header()

    def _update_hold_header(self):
        arrow = '↓' if self.hold_sort_desc else '↑'
        label = HOLD_SORT_LABEL.get(self.hold_sort_mode, self.hold_sort_mode)
        ts = self.positions_meta.get('updated_at_str', '')
        self.hold_title.setText(f"持仓 ({len(self.positions)}只)  排序：{label}{arrow}")
        self.hold_title.setToolTip(f"数据文件：firstrade_positions.json\n更新时间：{ts or '未知'}\n"
                                   f"（按 R 键重新读盘）")
        for mode, btn in self.sort_buttons.items():
            active = (mode == self.hold_sort_mode)
            btn.setText(f"{HOLD_SORT_LABEL[mode]}{(' ' + arrow) if active else ''}")
            btn.setObjectName("SortBtnOn" if active else "SortBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def on_sort_clicked(self, mode):
        if mode == self.hold_sort_mode:
            self.hold_sort_desc = not self.hold_sort_desc
        else:
            self.hold_sort_mode = mode
            self.hold_sort_desc = HOLD_DEFAULT_DESC.get(mode, True)
        self._apply_sort()
        arrow = '降序' if self.hold_sort_desc else '升序'
        self.statusBar().showMessage(
            f"持仓排序：{HOLD_SORT_LABEL[self.hold_sort_mode]} {arrow}"
            f"（图表左右键将按此顺序浏览）", 6000)

    def _apply_sort(self):
        cur = self.symbol_manager.current_symbol() if self.active_source == 'holdings' else None
        self.list_holdings = self._sorted_holdings()
        self._refresh_holdings_body()
        self._update_hold_header()
        if self.active_source == 'holdings':
            self.symbol_manager.update_symbols(self.list_holdings)
            if cur:
                self.symbol_manager.set_current_symbol(cur)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                self._clear_layout(sub)
                sub.deleteLater()

    def _refresh_holdings_body(self):
        # 先把旧控件从检索索引里摘掉，避免 / 搜索命中已销毁的对象
        for sym, container, _btn in self._hold_widget_refs:
            lst = self.symbol_widgets_map.get(sym)
            if lst:
                remain = [t for t in lst if t[0] is not container]
                if remain:
                    self.symbol_widgets_map[sym] = remain
                else:
                    self.symbol_widgets_map.pop(sym, None)
        self._hold_widget_refs = []

        self._clear_layout(self.hold_body)

        if not self.positions:
            tip = QLabel("无持仓数据\n请在 Chrome 插件里点\n「手动抓取全部持仓」\n然后按 R 刷新")
            tip.setStyleSheet("color:#888; font-size:15px; padding:12px;")
            self.hold_body.addWidget(tip)
            return

        items = self.list_holdings
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN]
                      for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout()
            col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for sym in chunk:
                col.addWidget(self._create_holding_widget(sym))
            col.addStretch(1)
            self.hold_body.addLayout(col)

    def _create_holding_widget(self, sym):
        rec = self.positions.get(sym, {})
        gl_txt = str(rec.get('gainloss') or '').strip()
        cost_txt = str(rec.get('cost') or '').strip()
        gl_num = position_num(rec, 'gainloss', 'gainlossPercent')

        parts = []
        if gl_txt:
            parts.append(gl_txt)
        if cost_txt:
            parts.append(fmt_money(cost_txt))
        disp = '  '.join(parts) or ' '

        if gl_num is None or gl_num == 0:
            style = 'Hold_Flat'
        else:
            style = 'Hold_Up' if gl_num > 0 else 'Hold_Dn'

        return self.create_symbol_widget(
            sym, override_text=disp, force_style=style,
            tooltip=self._holding_tooltip(sym),
            source='holdings', track=self._hold_widget_refs)

    def _holding_tooltip(self, sym):
        rec = self.positions.get(sym) or {}
        lst = self.list_holdings
        idx = lst.index(sym) + 1 if sym in lst else 0

        def g(key, label):
            v = rec.get(key)
            if v in (None, '', '--'):
                return None
            return f"{label} {v}"

        lines = [f"【{sym}】持仓"]
        row1 = [x for x in (g('quantity', '数量'), g('avg_cost', '均价'),
                            g('cost', '成本'), g('market_value', '市值')) if x]
        if row1:
            lines.append('｜'.join(row1))
        row2 = [x for x in (g('day_change', '今日'), g('gainloss', '总盈亏'),
                            g('gainloss_amount', '金额'), g('allocation', '仓位')) if x]
        if row2:
            lines.append('｜'.join(row2))
        lines.append(f"排序：{HOLD_SORT_LABEL[self.hold_sort_mode]} "
                     f"{'降序↓' if self.hold_sort_desc else '升序↑'}（第 {idx}/{len(lst)}）")
        ts = self.positions_meta.get('updated_at_str')
        if ts:
            lines.append(f"数据更新：{ts}")
        return "\n".join(lines)

    # ==================================================================
    # 搜索定位
    # ==================================================================
    def show_search_dialog(self):
        text, ok = QInputDialog.getText(self, "搜索 Symbol", "请输入 Symbol（回车确认）:")
        if ok and text.strip():
            self.search_and_locate_symbol(clean_ticker(text.strip()).upper())

    def search_and_locate_symbol(self, symbol):
        widgets = self.symbol_widgets_map.get(symbol)
        if not widgets:
            QMessageBox.information(self, "未找到", f"未在当前列表中找到: {symbol}")
            return
        primary_container, _ = widgets[0]
        self.scroll_area.ensureWidgetVisible(primary_container, 150, 150)
        self.symbol_manager.set_current_symbol(symbol)
        for _, btn in widgets:
            self.flash_highlight(btn)

    def flash_highlight(self, btn):
        highlight_style = "border: 3px solid #FFD700 !important;"
        state = {"count": 0, "on": False}

        def toggle():
            try:
                if state["count"] >= 6:
                    btn.setStyleSheet("")
                    return
                btn.setStyleSheet(highlight_style if not state["on"] else "")
            except RuntimeError:
                return
            state["on"] = not state["on"]
            state["count"] += 1
            QTimer.singleShot(250, toggle)

        toggle()

    # ==================================================================
    def _build_turning_section(self, main_lay):
        col_lay = QHBoxLayout()
        strong_n = sum(1 for r in self.turning_data if r['level'] > 0)
        title = f"转折 ({len(self.turning_data)}只 / ★{strong_n})"
        main_lay.addWidget(self._create_section_container(title, col_lay))

        if not self.turning_data:
            tip = QLabel("最近无转折信号")
            tip.setStyleSheet("color:#888; font-size:16px; padding:12px;")
            col_lay.addWidget(tip)
        else:
            items = self.turning_data
            for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN]
                          for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for r in chunk:
                    date_tag = "" if r['date'] == self.latest_date else f" {r['date'][5:]}"
                    disp = f"{r['from_n']}→{r['to_n']}{date_tag} {r['badge']}".strip()
                    col.addWidget(self.create_symbol_widget(
                        r['symbol'],
                        override_text=disp,
                        force_style=f"Turn_L{r['level']}",
                        tooltip=r['reason'],
                        source='turning'
                    ))
                col.addStretch(1); col_lay.addLayout(col)

        self._add_separator(main_lay)

    def _build_resonance_sections(self, main_lay):
        for item in self.resonance_data:
            count = item['count']
            symbols = item['symbols']
            strong_n = sum(1 for s in symbols if self.symbol_marks.get(s, {}).get('level', 0) > 0)

            col_lay = QHBoxLayout()
            title = f"共振 {count} 个分组 ({len(symbols)}只 / ★{strong_n})"
            main_lay.addWidget(self._create_section_container(title, col_lay))

            for chunk in [symbols[i:i + MAX_ITEMS_PER_COLUMN]
                          for i in range(0, len(symbols), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for sym in chunk:
                    mark = self.symbol_marks.get(sym, {'level': 0, 'badge': '', 'reason': ''})
                    base_text = self.compare_data.get(sym, '')
                    disp = f"{base_text} {mark['badge']}".strip()
                    col.addWidget(self.create_symbol_widget(
                        sym,
                        override_text=disp if disp else " ",
                        force_style=f"Reso_L{mark['level']}",
                        tooltip=mark.get('reason', ''),
                        source='resonance'
                    ))
                col.addStretch(1); col_lay.addLayout(col)

            self._add_separator(main_lay)

    # --- 辅助方法 ---
    def _create_section_container(self, title_text, layout_ref):
        c = QWidget(); v = QVBoxLayout(c); v.setContentsMargins(10, 0, 10, 0)
        t = QLabel(title_text); t.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t); v.addLayout(layout_ref); v.addStretch(1); return c

    def _add_separator(self, layout):
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(sep)

    def apply_stylesheet(self):
        button_styles = {
            "Cyan":     ("cyan", "black", "#333"),
            "Blue":     ("blue", "white", "#333"),
            "Purple":   ("purple", "white", "#333"),
            "Green":    ("green", "white", "#333"),
            "White":    ("white", "black", "#333"),
            "Yellow":   ("yellow", "black", "#333"),
            "Orange":   ("orange", "black", "#333"),
            "Red":      ("red", "black", "#333"),
            "Black":    ("black", "white", "#333"),
            "Default":  ("#111111", "gray", "#333"),
            # 共振
            "Reso_L0":  ("#111111", "#D8DEE9", "#3A3A3A"),
            "Reso_L1":  ("#10222A", "#D8DEE9", "#88C0D0"),
            "Reso_L2":  ("#2C2411", "#F2E3B4", "#EBCB8B"),
            "Reso_L3":  ("#3B171C", "#FFD5D9", "#BF616A"),
            # 转折
            "Turn_L0":  ("#111111", "#D8DEE9", "#3A3A3A"),
            "Turn_L1":  ("#13251C", "#D8E9DE", "#A3BE8C"),
            "Turn_L2":  ("#241B2C", "#EBD9F2", "#B48EAD"),
            "Turn_L3":  ("#3B171C", "#FFD5D9", "#BF616A"),
            # ★ 持仓（红涨绿跌，与 Chart 一致）
            "Hold_Up":  ("#3B171C", "#FFD5D9", "#BF616A"),
            "Hold_Dn":  ("#13251C", "#D8E9DE", "#A3BE8C"),
            "Hold_Flat": ("#111111", "#D8DEE9", "#3A3A3A"),
        }
        strong_set = {"Reso_L1", "Reso_L2", "Reso_L3",
                      "Turn_L1", "Turn_L2", "Turn_L3",
                      "Hold_Up", "Hold_Dn"}
        qss = ""
        for name, (bg, fg, border) in button_styles.items():
            strong = name in strong_set
            bw = 2 if strong else 1
            weight = "bold" if strong else "normal"
            qss += (f"QPushButton#{name} {{ background-color:{bg}; color:{fg}; font-size:16px; "
                    f"padding:5px; border:{bw}px solid {border}; border-radius:4px; "
                    f"text-align:left; padding-left:8px; font-weight:{weight}; }}\n")
            qss += f"QPushButton#{name}:hover {{ background-color: {self.lighten_color(bg)}; }}\n"

        # ★ 排序按钮
        qss += ("QPushButton#SortBtn { background-color:#2E3440; color:#D8DEE9; font-size:13px; "
                "border:1px solid #4C566A; border-radius:4px; padding:3px 4px; text-align:center; }\n"
                "QPushButton#SortBtn:hover { background-color:#3B4252; }\n"
                "QPushButton#SortBtnOn { background-color:#4C566A; color:#ECEFF4; font-size:13px; "
                "font-weight:bold; border:1px solid #88C0D0; border-radius:4px; "
                "padding:3px 4px; text-align:center; }\n"
                "QPushButton#SortBtnOn:hover { background-color:#5E81AC; }\n")

        qss += "QMenu { background-color: #2C2C2C; color: #E0E0E0; border: 1px solid #555; }\n"
        qss += ("QToolTip { background-color: #2E3440; color: #ECEFF4; "
                "border: 1px solid #4C566A; font-size: 14px; padding: 6px; }\n")
        self.setStyleSheet(qss)

    def lighten_color(self, color_name, factor=1.35):
        color = QColor(color_name)
        if not color.isValid():
            return color_name
        h, s, l, a = color.getHslF()
        if h < 0: h = 0.0
        l = min(1.0, max(l * factor, l + 0.08))
        color.setHslF(h, s, l, a)
        return color.name()

    def get_button_style_name(self, symbol, force_default=False, force_style=None):
        if force_style: return force_style
        if force_default: return "Default"
        color_map = {"red": "Red", "cyan": "Cyan", "blue": "Blue", "purple": "Purple",
                     "yellow": "Yellow", "orange": "Orange", "black": "Black",
                     "white": "White", "green": "Green"}
        for color, style_name in color_map.items():
            if symbol in self.keyword_colors.get(f"{color}_keywords", []):
                return style_name
        return "Default"

    def create_symbol_widget(self, symbol, override_text=None, override_tags=None,
                             force_default=False, force_style=None, tooltip=None,
                             source=None, track=None):
        btn_text = f"{symbol} {override_text if override_text else self.compare_data.get(symbol, '')}"
        button = QPushButton(btn_text.rstrip())
        button.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        button.setObjectName(self.get_button_style_name(symbol, force_default, force_style))
        button.clicked.connect(
            lambda _=False, s=symbol, src=source: self.on_symbol_click(s, src))
        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))

        tags_info = override_tags if override_tags else self.get_tags_for_symbol(symbol)
        if isinstance(tags_info, list): tags_info = ", ".join(tags_info)

        label = ClickableLabel(tags_info)
        label.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        font_size = 16
        label.setFont(QFont("Arial", font_size))

        fm = label.fontMetrics()
        rect = fm.boundingRect(0, 0, SYMBOL_WIDGET_FIXED_WIDTH - 16, 5000,
                               Qt.TextFlag.TextWordWrap, tags_info)
        label.setFixedHeight(max(rect.height() + 12, 35))

        label.setStyleSheet(f"""
            background-color: lightyellow;
            color: black;
            font-size: {font_size}px;
            padding-left: 8px;
            padding-right: 8px;
            padding-top: 6px;
            padding-bottom: 6px;
            border-radius: 4px;
            border: 1px solid #e0e0d0;
        """)
        label.clicked.connect(lambda s=symbol, src=source: self.on_symbol_click(s, src))
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))

        if tooltip:
            button.setToolTip(tooltip)
            label.setToolTip(tooltip)

        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(4)
        vlay.addWidget(button)
        vlay.addWidget(label)
        vlay.addStretch()
        container.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)

        clean_sym = clean_ticker(symbol).upper()
        self.symbol_widgets_map[clean_sym].append((container, button))
        if track is not None:
            track.append((clean_sym, container, button))
        return container

    def get_tags_for_symbol(self, symbol):
        for item in self.json_data.get("stocks", []) + self.json_data.get("etfs", []):
            if item.get("symbol") == symbol: return item.get("tag", "无标签")
        return "无标签"

    # ==================================================================
    # 导航作用域
    # ==================================================================
    def _use_list(self, source):
        src = 'holdings' if source == 'holdings' else 'main'
        if src == self.active_source:
            return
        self.active_source = src
        lst = self.list_holdings if src == 'holdings' else (self.list_turning + self.list_resonance)
        self.symbol_manager.update_symbols(lst)

    def get_symbol_group_info(self, symbol):
        # ★ 持仓作用域优先
        if self.active_source == 'holdings' and symbol in self.positions:
            lst = self.list_holdings
            idx = lst.index(symbol) + 1 if symbol in lst else 0
            rec = self.positions.get(symbol, {})
            bits = []
            gl = str(rec.get('gainloss') or '').strip()
            if gl: bits.append(gl)
            if rec.get('cost'): bits.append(fmt_money(rec.get('cost')))
            arrow = '↓' if self.hold_sort_desc else '↑'
            return (f"持仓 {' '.join(bits)} "
                    f"[{HOLD_SORT_LABEL[self.hold_sort_mode]}{arrow}] "
                    f"({idx}/{len(lst)})").replace("  ", " ").strip()

        for i, r in enumerate(self.turning_data):
            if r['symbol'] == symbol:
                return (f"转折 {r['from_n']}→{r['to_n']} @{r['date']} {r['badge']} "
                        f"({i + 1}/{len(self.turning_data)})")

        for item in self.resonance_data:
            if symbol in item['symbols']:
                idx = item['symbols'].index(symbol)
                badge = self.symbol_marks.get(symbol, {}).get('badge', '')
                badge_str = f" {badge}" if badge else ""
                return f"共振{item['count']}组{badge_str} ({idx + 1}/{len(item['symbols'])})"

        curr_list = self.symbol_manager.symbols
        if symbol in curr_list:
            return f"({curr_list.index(symbol) + 1}/{len(curr_list)})"
        return ""

    def on_symbol_click(self, symbol, source=None):
        if source:
            self._use_list(source)
        self.symbol_manager.set_current_symbol(symbol)
        pos_str = f"{symbol} {self.get_symbol_group_info(symbol)}".strip()

        shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, symbol)
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)

        try:
            plot_financial_data(
                DB_PATH, sector, symbol,
                self.compare_data.get(symbol, "N/A"),
                (shares_val, pb), marketcap, pe,
                self.json_data, '1Y', False,
                callback=self.handle_chart_callback,
                window_title_text=pos_str
            )
        except Exception as e:
            print(f"绘图错误: {e}")

    def handle_chart_callback(self, action):
        if action == 'next': QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('next'))
        elif action == 'prev': QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('prev'))

    def navigate_symbol_from_chart(self, direction):
        s = self.symbol_manager.next_symbol() if direction == 'next' else self.symbol_manager.previous_symbol()
        if s: self.on_symbol_click(s)      # 不传 source → 保持当前作用域

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
        elif event.key() == Qt.Key.Key_Down: self.navigate_symbol_from_chart('next')
        elif event.key() == Qt.Key.Key_Up: self.navigate_symbol_from_chart('prev')
        else: super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 加入 Firstrade 自选股分组
    # ------------------------------------------------------------------
    def add_symbol_to_watchlist(self, symbol, group=None):
        if not FT_WL_ADD_OK:
            QMessageBox.warning(self, "不可用", "未找到 ft_watchlist_add.py")
            return
        symbol = clean_ticker(symbol).upper()
        if not group:
            group = choose_group_dialog(symbol, watchlist_groups(), parent=self)
            if not group:
                return
        save_last_group(group)
        self.statusBar().showMessage(f"⏳ 正在把 {symbol} 加入「{group}」…（浏览器后台执行）", 60000)
        add_symbol_async(symbol, group, on_done=lambda res: self.wl_done.emit(res), wait=45)

    def add_current_to_watchlist(self):
        sym = self.symbol_manager.current_symbol()
        if not sym:
            QMessageBox.information(self, "提示", "请先点一下某个股票卡片，或用右键菜单添加")
            return
        self.add_symbol_to_watchlist(sym)

    def _on_wl_done(self, res):
        ok = bool(res.get('ok'))
        msg = res.get('message') or ('成功' if ok else '失败')
        self.statusBar().showMessage(("✅ " if ok else "❌ ") + msg, 10000)
        try:
            notify_mac("Firstrade 自选股", msg,
                       subtitle=f"{res.get('symbol','')} → {res.get('group','')}")
        except Exception:
            pass
        if not ok:
            QMessageBox.warning(self, "添加失败", msg)

    def show_context_menu(self, symbol):
        menu = QMenu(self)

        if FT_WL_ADD_OK:
            sub = menu.addMenu("➕ 加入自选股分组")
            for g in watchlist_groups():
                sub.addAction(g).triggered.connect(
                    lambda _=False, s=symbol, gg=g: self.add_symbol_to_watchlist(s, gg))
            lg = last_group()
            if lg:
                sub.addSeparator()
                sub.addAction(f"↺ 重复上次（{lg}）").triggered.connect(
                    lambda _=False, s=symbol, gg=lg: self.add_symbol_to_watchlist(s, gg))
            menu.addSeparator()

        menu.addAction("查看历史明细").triggered.connect(lambda: execute_external_script('earning', symbol))
        menu.addAction("查相似").triggered.connect(lambda: execute_external_script('similar', symbol))
        menu.addAction("富途查询").triggered.connect(lambda: execute_external_script('futu', symbol))
        menu.addSeparator()
        menu.addAction("编辑 Tags").triggered.connect(lambda: execute_external_script('tags', symbol))
        menu.addSeparator()
        menu.addAction("打开 High/Low 面板").triggered.connect(lambda: execute_external_script('highlow', symbol))
        if symbol in self.positions:
            menu.addSeparator()
            menu.addAction("🔄 重新读取持仓 (R)").triggered.connect(self.reload_positions)
        menu.exec(QCursor.pos())

    def closeEvent(self, event):
        self.symbol_manager.reset(); QApplication.quit(); event.accept()


if __name__ == '__main__':
    try:
        colors = load_json(COLORS_PATH)
        desc = load_json(DESCRIPTION_PATH)
        sects = load_json(SECTORS_ALL_PATH)
        comp = load_text_data(COMPARE_DATA_PATH)
        earn_hist = load_json(EARNING_HISTORY_PATH)

        app = QApplication(sys.argv)
        win = GroupWindow(colors, sects, comp, desc, earn_hist)
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"启动失败: {e}")