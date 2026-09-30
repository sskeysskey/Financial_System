# 「转折」条目太多：把 TURN_MIN_DROP 改成 2（只看 4→2、5→3 这类硬转折），或 TURN_MIN_STREAK 改 4，或 TURN_RECENT_DAYS 改 1（只看最新交易日）。
# 「转折」条目太少 / 漏掉你例子那种：把 TURN_MAX_GAP 调到 3（容忍中间连续 2 天无记录），TURN_RECENT_DAYS 调到 5。
# 想把“信号彻底消失”也抓出来：TURN_ALLOW_DROP_TO_ZERO = True（会明显变多，建议同时把 TURN_MIN_STREAK 提到 4）。
# 星级门槛：在 _score_turning() 末尾改 4.5 / 3.5 / 2.5。
# 关键项名单：直接改 TURN_LEVEL2_KEYS / TURN_LEVEL3_KEYS 即可。
#
# ★ 「持仓」分组（放在转折之前）：
#   - 数据来源 Modules/firstrade_positions.json（Chrome 插件 + bridge_server.py 落盘）
#   - 三种排序：A-Z｜盈亏%｜成本，同一按钮再点切换升/降序
#   - 左右键按当前持仓排序浏览；到最后一个顺畅流转到转折/共振
#   - 按 R 键重新读取 firstrade_positions.json
#
# ★ Tag 黑名单（Modules/Tag_Blacklist.json，分「确定」「疑似」两组）—— 按分组独立配置：
#   - 「转折」「共振 N 组」每个分组都可单独选择屏蔽「确定」/「疑似」；「持仓」始终完整显示
#   - 默认：确定 → 转折、共振3、共振2；疑似 → 共振2；其他（含以后新出现的共振N）默认不屏蔽
#   - 配置保存在 Modules/Check_Group_Blacklist_Sections.json，启动不再弹窗，沿用上次设定
#   - 修改方式：① 每个分组标题下的「⛔屏蔽 ☐确定 ☐疑似」即点即生效；② B 键 / ⚙ 按钮打开总表
#   - 黑名单、description.json、分组配置文件变化 1 秒内自动刷新
#   - 未被屏蔽但带黑名单 Tag 的卡片：Tag 标 ⛔ 并标红/橙

import sys
import json
import os
import sqlite3
import re
import html as _html
import tempfile
import subprocess
import traceback
from collections import OrderedDict, defaultdict

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QScrollArea, QLabel, QFrame, QMenu,
    QInputDialog, QMessageBox, QCheckBox, QDialog, QDialogButtonBox
)
from PyQt6.QtGui import QCursor, QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

# 外部绘图函数
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
from Chart_input import plot_financial_data

# ★ Tag 黑名单
try:
    import tag_blacklist as TB
    TB_OK = True
except Exception as _e:
    print(f"[黑名单] 加载 tag_blacklist 失败（黑名单功能不可用）: {_e}")
    TB = None
    TB_OK = False

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
WATCH_INTERVAL_MS = 1000

MODULES_DIR = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules")
CONFIG_PATH = os.path.join(MODULES_DIR, "Sectors_panel.json")
COLORS_PATH = os.path.join(MODULES_DIR, "Colors.json")
DESCRIPTION_PATH = os.path.join(MODULES_DIR, "description.json")
SECTORS_ALL_PATH = os.path.join(MODULES_DIR, "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
EARNING_HISTORY_PATH = os.path.join(MODULES_DIR, "Earning_History.json")

# ★ 分组级黑名单屏蔽配置文件
BL_SECTION_CONFIG_PATH = os.path.join(MODULES_DIR, "Check_Group_Blacklist_Sections.json")

# ---------- 黑名单分组常量（TB 不可用时也能正常运行）----------
BL_GROUP_SURE = TB.GROUP_SURE if TB_OK else "确定"
BL_GROUP_MAYBE = TB.GROUP_MAYBE if TB_OK else "疑似"
BL_GROUPS = tuple(TB.GROUPS) if TB_OK else (BL_GROUP_SURE, BL_GROUP_MAYBE)

SEC_TURNING = "turning"


def reso_key(n):
    return f"reso:{int(n)}"


# 默认：确定 → 转折 / 共振3 / 共振2；疑似 → 共振2
BL_SECTION_DEFAULTS = {
    SEC_TURNING: {BL_GROUP_SURE},
    reso_key(3): {BL_GROUP_SURE},
    reso_key(2): {BL_GROUP_SURE, BL_GROUP_MAYBE},
}
# 从未配置过的新分组（例如新出现的共振7）默认不屏蔽
BL_NEW_SECTION_DEFAULT = frozenset()

# ---------- 持仓分组排序配置 ----------
HOLD_SORT_MODES = [('alpha', 'A-Z'), ('gainloss', '盈亏%'), ('cost', '成本')]
HOLD_SORT_LABEL = dict(HOLD_SORT_MODES)
HOLD_SORT_KEYS = {
    'gainloss': ('gainloss', 'gainlossPercent', 'gainloss_amount'),
    'cost': ('cost', 'totalCost', 'market_value'),
}
HOLD_DEFAULT_DESC = {'alpha': False, 'gainloss': False, 'cost': True}

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

HIGH_WEIGHT_CATEGORIES = {
    "PE_Volume", "Short", "Short_W", "PE_Volume_high",
    "SupportLevel_Over", "PE_Deeper", "PE_Deep"
}
MEDIUM_WEIGHT_CATEGORIES = {
    "PE_Volume_up", "PE_W", "SupportLevel_Close", "PE_Hot",
    "OverSell_W", "season"
}

LOOKBACK_TRADING_DAYS = 120
MIN_HISTORY_DAYS = 5

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
    dates = set()
    for g, dm in (history_data or {}).items():
        if not is_valid_group(g) or not isinstance(dm, dict):
            continue
        dates.update(dm.keys())
    ordered = sorted(dates, key=norm_date, reverse=True)
    return ordered, {d: i for i, d in enumerate(ordered)}


def collapse_family(groups):
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


# ======================================================================
# 上下文感知的全局导航序列管理器
# ======================================================================
class GlobalNavigationManager:
    def __init__(self, items=None):
        self.items = []
        self.current_index = -1
        if items:
            self.set_items(items)

    def _find_exact(self, symbol, source):
        for idx, (sym, src) in enumerate(self.items):
            if sym == symbol and src == source:
                return idx
        return -1

    def set_items(self, items):
        """设置全量条目；若当前条目被过滤掉，则把指针放在其前一位，使“下一个”正好落在原位置的新条目"""
        old_item = self.current_item()
        old_index = self.current_index
        self.items = list(items) if items else []
        if not self.items:
            self.current_index = -1
            return
        if old_item:
            idx = self._find_exact(old_item[0], old_item[1])
            if idx >= 0:
                self.current_index = idx
            else:
                self.current_index = min(old_index, len(self.items)) - 1
        elif self.current_index >= len(self.items):
            self.current_index = len(self.items) - 1

    def next_item(self):
        if not self.items:
            return None
        self.current_index = (self.current_index + 1) % len(self.items)
        return self.items[self.current_index]

    def previous_item(self):
        if not self.items:
            return None
        self.current_index = (self.current_index - 1 + len(self.items)) % len(self.items)
        return self.items[self.current_index]

    def set_current(self, symbol, source=None):
        if not self.items:
            self.current_index = -1
            return
        if source:
            idx = self._find_exact(symbol, source)
            if idx >= 0:
                self.current_index = idx
                return
        for idx, (sym, _) in enumerate(self.items):
            if sym == symbol:
                self.current_index = idx
                return

    def current_item(self):
        if self.items and 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def current_symbol(self):
        item = self.current_item()
        return item[0] if item else None

    def reset(self):
        self.current_index = -1


# ----------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------
def clean_ticker(symbol):
    match = re.search(r"^([A-Za-z-]+)", symbol)
    return match.group(1) if match else symbol


def norm_symbol(s):
    return str(s).strip().upper().replace('.', '-')


def split_symbol_suffix(raw):
    base = clean_ticker(raw)
    suffix = raw[len(base):] if raw.startswith(base) else ""
    return base.upper(), suffix


def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)


