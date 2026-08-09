import sys
import json
import os
import sqlite3
import re
from collections import OrderedDict, defaultdict
import subprocess

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- PyQt6 引入 ---
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QLabel, QFrame,
    QMenu, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt6.QtGui import QCursor, QColor, QFont, QShortcut, QKeySequence

# --- 新增: 导入 Tiger_API ---
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Selenium"))
try:
    from pre_after import get_pre_after_changes
except ImportError as e:
    print(f"导入 pre_after 失败: {e}")
    def get_pre_after_changes(top_n=10):  # 兜底，防止崩溃
        return []

try:
    from Tiger_API import _get_global_fetcher
except ImportError as e:
    print(f"导入 Tiger_API 失败: {e}")

# 外部绘图函数
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
from Chart_input_single import plot_financial_data

# ----------------------------------------------------------------------
# 常量 / 全局配置
# ----------------------------------------------------------------------
MAX_ITEMS_PER_COLUMN = 9
SYMBOL_WIDGET_FIXED_WIDTH = 220

# 文件路径
HIGH_LOW_PATH = os.path.join(BASE_CODING_DIR, "News", "HighLow.txt")
CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")
COLORS_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Colors.json")
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
HIGH_LOW_5Y_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "HighLow.txt")
VOLUME_HIGH_PATH = os.path.join(BASE_CODING_DIR, "News", "0.5Y_volume_high.txt")
COMPARE_ETFS_PATH = os.path.join(BASE_CODING_DIR, "News", "CompareETFs.txt")
COMPARE_STOCK_PATH = os.path.join(BASE_CODING_DIR, "News", "CompareStock.txt")
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")

# 52周新低判定：以下板块内的 symbol 视为符合 52week_low 筛选
WEEK52_LOW_SECTORS = {
    "Basic_Materials", "Real_Estate", "Energy", "Technology",
    "Consumer_Cyclical", "Utilities", "Consumer_Defensive",
    "Industrials", "Communication_Services", "Financial_Services",
    "Healthcare"
}

# 新增：10年新高数据路径
NEW_HIGH_10Y_PRIMARY_PATH = os.path.join(BASE_CODING_DIR, "News", "10Y_newhigh_stock.txt")
NEW_HIGH_10Y_BACKUP_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "10Y_newhigh_stock.txt")

# ======================================================================
# 【新增】多组共振 —— 信号强度评估配置
# LOOKBACK_TRADING_DAYS = 120	稀有度回看窗口	想更看"近期习惯"就调到 60；想看长期基线调到 250
# MIN_HISTORY_DAYS = 5	样本太少的判定门槛	保持
# HIGH_WEIGHT_CATEGORIES / MEDIUM_WEIGHT_CATEGORIES	红/橙分类	想把某个组升权就搬到 HIGH 集合
# compute_rarity 里的 0.05 / 0.15 / 0.30 / 0.50	稀有度分档	如果 ★ 太多就把阈值调紧（例如 0.03/0.10/0.20/0.35）
# evaluate_symbol_signal 里 4.5 / 3.5 / 2.0	星级门槛	如果第一次跑发现 ★ 满屏，把 2.0 抬到 2.5；🔥 太少就把 4.5 降到 4.0
# ======================================================================
IGNORE_GROUPS = {"_Tag_Blacklist", "no_season"}

# 与 Check_Earning_history.py 的配色口径保持一致
HIGH_WEIGHT_CATEGORIES = {           # 红色：高权重
    "PE_Volume", "Short", "Short_W", "PE_Volume_high", 
    "SupportLevel_Over", "PE_Deeper", "PE_Deep"
}
MEDIUM_WEIGHT_CATEGORIES = {         # 橙色：中权重
    "PE_Volume_up", "PE_W", "SupportLevel_Close", "PE_Hot",
    "OverSell_W", "season"
}
# 其余 (PE_valid / PE_invalid / Strategy...) 视为蓝色：低权重

LOOKBACK_TRADING_DAYS = 120   # 稀有度回看窗口（交易日）
MIN_HISTORY_DAYS = 5          # 历史样本少于该值 → 视为“极少出现”

BADGE_TEXT = {0: "", 1: "★", 2: "★★", 3: "🔥★★★"}
BADGE_NAME = {0: "常态", 1: "值得一看", 2: "罕见/高质量", 3: "极罕见且极强"}


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

    def reset(self):
        self.current_index = -1

# ----------------------------------------------------------------------
# 工具函数
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

def calculate_frequency_data(history_data, week52_low_symbols=None):
    """计算多组共振（次数统计）数据"""
    if week52_low_symbols is None:
        week52_low_symbols = set()

    excluded_groups = {"no_season", "_Tag_Blacklist"}
    support_level_groups = {"SupportLevel_Close", "SupportLevel_Over"}
    source_groups = {
        "Short", "Short_W", "Strategy12", "Strategy34", "OverSell_W",
        "PE_Deep", "PE_Deeper", "PE_W", "PE_valid", "PE_invalid",
        "PE_low", "PE_lower", "PE_lowest",
        "PE_Volume", "PE_Volume_up", "PE_Hot", "PE_Volume_high", "season"
    }

    pe_hot_sources = {
        "PE_Deep", "PE_Deeper", "PE_W", "OverSell_W",
        "PE_valid", "PE_invalid", "season"
    }

    pe_chaodi_sources = {"PE_Null"}

    symbol_groups = {}
    symbols_with_chaodi = set()

    # 1. 遍历所有分组
    for group, date_map in history_data.items():
        if group in excluded_groups:
            continue
        if not date_map:
            continue

        sorted_dates = sorted(date_map.keys(), reverse=True)
        latest_date = sorted_dates[0]
        symbols = date_map[latest_date]

        for s in symbols:
            if "抄底" in s:
                symbols_with_chaodi.add(clean_ticker(s).upper())

        clean_symbols = set(clean_ticker(s).upper() for s in symbols)

        for sym in clean_symbols:
            if sym not in symbol_groups:
                symbol_groups[sym] = set()
            symbol_groups[sym].add(group)

    # --- 为符合 52week_low 的 symbol 追加一个虚拟分组，使共振次数 +1 ---
    for sym in list(symbol_groups.keys()):
        if sym in week52_low_symbols:
            symbol_groups[sym].add("52week_low")

    # 按次数分组，并过滤掉无意义的 2 次共振
    count_to_symbols = {}
    for sym, groups in symbol_groups.items():

        if sym in symbols_with_chaodi:
            groups = groups - pe_chaodi_sources

        count = len(groups)
        if count >= 2:
            if count == 2:
                has_support = not groups.isdisjoint(support_level_groups)
                has_source = not groups.isdisjoint(source_groups)
                if has_support and has_source:
                    continue

            if count not in count_to_symbols:
                count_to_symbols[count] = []
            count_to_symbols[count].append(sym)

    result = []
    for count in sorted(count_to_symbols.keys(), reverse=True):
        result.append({
            'count': count,
            'symbols': sorted(count_to_symbols[count])
        })
    return result

# ======================================================================
# 【新增】Earning_History 索引 & 信号强度评估
# ======================================================================

def build_symbol_history_index(history_data):
    """
    构建 symbol 维度的历史索引
    返回:
        sym_items     : dict[symbol][date] -> [(group, suffix), ...]
        sorted_dates  : 全局交易日列表（降序）
    """
    sym_items = defaultdict(dict)
    all_dates = set()

    for group, date_map in (history_data or {}).items():
        if group in IGNORE_GROUPS or not isinstance(date_map, dict):
            continue
        for date_str, symbols in date_map.items():
            if not isinstance(symbols, list):
                continue
            all_dates.add(date_str)
            for raw in symbols:
                sym, suf = split_symbol_suffix(raw)
                sym_items[sym].setdefault(date_str, []).append((group, suf))

    return {
        'sym_items': sym_items,
        'sorted_dates': sorted(all_dates, reverse=True)
    }


def get_today_items(history_data):
    """
    按每个分组“各自的最新日期”汇总每个 symbol 当日命中的分组（与共振统计口径一致）
    返回 dict[symbol] -> [(group, suffix), ...]
    """
    today_items = defaultdict(list)
    for group, date_map in (history_data or {}).items():
        if group in IGNORE_GROUPS or not isinstance(date_map, dict) or not date_map:
            continue
        latest = max(date_map.keys())
        symbols = date_map.get(latest) or []
        if not isinstance(symbols, list):
            continue
        for raw in symbols:
            sym, suf = split_symbol_suffix(raw)
            today_items[sym].append((group, suf))
    return today_items


def category_color(cat, suffix):
    """返回 'red' / 'orange' / 'blue'（与 Check_Earning_history 口径一致）"""
    if cat == "PE_Volume_high":
        return 'red' if (suffix and '甲' in suffix) else 'orange'
    if cat in HIGH_WEIGHT_CATEGORIES:
        return 'red'
    if cat in MEDIUM_WEIGHT_CATEGORIES:
        return 'orange'
    return 'blue'