def file_mtime(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def atomic_write_json(path, obj):
    """临时文件 + fsync + os.replace 原子替换，避免写一半被其他进程读到"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def open_text_file(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", path])
        elif sys.platform == "win32":
            os.startfile(path)   # noqa
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"打开文件失败: {e}")


def load_text_data(path):
    data = {}
    if not os.path.exists(path): return data
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if ':' in line:
                key, value = map(str.strip, line.split(':', 1))
                key_parts = key.split()
                if not key_parts:          # ": xxx" 这种行会 IndexError
                    continue
                cleaned_key = key_parts[-1]
                data[cleaned_key] = value.split(',')[0].strip() if ',' in value else value
    return data


def load_52week_low_symbols(path):
    symbols = set()
    data = load_json(path)
    for sector in WEEK52_LOW_SECTORS:
        for sym in data.get(sector, {}).keys():
            symbols.add(clean_ticker(sym).upper())
    return symbols


def build_tags_index(json_data):
    """{规范化symbol: [tag, ...]}"""
    idx = {}
    for src in ('stocks', 'etfs'):
        for item in (json_data or {}).get(src, []) or []:
            sym = item.get('symbol')
            if not sym:
                continue
            tags = item.get('tag') or []
            if isinstance(tags, str):
                tags = [tags]
            idx.setdefault(norm_symbol(sym), [str(t) for t in tags])
    return idx


def preview_tags(tags, n=30):
    if not tags:
        return "（空）"
    s = "、".join(tags[:n])
    return s + (f" … 共{len(tags)}个" if len(tags) > n else "")


def fetch_mnspp_data_from_db(db_path, symbol):
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
# ★ 分组级黑名单屏蔽配置
# ======================================================================
def normalize_section_key(k):
    """兼容手动编辑：turning / 转折 / reso:2 / reso_2 / 共振2 / 共振2组"""
    s = str(k).strip()
    if s.lower() in ("turning", "转折"):
        return SEC_TURNING
    m = re.search(r"(\d+)", s)
    if m and (s.lower().startswith("reso") or s.startswith("共振")):
        return reso_key(int(m.group(1)))
    return None


def section_label(key):
    if key == SEC_TURNING:
        return "转折"
    if key.startswith("reso:"):
        return f"共振{key.split(':', 1)[1]}组"
    return key


def section_sort_key(key):
    if key == SEC_TURNING:
        return (0, 0)
    try:
        return (1, -int(key.split(":", 1)[1]))
    except Exception:
        return (2, 0)


def ordered_groups(groups):
    return [g for g in BL_GROUPS if g in groups]


class SectionFilterConfig:
    """每个分组（转折 / 共振N）各自屏蔽哪些黑名单类别；持久化到 JSON"""
    NOTE = ("Check_Group 分组级黑名单屏蔽配置。sections 的键：turning=转折，reso:N=共振N组"
            "（也接受 转折 / 共振N / reso_N）；值为要屏蔽的黑名单类别数组，可选「确定」「疑似」，"
            "空数组 = 不屏蔽。未列出的分组用程序默认值（确定→转折/共振3/共振2，疑似→共振2，其它不屏蔽）。"
            "保存后约 1 秒内自动生效；程序内修改也会写回本文件。")

    def __init__(self, path=BL_SECTION_CONFIG_PATH):
        self.path = path
        self.sections = {k: set(v) for k, v in BL_SECTION_DEFAULTS.items()}
        self.error = None
        self.sig = None
        self.load()

    def signature(self):
        return file_mtime(self.path)

    def load(self):
        self.sig = self.signature()
        if not os.path.exists(self.path):
            self.error = None
            return
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                txt = f.read()
            raw = json.loads(txt) if txt.strip() else {}
            secs = raw.get("sections", {}) if isinstance(raw, dict) else None
            if not isinstance(secs, dict):
                raise ValueError("缺少 sections 对象（应为 {\"sections\": {...}}）")
            out = {}
            for k, v in secs.items():
                nk = normalize_section_key(k)
                if not nk:
                    continue
                if v is None:
                    v = []
                if isinstance(v, str):
                    v = [v]
                if not isinstance(v, (list, tuple)):
                    continue
                out[nk] = {str(g).strip() for g in v if str(g).strip() in BL_GROUPS}
            self.sections = out
            self.error = None
        except Exception as e:
            # 解析失败：沿用上次内容（首次即失败则为默认值）
            self.error = f"{type(e).__name__}: {e}"
            print(f"[分组屏蔽] 解析 {self.path} 失败，沿用上次/默认配置: {e}")

    def get(self, key):
        if key in self.sections:
            return set(self.sections[key])
        return set(BL_SECTION_DEFAULTS.get(key, BL_NEW_SECTION_DEFAULT))

    def default_of(self, key):
        return set(BL_SECTION_DEFAULTS.get(key, BL_NEW_SECTION_DEFAULT))

    def configured_keys(self):
        return list(self.sections.keys())

    def update(self, mapping):
        """mapping: {key: set(groups)}；先改内存再落盘，落盘失败抛异常（内存设置仍生效）"""
        for k, v in mapping.items():
            self.sections[k] = {g for g in v if g in BL_GROUPS}
        self.save()

    def save(self):
        if self.error and os.path.exists(self.path):
            # 文件被手动改坏：先备份，不静默冲掉
            try:
                bak = self.path + ".corrupt.bak"
                with open(self.path, "rb") as src, open(bak, "wb") as dst:
                    dst.write(src.read())
                print(f"[分组屏蔽] 原文件解析失败，已备份到 {bak}")
            except Exception as e:
                print(f"[分组屏蔽] 备份损坏文件失败: {e}")
        obj = OrderedDict()
        obj["_说明"] = self.NOTE
        obj["sections"] = OrderedDict(
            (k, ordered_groups(self.sections[k]))
            for k in sorted(self.sections, key=section_sort_key))
        atomic_write_json(self.path, obj)
        self.error = None
        self.sig = self.signature()

    def ensure_file(self):
        if not os.path.exists(self.path):
            self.save()


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
                'symbol': sym, 'date': d, 'to_n': m, 'from_n': from_n,
                'from_max': max(counts), 'drop': drop, 'streak': len(plateau),
                'key_max': max(k for _, _, k in plateau), 'plateau': plateau,
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


# ======================================================================
# ★ 分组级黑名单设置对话框（B 键 / ⚙ 按钮）
# ======================================================================
DIALOG_QSS = """
QDialog { background-color: #2E3440; }
QLabel { color: #D8DEE9; font-size: 14px; }
QLabel#DlgHead { color: #ECEFF4; font-size: 16px; font-weight: bold; }
QLabel#DlgColHead { color: #ECEFF4; font-size: 14px; font-weight: bold; }
QLabel#DlgDim { color: #6B7385; font-size: 14px; }
QLabel#DlgHint { color: #88C0D0; font-size: 12px; }
QCheckBox { color: #ECEFF4; font-size: 16px; font-weight: bold; spacing: 10px; }
QCheckBox::indicator { width: 20px; height: 20px; }
QPushButton { background-color: #4C566A; color: #ECEFF4; border: none; padding: 7px 16px;
              border-radius: 5px; font-size: 14px; }
QPushButton:default { background-color: #5E81AC; font-weight: bold; }
QPushButton:hover { background-color: #81A1C1; }
"""


class SectionBlacklistDialog(QDialog):
    """rows: [(key, 显示文字, 今日是否出现)]；current: {key: set(groups)}"""

    def __init__(self, rows, current, default_of, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check_Group · 分组黑名单屏蔽设置")
        self.setMinimumWidth(620)
        self.rows = rows
        self.default_of = default_of
        data = TB.load() if TB_OK else {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        head = QLabel("为每个分组单独选择要屏蔽的黑名单类别\n"
                      "（「持仓」始终完整显示；从未配置过的新分组默认不屏蔽）")
        head.setObjectName("DlgHead")
        lay.addWidget(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(8)
        h0 = QLabel("分组")
        h0.setObjectName("DlgColHead")
        grid.addWidget(h0, 0, 0)

        self.checks = {}
        for c, g in enumerate(BL_GROUPS, start=1):
            b = QPushButton(f"{g}（{len(data.get(g, []))}个Tag）全选/清空")
            b.setAutoDefault(False)
            b.setDefault(False)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(f"「{g}」黑名单 Tag：\n{preview_tags(data.get(g, []), 60)}")
            b.clicked.connect(lambda _=False, gg=g: self._toggle_column(gg))
            grid.addWidget(b, 0, c)

        for r, (key, text, present) in enumerate(rows, start=1):
            lb = QLabel(text)
            if not present:
                lb.setObjectName("DlgDim")
            grid.addWidget(lb, r, 0)
            for c, g in enumerate(BL_GROUPS, start=1):
                cb = QCheckBox()
                cb.setChecked(g in current.get(key, set()))
                cb.setToolTip(f"在「{section_label(key)}」中屏蔽带「{g}」黑名单 Tag 的股票")
                grid.addWidget(cb, r, c, alignment=Qt.AlignmentFlag.AlignCenter)
                self.checks[(key, g)] = cb
        lay.addLayout(grid)

        hint = QLabel("Enter 应用 ｜ Esc 取消 ｜ 也可在主界面每个分组标题下直接勾选（即点即生效）\n"
                      "灰色行 = 今日未出现、但曾配置过的分组")
        hint.setObjectName("DlgHint")
        lay.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("应用")
        ok_btn.setDefault(True)
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        b_def = btns.addButton("恢复默认", QDialogButtonBox.ButtonRole.ResetRole)
        b_none = btns.addButton("全部不屏蔽", QDialogButtonBox.ButtonRole.ResetRole)
        for b in (b_def, b_none):
            b.setAutoDefault(False)
        b_def.clicked.connect(self._restore_defaults)
        b_none.clicked.connect(self._clear_all)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.setStyleSheet(DIALOG_QSS)

    def _toggle_column(self, g):
        cbs = [cb for (k, gg), cb in self.checks.items() if gg == g]
        target = not all(cb.isChecked() for cb in cbs)
        for cb in cbs:
            cb.setChecked(target)

    def _restore_defaults(self):
        for (k, g), cb in self.checks.items():
            cb.setChecked(g in self.default_of(k))

    def _clear_all(self):
        for cb in self.checks.values():
            cb.setChecked(False)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self.raise_()
        self.activateWindow()

    def result_map(self):
        out = {}
        for key, _, _ in self.rows:
            out[key] = {g for g in BL_GROUPS if self.checks[(key, g)].isChecked()}
        return out


# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------
class GroupWindow(QMainWindow):
    wl_done = pyqtSignal(dict)

    def __init__(self, keyword_colors, sector_data, compare_data, json_data, earning_history_data):
        super().__init__()
        self.keyword_colors = keyword_colors
        self.sector_data = sector_data
        self.compare_data = compare_data
        self.json_data = json_data
        self.earning_history_data = earning_history_data

        self.symbol_widgets_map = defaultdict(list)

        # ===== ★ 黑名单状态（分组级）=====
        self.sec_cfg = SectionFilterConfig()
        self.tags_index = build_tags_index(self.json_data)
        self.hidden_info = {}          # sym -> {'hits': [(tag, group)], 'sections': [label]}
        self.section_hidden = {}       # section_key -> 隐藏数量
        self.view_turning = []
        self.view_resonance = []
        self.turning_hidden = 0

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

        # ===== 持仓 =====
        self.positions = {}
        self.positions_meta = {}
        self.hold_sort_mode = 'gainloss'
        self.hold_sort_desc = HOLD_DEFAULT_DESC['gainloss']
        self._hold_widget_refs = []
        self.load_positions_data()
        self.list_holdings = self._sorted_holdings()

        # ===== 应用黑名单过滤 → 生成可见列表 =====
        self._compute_views()

        self.nav_manager = GlobalNavigationManager(self._build_full_navigation_list())

        self.init_ui()

        # ===== ★ 文件联动监视 =====
        self._bl_sig = TB.signature() if TB_OK else None
        self._desc_sig = file_mtime(DESCRIPTION_PATH)
        self.watch_timer = QTimer(self)
        self.watch_timer.setInterval(WATCH_INTERVAL_MS)
        self.watch_timer.timeout.connect(self._poll_external_changes)
        self.watch_timer.start()

    # ==================================================================
    # ★ 黑名单：命中计算 / 过滤（分组级）
    # ==================================================================
    def _blacklist_hits(self, symbol, groups=None):
        if not TB_OK:
            return []
        tags = self.tags_index.get(norm_symbol(symbol), [])
        return TB.blacklisted_tags(tags, groups)

    def present_section_keys(self):
        return [SEC_TURNING] + [reso_key(item['count']) for item in self.resonance_data]

    def _compute_views(self):
        self.hidden_info = {}
        self.section_hidden = {}

        def visible(sym, key):
            if not TB_OK:
                return True
            groups = self.sec_cfg.get(key)
            if not groups:
                return True
            hits = self._blacklist_hits(sym, groups)
            if not hits:
                return True
            info = self.hidden_info.setdefault(sym, {'hits': [], 'sections': []})
            for h in hits:
                if h not in info['hits']:
                    info['hits'].append(h)
            lbl = section_label(key)
            if lbl not in info['sections']:
                info['sections'].append(lbl)
            self.section_hidden[key] = self.section_hidden.get(key, 0) + 1
            return False

        self.view_turning = [r for r in self.turning_data if visible(r['symbol'], SEC_TURNING)]
        self.turning_hidden = len(self.turning_data) - len(self.view_turning)
        self.view_resonance = []
        for item in self.resonance_data:
            key = reso_key(item['count'])
            vis = [s for s in item['symbols'] if visible(s, key)]
            self.view_resonance.append({'count': item['count'], 'key': key, 'symbols': vis,
                                        'total': len(item['symbols']),
                                        'hidden': len(item['symbols']) - len(vis)})
        self.list_turning = [r['symbol'] for r in self.view_turning]
        self.list_resonance = [s for item in self.view_resonance for s in item['symbols']]

    def apply_blacklist_filter(self):
        self._compute_views()
        self._sync_navigation_list()
        self._rebuild_content()
        self._update_bl_bar()
        self._update_window_title()

    def _config_summary(self):
        parts = []
        for key in self.present_section_keys():
            g = ordered_groups(self.sec_cfg.get(key))
            if g:
                parts.append(f"{section_label(key)}:{'+'.join(g)}")
        return "屏蔽 → " + "  ".join(parts) if parts else "当前各分组均未屏蔽"

    def _save_section_config(self, mapping):
        try:
            self.sec_cfg.update(mapping)
            return True
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(self, "保存失败",
                                f"分组屏蔽配置写入失败（本次运行内仍生效）：\n{e}")
            return False

    def _after_config_change(self, msg=""):
        self.apply_blacklist_filter()
        text = (msg + " ｜ " if msg else "") + f"共隐藏 {len(self.hidden_info)} 只"
        self.statusBar().showMessage(text, 6000)

    def _on_section_toggle(self, key, group, checked):
        groups = self.sec_cfg.get(key)
        if checked:
            groups.add(group)
        else:
            groups.discard(group)
        self._save_section_config({key: groups})
        desc = "+".join(ordered_groups(groups)) or "不屏蔽"
        # 推迟重建：当前勾选框本身就在将被重建的分组里，不能在其信号里同步销毁
        QTimer.singleShot(0, lambda: self._after_config_change(f"「{section_label(key)}」→ {desc}"))

    def _dialog_rows(self):
        rows = [(SEC_TURNING,
                 f"转折（{len(self.turning_data)}只，隐藏 {self.turning_hidden}）", True)]
        present = {SEC_TURNING}
        for item in self.view_resonance:
            rows.append((item['key'],
                         f"共振 {item['count']} 组（{item['total']}只，隐藏 {item['hidden']}）", True))
            present.add(item['key'])
        absent = sorted((k for k in self.sec_cfg.configured_keys() if k not in present),
                        key=section_sort_key)
        for k in absent:
            rows.append((k, f"{section_label(k)}（今日未出现）", False))
        return rows

    def open_blacklist_settings(self):
        if not TB_OK:
            QMessageBox.warning(self, "不可用", "tag_blacklist.py 未加载")
            return
        rows = self._dialog_rows()
        current = {k: self.sec_cfg.get(k) for k, _, _ in rows}
        dlg = SectionBlacklistDialog(rows, current, self.sec_cfg.default_of, parent=self)
        if dlg.exec():
            self._save_section_config(dlg.result_map())
            self._after_config_change("已应用分组屏蔽设置")

    def open_blacklist_file(self):
        if TB_OK:
            TB.open_in_editor()
            self.statusBar().showMessage(f"已打开 {TB.BLACKLIST_PATH}（保存后约 1 秒自动生效）", 8000)

    def open_section_config_file(self):
        try:
            self.sec_cfg.ensure_file()
        except Exception as e:
            QMessageBox.warning(self, "失败", f"创建配置文件失败：{e}")
            return
        open_text_file(self.sec_cfg.path)
        self.statusBar().showMessage(f"已打开 {self.sec_cfg.path}（保存后约 1 秒自动生效）", 8000)

    def _poll_external_changes(self, force=False):
        changed = False
        try:
            dsig = file_mtime(DESCRIPTION_PATH)
            if force or dsig != self._desc_sig:
                self._desc_sig = dsig
                try:
                    new = load_json(DESCRIPTION_PATH)
                except Exception as e:
                    # 只报一次；文件写完后签名会变化，届时自动重读
                    print(f"[联动] description.json 读取失败（可能正在写入），等待下次变化: {e}")
                    new = None
                if isinstance(new, dict) and new:
                    # 原地更新：Chart 持有同一个 dict 引用，也能拿到新数据
                    self.json_data.clear()
                    self.json_data.update(new)
                    self.tags_index = build_tags_index(self.json_data)
                    changed = True
            if TB_OK:
                bsig = TB.signature()
                if force or bsig != self._bl_sig:
                    self._bl_sig = bsig
                    TB.load(force=True)
                    changed = True
            ssig = self.sec_cfg.signature()
            if force or ssig != self.sec_cfg.sig:
                self.sec_cfg.load()
                changed = True
        except Exception:
            traceback.print_exc()
        if changed:
            before = set(self.hidden_info)
            self.apply_blacklist_filter()
            after = set(self.hidden_info)
            add_n, rm_n = len(after - before), len(before - after)
            msg = "黑名单 / Tag / 分组配置 已更新"
            if add_n or rm_n:
                msg += f"：新隐藏 {add_n} 只，恢复显示 {rm_n} 只"
            self.statusBar().showMessage(msg, 6000)

    def _update_window_title(self):
        if TB_OK:
            self.setWindowTitle(f"持仓 / 多组共振 / 转折   ｜ 黑名单（按分组）已隐藏 {len(self.hidden_info)} 只")
        else:
            self.setWindowTitle("持仓 / 多组共振 / 转折")

    # ==================================================================
    # 导航全序列生成
    # ==================================================================
    def _build_full_navigation_list(self):
        items = []
        for s in self.list_holdings:
            items.append((s, 'holdings'))
        for s in self.list_turning:
            items.append((s, 'turning'))
        for s in self.list_resonance:
            items.append((s, 'resonance'))
        return items

    def _sync_navigation_list(self):
        self.nav_manager.set_items(self._build_full_navigation_list())

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
        self._update_window_title()
        self.setGeometry(100, 100, 1600, 1000)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # legend = QLabel(
        #     "【持仓】读取 firstrade_positions.json；点上方按钮切换排序（同一按钮再点一次切升/降序），"
        #     "浏览完持仓最后一项将顺畅进入转折/共振；按 R 键重新读盘。\n"
        #     "【共振】🔥★★★ 极罕见且信号极强（红框）｜ ★★ 罕见/高质量（黄框）｜ ★ 值得一看（蓝框）｜ 无标记 = 常态（灰框）\n"
        #     f"【转折】连续 ≥{TURN_MIN_STREAK} 天保持多项关键信号后，突然减项（如 4项→2项 / 2项→1项）；"
        #     "按钮上的 4→2 表示“平台4项 → 当日2项”，鼠标悬停可看平台期逐日明细。"
        #     f"  只显示最近 {TURN_RECENT_DAYS} 个交易日内发生的转折。\n"
        #     "【黑名单】每个分组标题下可单独勾选屏蔽「确定 / 疑似」，即点即生效并自动保存（持仓不受影响）；"
        #     "B 键打开总表设置。未隐藏卡片里的黑名单 Tag 以 ⛔ 标出（红=确定，橙=疑似）。"
        # )
        # legend.setStyleSheet("color:#9AA5B1; font-size:14px; padding:6px 10px;")
        # legend.setWordWrap(True)
        # layout.addWidget(legend)

        layout.addLayout(self._build_blacklist_bar())

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        self.apply_stylesheet()
        self._rebuild_content()
        self._update_bl_bar()

        QShortcut(QKeySequence(Qt.Key.Key_Slash), self).activated.connect(self.show_search_dialog)
        QShortcut(QKeySequence(Qt.Key.Key_A), self).activated.connect(self.add_current_to_watchlist)
        QShortcut(QKeySequence(Qt.Key.Key_R), self).activated.connect(self.reload_positions)
        QShortcut(QKeySequence(Qt.Key.Key_B), self).activated.connect(self.open_blacklist_settings)
        self.wl_done.connect(self._on_wl_done)
        self.statusBar().showMessage(
            "提示：/ 搜索 ｜ a 加自选 ｜ R 重新读取持仓 ｜ B 分组黑名单设置 ｜ 右键卡片有更多操作 ｜ "
            + self._config_summary(), 10000)

    # ==================================================================
    # ★ 黑名单工具栏
    # ==================================================================
    def _build_blacklist_bar(self):
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 0, 10, 4)
        bar.setSpacing(12)
        title = QLabel("⛔ 黑名单（按分组配置，不影响持仓）：")
        title.setObjectName("BLTitle")
        bar.addWidget(title)

        self.bl_info_label = QLabel("" if TB_OK else "tag_blacklist.py 未加载，黑名单功能不可用")
        self.bl_info_label.setObjectName("BLInfo")
        self.bl_info_label.setWordWrap(True)
        bar.addWidget(self.bl_info_label, 1)

        for text, slot, tip in (
                ("⚙ 分组屏蔽设置 (B)", self.open_blacklist_settings, "按分组勾选要屏蔽的黑名单类别"),
                ("📝 编辑黑名单 Tag", self.open_blacklist_file, "用文本编辑器打开 Tag_Blacklist.json"),
                ("📝 编辑分组配置", self.open_section_config_file,
                 "用文本编辑器打开 Check_Group_Blacklist_Sections.json"),
                ("↻ 重新读取", lambda: self._poll_external_changes(force=True),
                 "强制重新读取黑名单、分组配置与 description.json")):
            b = QPushButton(text)
            b.setObjectName("SortBtn")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, f=slot: f())
            b.setEnabled(TB_OK)
            bar.addWidget(b)
        return bar

    def _update_bl_bar(self):
        if not TB_OK or not hasattr(self, 'bl_info_label'):
            return
        data = TB.load()
        parts = [self._config_summary()]
        n = len(self.hidden_info)
        parts.append(f"｜ 共隐藏 {n} 只" if n else "｜ 无隐藏")
        err = TB.last_error()
        if err:
            parts.append("⚠ 黑名单文件解析失败，沿用上次内容")
        if self.sec_cfg.error:
            parts.append("⚠ 分组配置文件解析失败，沿用上次/默认配置")
        self.bl_info_label.setText("   ".join(parts))

        lines = [f"黑名单 Tag 数：" + "，".join(f"{g} {len(data.get(g, []))}" for g in BL_GROUPS), ""]
        for key in self.present_section_keys():
            g = ordered_groups(self.sec_cfg.get(key))
            lines.append(f"{section_label(key)}：屏蔽 {'+'.join(g) or '无'}，"
                         f"隐藏 {self.section_hidden.get(key, 0)} 只")
        if self.hidden_info:
            lines.append("")
            for sym in sorted(self.hidden_info)[:80]:
                info = self.hidden_info[sym]
                lines.append(f"{sym}［{'、'.join(info['sections'])}］：" +
                             "、".join(f"{t}[{g}]" for t, g in info['hits']))
            if len(self.hidden_info) > 80:
                lines.append(f"… 共 {len(self.hidden_info)} 只")
        if err:
            lines.insert(0, f"黑名单解析错误：{err}\n")
        if self.sec_cfg.error:
            lines.insert(0, f"分组配置解析错误：{self.sec_cfg.error}\n")
        self.bl_info_label.setToolTip("\n".join(lines))

    # ==================================================================
    # ★ 整体重建内容区（保持滚动位置）
    # ==================================================================
    def _rebuild_content(self):
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        hv, vv = hbar.value(), vbar.value()

        self.symbol_widgets_map = defaultdict(list)
        self._hold_widget_refs = []

        content = QWidget()
        main_lay = QHBoxLayout(content)
        self._build_holdings_section(main_lay)
        self._build_turning_section(main_lay)
        self._build_resonance_sections(main_lay)
        main_lay.addStretch(1)

        old = self.scroll_area.takeWidget()
        self.scroll_area.setWidget(content)
        if old is not None:
            old.deleteLater()

        def restore():
            try:
                hbar.setValue(hv)
                vbar.setValue(vv)
            except RuntimeError:
                pass
        QTimer.singleShot(0, restore)

    # ==================================================================
    # 持仓分组
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
            f"（图表左右键将按此顺序浏览并流转至后续分组）", 6000)

    def _apply_sort(self):
        self.list_holdings = self._sorted_holdings()
        self._refresh_holdings_body()
        self._update_hold_header()
        self._sync_navigation_list()

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
        info = self.hidden_info.get(symbol)
        if not widgets:
            if info:
                QMessageBox.information(
                    self, "已被黑名单隐藏",
                    f"{symbol} 在「{'、'.join(info['sections'])}」中被黑名单隐藏：\n" +
                    "、".join(f"{t}[{g}]" for t, g in info['hits']) +
                    "\n\n可在对应分组标题下取消勾选（或按 B 打开设置）后再查看。")
            else:
                QMessageBox.information(self, "未找到", f"未在当前列表中找到: {symbol}")
            return
        primary_container, _ = widgets[0]
        self.scroll_area.ensureWidgetVisible(primary_container, 150, 150)
        self.nav_manager.set_current(symbol)
        for _, btn in widgets:
            self.flash_highlight(btn)
        if info:
            self.statusBar().showMessage(
                f"{symbol} 另在「{'、'.join(info['sections'])}」中被黑名单隐藏", 6000)

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
        strong_n = sum(1 for r in self.view_turning if r['level'] > 0)
        title = f"转折 ({len(self.view_turning)}只 / ★{strong_n})"
        if self.turning_hidden:
            title += f" ⛔{self.turning_hidden}"
        main_lay.addWidget(self._create_section_container(title, col_lay, SEC_TURNING))

        if not self.view_turning:
            msg = (f"最近的 {self.turning_hidden} 只转折\n均已被黑名单隐藏"
                   if self.turning_hidden else "最近无转折信号")
            tip = QLabel(msg)
            tip.setStyleSheet("color:#888; font-size:16px; padding:12px;")
            col_lay.addWidget(tip)
        else:
            items = self.view_turning
            for chunk in [items[i:i + MAX_ITEMS_PER_COLUMN]
                          for i in range(0, len(items), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for r in chunk:
                    date_tag = "" if r['date'] == self.latest_date else f" {r['date'][5:]}"
                    disp = f"{r['from_n']}→{r['to_n']}{date_tag} {r['badge']}".strip()
                    col.addWidget(self.create_symbol_widget(
                        r['symbol'], override_text=disp,
                        force_style=f"Turn_L{r['level']}",
                        tooltip=r['reason'], source='turning'))
                col.addStretch(1); col_lay.addLayout(col)

        self._add_separator(main_lay)

    def _build_resonance_sections(self, main_lay):
        for item in self.view_resonance:
            count = item['count']
            symbols = item['symbols']
            strong_n = sum(1 for s in symbols if self.symbol_marks.get(s, {}).get('level', 0) > 0)

            col_lay = QHBoxLayout()
            title = f"共振 {count} 个分组 ({len(symbols)}只 / ★{strong_n})"
            if item['hidden']:
                title += f" ⛔{item['hidden']}"
            main_lay.addWidget(self._create_section_container(title, col_lay, item['key']))

            if not symbols:
                # 整组被屏蔽也保留分组（否则无法在标题下取消屏蔽）
                tip = QLabel(f"本组 {item['hidden']} 只\n均已被黑名单隐藏")
                tip.setStyleSheet("color:#888; font-size:16px; padding:12px;")
                col_lay.addWidget(tip)
                self._add_separator(main_lay)
                continue

            for chunk in [symbols[i:i + MAX_ITEMS_PER_COLUMN]
                          for i in range(0, len(symbols), MAX_ITEMS_PER_COLUMN)]:
                col = QVBoxLayout(); col.setAlignment(Qt.AlignmentFlag.AlignTop)
                for sym in chunk:
                    mark = self.symbol_marks.get(sym, {'level': 0, 'badge': '', 'reason': ''})
                    base_text = self.compare_data.get(sym, '')
                    disp = f"{base_text} {mark['badge']}".strip()
                    col.addWidget(self.create_symbol_widget(
                        sym, override_text=disp if disp else " ",
                        force_style=f"Reso_L{mark['level']}",
                        tooltip=mark.get('reason', ''), source='resonance'))
                col.addStretch(1); col_lay.addLayout(col)

            self._add_separator(main_lay)

    # --- 辅助方法 ---
    def _section_bl_row(self, key):
        """分组标题下的「⛔屏蔽 ☐确定 ☐疑似」"""
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        lab = QLabel("⛔屏蔽")
        lab.setObjectName("SecBLLabel")
        row.addWidget(lab)
        active = self.sec_cfg.get(key)
        data = TB.load() if TB_OK else {}
        is_default = active == self.sec_cfg.default_of(key)
        for g in BL_GROUPS:
            cb = QCheckBox(g)
            cb.setObjectName("SecBLSure" if g == BL_GROUP_SURE else "SecBLMaybe")
            cb.setChecked(g in active)
            cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            cb.setToolTip(f"在「{section_label(key)}」中屏蔽带「{g}」黑名单 Tag 的股票"
                          f"（即点即生效，自动保存）\n{'当前 = 默认设置' if is_default else '当前 ≠ 默认设置'}\n\n"
                          f"「{g}」Tag：{preview_tags(data.get(g, []), 60)}")
            cb.toggled.connect(lambda checked, k=key, gg=g: self._on_section_toggle(k, gg, checked))
            row.addWidget(cb)
        row.addStretch(1)
        return row

    def _create_section_container(self, title_text, layout_ref, section_key=None):
        c = QWidget(); v = QVBoxLayout(c); v.setContentsMargins(10, 0, 10, 0)
        t = QLabel(title_text); t.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        if section_key and TB_OK:
            v.addLayout(self._section_bl_row(section_key))
        v.addLayout(layout_ref); v.addStretch(1); return c

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
            "Reso_L0":  ("#111111", "#D8DEE9", "#3A3A3A"),
            "Reso_L1":  ("#10222A", "#D8DEE9", "#88C0D0"),
            "Reso_L2":  ("#2C2411", "#F2E3B4", "#EBCB8B"),
            "Reso_L3":  ("#3B171C", "#FFD5D9", "#BF616A"),
            "Turn_L0":  ("#111111", "#D8DEE9", "#3A3A3A"),
            "Turn_L1":  ("#13251C", "#D8E9DE", "#A3BE8C"),
            "Turn_L2":  ("#241B2C", "#EBD9F2", "#B48EAD"),
            "Turn_L3":  ("#3B171C", "#FFD5D9", "#BF616A"),
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

        qss += ("QPushButton#SortBtn { background-color:#2E3440; color:#D8DEE9; font-size:13px; "
                "border:1px solid #4C566A; border-radius:4px; padding:3px 8px; text-align:center; }\n"
                "QPushButton#SortBtn:hover { background-color:#3B4252; }\n"
                "QPushButton#SortBtn:disabled { color:#666; }\n"
                "QPushButton#SortBtnOn { background-color:#4C566A; color:#ECEFF4; font-size:13px; "
                "font-weight:bold; border:1px solid #88C0D0; border-radius:4px; "
                "padding:3px 4px; text-align:center; }\n"
                "QPushButton#SortBtnOn:hover { background-color:#5E81AC; }\n")

        qss += ("QLabel#BLTitle { color:#BF616A; font-size:14px; font-weight:bold; }\n"
                "QLabel#BLInfo { color:#9AA5B1; font-size:13px; }\n"
                "QLabel#SecBLLabel { color:#8F9BB3; font-size:12px; }\n"
                "QCheckBox#SecBLSure { color:#BF616A; font-size:13px; font-weight:bold; spacing:4px; }\n"
                "QCheckBox#SecBLMaybe { color:#D08770; font-size:13px; font-weight:bold; spacing:4px; }\n"
                "QCheckBox#SecBLSure::indicator, QCheckBox#SecBLMaybe::indicator "
                "{ width:14px; height:14px; }\n")

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

    # ------------------------------------------------------------------
    def _tags_rich_text(self, tags, hits):
        hit_map = {TB.norm_tag(t): g for t, g in hits} if TB_OK else {}
        html_parts, plain_parts = [], []
        for t in tags:
            g = hit_map.get(TB.norm_tag(t)) if TB_OK else None
            esc = _html.escape(str(t))
            if g:
                color = "#C0392B" if g == BL_GROUP_SURE else "#D35400"
                html_parts.append(f'<span style="color:{color}; font-weight:bold;">⛔{esc}</span>')
                plain_parts.append(f"⛔{t}")
            else:
                html_parts.append(esc)
                plain_parts.append(str(t))
        return ", ".join(html_parts), ", ".join(plain_parts)

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

        # ---- Tag 文本（黑名单 Tag 高亮）----
        if override_tags is not None:
            tags = override_tags if isinstance(override_tags, list) else [str(override_tags)]
        else:
            tags = self.tags_index.get(norm_symbol(symbol), [])
        hits = self._blacklist_hits(symbol)            # 不论是否屏蔽，都用于标识
        if tags:
            rich, plain = self._tags_rich_text(tags, hits)
        else:
            rich = plain = "无标签"

        label = ClickableLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(rich)
        label.setFixedWidth(SYMBOL_WIDGET_FIXED_WIDTH)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        font_size = 16
        label.setFont(QFont("Arial", font_size))
        fm = label.fontMetrics()
        rect = fm.boundingRect(0, 0, SYMBOL_WIDGET_FIXED_WIDTH - 20, 5000,
                               Qt.TextFlag.TextWordWrap, plain)
        label.setFixedHeight(max(rect.height() + 16, 35))

        if hits:
            sure = any(g == BL_GROUP_SURE for _, g in hits)
            border = f"2px solid {'#BF616A' if sure else '#D08770'}"
            bg = "#FFE9E9" if sure else "#FFF1E3"
        else:
            border, bg = "1px solid #e0e0d0", "lightyellow"
        label.setStyleSheet(f"""
            background-color: {bg};
            color: black;
            font-size: {font_size}px;
            padding-left: 8px; padding-right: 8px;
            padding-top: 6px; padding-bottom: 6px;
            border-radius: 4px;
            border: {border};
        """)
        label.clicked.connect(lambda s=symbol, src=source: self.on_symbol_click(s, src))
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda pos, s=symbol: self.show_context_menu(s))

        clean_sym = clean_ticker(symbol).upper()
        head_lines = []
        if hits:
            head_lines.append("⛔ 黑名单 Tag：" + "、".join(f"{t}[{g}]" for t, g in hits))
        hinfo = self.hidden_info.get(clean_sym)
        if hinfo:
            head_lines.append(f"（该股在「{'、'.join(hinfo['sections'])}」中已被屏蔽）")
        if head_lines:
            head = "\n".join(head_lines)
            tooltip = f"{head}\n\n{tooltip}" if tooltip else head
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

        self.symbol_widgets_map[clean_sym].append((container, button))
        if track is not None:
            track.append((clean_sym, container, button))
        return container

    def get_tags_for_symbol(self, symbol):
        tags = self.tags_index.get(norm_symbol(symbol))
        return tags if tags else "无标签"

    # ==================================================================
    # 标题信息与导航
    # ==================================================================
    def get_symbol_group_info(self, symbol, source=None):
        if source == 'holdings' and symbol in self.positions:
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

        if source == 'turning':
            for i, r in enumerate(self.view_turning):
                if r['symbol'] == symbol:
                    return (f"转折 {r['from_n']}→{r['to_n']} @{r['date']} {r['badge']} "
                            f"({i + 1}/{len(self.view_turning)})")

        if source == 'resonance':
            for item in self.view_resonance:
                if symbol in item['symbols']:
                    idx = item['symbols'].index(symbol)
                    badge = self.symbol_marks.get(symbol, {}).get('badge', '')
                    badge_str = f" {badge}" if badge else ""
                    return f"共振{item['count']}组{badge_str} ({idx + 1}/{len(item['symbols'])})"

        if symbol in self.positions:
            lst = self.list_holdings
            idx = lst.index(symbol) + 1 if symbol in lst else 0
            return f"持仓 ({idx}/{len(lst)})"
        for i, r in enumerate(self.view_turning):
            if r['symbol'] == symbol:
                return f"转折 {r['from_n']}→{r['to_n']} ({i + 1}/{len(self.view_turning)})"
        for item in self.view_resonance:
            if symbol in item['symbols']:
                idx = item['symbols'].index(symbol)
                return f"共振{item['count']}组 ({idx + 1}/{len(item['symbols'])})"
        return ""

    def on_symbol_click(self, symbol, source=None):
        self.nav_manager.set_current(symbol, source)
        self._plot_current_symbol(source)

    def _plot_current_symbol(self, preferred_source=None):
        item = self.nav_manager.current_item()
        if not item:
            return
        symbol, src = item
        if preferred_source:
            src = preferred_source

        pos_str = f"{symbol} {self.get_symbol_group_info(symbol, src)}".strip()
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
        if action == 'next':
            QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('next'))
        elif action == 'prev':
            QTimer.singleShot(50, lambda: self.navigate_symbol_from_chart('prev'))

    def navigate_symbol_from_chart(self, direction):
        item = self.nav_manager.next_item() if direction == 'next' else self.nav_manager.previous_item()
        if item:
            self._plot_current_symbol()

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
        sym = self.nav_manager.current_symbol()
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
        menu.addAction("编辑 Tags / 黑名单").triggered.connect(lambda: execute_external_script('tags', symbol))
        if TB_OK:
            menu.addAction("⛔ 分组黑名单屏蔽设置 (B)").triggered.connect(self.open_blacklist_settings)
        menu.addSeparator()
        menu.addAction("打开 High/Low 面板").triggered.connect(lambda: execute_external_script('highlow', symbol))
        if symbol in self.positions:
            menu.addSeparator()
            menu.addAction("🔄 重新读取持仓 (R)").triggered.connect(self.reload_positions)
        menu.exec(QCursor.pos())

    def closeEvent(self, event):
        try:
            self.watch_timer.stop()
        except Exception:
            pass
        self.nav_manager.reset(); QApplication.quit(); event.accept()


if __name__ == '__main__':
    try:
        colors = load_json(COLORS_PATH)
        desc = load_json(DESCRIPTION_PATH)
        sects = load_json(SECTORS_ALL_PATH)
        comp = load_text_data(COMPARE_DATA_PATH)
        earn_hist = load_json(EARNING_HISTORY_PATH)

        app = QApplication(sys.argv)

        if TB_OK:
            try:
                TB.ensure_file()
            except Exception as e:
                print(f"[黑名单] 创建文件失败: {e}")

        # 不再弹窗：直接按默认 / 上次保存的分组配置打开
        win = GroupWindow(colors, sects, comp, desc, earn_hist)
        win.show()
        win.raise_()
        win.activateWindow()
        sys.exit(app.exec())
    except Exception as e:
        traceback.print_exc()
        print(f"启动失败: {e}")