def compute_rarity(sym_date_items, sorted_dates, today, n_today):
    """
    稀有度：今天的分组数相对该 symbol 自身历史基线有多罕见
    返回 (rarity_score, p, active_days, typical_count)
    """
    idx = sorted_dates.index(today) if today in sorted_dates else -1
    if idx >= 0:
        window = sorted_dates[idx + 1: idx + 1 + LOOKBACK_TRADING_DAYS]
    else:
        window = sorted_dates[:LOOKBACK_TRADING_DAYS]

    counts = []
    for d in window:
        items = sym_date_items.get(d)
        if items:
            counts.append(len({c for c, _ in items}))

    active = len(counts)
    if active < MIN_HISTORY_DAYS:
        # 历史几乎没出现过 → 本身就极罕见
        return (3.0 if n_today >= 3 else 2.0), 0.0, active, 0

    ge = sum(1 for c in counts if c >= n_today)
    p = ge / active
    typical = sorted(counts)[active // 2]      # 中位数

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
    """今天命中的分组“颜色纯度”打分"""
    colors = [category_color(c, s) for c, s in today_items]
    total = len(colors)
    if total == 0:
        return 0.0, 0, 0, 0, 0.0
    red = colors.count('red')
    orange = colors.count('orange')
    blue = colors.count('blue')
    purity = (red + orange) / total

    if purity >= 0.999:
        if red >= 2:
            q = 2.0
        elif red == 1:
            q = 1.5
        else:
            q = 1.0
    elif purity >= 0.6:
        q = 0.5
    else:
        q = 0.0
    return q, red, orange, blue, purity


def detect_bonus_markers(sym_date_items, sorted_dates, today, today_items):
    """
    跨日接力类标记（紫色 / 红色），逻辑来自 Check_Earning_history.build_overlap_marker
    返回 (purple_cnt, red_cnt, notes)
    """
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

    # 紫：SupportLevel_* + 近15日 PE_Volume
    if today_cats & {"SupportLevel_Close", "SupportLevel_Over"}:
        hits = [d for d in prev15 if "PE_Volume" in cats_on(d)]
        if hits:
            purple += 1
            notes.append(f"紫｜SupportLevel + 近15日PE_Volume({hits[0]})")

    # 紫：PE_W 跨日接力
    if "PE_W" in today_cats and prev1:
        pcats = cats_on(prev1)
        if pcats & {"PE_Hot", "PE_Volume"}:
            purple += 1
            notes.append("紫｜PE_W 接力(前日 Hot/Volume)")
        if pcats & {"Short", "Short_W"}:
            purple += 1
            notes.append("紫｜PE_W 接力(前日 Short)")

    # 红：PE_Volume_high(甲) 15日内重复
    if any(c == "PE_Volume_high" and s and '甲' in s for c, s in today_items):
        if any(has_jia(d) for d in prev15):
            red_mark += 1
            notes.append("红｜15日内重复 PE_Volume_high(甲)")

    # 红：Short 且前一周出现过 PE_Volume_high(甲)
    if "Short" in today_cats and any(has_jia(d) for d in prev5):
        red_mark += 1
        notes.append("红｜一周内曾 PE_Volume_high(甲)")

    # 红：当日 抄底 + Short
    if (today_cats & {"Short", "Short_W"}) and \
       any(c == "PE_Volume_high" and s and '抄底' in s for c, s in today_items):
        red_mark += 1
        notes.append("红｜当日 抄底 + Short")

    return purple, red_mark, notes


def evaluate_symbol_signal(sym, resonance_count, index, today_items_map, week52_low_symbols):
    """
    综合评估一个 symbol 今天的“值得关注度”
    返回 dict: {level, score, badge, reason}
    """
    sym_date_items = index['sym_items'].get(sym, {})
    sorted_dates = index['sorted_dates']
    today = sorted_dates[0] if sorted_dates else None

    # 今天命中的分组（同一分组去重，保留有后缀的那条）
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

    # 惩罚：今天红橙占比不足一半（全靠蓝色凑数）→ 降一级
    if today_items and purity < 0.5 and level > 0:
        level -= 1

    # tooltip 文本
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

    return {
        'level': level,
        'score': score,
        'badge': BADGE_TEXT[level],
        'reason': reason.strip(),
    }


def execute_external_script(script_type, keyword):
    script_configs = {
        'similar':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Search_Similar_Tag.py'),
        'tags':     os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'futu':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'earning':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Check_Earning_history.py'),
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

def parse_high_low_file(path):
    data = OrderedDict()
    current_period, current_category = None, None
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                current_period = line[1:-1]
                data[current_period] = {'Low': [], 'High': []}
            elif line.lower() == 'low:': current_category = 'Low'
            elif line.lower() == 'high:': current_category = 'High'
            elif current_period and current_category:
                symbols = [s.strip() for s in line.split(',') if s.strip()]
                data[current_period][current_category].extend(symbols)
    return data

def parse_volume_high_file(path):
    data = OrderedDict()
    current_section = None
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            if line.startswith("===") and line.endswith("==="):
                current_section = line.replace("=", "").strip()
                data[current_section] = []
                continue
            if current_section:
                parts = line.split()
                if len(parts) >= 4:
                    data[current_section].append({
                        'symbol': parts[1],
                        'info': parts[2],
                        'tags': " ".join(parts[4:])
                    })
    return data

def parse_10y_newhigh_file(path):
    data = OrderedDict()
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line: continue
            parts = line.split()
            if len(parts) >= 2:
                category = parts[0]
                symbol = parts[1]
                info = parts[2] if len(parts) > 2 else ""
                tags = " ".join(parts[3:]) if len(parts) > 3 else ""
                if category not in data:
                    data[category] = []
                data[category].append({
                    'symbol': symbol,
                    'info': info,
                    'tags': tags
                })
    return data

def parse_etf_file(path):
    items = []
    if not os.path.exists(path): return items
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                raw_symbol_part, content_part = line.split(':', 1)
                symbol = raw_symbol_part.split('.')[0].strip()
                parts = content_part.strip().split()
                if len(parts) >= 1:
                    items.append({
                        'symbol': symbol,
                        'percentage': parts[0],
                        'tags': " ".join(parts[3:]) if len(parts) > 3 else ""
                    })
    return items

def parse_stock_file(path):
    items = []
    if not os.path.exists(path): return items
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                left_part, right_part = line.split(':', 1)
                left_tokens = left_part.strip().split()
                if len(left_tokens) < 2: continue
                raw_symbol_str = left_tokens[1]
                if '.' in raw_symbol_str:
                    symbol, suffix_info = raw_symbol_str.split('.', 1)
                else:
                    symbol, suffix_info = raw_symbol_str, ""
                right_tokens = right_part.strip().split()
                if not right_tokens: continue
                percentage = right_tokens[0]
                tags = " ".join(right_tokens[1:]) if len(right_tokens) > 1 else ""
                items.append({
                    'symbol': symbol,
                    'suffix': suffix_info,
                    'display_text': f"{suffix_info} {percentage}" if suffix_info else percentage,
                    'tags': tags
                })
    return items

def load_52week_low_symbols(path):
    """从 Sectors_panel.json 中读取指定板块下的 symbol，作为 52week_low 集合"""
    symbols = set()
    data = load_json(path)
    for sector in WEEK52_LOW_SECTORS:
        for sym in data.get(sector, {}).keys():
            symbols.add(clean_ticker(sym).upper())
    return symbols

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

def fetch_mnspp_data_from_db(db_path, symbol):
    """从数据库获取财务数据"""
    if not os.path.exists(db_path):
        return "N/A", None, "N/A", "--"
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?"
            cursor.execute(query, (symbol,))
            result = cursor.fetchone()
            if result:
                return result
            else:
                return "N/A", None, "N/A", "--"
    except Exception as e:
        print(f"查询财务数据出错: {e}")
        return "N/A", None, "N/A", "--"

# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------

class PreAfterWorker(QThread):
    data_finished = pyqtSignal(list)

    def run(self):
        try:
            data = get_pre_after_changes(top_n=10)
            self.data_finished.emit(data)
        except Exception as e:
            print(f"后台获取盘前数据失败: {e}")
            self.data_finished.emit([])


class HighLowWindow(QMainWindow):
    def __init__(self, high_low_data, keyword_colors, sector_data, compare_data, json_data,
                 high_low_5y_data, volume_high_data, etf_data, stock_data,
                 earning_history_data, newhigh_10y_data, pre_after_data):
        super().__init__()
        self.high_low_data = high_low_data
        self.keyword_colors = keyword_colors
        self.sector_data = sector_data
        self.compare_data = compare_data
        self.json_data = json_data
        self.high_low_5y_data = high_low_5y_data
        self.volume_high_data = volume_high_data
        self.etf_data = etf_data
        self.stock_data = stock_data
        self.earning_history_data = earning_history_data
        self.newhigh_10y_data = newhigh_10y_data
        self.pre_after_data = []

        # --- 启动异步线程 ---
        self.worker = PreAfterWorker()
        self.worker.data_finished.connect(self.update_pre_after_tab)
        self.worker.start()

        # 计算多组共振数据（含 52week_low 加成）
        self.week52_low_symbols = load_52week_low_symbols(CONFIG_PATH)
        self.resonance_data = calculate_frequency_data(self.earning_history_data, self.week52_low_symbols)

        # ===== 【新增】信号强度评估 + 组内按分数排序 =====
        self.history_index = build_symbol_history_index(self.earning_history_data)
        self.today_items_map = get_today_items(self.earning_history_data)
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
            # 组内：分数高的排前面，同分按字母序
            item['symbols'] = sorted(
                item['symbols'],
                key=lambda s: (-self.symbol_marks[s]['score'], s)
            )

        self.list_resonance = [sym for item in self.resonance_data for sym in item['symbols']]

        # 准备列表
        self.list_high_low = []
        for p in high_low_data.values():
            self.list_high_low.extend(p.get('Low', []) + p.get('High', []))
        self.list_high_low.extend(self.high_low_5y_data.get('5Y', {}).get('High', []))

        self.list_volume = [i['symbol'] for s in volume_high_data.values() for i in s]
        self.list_10y_newhigh = [item['symbol'] for items in self.newhigh_10y_data.values() for item in items]
        self.list_pre_after = [item['symbol'] for item in self.pre_after_data]

        self.etf_gainers = [i['symbol'] for i in self.etf_data[:24]]
        self.etf_losers = [i['symbol'] for i in self.etf_data[-24:][::-1]]
        self.list_etf = self.etf_gainers + self.etf_losers

        self.stock_gainers = [i['symbol'] for i in self.stock_data[:24]]
        self.stock_losers = [i['symbol'] for i in self.stock_data[-24:][::-1]]
        self.list_stock = self.stock_gainers + self.stock_losers

        self.symbol_manager = SymbolManager(self.list_resonance)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("High/Low & Volume Viewer")
        self.setGeometry(100, 100, 1600, 1000)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 0: 多组共振
        self.tab_resonance = QWidget()
        self._init_resonance_tab(self.tab_resonance)
        self.tabs.addTab(self.tab_resonance, "多组共振")

        # Tab 1: 盘前/盘后
        self.tab_pre_after = QWidget()
        self._init_pre_after_tab(self.tab_pre_after)
        self.tabs.addTab(self.tab_pre_after, "盘前/盘后")

        # Tab 2: Volume
        self.tab_volume = QWidget()
        self._init_volume_tab(self.tab_volume)
        self.tabs.addTab(self.tab_volume, "Volume成交额")

        # Tab 3: 10年新高
        self.tab_10y_newhigh = QWidget()
        self._init_10y_newhigh_tab(self.tab_10y_newhigh)
        self.tabs.addTab(self.tab_10y_newhigh, "10年新高")

        # Tab 4: ETFs
        self.tab_etfs = QWidget()
        self._init_etf_tab(self.tab_etfs)
        self.tabs.addTab(self.tab_etfs, "ETFs")

        # Tab 5: Stocks
        self.tab_stocks = QWidget()
        self._init_stock_tab(self.tab_stocks)
        self.tabs.addTab(self.tab_stocks, "Stocks")

        # Tab 6: High/Low
        self.tab_high_low = QWidget()
        self._init_high_low_tab(self.tab_high_low)
        self.tabs.addTab(self.tab_high_low, "High / Low")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QShortcut(QKeySequence(Qt.Key.Key_Tab), self).activated.connect(self.switch_tab)
        QShortcut(QKeySequence("Shift+Tab"), self).activated.connect(self.switch_tab_reverse)

        self.apply_stylesheet()

    def on_tab_changed(self, index):
        mapping = {
            0: self.list_resonance,
            1: self.list_pre_after,
            2: self.list_volume,
            3: self.list_10y_newhigh,
            4: self.list_etf,
            5: self.list_stock,
            6: self.list_high_low,
        }
        self.symbol_manager.update_symbols(mapping.get(index, []))

    def switch_tab(self): self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())
    def switch_tab_reverse(self): self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1 + self.tabs.count()) % self.tabs.count())

    def _init_pre_after_tab(self, parent):
        layout = QVBoxLayout(parent)
        self.scroll_pre_after = QScrollArea()
        self.scroll_pre_after.setWidgetResizable(True)
        layout.addWidget(self.scroll_pre_after)

        self.pre_after_content = QWidget()
        self.pre_after_layout = QVBoxLayout(self.pre_after_content)
        self.scroll_pre_after.setWidget(self.pre_after_content)

        self.loading_label = QLabel("正在获取盘前/盘后数据，请稍候...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pre_after_layout.addWidget(self.loading_label)

    def update_pre_after_tab(self, data):
        self.pre_after_data = data
        self.list_pre_after = [it['symbol'] for it in data]

        while self.pre_after_layout.count():
            item = self.pre_after_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not self.pre_after_data:
            tip = QLabel("⚠️ 暂无盘前/盘后数据（可能是非交易时段或拉取失败）")
            tip.setStyleSheet("color: #ccc; font-size: 18px; padding: 30px;")
            self.pre_after_layout.addWidget(tip)
            return

        main_lay = QHBoxLayout()
        self.pre_after_layout.addLayout(main_lay)

        losers = [it for it in self.pre_after_data if it['pct'] < 0]
        gainers = [it for it in self.pre_after_data if it['pct'] >= 0]

        def _build_column(title, items, parent_layout):
            col_lay = QHBoxLayout()
            parent_layout.addWidget(self._create_section_container(title, col_lay))
            for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN]
                          for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for it in chunk:
                    pct_text = f"{it['pct']:+.2f}%"
                    col.addWidget(self.create_symbol_widget(
                        it['symbol'],
                        override_text=pct_text,
                        force_default=True
                    ))
                col.addStretch(1); col_lay.addLayout(col)

        if losers:
            _build_column(f"下跌 ({len(losers)})", losers, main_lay)
            self._add_separator(main_lay)
        if gainers:
            _build_column(f"上涨 ({len(gainers)})", gainers, main_lay)

        if self.tabs.currentIndex() == 1:
            self.symbol_manager.update_symbols(self.list_pre_after)

    # --- Tab 初始化方法 ---
    def _init_resonance_tab(self, parent):
        layout = QVBoxLayout(parent)

        # 图例说明
        legend = QLabel(
            "标记规则：  🔥★★★ 极罕见且信号极强（红框）   ｜   ★★ 罕见 / 高质量（黄框）   ｜   "
            "★ 值得一看（蓝框）   ｜   无标记 = 该票的常态表现（灰框）"
            "        —— 每组内已按强度从左上到右下排序，鼠标悬停可查看判定依据"
        )
        legend.setStyleSheet("color:#9AA5B1; font-size:14px; padding:6px 10px;")
        legend.setWordWrap(True)
        layout.addWidget(legend)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)

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
                        tooltip=mark.get('reason', '')
                    ))
                col.addStretch(1); col_lay.addLayout(col)

            self._add_separator(main_lay)

    def _init_high_low_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)

        self.low_columns_layout = QHBoxLayout()
        main_lay.addWidget(self._create_section_container("新低", self.low_columns_layout))
        self._add_separator(main_lay)
        self.high_columns_layout = QHBoxLayout()
        main_lay.addWidget(self._create_section_container("新高", self.high_columns_layout))
        self._add_separator(main_lay)
        self.high_5y_columns_layout = QHBoxLayout()
        main_lay.addWidget(self._create_section_container("5Y HIGH", self.high_5y_columns_layout))

        self._populate_category_columns(self.low_columns_layout, 'Low')
        self._populate_category_columns(self.high_columns_layout, 'High')
        self._populate_5y_high_section()

    def _init_volume_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        for title, items in self.volume_high_data.items():
            col_lay = QHBoxLayout()
            main_lay.addWidget(self._create_section_container(title, col_lay))
            self._populate_volume_items(col_lay, items)
            self._add_separator(main_lay)

    def _init_10y_newhigh_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QVBoxLayout(content)

        for category, items in self.newhigh_10y_data.items():
            row_lay = QHBoxLayout()
            row_lay.addStretch(1)

            cat_label = QLabel(category)
            cat_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            cat_label.setFixedWidth(200)
            cat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cat_label.setWordWrap(True)
            cat_label.setStyleSheet("background-color: #3A3A3A; color: #E0E0E0; border-radius: 8px; padding: 15px;")

            left_vlay = QVBoxLayout()
            left_vlay.addStretch()
            left_vlay.addWidget(cat_label)
            left_vlay.addStretch()
            row_lay.addLayout(left_vlay)

            sym_lay = QHBoxLayout()
            for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for item in chunk:
                    col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['info'],
                                                            override_tags=item['tags'], force_default=True))
                col.addStretch(1)
                sym_lay.addLayout(col)

            row_lay.addLayout(sym_lay)
            row_lay.addStretch(1)

            main_lay.addLayout(row_lay)
            self._add_separator_horizontal(main_lay)

        main_lay.addStretch(1)

    def _init_etf_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        top_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Gainers", top_lay))
        self._populate_etf_grid(top_lay, self.etf_data[:24])
        self._add_separator(main_lay)
        bot_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Losers", bot_lay))
        self._populate_etf_grid(bot_lay, self.etf_data[-24:][::-1])

    def _init_stock_tab(self, parent):
        layout = QVBoxLayout(parent)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); main_lay = QHBoxLayout(content)
        top_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Gainers", top_lay))
        self._populate_stock_grid(top_lay, self.stock_data[:24])
        self._add_separator(main_lay)
        bot_lay = QHBoxLayout(); main_lay.addWidget(self._create_section_container("Top Losers", bot_lay))
        self._populate_stock_grid(bot_lay, self.stock_data[-24:][::-1])

    # --- 填充逻辑 ---
    def _populate_etf_grid(self, parent_layout, items):
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for item in chunk:
                col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['percentage'],
                                                        override_tags=item['tags'], force_default=True))
            col.addStretch(1); parent_layout.addLayout(col)

    def _populate_stock_grid(self, parent_layout, items):
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for item in chunk:
                is_earnings = any(k in (item.get('suffix') or "") for k in ["前", "后"])
                style = "Earnings" if is_earnings else "Default"
                col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['display_text'],
                                                        override_tags=item['tags'], force_style=style))
            col.addStretch(1); parent_layout.addLayout(col)

    def _populate_volume_items(self, parent_layout, items):
        for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for item in chunk:
                col.addWidget(self.create_symbol_widget(item['symbol'], override_text=item['info'],
                                                        override_tags=item['tags'], force_default=True))
            col.addStretch(1); parent_layout.addLayout(col)

    def _populate_category_columns(self, parent_layout, cat):
        groups = []
        for p, cats in self.high_low_data.items():
            syms = cats.get(cat, [])
            if not syms: continue
            for i in range(0, len(syms), MAX_ITEMS_PER_COLUMN):
                groups.append((f"{p} {cat}" + (f" ({i//MAX_ITEMS_PER_COLUMN+1})" if len(syms) > MAX_ITEMS_PER_COLUMN else ""),
                               syms[i:i+MAX_ITEMS_PER_COLUMN]))

        curr_col, curr_count = None, 0
        for title, syms in groups:
            if curr_col is None or (curr_count + len(syms) > MAX_ITEMS_PER_COLUMN):
                if curr_col: parent_layout.addLayout(curr_col)
                curr_col = QVBoxLayout(); curr_col.setAlignment(Qt.AlignmentFlag.AlignTop); curr_count = 0

            box = QGroupBox(title)
            b_lay = QVBoxLayout(box)
            b_lay.setContentsMargins(8, 35, 8, 8)
            b_lay.setSpacing(6)

            for s in syms:
                b_lay.addWidget(self.create_symbol_widget(s))

            curr_col.addWidget(box)
            curr_count += len(syms)
        if curr_col: parent_layout.addLayout(curr_col)

    def _populate_5y_high_section(self):
        syms = self.high_low_5y_data.get('5Y', {}).get('High', [])
        for chunk in [syms[i:i + MAX_ITEMS_PER_COLUMN] for i in range(0, len(syms), MAX_ITEMS_PER_COLUMN)]:
            col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
            for s in chunk: col.addWidget(self.create_symbol_widget(s))
            col.addStretch(1); self.high_5y_columns_layout.addLayout(col)

    # --- 辅助方法 ---
    def _create_section_container(self, title_text, layout_ref):
        c = QWidget(); v = QVBoxLayout(c); v.setContentsMargins(10, 0, 10, 0)
        t = QLabel(title_text); t.setFont(QFont("Arial", 20, QFont.Weight.Bold)); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t); v.addLayout(layout_ref); v.addStretch(1); return c

    def _add_separator(self, layout):
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine); sep.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(sep)

    def _add_separator_horizontal(self, layout):
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(sep)

    def apply_stylesheet(self):
        # (背景色, 文字色, 边框色)
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
            "Earnings": ("#111111", "red", "#333"),
            # ===== 多组共振专用：统一灰白标题 + 强度描边 =====
            "Reso_L0":  ("#111111", "#D8DEE9", "#3A3A3A"),
            "Reso_L1":  ("#10222A", "#D8DEE9", "#88C0D0"),
            "Reso_L2":  ("#2C2411", "#F2E3B4", "#EBCB8B"),
            "Reso_L3":  ("#3B171C", "#FFD5D9", "#BF616A"),
        }
        qss = ""
        for name, (bg, fg, border) in button_styles.items():
            strong = name in ("Reso_L1", "Reso_L2", "Reso_L3")
            bw = 2 if strong else 1
            weight = "bold" if strong else "normal"
            qss += (f"QPushButton#{name} {{ background-color:{bg}; color:{fg}; font-size:16px; "
                    f"padding:5px; border:{bw}px solid {border}; border-radius:4px; "
                    f"text-align:left; padding-left:8px; font-weight:{weight}; }}\n")
            qss += f"QPushButton#{name}:hover {{ background-color: {self.lighten_color(bg)}; }}\n"

        qss += """
            QGroupBox { 
                font-size: 18px; 
                font-weight: bold; 
                margin-top: 25px;
                border: 2px solid #555; 
                border-radius: 8px; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                padding: 0 5px; 
                left: 10px;
                top: 5px;
                color: #EEE;
            }
        """
        qss += "QMenu { background-color: #2C2C2C; color: #E0E0E0; border: 1px solid #555; }\n"
        qss += "QTabBar::tab:selected { background: #444; color: white; }\n"
        qss += "QToolTip { background-color: #2E3440; color: #ECEFF4; border: 1px solid #4C566A; font-size: 14px; padding: 6px; }\n"
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
                             force_default=False, force_style=None, tooltip=None):
        # 1. 按钮创建
        btn_text = f"{symbol} {override_text if override_text else self.compare_data.get(symbol, '')}"
        button = QPushButton(btn_text.rstrip())
        button.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        button.setObjectName(self.get_button_style_name(symbol, force_default, force_style))
        button.clicked.connect(lambda _, s=symbol: self.on_symbol_click(s))
        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))

        tags_info = override_tags if override_tags else self.get_tags_for_symbol(symbol)
        if isinstance(tags_info, list): tags_info = ", ".join(tags_info)

        # 2. 标签部分 (自适应高度)
        label = ClickableLabel(tags_info)
        label.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        font_size = 16
        font = QFont("Arial", font_size)
        label.setFont(font)

        padding_h = 16
        padding_v = 12
        fm = label.fontMetrics()
        rect = fm.boundingRect(
            0, 0,
            SYMBOL_WIDGET_FIXED_WIDTH - padding_h,
            5000,
            Qt.TextFlag.TextWordWrap,
            tags_info
        )
        calculated_height = rect.height() + padding_v
        final_height = max(calculated_height, 35)
        label.setFixedHeight(final_height)

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

        label.clicked.connect(lambda: self.on_symbol_click(symbol))
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
        return container

    def get_tags_for_symbol(self, symbol):
        for item in self.json_data.get("stocks", []) + self.json_data.get("etfs", []):
            if item.get("symbol") == symbol: return item.get("tag", "无标签")
        return "无标签"

    def get_symbol_group_info(self, symbol):
        current_tab = self.tabs.currentIndex()

        # Tab 0: 多组共振
        if current_tab == 0:
            for item in self.resonance_data:
                if symbol in item['symbols']:
                    idx = item['symbols'].index(symbol)
                    badge = self.symbol_marks.get(symbol, {}).get('badge', '')
                    badge_str = f" {badge}" if badge else ""
                    return f"共振{item['count']}组{badge_str} ({idx + 1}/{len(item['symbols'])})"

        # Tab 1: 盘前/盘后
        elif current_tab == 1:
            for i, it in enumerate(self.pre_after_data):
                if it['symbol'] == symbol:
                    return f"盘前/盘后 {it['pct']:+.2f}% ({i + 1}/{len(self.pre_after_data)})"

        # Tab 2: Volume High
        elif current_tab == 2:
            for group_name, items in self.volume_high_data.items():
                symbols_in_group = [item['symbol'] for item in items]
                if symbol in symbols_in_group:
                    idx = symbols_in_group.index(symbol)
                    return f"{group_name} ({idx + 1}/{len(symbols_in_group)})"

        # Tab 3: 10年新高
        elif current_tab == 3:
            total_all_symbols = len(self.list_10y_newhigh)
            overall_idx = 0
            if symbol in self.list_10y_newhigh:
                overall_idx = self.list_10y_newhigh.index(symbol) + 1
            for group_name, items in self.newhigh_10y_data.items():
                symbols_in_group = [item['symbol'] for item in items]
                if symbol in symbols_in_group:
                    idx = symbols_in_group.index(symbol)
                    return f"{group_name} ({idx + 1}/{len(symbols_in_group)}/{overall_idx}/{total_all_symbols})"

        # Tab 4: ETFs
        elif current_tab == 4:
            if symbol in self.etf_gainers:
                idx = self.etf_gainers.index(symbol)
                return f"Top Gainers ({idx + 1}/{len(self.etf_gainers)})"
            elif symbol in self.etf_losers:
                idx = self.etf_losers.index(symbol)
                return f"Top Losers ({idx + 1}/{len(self.etf_losers)})"

        # Tab 5: Stocks
        elif current_tab == 5:
            if symbol in self.stock_gainers:
                idx = self.stock_gainers.index(symbol)
                return f"Top Gainers ({idx + 1}/{len(self.stock_gainers)})"
            elif symbol in self.stock_losers:
                idx = self.stock_losers.index(symbol)
                return f"Top Losers ({idx + 1}/{len(self.stock_losers)})"

        # Tab 6: High/Low
        curr_list = self.symbol_manager.symbols
        if symbol in curr_list:
            return f"({curr_list.index(symbol) + 1}/{len(curr_list)})"
        return ""

    def on_symbol_click(self, symbol):
        self.symbol_manager.set_current_symbol(symbol)

        group_info = self.get_symbol_group_info(symbol)
        pos_str = f"{symbol} {group_info}".strip()

        shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, symbol)
        sector = next((s for s, names in self.sector_data.items() if symbol in names), None)

        try:
            plot_financial_data(
                DB_PATH,
                sector,
                symbol,
                self.compare_data.get(symbol, "N/A"),
                (shares_val, pb),
                marketcap,
                pe,
                self.json_data,
                '1Y',
                False,
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
        if s: self.on_symbol_click(s)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
        elif event.key() == Qt.Key.Key_Down: self.navigate_symbol_from_chart('next')
        elif event.key() == Qt.Key.Key_Up: self.navigate_symbol_from_chart('prev')
        else: super().keyPressEvent(event)

    def show_context_menu(self, symbol):
        menu = QMenu(self)
        menu.addAction("查看历史明细").triggered.connect(lambda: execute_external_script('earning', symbol))
        menu.addAction("查相似").triggered.connect(lambda: execute_external_script('similar', symbol))
        menu.addAction("富途查询").triggered.connect(lambda: execute_external_script('futu', symbol))
        menu.addSeparator()
        menu.addAction("编辑 Tags").triggered.connect(lambda: execute_external_script('tags', symbol))
        menu.exec(QCursor.pos())

    def closeEvent(self, event):
        self.symbol_manager.reset(); QApplication.quit(); event.accept()


if __name__ == '__main__':
    try:
        hl = parse_high_low_file(HIGH_LOW_PATH)
        colors = load_json(COLORS_PATH)
        desc = load_json(DESCRIPTION_PATH)
        sects = load_json(SECTORS_ALL_PATH)
        comp = load_text_data(COMPARE_DATA_PATH)
        hl5y = parse_high_low_file(HIGH_LOW_5Y_PATH)
        vol = parse_volume_high_file(VOLUME_HIGH_PATH)
        etf = parse_etf_file(COMPARE_ETFS_PATH)
        stk = parse_stock_file(COMPARE_STOCK_PATH)
        earn_hist = load_json(EARNING_HISTORY_PATH)

        if os.path.exists(NEW_HIGH_10Y_PRIMARY_PATH):
            target_10y_path = NEW_HIGH_10Y_PRIMARY_PATH
            print(f"正在读取主 10年新高文件: {target_10y_path}")
        else:
            target_10y_path = NEW_HIGH_10Y_BACKUP_PATH
            print(f"主文件不存在，正在读取备份 10年新高文件: {target_10y_path}")

        newhigh_10y = parse_10y_newhigh_file(target_10y_path)

        print("▶ 正在拉取盘前/盘后数据...")

        app = QApplication(sys.argv)
        win = HighLowWindow(hl, colors, sects, comp, desc, hl5y, vol,
                            etf, stk, earn_hist, newhigh_10y, [])

        win.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"启动失败: {e}")