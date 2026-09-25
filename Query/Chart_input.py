"""
Chart_input.py —— 统一的价格曲线图表模块（合并自 Chart_input / Chart_input_single）

用法（签名与旧版完全一致）：
    from Chart_input import plot_financial_data
    plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel=False, callback=None,
                        window_title_text=None, display_name=None, block=None)

运行模式自动判定：
  * 调用时 Qt 事件循环已在运行（Panel / Check_Group / Check_HighLow / Insert_Earning_auto /
    Check_Options / Check_Earning_Similar / Search_Similar_Tag ...）：
        → 非阻塞；进程内复用同一个图表窗口，切换 symbol 只刷新数据。
  * 调用时没有事件循环在运行（Stock_Chart.py 这类独立脚本）：
        → 本模块自己阻塞运行，直到图表窗口关闭。
  * 也可以用 block=True/False 显式指定。

回调 callback(action)：action ∈ {'next', 'prev', 'deleted'}
"""
import os
import re
import sys
import json
import glob
import time
import sqlite3
import threading
import subprocess
import warnings
import traceback
from datetime import datetime, timedelta, date
from functools import lru_cache

# ---- 先导入 PyQt6，再强制 matplotlib 使用 QtAgg 后端 ----
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QThread

import numpy as np
import matplotlib
try:
    matplotlib.use("QtAgg")
except Exception as _e:
    print(f"[Chart] 切换 QtAgg 后端失败: {_e}")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import RadioButtons
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.collections import LineCollection
from scipy.interpolate import interp1d

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DEFAULT_DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")

# --- 买入/卖出痕迹（Firstrade order-status 抓取结果） ---
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.append(_THIS_DIR)
try:
    from ft_trades import (get_trades_for_symbol, build_marker_text, short_trade_label,
                           BUY_COLOR, SELL_COLOR, BUY_MARKER, SELL_MARKER)
except Exception as _e:
    print(f"[FT] 加载 ft_trades 失败（买卖点将不显示）: {_e}")
    BUY_COLOR, SELL_COLOR, BUY_MARKER, SELL_MARKER = '#5E81AC', '#D08770', '^', 'v'
    def get_trades_for_symbol(_s): return {}
    def build_marker_text(*_a, **_k): return ''
    def short_trade_label(*_a, **_k): return ''

# --- 持仓 / 自选股行情统一读取层 ---
try:
    from ft_quotes import (build_market_items, get_firstrade_position,
                           get_watchlist_quote, _ft_norm_sym,
                           FT_DEBUG, FT_SHOW_MISS,
                           FIRSTRADE_POSITIONS_FILE, FIRSTRADE_WATCHLIST_FILE,
                           build_membership_items, membership_signature)
except Exception as _e:
    print(f"[FT] 加载 ft_quotes 失败（持仓/自选行情将不显示）: {_e}")
    FT_DEBUG, FT_SHOW_MISS = False, False
    FIRSTRADE_POSITIONS_FILE = FIRSTRADE_WATCHLIST_FILE = ""
    def _ft_norm_sym(s): return str(s).strip().upper().replace('.', '-')
    def get_firstrade_position(_s): return None
    def get_watchlist_quote(_s): return None
    def build_market_items(_s, _t, show_miss=None): return []
    def build_membership_items(_s, _t): return []
    def membership_signature(): return 0.0

# --- Firstrade 一键加入自选股分组 ---
try:
    from ft_watchlist_add import (add_symbol_async, watchlist_groups,
                                  choose_group_dialog, last_group, save_last_group,
                                  notify_mac, scan_groups_async)
    FT_WL_ADD_OK = True
except Exception as _e:
    print(f"[FT] 加载 ft_watchlist_add 失败（一键加自选不可用）: {_e}")
    FT_WL_ADD_OK = False
    def watchlist_groups(): return []
    def choose_group_dialog(*a, **k): return None
    def last_group(): return ""
    def scan_groups_async(*a, **k): return None
    def save_last_group(g): pass
    def notify_mac(*a, **k): pass
    def add_symbol_async(*a, **k): return None

# --- 导入 Tiger_API ---
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Selenium"))
try:
    from Tiger_API import _get_global_fetcher
except ImportError as e:
    print(f"导入 Tiger_API 失败: {e}")
    def _get_global_fetcher():
        raise RuntimeError("Tiger_API 不可用")

# --- Nord 主题 ---
NORD_THEME = {
    'background': '#2E3440',
    'widget_bg': '#3B4252',
    'border': '#4C566A',
    'text_light': '#D8DEE9',
    'text_bright': '#ECEFF4',
    'accent_blue': '#5E81AC',
    'accent_cyan': '#88C0D0',
    'accent_red': '#BF616A',
    'accent_orange': '#D08770',
    'accent_yellow': '#EBCB8B',
    'pure_yellow': 'yellow',
    'accent_green': '#A3BE8C',
    'accent_deepgreen': '#607254',
    'accent_purple': '#B48EAD',
}

TIME_OPTIONS = {"1m": 0.08, "3m": 0.25, "6m": 0.5, "1Y": 1, "2Y": 2,
                "3Y": 3, "5Y": 5, "10Y": 10, "All": 0}
HOVER_THROTTLE = 1 / 90.0
REBUILD_THROTTLE = 0.15


# ======================================================================
# 通用工具
# ======================================================================
def _file_sig(*paths):
    """文件修改时间签名，用作缓存失效键"""
    sig = []
    for p in paths:
        try:
            sig.append(os.path.getmtime(p))
        except OSError:
            sig.append(0.0)
    return tuple(sig)


def _db_sig(db_path):
    # WAL 模式下写入先落到 -wal 文件，所以两者都要看
    return _file_sig(db_path, db_path + "-wal")


def _to_bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return bool(v)


def _qt_loop_running():
    """当前线程是否已处于 Qt 事件循环中"""
    app = QApplication.instance()
    if app is None:
        return False
    try:
        return QThread.currentThread().loopLevel() > 0
    except Exception:
        # 兜底：有可见的顶层窗口，基本可以认为是嵌入在 GUI 程序里
        try:
            return any(w.isVisible() for w in QApplication.topLevelWidgets())
        except Exception:
            return False


def display_dialog(message):
    msg = str(message).replace('\\', '\\\\').replace('"', '\\"')
    try:
        subprocess.run(['osascript', '-e',
                        f'display dialog "{msg}" buttons {{"OK"}} default button "OK"'],
                       check=False)
    except Exception:
        print(message)


def _ft_layout_text_row(fig, x0, y, items, fontsize=12, gap_px=10, x_limit=0.345):
    """按实际像素宽度自适应地把 [(文本, 颜色, 粗细), ...] 横向排成一行，避免互相重叠"""
    arts = []
    try:
        renderer = fig.canvas.get_renderer()
    except Exception:
        renderer = None
    fig_w_px = max(1.0, fig.get_figwidth() * fig.dpi)
    x = x0
    for txt, color, weight in items:
        if x > x_limit:
            break
        t = fig.text(x, y, txt, color=color, fontsize=fontsize, fontweight=weight,
                     ha='left', va='top', fontname='Arial Unicode MS')
        arts.append(t)
        w_frac = None
        if renderer is not None:
            try:
                w_frac = (t.get_window_extent(renderer=renderer).width + gap_px) / fig_w_px
            except Exception:
                w_frac = None
        if not w_frac or w_frac <= 0:
            w_frac = (len(txt) * fontsize * 0.62 + gap_px) / fig_w_px
        x += w_frac
    return arts


# ============ 全局实时价格管理器 ============
class _RealtimeManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._symbol = None
        self._latest = {}
        self._thread = None
        self._stop = threading.Event()
        self._fetcher = None

    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def set_symbol(self, symbol):
        with self._lock:
            self._symbol = symbol
        self._ensure_thread()

    def get_latest(self, symbol):
        with self._lock:
            return self._latest.get(symbol)

    def _run(self):
        try:
            self._fetcher = _get_global_fetcher()
        except Exception as e:
            print(f"初始化 fetcher 失败: {e}")
            return
        while not self._stop.is_set():
            with self._lock:
                sym = self._symbol
            if sym:
                try:
                    quote = self._fetcher.get_realtime_quote(sym)
                    if quote and 'price' in quote:
                        with self._lock:
                            self._latest[sym] = quote['price']
                except Exception as e:
                    print(f"后台获取实时价格失败: {e}")
            if self._stop.wait(timeout=5.0):
                break


_RT_MANAGER = _RealtimeManager()


# ============ Earning Release（按文件 mtime 自动失效） ============
_EARNING_RELEASE_CACHE = {"sig": None, "data": {}}


def _load_all_earning_releases(txt_dir=None):
    if txt_dir is None:
        txt_dir = os.path.join(BASE_CODING_DIR, "News")
    files = sorted(glob.glob(os.path.join(txt_dir, 'Earnings_Release_*.txt')))
    sig = tuple((f, _file_sig(f)[0]) for f in files)
    if _EARNING_RELEASE_CACHE["sig"] == sig:
        return _EARNING_RELEASE_CACHE["data"]
    result = {}
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split(':')]
                    if len(parts) >= 3:
                        sym, date_str = parts[0], parts[2]
                        if sym not in result:
                            try:
                                result[sym] = datetime.strptime(date_str, "%Y-%m-%d").date()
                            except ValueError:
                                pass
        except Exception as e:
            print(f"读取文件 {file_path} 时出错: {e}")
    _EARNING_RELEASE_CACHE["sig"] = sig
    _EARNING_RELEASE_CACHE["data"] = result
    return result


def find_earning_release_date(symbol, txt_dir=None):
    return _load_all_earning_releases(txt_dir).get(symbol)


# ============ Polymarket（按文件 mtime 自动失效） ============
_POLYMARKET_PATH = os.path.join(BASE_CODING_DIR, "News", "earning_polymarket.txt")


@lru_cache(maxsize=4)
def _load_polymarket_cached(_sig):
    data = {}
    if not os.path.exists(_POLYMARKET_PATH):
        return data
    try:
        with open(_POLYMARKET_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(':')
                if len(parts) == 2:
                    data[parts[0].strip()] = parts[1].strip()
    except Exception as e:
        print(f"读取 polymarket 文件出错: {e}")
    return data


def _load_polymarket_data():
    return _load_polymarket_cached(_file_sig(_POLYMARKET_PATH))


def get_polymarket_percentage(symbol):
    return _load_polymarket_data().get(symbol)


# ============ 日期区间 ============
def calculate_three_weeks_before_range(target_date):
    three_weeks_before = target_date - timedelta(days=21)
    week_start = three_weeks_before - timedelta(days=three_weeks_before.weekday())
    return week_start, week_start + timedelta(days=4)


def calculate_one_week_before_range(target_date):
    one_week_before = target_date - timedelta(days=7)
    week_start = one_week_before - timedelta(days=one_week_before.weekday())
    return week_start, week_start + timedelta(days=4)


def calculate_five_weeks_after_range(target_date):
    current_week_start = target_date - timedelta(days=target_date.weekday())
    target_week_start = current_week_start + timedelta(weeks=5)
    return target_week_start, target_week_start + timedelta(days=4)


def calculate_three_weeks_after_range(target_date):
    current_week_start = target_date - timedelta(days=target_date.weekday())
    target_week_start = current_week_start + timedelta(weeks=3)
    return target_week_start, target_week_start + timedelta(days=4)


# ============ 标题颜色（按 DB mtime 自动失效） ============
def get_title_color_logic(db_path, symbol, table_name):
    return _title_color_cached(db_path, symbol, table_name, _db_sig(db_path))


@lru_cache(maxsize=256)
def _title_color_cached(db_path, symbol, table_name, _sig):
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT date, price FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 2",
                (symbol,)
            )
            earning_rows = cursor.fetchall()
        if not earning_rows:
            return NORD_THEME['text_bright']
        latest_earning_date_str, latest_earning_price_str = earning_rows[0]
        latest_earning_date = datetime.strptime(latest_earning_date_str, "%Y-%m-%d").date()
        latest_earning_price = float(latest_earning_price_str) if latest_earning_price_str is not None else 0.0
        if (date.today() - latest_earning_date).days > 75:
            return NORD_THEME['text_bright']
        if len(earning_rows) < 2:
            price_trend = 'single'
        else:
            previous_earning_date_str, _ = earning_rows[1]
            previous_earning_date = datetime.strptime(previous_earning_date_str, "%Y-%m-%d").date()
            with sqlite3.connect(db_path, timeout=60.0) as conn:
                cursor = conn.cursor()
                cursor.execute(f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?',
                               (symbol, latest_earning_date.isoformat()))
                latest_stock_price_row = cursor.fetchone()
                cursor.execute(f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?',
                               (symbol, previous_earning_date.isoformat()))
                previous_stock_price_row = cursor.fetchone()
            if not latest_stock_price_row or not previous_stock_price_row:
                return NORD_THEME['text_bright']
            price_trend = 'rising' if float(latest_stock_price_row[0]) > float(previous_stock_price_row[0]) else 'falling'
        color = NORD_THEME['text_bright']
        if price_trend == 'single':
            if latest_earning_price > 0: color = NORD_THEME['accent_red']
            elif latest_earning_price < 0: color = NORD_THEME['accent_green']
        else:
            is_price_positive = latest_earning_price > 0
            is_trend_rising = price_trend == 'rising'
            if is_trend_rising and is_price_positive: color = NORD_THEME['accent_red']
            elif not is_trend_rising and is_price_positive: color = NORD_THEME['accent_green']
            elif is_trend_rising and not is_price_positive: color = NORD_THEME['accent_purple']
            elif not is_trend_rising and not is_price_positive: color = NORD_THEME['accent_deepgreen']
        return color
    except Exception as e:
        print(f"[颜色决策逻辑错误] {symbol}: {e}")
        return NORD_THEME['text_bright']


# ============ 行情数据（按 DB mtime 自动失效） ============
def fetch_data(db_path, table_name, name):
    return _fetch_data_cached(db_path, table_name, name, _db_sig(db_path))


@lru_cache(maxsize=256)
def _fetch_data_cached(db_path, table_name, name, _sig):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        # 索引名在 SQLite 中是全库唯一的，必须按表区分
        idx_name = "idx_" + re.sub(r'\W', '_', str(table_name)) + "_name"
        try:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" (name);')
        except sqlite3.Error:
            pass
        for cols in ("date, price, volume, open, high, low",
                     "date, price, volume, open",
                     "date, price, volume"):
            try:
                result = cursor.execute(
                    f'SELECT {cols} FROM "{table_name}" WHERE name = ? ORDER BY date;', (name,)
                ).fetchall()
                if result:
                    return tuple(result)
            except sqlite3.OperationalError:
                pass
        result = cursor.execute(
            f'SELECT date, price FROM "{table_name}" WHERE name = ? ORDER BY date;', (name,)
        ).fetchall()
        if not result:
            raise ValueError("没有查询到可用数据")
        return tuple(result)


def smooth_curve(dates, prices, num_points=500):
    date_nums = mdates.date2num(dates)
    kind = 'linear' if len(dates) < 4 else 'cubic'
    interp_func = interp1d(date_nums, prices, kind=kind)
    new_date_nums = np.linspace(min(date_nums), max(date_nums), num_points)
    return mdates.num2date(new_date_nums), interp_func(new_date_nums)


def process_data(data):
    if not data:
        raise ValueError("没有可供处理的数据")
    dates, prices, volumes, opens, highs, lows = [], [], [], [], [], []
    for row in data:
        d = datetime.strptime(row[0], "%Y-%m-%d")
        price = float(row[1]) if row[1] is not None else None
        volume = int(row[2]) if len(row) > 2 and row[2] is not None else None
        open_price = float(row[3]) if len(row) > 3 and row[3] is not None else None
        high_price = float(row[4]) if len(row) > 4 and row[4] is not None else None
        low_price = float(row[5]) if len(row) > 5 and row[5] is not None else None
        if price is not None:
            dates.append(d)
            prices.append(price)
            volumes.append(volume)
            opens.append(open_price)
            highs.append(high_price)
            lows.append(low_price)
    return dates, prices, volumes, opens, highs, lows


def update_plot(line1, gradient_image, line2, dates, prices, volumes, ax1, ax2, show_volume, cmap,
                force_recreate=False, gradient_clip_patch=None, zero_line=None):
    """imshow + clip_path 渐变填充；含高价股视觉比例优化"""
    fig = ax1.figure
    if not dates or not prices:
        line1.set_data([], [])
        if volumes: line2.set_data([], [])
        ax1.set_xlim(datetime.now() - timedelta(days=1), datetime.now())
        ax1.set_ylim(0, 1)
        if show_volume: ax2.set_ylim(0, 1)
        line2.set_visible(show_volume and bool(volumes))
        if zero_line is not None:
            zero_line.set_visible(False)
        if gradient_image:
            gradient_image.set_visible(False)
            fig.canvas.draw_idle()
        return gradient_image

    if gradient_image and not gradient_image.get_visible():
        gradient_image.set_visible(True)

    line1.set_data(dates, prices)
    if volumes:
        line2.set_data(dates, volumes)
    else:
        line2.set_data([], [])

    date_min_val, date_max_val = np.min(dates), np.max(dates)
    if date_min_val == date_max_val:
        ax1.set_xlim(date_min_val - timedelta(days=1), date_max_val + timedelta(days=1))
    else:
        ax1.set_xlim(date_min_val, date_max_val + (date_max_val - date_min_val) * 0.01)

    min_p, max_p = np.min(prices), np.max(prices)
    MIN_DISPLAY_PCT = 0.15
    actual_span = max_p - min_p
    min_required_span = abs(max_p) * MIN_DISPLAY_PCT
    top_pad = 0.1

    if min_p == max_p:
        buffer = abs(min_p * 0.1) if min_p != 0 else 0.1
        ax1.set_ylim(min_p - buffer, max_p + buffer)
    elif actual_span < min_required_span:
        center_price = (max_p + min_p) / 2
        half_span = min_required_span / 2
        top_pad = abs(max_p) * 0.02
        ax1.set_ylim(center_price - half_span, center_price + half_span + top_pad)
    else:
        top_pad = max(actual_span * 0.03, 0.02 * max(1.0, abs(max_p)))
        ax1.set_ylim(min_p - actual_span * 0.01, max_p + top_pad)

    if zero_line is not None:
        if min_p < 0.0:
            zero_line.set_visible(True)
            y0, y1 = ax1.get_ylim()
            if y1 < 0:
                ax1.set_ylim(y0, 0 + top_pad)
            elif y0 > 0:
                ax1.set_ylim(0 - ((y1 - y0) * 0.05), y1)
        else:
            zero_line.set_visible(False)

    if show_volume:
        valid_v = [v for v in (volumes or []) if v is not None]
        ax2.set_ylim(0, np.max(valid_v) if valid_v else 1)

    xlim = ax1.get_xlim()
    ylim = ax1.get_ylim()
    fill_base = 0 if max_p < 0 else ylim[0]
    line_x_nums = mdates.date2num(dates)
    verts = [(line_x_nums[0], fill_base), *zip(line_x_nums, prices), (line_x_nums[-1], fill_base)]
    clip_path = Path(verts)

    if gradient_clip_patch is not None and gradient_clip_patch[0] is not None:
        try: gradient_clip_patch[0].remove()
        except Exception: pass
        gradient_clip_patch[0] = None

    if force_recreate or gradient_image is None:
        if gradient_image is not None:
            try: gradient_image.remove()
            except Exception: pass
        gradient = np.linspace(1.0, 0.0, 256).reshape(-1, 1)
        gradient_image = ax1.imshow(
            gradient, aspect='auto', cmap=cmap, extent=[*xlim, *ylim],
            origin='lower', zorder=1, interpolation='nearest'
        )
    else:
        gradient_image.set_extent([*xlim, *ylim])

    new_clip_patch = PathPatch(clip_path, transform=ax1.transData, facecolor='none', edgecolor='none')
    ax1.add_patch(new_clip_patch)
    gradient_image.set_clip_path(new_clip_patch)
    if gradient_clip_patch is not None:
        gradient_clip_patch[0] = new_clip_patch

    line2.set_visible(show_volume and bool(volumes))
    fig.canvas.draw_idle()
    return gradient_image


class InfoDialog(QDialog):
    def __init__(self, title, content, font_family, font_size, width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(0, 0, width, height)
        self.center_on_screen()
        layout = QVBoxLayout(self)
        text_box = QTextEdit(self)
        text_box.setReadOnly(True)
        text_box.setFont(QFont(font_family))
        text_box.setText(content)
        layout.addWidget(text_box)
        self.setLayout(layout)
        self.apply_nord_style(font_size)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def center_on_screen(self):
        screen_geometry = QApplication.primaryScreen().geometry()
        self.move((screen_geometry.width() - self.width()) // 2,
                  (screen_geometry.height() - self.height()) // 2)

    def apply_nord_style(self, font_size):
        self.setStyleSheet(f"""
        QDialog {{ background-color: {NORD_THEME['background']}; }}
        QTextEdit {{
            background-color: {NORD_THEME['widget_bg']}; color: {NORD_THEME['text_bright']};
            border: 1px solid {NORD_THEME['border']}; border-radius: 5px;
            font-size: {font_size}px; padding: 5px;
        }}
        QScrollBar:vertical {{
            border: none; background: {NORD_THEME['widget_bg']}; width: 10px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {NORD_THEME['accent_blue']}; min-height: 20px; border-radius: 5px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)


def execute_external_script(script_type, keyword, on_done=None, block=False):
    fs = os.path.join(BASE_CODING_DIR, 'Financial_System')
    se = os.path.join(BASE_CODING_DIR, 'ScriptEditor')
    script_configs = {
        'earning_input': os.path.join(fs, 'Operations', 'Insert_Earning_Manual.py'),
        'earning_edit': os.path.join(fs, 'Operations', 'Editor_Earning_DB.py'),
        'tags_edit': os.path.join(fs, 'Operations', 'Editor_Tags.py'),
        'event_input': os.path.join(fs, 'Operations', 'Insert_Events.py'),
        'event_edit': os.path.join(fs, 'Operations', 'Editor_Events.py'),
        'symbol_compare': os.path.join(fs, 'Query', 'Compare_Chart.py'),
        'panel_input': os.path.join(fs, 'Operations', 'Insert_Panel.py'),
        'panel_delete': os.path.join(fs, 'Operations', 'Delete_Panel.py'),
        'similar_tags': os.path.join(fs, 'Query', 'Search_Similar_Tag.py'),
        'check_history': os.path.join(fs, 'Query', 'Check_Earning_history.py'),
        'check_kimi': os.path.join(se, 'Check_Earning.scpt'),
        'check_futu': os.path.join(se, 'Stock_CheckFutu.scpt'),
        'check_seekingalpha': os.path.join(se, 'Stock_seekingalpha.scpt'),
        'stock_chart': os.path.join(se, 'Stock_Chart.scpt'),
    }
    script_path = script_configs.get(script_type)
    if not script_path:
        display_dialog(f"未知的脚本类型: {script_type}")
        return
    try:
        if script_path.endswith('.scpt'):
            if block:
                subprocess.run(['osascript', script_path, keyword], check=False)
            else:
                subprocess.Popen(['osascript', script_path, keyword])
            if callable(on_done):
                on_done()
        else:
            if block:
                result = subprocess.run([sys.executable, script_path, keyword], check=False)
                if callable(on_done):
                    on_done(result.returncode)
            else:
                proc = subprocess.Popen([sys.executable, script_path, keyword])
                if callable(on_done):
                    on_done(proc.returncode)
    except Exception as e:
        display_dialog(f"启动程序失败: {e}")


# ============ 期权数据（按 DB mtime 自动失效） ============
def get_options_metrics(symbol):
    return _options_metrics_cached(symbol, _db_sig(DEFAULT_DB_PATH))


@lru_cache(maxsize=256)
def _options_metrics_cached(symbol, _sig):
    try:
        with sqlite3.connect(DEFAULT_DB_PATH, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT iv, price, change, date FROM Options WHERE name = ? ORDER BY date DESC LIMIT 2",
                (symbol,)
            )
            rows = cursor.fetchall()
        if len(rows) < 2:
            return None

        def parse_row(row):
            iv_s = row[0] if row[0] else "--"
            try:
                iv_v = float(iv_s.replace('%', '').replace(' ', '')) if isinstance(iv_s, str) and '%' in iv_s else 0.0
            except Exception:
                iv_v = 0.0
            p = float(row[1]) if row[1] is not None else 0.0
            c = float(row[2]) if row[2] is not None else 0.0
            try:
                d_obj = datetime.strptime(row[3], "%Y-%m-%d").date()
            except Exception:
                d_obj = None
            return iv_v, iv_s, p + c, d_obj

        iv1_val, iv1_str, sum1_val, date1 = parse_row(rows[0])
        iv2_val, iv2_str, sum2_val, date2 = parse_row(rows[1])
        return {'iv1': (iv1_val, iv1_str), 'iv2': (iv2_val, iv2_str),
                'sum1': sum1_val, 'sum2': sum2_val, 'date1': date1, 'date2': date2}
    except Exception as e:
        print(f"读取 Options 表出错: {e}")
        return None


def clean_percentage_string(s):
    try:
        return float(s.strip('%'))
    except (ValueError, AttributeError):
        return None


def query_database_text(db_path, table_name, condition):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        cursor.execute(f'SELECT * FROM "{table_name}" WHERE {condition} ORDER BY date DESC;')
        rows = cursor.fetchall()
        if not rows:
            return "今天没有数据可显示。\n"
        cols = [d[0] for d in cursor.description]
        widths = [max(len(str(r[i])) for r in rows + [cols]) for i in range(len(cols))]
        header = ' | '.join([c.ljust(widths[i]) for i, c in enumerate(cols)])
        lines = [header, '-' * len(header)]
        for row in rows:
            lines.append(' | '.join([str(item).ljust(widths[i]) for i, item in enumerate(row)]))
        return '\n'.join(lines)


# ======================================================================
# 可复用的图表窗口（进程级单例）
# ======================================================================
class ChartWindow:
    def __init__(self):
        self.closed = False
        self.owns_loop = False       # 是否由本模块阻塞运行事件循环（独立脚本模式）
        matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
        matplotlib.rcParams['toolbar'] = 'none'
        # 关掉 matplotlib 默认快捷键，避免抢键
        for _k in ('keymap.fullscreen', 'keymap.save', 'keymap.quit', 'keymap.quit_all',
                   'keymap.grid', 'keymap.grid_minor', 'keymap.yscale', 'keymap.xscale',
                   'keymap.home', 'keymap.back', 'keymap.forward',
                   'keymap.pan', 'keymap.zoom', 'keymap.copy', 'keymap.help'):
            try:
                matplotlib.rcParams[_k] = []
            except Exception:
                pass

        # ---------- 静态部分：只创建一次 ----------
        self.fig, self.ax1 = plt.subplots(figsize=(16, 8))
        self.fig.subplots_adjust(left=0.05, bottom=0.1, right=0.83, top=0.8)
        self.ax2 = self.ax1.twinx()
        self.ax2.axis('off')
        self.fig.patch.set_facecolor(NORD_THEME['background'])

        ax1 = self.ax1
        ax1.set_facecolor(NORD_THEME['background'])
        ax1.spines['bottom'].set_visible(True)
        for sp in ('top', 'right', 'left'):
            ax1.spines[sp].set_visible(False)
        ax1.tick_params(axis='y', which='both', left=False, labelleft=False)
        ax1.tick_params(axis='x', colors=NORD_THEME['text_light'], rotation=45)
        ax1.spines['bottom'].set_color(NORD_THEME['border'])
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.grid(True, color=NORD_THEME['border'], alpha=0.1, linestyle='--')

        self.highlight_point = ax1.scatter([], [], s=100, color=NORD_THEME['accent_cyan'], zorder=5)
        self.line1, = ax1.plot([], [], marker='', linestyle='-', linewidth=2,
                               color=NORD_THEME['accent_cyan'], alpha=0.8, label='Price', zorder=2)
        self.small_dot_scatter = ax1.scatter([], [], s=5, color=NORD_THEME['text_bright'], zorder=1.5)
        self.line2, = self.ax2.plot([], [], marker='o', markersize=2, linestyle='-', linewidth=2,
                                    color=NORD_THEME['accent_purple'], alpha=0.7, label='Turnover')
        self.line2.set_visible(False)

        self.zero_line = ax1.axhline(y=0, color=NORD_THEME['text_bright'], linestyle=(0, (6, 3)),
                                     linewidth=1.8, alpha=0.95, zorder=3, visible=False)

        cyan_base_color = matplotlib.colors.to_rgb(NORD_THEME['accent_cyan'])
        self.cyan_transparent_cmap = LinearSegmentedColormap.from_list(
            'cyan_transparent_gradient', [(*cyan_base_color, 0.0), (*cyan_base_color, 0.5)])

        self.annot = ax1.annotate(
            "", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
            bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_cyan']),
            arrowprops=dict(arrowstyle="->"), color=NORD_THEME['text_bright'], visible=False)
        self.vline = ax1.axvline(x=0, color=NORD_THEME['accent_cyan'], linestyle='--',
                                 linewidth=1, visible=False)

        self.title_artist = self.fig.text(0.5, 0.95, "", ha='center', va='top',
                                          color=NORD_THEME['text_bright'], fontsize=16,
                                          fontweight='bold', transform=self.fig.transFigure)

        # 一键加自选：状态提示行 + 后台线程结果队列
        self.wl_status_artist = self.fig.text(
            0.5, 0.885, "", ha='center', va='top', fontsize=13, fontweight='bold',
            color=NORD_THEME['accent_yellow'], visible=False,
            transform=self.fig.transFigure, fontname='Arial Unicode MS')
        self._wl_results = []
        self._wl_hide_at = 0.0
        self.member_artists = []
        self._member_sig = None

        # RadioButtons（activecolor 兼容新旧 matplotlib）
        self.rax = self.fig.add_axes([0.95, 0.0, 0.05, 0.65], facecolor=NORD_THEME['background'])
        self.radio = RadioButtons(self.rax, list(TIME_OPTIONS.keys()), active=3,
                                  activecolor=NORD_THEME['accent_red'])
        self.rax.set_facecolor(NORD_THEME['background'])
        self.rax.set_frame_on(False)
        for spine in self.rax.spines.values():
            spine.set_visible(False)
        for label in self.radio.labels:
            label.set_color(NORD_THEME['text_light'])
            label.set_fontsize(14)
        self._style_radio_edges()

        instructions = ("E:改财报\nW:新事件\nQ:改事件\nK:查豆包\n"
                        "P:做比较\nJ:加Panel\nL:查相似\nY:删除\nB:分组\n"
                        "I/U:买入卖出点\nF:加自选\n⇧F:同上组\nM:刷新分组")
        self.rax.text(0.5, 0.98, instructions, transform=self.rax.transAxes, ha="center", va="bottom",
                      color=NORD_THEME['text_light'], fontsize=10, fontfamily="Arial Unicode MS")

        # ---------- 每 symbol 状态容器 ----------
        self.gradient_image = None
        self.gradient_clip_patch = [None]
        self.colored_lc = [None]
        self.subtitle_artists = []
        self.pa_text_artist = [None]
        self.current_pre_after_pct = [None]

        self.global_markers, self.specific_markers, self.earning_markers = {}, {}, {}
        self.global_scatter_points, self.specific_scatter_points, self.earning_scatter_points = [], [], []
        self.buy_markers, self.sell_markers = {}, {}
        self.buy_scatter_points, self.sell_scatter_points = [], []
        self.trade_map = {}
        self.show_buy_markers = True
        self.show_sell_markers = True
        self.all_annotations = []

        self.purple_shade = None
        self.blue_shade = None
        self.post_earning_shade = None
        self.post_earning_shade_3w = None
        self.earning_release_date = None
        self.latest_db_earning_date = None

        self.name = None
        self.callback = None
        self.panel = False
        self.clickable = False
        self.dates, self.prices = [], []

        self.last_hover_ts = 0.0
        self.last_rebuild_ts = 0.0

        self.DESCRIPTION_JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")

        # ---------- 事件绑定 ----------
        c = self.fig.canvas
        c.mpl_connect("motion_notify_event", self.hover)
        c.mpl_connect('key_press_event', self.on_key)
        c.mpl_connect('button_press_event', self.on_mouse_press)
        c.mpl_connect('button_release_event', self.on_mouse_release)
        c.mpl_connect('pick_event', self.on_pick)
        c.mpl_connect('figure_leave_event', self.hide_annot_on_leave)
        c.mpl_connect('close_event', self._on_close)
        self.radio.on_clicked(self.update)

        self.ui_timer = c.new_timer(interval=1000)
        self.ui_timer.add_callback(self._ui_poll_realtime)
        self.ui_timer.start()

        try:
            c.toolbar_visible = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    # RadioButtons 新旧 matplotlib 兼容
    # ------------------------------------------------------------------
    def _radio_circles(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                return getattr(self.radio, 'circles', None)
            except Exception:
                return None

    def _style_radio_edges(self):
        circles = self._radio_circles()
        if circles:
            for circle in circles:
                circle.set_edgecolor(NORD_THEME['border'])
                circle.set_facecolor(NORD_THEME['background'])
            circles[3].set_facecolor(NORD_THEME['accent_red'])
            return
        btns = getattr(self.radio, '_buttons', None)
        if btns is not None:
            try:
                btns.set_edgecolor(NORD_THEME['border'])
            except Exception:
                pass

    def _paint_radio(self, active_label):
        keys = list(TIME_OPTIONS.keys())
        circles = self._radio_circles()
        if circles:
            for i, circle in enumerate(circles):
                circle.set_facecolor(NORD_THEME['accent_red'] if keys[i] == active_label
                                     else NORD_THEME['background'])
            return
        btns = getattr(self.radio, '_buttons', None)
        if btns is not None:
            try:
                btns.set_facecolor([NORD_THEME['accent_red'] if k == active_label else 'none' for k in keys])
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 加载 / 切换 symbol
    # ------------------------------------------------------------------
    def load(self, db_path, table_name, name, compare, share, marketcap, pe, json_data,
             default_time_range="1Y", panel=False, callback=None,
             window_title_text=None, display_name=None):
        # ---- 1) 先取数，失败时不破坏当前窗口状态 ----
        if not table_name:
            display_dialog(f"未在 Sectors_All.json 中找到 {name} 所属板块，无法绘图。")
            return False
        if default_time_range not in TIME_OPTIONS:
            default_time_range = "1Y"
        try:
            data = fetch_data(db_path, table_name, name)
            dates, prices, volumes, opens, highs, lows = process_data(data)
        except (ValueError, sqlite3.Error) as e:
            display_dialog(f"{name}: {e}")
            return False
        if not dates or not prices:
            display_dialog("没有有效的数据来绘制图表。")
            return False

        # ---- 2) 提交状态 ----
        self.db_path = db_path
        self.table_name = table_name
        self.name = name
        self.compare = compare
        self.marketcap = marketcap
        self.pe = pe
        self.panel = _to_bool(panel)
        self.callback = callback
        self.display_name = display_name
        self.current_json_data = {'data': json_data}
        self.dates, self.prices, self.volumes = dates, prices, volumes
        self.opens, self.highs, self.lows = opens, highs, lows

        if isinstance(share, tuple):
            self.share_val, pb = share
            self.pb_text = f"{pb}" if pb not in [None, ""] else "--"
        else:
            self.share_val, self.pb_text = share, "--"

        self.show_volume = False
        self.mouse_pressed = False
        self.initial_price = None
        self.initial_volume = None
        self.initial_date = None
        self.show_global_markers = False
        self.show_specific_markers = True
        self.show_earning_markers = True
        self.show_buy_markers = True
        self.show_sell_markers = True
        self.trade_map = get_trades_for_symbol(name)
        self.show_all_annotations = False
        self.show_colored_lines = True
        self.current_filtered_dates = []
        self.current_filtered_prices = []
        self.current_filtered_volumes = []
        self.current_filtered_date_nums = np.array([])
        self.current_filtered_opens = []
        self.current_filtered_highs = []
        self.current_filtered_lows = []
        self.last_hover_ts = 0.0
        self.last_rebuild_ts = 0.0
        self.current_pre_after_pct[0] = None

        self.has_ohlc = any(o is not None for o in self.opens)
        self.line1.set_alpha(0 if self.has_ohlc else 0.8)

        self.turnovers = [p * v if (p is not None and v is not None) else 0.0
                          for p, v in zip(self.prices, self.volumes)] if self.volumes else [0.0] * len(self.dates)

        self.date_nums = mdates.date2num(self.dates)
        self.small_dot_scatter.set_offsets(np.column_stack([self.date_nums, self.prices]))

        try:
            self.fig.canvas.manager.set_window_title(window_title_text if window_title_text else name)
        except Exception:
            pass

        self._clear_symbol_artists()
        self._setup_shades()

        # Earning markers（DB）
        try:
            with sqlite3.connect(db_path, timeout=60.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date", (name,))
                for date_str, price_change in cursor.fetchall():
                    try:
                        marker_date = datetime.strptime(date_str, "%Y-%m-%d")
                        closest_date = min(self.dates, key=lambda d: abs(d - marker_date))
                        index = self.dates.index(closest_date)
                        marker_price, latest_price = self.prices[index], self.prices[-1]
                        diff_percent = ((latest_price - marker_price) / marker_price) * 100 if marker_price else 0
                        self.earning_markers[marker_date] = f"昨日财报: {price_change}%\n最新价差: {diff_percent:.2f}%\n{date_str}"
                    except (ValueError, IndexError):
                        print(f"无法解析或处理收益公告日期: {date_str}")
        except sqlite3.OperationalError as e:
            print(f"获取收益数据失败: {e}")

        np_dates = np.array(self.dates)
        for marker_date, text in self.earning_markers.items():
            if min(self.dates) <= marker_date <= max(self.dates):
                idx = (np.abs(np_dates - marker_date)).argmin()
                scatter = self.ax1.scatter([self.dates[idx]], [self.prices[idx]], s=100,
                                           color=NORD_THEME['pure_yellow'], alpha=0.7, zorder=4,
                                           picker=5, visible=self.show_earning_markers)
                self.earning_scatter_points.append((scatter, self.dates[idx], self.prices[idx], text))

        self.create_markers_and_annotations()

        title_text, title_color, self.clickable = self.create_or_update_title()
        self.title_artist.set_text(title_text)
        self.title_artist.set_color(title_color)

        self.wl_status_artist.set_visible(False)
        self._wl_hide_at = 0.0
        self.annot.set_visible(False)
        self.highlight_point.set_visible(False)
        self.vline.set_visible(False)

        _RT_MANAGER.set_symbol(name)

        # 选中默认时间范围（关事件，避免 update 被触发两次），然后显式刷新一次
        default_index = list(TIME_OPTIONS.keys()).index(default_time_range)
        self.radio.eventson = False
        try:
            self.radio.set_active(default_index)
        finally:
            self.radio.eventson = True
        self.update(default_time_range)
        self._draw_membership(force=True)
        self.fig.canvas.draw_idle()
        return True

    # ------------------------------------------------------------------
    def _clear_symbol_artists(self):
        for attr in ('purple_shade', 'blue_shade', 'post_earning_shade', 'post_earning_shade_3w'):
            s = getattr(self, attr, None)
            if s is not None:
                try: s.remove()
                except Exception: pass
                setattr(self, attr, None)

        for lst in (self.global_scatter_points, self.specific_scatter_points,
                    self.earning_scatter_points, self.buy_scatter_points,
                    self.sell_scatter_points):
            for item in lst:
                try: item[0].remove()
                except Exception: pass
            lst.clear()

        for item in self.all_annotations:
            try: item[0].remove()
            except Exception: pass
        self.all_annotations.clear()

        self.global_markers.clear()
        self.specific_markers.clear()
        self.earning_markers.clear()
        self.buy_markers.clear()
        self.sell_markers.clear()

        if self.colored_lc[0] is not None:
            try: self.colored_lc[0].remove()
            except Exception: pass
            self.colored_lc[0] = None

        if self.gradient_image is not None:
            try: self.gradient_image.remove()
            except Exception: pass
            self.gradient_image = None
        if self.gradient_clip_patch[0] is not None:
            try: self.gradient_clip_patch[0].remove()
            except Exception: pass
            self.gradient_clip_patch[0] = None

        for a in self.subtitle_artists:
            try: a.remove()
            except Exception: pass
        self.subtitle_artists.clear()
        self.pa_text_artist[0] = None
        for a in self.member_artists:
            try: a.remove()
            except Exception: pass
        self.member_artists.clear()
        self._member_sig = None

    # ------------------------------------------------------------------
    def _setup_shades(self):
        self.earning_release_date = find_earning_release_date(self.name)
        if self.earning_release_date:
            ws, we = calculate_three_weeks_before_range(self.earning_release_date)
            self.purple_shade = self.ax1.axvspan(ws, we, facecolor=NORD_THEME['accent_purple'],
                                                 alpha=0.15, zorder=0.5, visible=False)
            ws, we = calculate_one_week_before_range(self.earning_release_date)
            self.blue_shade = self.ax1.axvspan(ws, we, facecolor=NORD_THEME['accent_blue'],
                                               alpha=0.15, zorder=0.5, visible=False)

        self.latest_db_earning_date = None
        try:
            with sqlite3.connect(self.db_path, timeout=60.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1", (self.name,))
                row = cursor.fetchone()
                if row:
                    self.latest_db_earning_date = datetime.strptime(row[0], "%Y-%m-%d").date()
        except Exception as e:
            print(f"查询最新财报日期失败: {e}")

        if self.latest_db_earning_date:
            ps, pe_ = calculate_five_weeks_after_range(self.latest_db_earning_date)
            self.post_earning_shade = self.ax1.axvspan(ps, pe_, facecolor=NORD_THEME['accent_blue'],
                                                       alpha=0.15, zorder=0.5, visible=False)
            ps, pe_ = calculate_three_weeks_after_range(self.latest_db_earning_date)
            self.post_earning_shade_3w = self.ax1.axvspan(ps, pe_, facecolor=NORD_THEME['accent_purple'],
                                                          alpha=0.15, zorder=0.5, visible=False)

    # ------------------------------------------------------------------
    def build_colored_line_collection(self, f_dates, f_prices, f_opens):
        if self.colored_lc[0] is not None:
            try: self.colored_lc[0].remove()
            except Exception: pass
            self.colored_lc[0] = None
        if not self.has_ohlc or not f_dates or len(f_dates) < 2:
            return
        date_nums_lc = mdates.date2num(f_dates)
        segments, seg_colors = [], []
        for i in range(len(f_dates) - 1):
            segments.append([(date_nums_lc[i], f_prices[i]), (date_nums_lc[i + 1], f_prices[i + 1])])
            color = NORD_THEME['accent_cyan']
            if self.show_colored_lines:
                next_open = f_opens[i + 1] if (f_opens and i + 1 < len(f_opens)) else None
                next_close = f_prices[i + 1]
                if next_open is not None and next_close is not None:
                    if next_close > next_open:
                        color = NORD_THEME['accent_red']
                    elif next_close < next_open:
                        color = NORD_THEME['accent_green']
            seg_colors.append(color)
        lc = LineCollection(segments, colors=seg_colors, linewidths=2, zorder=2, alpha=0.8)
        self.ax1.add_collection(lc)
        self.colored_lc[0] = lc

    # ------------------------------------------------------------------
    def build_trade_markers(self):
        for scatter, _, _, _ in self.buy_scatter_points + self.sell_scatter_points:
            try: scatter.remove()
            except Exception: pass
        self.buy_scatter_points.clear()
        self.sell_scatter_points.clear()
        self.buy_markers.clear()
        self.sell_markers.clear()
        if not self.trade_map:
            return

        dates, prices, turnovers = self.dates, self.prices, self.turnovers
        dmin, dmax = min(dates).date(), max(dates).date()
        np_dates = np.array(dates)
        latest_price = prices[-1] if prices else None
        latest_turnover = turnovers[-1] if turnovers else None

        for d in sorted(self.trade_map.keys()):
            if d < dmin or d > dmax:
                continue
            target = datetime.combine(d, datetime.min.time())
            idx = int((np.abs(np_dates - target)).argmin())
            px = prices[idx]
            for side in ('buy', 'sell'):
                agg = self.trade_map[d].get(side)
                if not agg:
                    continue
                txt = build_marker_text(side, d, agg, close_price=px)
                is_buy = (side == 'buy')
                sc = self.ax1.scatter(
                    [dates[idx]], [px], s=150,
                    marker=(BUY_MARKER if is_buy else SELL_MARKER),
                    color=(BUY_COLOR if is_buy else SELL_COLOR),
                    edgecolors=NORD_THEME['text_bright'], linewidths=0.7,
                    alpha=0.95, zorder=4.6, picker=5,
                    visible=(self.show_buy_markers if is_buy else self.show_sell_markers))
                if is_buy:
                    self.buy_markers[dates[idx]] = txt
                    self.buy_scatter_points.append((sc, dates[idx], px, txt))
                else:
                    self.sell_markers[dates[idx]] = txt
                    self.sell_scatter_points.append((sc, dates[idx], px, txt))

        trade_offsets = [(45, 45), (-170, 45), (45, -110), (-170, -110)]
        all_trade_pts = self.buy_scatter_points + self.sell_scatter_points
        n_buy = len(self.buy_scatter_points)

        for i, (sc, date_v, price_v, txt) in enumerate(all_trade_pts):
            is_buy = i < n_buy
            color = BUY_COLOR if is_buy else SELL_COLOR
            diff_line = "最新价差: --"
            try:
                if latest_price is not None and price_v:
                    diff_line = f"最新价差: {((latest_price - price_v) / price_v) * 100:.2f}%"
            except Exception:
                pass
            vol_line = "最新额差: --"
            try:
                if turnovers and date_v in dates:
                    turnover_v = turnovers[dates.index(date_v)]
                    if turnover_v and turnover_v > 0 and latest_turnover:
                        vol_line = f"最新额差: {((latest_turnover - turnover_v) / turnover_v) * 100:.2f}%"
            except Exception:
                pass
            annotation = self.ax1.annotate(
                f"{txt}\n{diff_line}\n{vol_line}", xy=(date_v, price_v),
                xytext=trade_offsets[i % len(trade_offsets)], textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=color, alpha=0.85),
                arrowprops=dict(arrowstyle="->", color=color),
                color=color, fontsize=11,
                visible=(self.show_buy_markers if is_buy else self.show_sell_markers) and self.show_all_annotations)
            self.all_annotations.append((annotation, 'buy' if is_buy else 'sell', date_v, price_v))

    # ------------------------------------------------------------------
    def _diff_lines(self, date_v, price_v, vol_missing_text):
        prices, dates, turnovers = self.prices, self.dates, self.turnovers
        diff_line, vol_line = "", ""
        try:
            diff_percent = ((prices[-1] - price_v) / price_v) * 100 if price_v else 0
            diff_line = f"{diff_percent:.2f}%"
            if turnovers:
                turnover_v = turnovers[dates.index(date_v)]
                latest_turnover = turnovers[-1]
                if turnover_v and turnover_v > 0 and latest_turnover:
                    vol_line = f"{((latest_turnover - turnover_v) / turnover_v) * 100:.2f}%"
                else:
                    vol_line = vol_missing_text
        except Exception:
            pass
        return diff_line, vol_line

    def create_markers_and_annotations(self):
        for scatter, _, _, _ in self.global_scatter_points + self.specific_scatter_points:
            try: scatter.remove()
            except Exception: pass
        for annotation, _, _, _ in self.all_annotations:
            try: annotation.remove()
            except Exception: pass

        self.global_markers.clear()
        self.specific_markers.clear()
        self.global_scatter_points.clear()
        self.specific_scatter_points.clear()
        self.all_annotations.clear()

        dates, prices, turnovers = self.dates, self.prices, self.turnovers
        data = self.current_json_data['data'] or {}

        if 'global' in data:
            for date_str, text in data['global'].items():
                try:
                    self.global_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                except ValueError:
                    print(f"无法解析全局标记日期: {date_str}")

        found_item = None
        for source in ['stocks', 'etfs']:
            for item in data.get(source, []):
                sym = item['symbol']
                if (sym == self.name or sym.replace('-', '.') == self.name.replace('-', '.')) and 'description3' in item:
                    found_item = item
                    for date_obj in item.get('description3', []):
                        for date_str, text in date_obj.items():
                            try:
                                self.specific_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                            except ValueError:
                                print(f"无法解析特定标记日期: {date_str}")
                    break
            if found_item:
                break

        np_dates = np.array(dates)
        dmin, dmax = min(dates), max(dates)
        for marker_date, text in self.global_markers.items():
            if dmin <= marker_date <= dmax:
                idx = (np.abs(np_dates - marker_date)).argmin()
                scatter = self.ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['accent_red'],
                                           alpha=0.7, zorder=4, picker=5, visible=self.show_global_markers)
                self.global_scatter_points.append((scatter, dates[idx], prices[idx], text))

        for marker_date, text in self.specific_markers.items():
            if dmin <= marker_date <= dmax:
                idx = (np.abs(np_dates - marker_date)).argmin()
                scatter = self.ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['text_bright'],
                                           alpha=0.7, zorder=4, picker=5, visible=self.show_specific_markers)
                self.specific_scatter_points.append((scatter, dates[idx], prices[idx], text))

        red_offsets = [(-60, 30), (50, -30), (-70, 45), (-50, -35)]
        for i, (scatter, date_v, price_v, text) in enumerate(self.global_scatter_points):
            diff_line, vol_line = self._diff_lines(date_v, price_v, "最新额差: --")
            annotation = self.ax1.annotate(
                f"{text}\n{diff_line}\n{vol_line}\n{date_v.strftime('%Y-%m-%d')}",
                xy=(date_v, price_v), xytext=red_offsets[i % len(red_offsets)], textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_red'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_red']),
                color=NORD_THEME['accent_red'], fontsize=12, visible=False)
            self.all_annotations.append((annotation, 'global', date_v, price_v))

        specific_offsets = [(-50, -50), (-100, 20)]
        for i, (scatter, date_v, price_v, text) in enumerate(self.specific_scatter_points):
            diff_line, vol_line = self._diff_lines(date_v, price_v, "Vol: --")
            annotation = self.ax1.annotate(
                f"{text}\n{diff_line}\n{vol_line}\n{date_v.strftime('%Y-%m-%d')}",
                xy=(date_v, price_v), xytext=specific_offsets[i % len(specific_offsets)], textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['text_bright'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['text_bright']),
                color=NORD_THEME['text_bright'], fontsize=12,
                visible=self.show_specific_markers and self.show_all_annotations)
            self.all_annotations.append((annotation, 'specific', date_v, price_v))

        earning_offsets = [(50, -50), (-150, 25)]
        for i, (scatter, date_v, price_v, text) in enumerate(self.earning_scatter_points):
            final_text = text
            try:
                if turnovers:
                    turnover_v = turnovers[dates.index(date_v)]
                    latest_turnover = turnovers[-1]
                    if turnover_v and turnover_v > 0 and latest_turnover:
                        vol_msg = f"最新额差: {((latest_turnover - turnover_v) / turnover_v) * 100:.2f}%"
                    else:
                        vol_msg = "最新额差: --"
                    parts = text.split('\n')
                    parts.insert(-1, vol_msg)
                    final_text = "\n".join(parts)
            except Exception:
                pass
            annotation = self.ax1.annotate(
                final_text, xy=(date_v, price_v), xytext=earning_offsets[i % len(earning_offsets)],
                textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_yellow'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_cyan']),
                color=NORD_THEME['accent_yellow'], fontsize=12,
                visible=self.show_earning_markers and self.show_all_annotations)
            self.all_annotations.append((annotation, 'earning', date_v, price_v))

        self.build_trade_markers()

    # ------------------------------------------------------------------
    def create_or_update_title(self):
        volumes, prices = self.volumes, self.prices
        turnover = (volumes[-1] * prices[-1]) / 1e6 if volumes and volumes[-1] is not None and prices[-1] is not None else None
        turnover_str = ""
        if turnover is not None:
            turnover_str = f"{turnover / 1000:.1f}B" if turnover >= 1000 else f"{turnover:.1f}M"

        compare_value = clean_percentage_string(re.sub(r'[\u4e00-\u9fff+]', '', str(self.compare)))
        if turnover is not None and turnover < 100 and compare_value is not None and compare_value > 0:
            turnover_str = f"可疑{turnover_str}"

        try:
            share_int = int(self.share_val)
            turnover_rate = f"{(volumes[-1] / share_int) * 100:.2f}" if volumes and volumes[-1] is not None and share_int > 0 else "--"
        except (ValueError, TypeError):
            turnover_rate = "--"

        marketcap_in_billion = ""
        if self.marketcap not in [None, "N/A"]:
            try:
                mc_val = float(self.marketcap) / 1e9
                marketcap_in_billion = f"{int(mc_val)}B" if mc_val == int(mc_val) else f"{mc_val:.1f}B"
            except (ValueError, TypeError):
                pass

        pe_text = f"{self.pe}" if self.pe not in [None, "N/A"] else "--"

        tag_str, fullname, clickable = "", "", False
        for source in ['stocks', 'etfs']:
            for item in (self.current_json_data['data'] or {}).get(source, []):
                sym = item['symbol']
                if sym == self.name or sym.replace('-', '.') == self.name.replace('-', '.'):
                    fullname = item.get('name', '')
                    tag_str = ','.join(item.get('tag', []))
                    if len(tag_str) > 45:
                        tag_str = tag_str[:45] + '...'
                    clickable = True
                    break
            if clickable:
                break

        title_symbol = self.display_name if self.display_name else self.name
        if self.table_name == 'ETFs':
            title_color = NORD_THEME['accent_orange']
            title_text = f'{title_symbol}  {self.compare}  {turnover_str} "{self.table_name}" {fullname} {tag_str}'
        else:
            title_color = get_title_color_logic(self.db_path, self.name, self.table_name)
            title_text = (f'{title_symbol}  {self.compare}  {turnover_str} {turnover_rate} {marketcap_in_billion} '
                          f'{pe_text} {self.pb_text} "{self.table_name}" {fullname} {tag_str}')
        return title_text, title_color, clickable

    def draw_subtitle(self, current_prices=None, pre_after_pct=None):
        for artist in self.subtitle_artists:
            try: artist.remove()
            except Exception: pass
        self.subtitle_artists.clear()

        fig, name = self.fig, self.name

        ft_items = build_market_items(name, NORD_THEME, show_miss=FT_SHOW_MISS)
        if ft_items:
            self.subtitle_artists.extend(_ft_layout_text_row(fig, 0.045, 0.915, ft_items, fontsize=12))

        er_pct_str, max_pct_str, min_pct_str = "--", "--", "--"
        er_color = NORD_THEME['text_bright']

        if current_prices:
            latest_p = current_prices[-1]
            max_p, min_p = max(current_prices), min(current_prices)
            if max_p != 0:
                max_pct_str = f"{(max_p - latest_p) / max_p * 100:.1f}%"
            if min_p != 0:
                min_pct_str = f"{(latest_p - min_p) / min_p * 100:.1f}%"
            if self.latest_db_earning_date:
                try:
                    target_dt = datetime.combine(self.latest_db_earning_date, datetime.min.time())
                    closest_date = min(self.dates, key=lambda d: abs(d - target_dt))
                    earning_p = self.prices[self.dates.index(closest_date)]
                    if earning_p != 0:
                        er_pct = (latest_p - earning_p) / earning_p * 100
                        er_pct_str = f"{er_pct:.1f}%"
                        er_color = NORD_THEME['accent_red'] if er_pct > 0 else NORD_THEME['accent_green']
                except Exception:
                    pass

        y_pos = 0.915
        center_x = 0.35
        spacing_outer = 0.16
        base_x = center_x + spacing_outer + 0.08

        pre_after_str = "--"
        pa_color = NORD_THEME['text_bright']
        if pre_after_pct is not None:
            pre_after_str = f"{pre_after_pct:+.2f}%"
            pa_color = NORD_THEME['accent_red'] if pre_after_pct > 0 else NORD_THEME['accent_green']

        t_pa = fig.text(base_x - 0.08, y_pos, f"P/A:{pre_after_str}",
                        color=pa_color, fontsize=12, fontweight='bold', ha='left', va='top')
        self.subtitle_artists.append(t_pa)
        self.pa_text_artist[0] = t_pa

        self.subtitle_artists.append(fig.text(base_x, y_pos, f"Max:{max_pct_str}",
                                              color=NORD_THEME['accent_green'], fontsize=12, ha='left', va='top'))
        self.subtitle_artists.append(fig.text(base_x + 0.08, y_pos, f"Min:{min_pct_str}",
                                              color=NORD_THEME['accent_green'], fontsize=12, ha='left', va='top'))
        self.subtitle_artists.append(fig.text(base_x + 0.16, y_pos, f"ER:{er_pct_str}",
                                              color=er_color, fontsize=12, ha='left', va='top'))

        poly_pct = get_polymarket_percentage(name)
        if poly_pct:
            self.subtitle_artists.append(fig.text(base_x + 0.24, y_pos, f"Polymarket: {poly_pct}",
                                                  color=er_color, fontsize=26, fontweight='bold',
                                                  ha='left', va='top'))

        try:
            metrics_data = get_options_metrics(name)
        except Exception as e:
            print(f"DEBUG: 获取 {name} 期权数据时发生异常: {e}")
            metrics_data = None
        if metrics_data is None:
            return
        if metrics_data.get('date1') != date.today() - timedelta(days=1):
            return

        compare_str = str(self.compare[0]) if isinstance(self.compare, tuple) else str(self.compare)
        if compare_str == "nan":
            compare_str = "--"

        COLOR_PRI_UP, COLOR_PRI_DN = "#FF4500", "#00FA9A"
        COLOR_SEC_UP, COLOR_SEC_DN = "#E57373", "#81C784"
        COLOR_NULL, COLOR_BADGE_BG = "#DDDDDD", "#2c3e50"

        def get_style(val, role):
            if val == 0 or val is None or isinstance(val, str):
                return COLOR_NULL, 'normal', 13
            is_up = val > 0
            if role == 'primary':
                return (COLOR_PRI_UP if is_up else COLOR_PRI_DN), 'bold', 18
            return (COLOR_SEC_UP if is_up else COLOR_SEC_DN), 'normal', 12

        spacing_inner = 0.08
        self.subtitle_artists.append(fig.text(
            center_x, y_pos, compare_str, color='white', fontsize=13, fontweight='bold',
            fontname='Arial Unicode MS', ha='center', va='top',
            bbox=dict(boxstyle="round,pad=0.3", fc=COLOR_BADGE_BG, ec="none", alpha=0.9)))

        def put(x, y, val_num, text, role, ha):
            c, w, s = get_style(val_num, role)
            self.subtitle_artists.append(fig.text(x, y, text, color=c, fontsize=s, fontweight=w,
                                                  fontname='Arial Unicode MS', ha=ha, va='top'))

        iv2_v, iv2_s = metrics_data['iv2']
        put(center_x - spacing_inner, y_pos + 0.003, iv2_v, iv2_s, 'secondary', 'right')
        sum2_v = metrics_data['sum2']
        put(center_x + spacing_inner, y_pos + 0.003, sum2_v,
            f"{sum2_v:.2f}" if isinstance(sum2_v, (int, float)) else str(sum2_v), 'secondary', 'left')
        iv1_v, iv1_s = metrics_data['iv1']
        put(center_x - spacing_outer, y_pos, iv1_v, iv1_s, 'primary', 'right')
        sum1_v = metrics_data['sum1']
        put(center_x + spacing_outer, y_pos, sum1_v,
            f"{sum1_v:.2f}" if isinstance(sum1_v, (int, float)) else str(sum1_v), 'primary', 'left')

    # ------------------------------------------------------------------
    # 交互切换
    # ------------------------------------------------------------------
    def _anno_visible(self, anno_type):
        flag = {'global': self.show_global_markers, 'specific': self.show_specific_markers,
                'earning': self.show_earning_markers, 'buy': self.show_buy_markers,
                'sell': self.show_sell_markers}.get(anno_type, False)
        return flag and self.show_all_annotations

    def toggle_all_annotations(self):
        self.show_all_annotations = not self.show_all_annotations
        for annotation, anno_type, _, _ in self.all_annotations:
            annotation.set_visible(self._anno_visible(anno_type))
        self.fig.canvas.draw_idle()

    def toggle_colored_lines(self):
        self.show_colored_lines = not self.show_colored_lines
        self.build_colored_line_collection(self.current_filtered_dates, self.current_filtered_prices,
                                           self.current_filtered_opens)
        self.fig.canvas.draw_idle()

    def _toggle_marker_kind(self, attr, points, anno_type):
        setattr(self, attr, not getattr(self, attr))
        flag = getattr(self, attr)
        for scatter, _, _, _ in points:
            scatter.set_visible(flag)
        for annotation, t, _, _ in self.all_annotations:
            if t == anno_type:
                annotation.set_visible(flag and self.show_all_annotations)
        self.fig.canvas.draw_idle()

    def toggle_global_markers(self):
        self._toggle_marker_kind('show_global_markers', self.global_scatter_points, 'global')

    def toggle_specific_markers(self):
        self._toggle_marker_kind('show_specific_markers', self.specific_scatter_points, 'specific')

    def toggle_earning_markers(self):
        self._toggle_marker_kind('show_earning_markers', self.earning_scatter_points, 'earning')

    def toggle_buy_markers(self):
        self._toggle_marker_kind('show_buy_markers', self.buy_scatter_points, 'buy')

    def toggle_sell_markers(self):
        self._toggle_marker_kind('show_sell_markers', self.sell_scatter_points, 'sell')

    def update_marker_visibility(self):
        years = TIME_OPTIONS[self.radio.value_selected]
        min_date = min(self.dates) if years == 0 else datetime.now() - timedelta(days=years * 365)
        for pts, flag in ((self.global_scatter_points, self.show_global_markers),
                          (self.specific_scatter_points, self.show_specific_markers),
                          (self.earning_scatter_points, self.show_earning_markers),
                          (self.buy_scatter_points, self.show_buy_markers),
                          (self.sell_scatter_points, self.show_sell_markers)):
            for scatter, date_v, _, _ in pts:
                scatter.set_visible((min_date <= date_v) and flag)
        for annotation, anno_type, date_v, _ in self.all_annotations:
            annotation.set_visible(min_date <= date_v and self._anno_visible(anno_type))
        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    def _filter_by_years(self, years):
        if years == 0:
            return (self.dates, self.prices, self.volumes, self.turnovers,
                    self.opens, self.highs, self.lows)
        min_date = datetime.now() - timedelta(days=years * 365)
        indices = [i for i, d in enumerate(self.dates) if d >= min_date]
        if not indices:
            return ([self.dates[-1]], [self.prices[-1]],
                    [self.volumes[-1]] if self.volumes else None,
                    [self.turnovers[-1]] if self.turnovers else None,
                    [self.opens[-1]] if self.opens else None,
                    [self.highs[-1]] if self.highs else None,
                    [self.lows[-1]] if self.lows else None)
        return ([self.dates[i] for i in indices],
                [self.prices[i] for i in indices],
                [self.volumes[i] for i in indices] if self.volumes else None,
                [self.turnovers[i] for i in indices] if self.turnovers else None,
                [self.opens[i] for i in indices],
                [self.highs[i] for i in indices],
                [self.lows[i] for i in indices])

    def _set_filtered(self, f_dates, f_prices, f_volumes, f_opens, f_highs, f_lows):
        self.current_filtered_dates = f_dates
        self.current_filtered_prices = f_prices
        self.current_filtered_volumes = f_volumes
        self.current_filtered_date_nums = mdates.date2num(f_dates) if f_dates else np.array([])
        self.current_filtered_opens = f_opens
        self.current_filtered_highs = f_highs
        self.current_filtered_lows = f_lows

    def update(self, val):
        if not self.dates:
            return
        try:
            years = TIME_OPTIONS[val]
            f_dates, f_prices, f_volumes, f_turnovers, f_opens, f_highs, f_lows = self._filter_by_years(years)
            self._set_filtered(f_dates, f_prices, f_volumes, f_opens, f_highs, f_lows)

            # 遮罩显隐
            shades = [(self.purple_shade, self.earning_release_date, calculate_three_weeks_before_range),
                      (self.blue_shade, self.earning_release_date, calculate_one_week_before_range),
                      (self.post_earning_shade, self.latest_db_earning_date, calculate_five_weeks_after_range),
                      (self.post_earning_shade_3w, self.latest_db_earning_date, calculate_three_weeks_after_range)]
            if f_dates:
                display_start = min(f_dates).date()
                display_end = max(f_dates).date()
                for shade, base, fn in shades:
                    if shade is None:
                        continue
                    if base:
                        ws, we = fn(base)
                        shade.set_visible(not (we < display_start or ws > display_end))
                    else:
                        shade.set_visible(False)
            else:
                for shade, _, _ in shades:
                    if shade: shade.set_visible(False)

            now = time.time()
            force_flag = (now - self.last_rebuild_ts) > REBUILD_THROTTLE
            if force_flag:
                self.last_rebuild_ts = now

            self.gradient_image = update_plot(
                self.line1, self.gradient_image, self.line2,
                f_dates, f_prices, f_turnovers,
                self.ax1, self.ax2, self.show_volume,
                self.cyan_transparent_cmap,
                force_recreate=force_flag,
                gradient_clip_patch=self.gradient_clip_patch,
                zero_line=self.zero_line)

            self.build_colored_line_collection(f_dates, f_prices, f_opens)
            self.draw_subtitle(current_prices=f_prices, pre_after_pct=self.current_pre_after_pct[0])
            self._paint_radio(val)
            self.small_dot_scatter.set_visible(val in ["1m", "3m", "6m"])
            self.update_marker_visibility()
            self.fig.canvas.draw_idle()
        except Exception:
            traceback.print_exc()

    def toggle_volume(self):
        try:
            self.show_volume = not self.show_volume
            years = TIME_OPTIONS[self.radio.value_selected]
            f_dates, f_prices, f_volumes, f_turnovers, f_opens, f_highs, f_lows = self._filter_by_years(years)
            self._set_filtered(f_dates, f_prices, f_volumes, f_opens, f_highs, f_lows)
            self.gradient_image = update_plot(
                self.line1, self.gradient_image, self.line2,
                f_dates, f_prices, f_turnovers,
                self.ax1, self.ax2, self.show_volume,
                self.cyan_transparent_cmap,
                force_recreate=False,
                gradient_clip_patch=self.gradient_clip_patch,
                zero_line=self.zero_line)
            self.build_colored_line_collection(f_dates, f_prices, f_opens)
            self.fig.canvas.draw_idle()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------
    # 鼠标 / 键盘
    # ------------------------------------------------------------------
    def _nearest_idx(self, xdata):
        nums = self.current_filtered_date_nums
        if len(nums) == 0:
            return 0
        idx = int(np.searchsorted(nums, xdata))
        if idx >= len(nums):
            idx = len(nums) - 1
        elif idx > 0 and abs(nums[idx - 1] - xdata) < abs(nums[idx] - xdata):
            idx -= 1
        return idx

    @staticmethod
    def _find_near(markers, current_date):
        for d, t in markers.items():
            if abs((d - current_date).total_seconds()) < 86400:
                return t
        return None

    def update_annot(self, ind):
        try:
            annot = self.annot
            x_data, y_data = self.line1.get_data()
            idx = ind["ind"][0]
            xval, yval = x_data[idx], y_data[idx]
            if annot.xy == (xval, yval):
                return
            annot.xy = (xval, yval)
            current_date = xval.replace(tzinfo=None)
            g_text = self._find_near(self.global_markers, current_date)
            s_text = self._find_near(self.specific_markers, current_date)
            e_text = self._find_near(self.earning_markers, current_date)
            b_text = self._find_near(self.buy_markers, current_date)
            sl_text = self._find_near(self.sell_markers, current_date)

            if self.mouse_pressed and self.initial_price is not None:
                text = f"{((yval - self.initial_price) / self.initial_price) * 100:.1f}%"
                color = NORD_THEME['accent_cyan']
                annot.get_bbox_patch().set_edgecolor(color)
            else:
                fv, fl, fh = self.current_filtered_volumes, self.current_filtered_lows, self.current_filtered_highs
                current_vol = fv[idx] if fv and idx < len(fv) else None
                current_low = fl[idx] if fl and idx < len(fl) else None
                current_high = fh[idx] if fh and idx < len(fh) else None

                price_display = f"{yval:.2f}"
                if yval:
                    low_str = f"{((current_low - yval) / yval) * 100:+.2f}%" if current_low is not None else "--"
                    high_str = f"{((current_high - yval) / yval) * 100:+.2f}%" if current_high is not None else "--"
                    if current_low is not None or current_high is not None:
                        price_display = f"{yval:.2f} | {low_str} | {high_str}"

                turnover_str = "--"
                if current_vol is not None and yval is not None:
                    tv = current_vol * yval
                    if tv >= 1e9: turnover_str = f"{tv / 1e9:.2f}B"
                    elif tv >= 1e6: turnover_str = f"{tv / 1e6:.2f}M"
                    elif tv >= 1e3: turnover_str = f"{tv / 1e3:.1f}K"
                    else: turnover_str = f"{tv:.1f}"

                days_diff = abs((self.dates[-1] - current_date).days)
                parts = [xval.strftime('%Y-%m-%d'), price_display, turnover_str, f"{days_diff}天", ""]

                has_earning = False
                if g_text: parts.append(g_text)
                if s_text: parts.append(s_text + "\n")
                if e_text:
                    for line in e_text.split('\n'):
                        if "昨日财报" in line:
                            parts.append(line)
                            break
                    has_earning = True
                if b_text: parts.append(b_text)
                if sl_text: parts.append(sl_text)

                parts.append(f"最新价差: {((self.prices[-1] - yval) / yval) * 100:.2f}%")

                if fv and idx < len(fv) and self.turnovers:
                    sel_vol = fv[idx]
                    sel_turnover = sel_vol * yval if (sel_vol is not None and yval is not None) else 0
                    latest_turnover = self.turnovers[-1]
                    if sel_turnover > 0 and latest_turnover > 0:
                        parts.append(f"最新额差: {((latest_turnover - sel_turnover) / sel_turnover) * 100:.2f}%")
                    else:
                        parts.append("最新额差: --")
                text = "\n".join(parts)

                if (b_text or sl_text) and not (g_text or s_text or has_earning):
                    color = BUY_COLOR if b_text else SELL_COLOR
                elif has_earning and not (g_text or s_text): color = NORD_THEME['accent_yellow']
                elif g_text and not (s_text or has_earning): color = NORD_THEME['accent_red']
                elif s_text and not (g_text or has_earning): color = NORD_THEME['text_bright']
                elif g_text and (s_text or has_earning): color = NORD_THEME['accent_purple']
                else: color = NORD_THEME['accent_cyan']
                annot.get_bbox_patch().set_edgecolor(color)

            annot.set_text(text)
            annot.set_color(color)
            annot.get_bbox_patch().set_alpha(0.8)
            annot.set_fontsize(16)

            y_range = self.ax1.get_ylim()
            y_ratio = (yval - y_range[0]) / (y_range[1] - y_range[0] + 1e-12)
            x_range = self.ax1.get_xlim()
            x_ratio = (mdates.date2num(xval) - x_range[0]) / (x_range[1] - x_range[0] + 1e-12)
            y_offset = 60 if y_ratio < 0.2 else (-120 if y_ratio > 0.8 else -70)
            if x_ratio > 0.7:
                x_offset = -min(20 + len(annot.get_text()) * 6, 320)
            elif x_ratio < 0.3:
                x_offset = 50
            else:
                x_offset = -200
            annot.set_position((x_offset, y_offset))
        except Exception:
            pass

    def hover(self, event):
        try:
            now = time.time()
            if now - self.last_hover_ts < HOVER_THROTTLE:
                return
            self.last_hover_ts = now
            annot, ax1, fig = self.annot, self.ax1, self.fig

            if event.inaxes in [self.ax1, self.ax2] and event.xdata and self.current_filtered_dates:
                self.vline.set_xdata([event.xdata, event.xdata])
                self.vline.set_visible(True)
                idx = self._nearest_idx(event.xdata)
                x_data, y_data = self.line1.get_data()

                if self.mouse_pressed:
                    if idx < len(x_data) and idx < len(y_data) and self.initial_price is not None:
                        sel_date, sel_price = x_data[idx], y_data[idx]
                        try:
                            percent_change = ((sel_price - self.initial_price) / (self.initial_price + 1e-12)) * 100.0
                        except Exception:
                            percent_change = 0.0
                        turnover_text = ""
                        fv = self.current_filtered_volumes
                        if self.initial_volume is not None and fv and idx < len(fv):
                            sel_vol = fv[idx]
                            if sel_vol is not None:
                                try:
                                    start_turnover = self.initial_price * self.initial_volume
                                    if start_turnover > 0:
                                        turnover_text = f"{((sel_price * sel_vol - start_turnover) / start_turnover) * 100.0:.1f}%"
                                    else:
                                        turnover_text = "--%"
                                except Exception:
                                    turnover_text = "--%"

                        days_diff = abs((sel_date - self.initial_date).days)
                        annot.xy = (sel_date, sel_price)
                        annot.set_text(f"{self.initial_date.strftime('%Y-%m-%d')}\n{sel_date.strftime('%Y-%m-%d')}\n"
                                       f"{days_diff}\n{percent_change:.1f}%\n{turnover_text}")
                        drag_color = NORD_THEME['accent_red'] if percent_change > 0 else NORD_THEME['accent_green']
                        annot.set_color(drag_color)
                        annot.get_bbox_patch().set_edgecolor(drag_color)
                        annot.get_bbox_patch().set_alpha(0.8)
                        annot.set_fontsize(16)

                        y_range, x_range = ax1.get_ylim(), ax1.get_xlim()
                        y_ratio = (sel_price - y_range[0]) / (y_range[1] - y_range[0] + 1e-12)
                        x_ratio = (mdates.date2num(sel_date) - x_range[0]) / (x_range[1] - x_range[0] + 1e-12)
                        y_offset = 60 if y_ratio < 0.2 else -160 if y_ratio > 0.8 else -100
                        x_offset = -120 if x_ratio > 0.7 else 50 if x_ratio < 0.3 else -100
                        annot.set_position((x_offset, y_offset))
                        annot.set_visible(True)
                        self.highlight_point.set_offsets([[mdates.date2num(sel_date), sel_price]])
                        self.highlight_point.set_visible(True)
                    fig.canvas.draw_idle()
                    return

                if idx < len(x_data) and idx < len(y_data):
                    sel_date, sel_price = x_data[idx], y_data[idx]
                    color = NORD_THEME['accent_cyan']
                    if any(d == sel_date for _, d, _, _ in self.global_scatter_points):
                        color = NORD_THEME['accent_red']
                    elif any(d == sel_date for _, d, _, _ in self.specific_scatter_points):
                        color = NORD_THEME['text_bright']
                    elif any(d == sel_date for _, d, _, _ in self.earning_scatter_points):
                        color = NORD_THEME['accent_yellow']
                    if any(d == sel_date for _, d, _, _ in self.buy_scatter_points):
                        color = BUY_COLOR
                    if any(d == sel_date for _, d, _, _ in self.sell_scatter_points):
                        color = SELL_COLOR

                    self.highlight_point.set_color(color)
                    dist = 0.2 * ((ax1.get_xlim()[1] - ax1.get_xlim()[0]) / 365)
                    if np.isclose(mdates.date2num(sel_date), event.xdata, atol=dist):
                        self.update_annot({"ind": [idx]})
                        annot.set_visible(True)
                        self.highlight_point.set_offsets([[mdates.date2num(sel_date), sel_price]])
                        self.highlight_point.set_visible(True)
                    else:
                        annot.set_visible(False)
                        self.highlight_point.set_visible(False)
                fig.canvas.draw_idle()

            elif event.inaxes != self.rax:
                self.vline.set_visible(False)
                annot.set_visible(False)
                self.highlight_point.set_visible(False)
                fig.canvas.draw_idle()
        except Exception:
            pass

    def on_mouse_press(self, event):
        try:
            if event.button == 1 and event.xdata is not None and self.current_filtered_dates \
                    and event.inaxes in (self.ax1, self.ax2):
                self.mouse_pressed = True
                idx = self._nearest_idx(event.xdata)
                if idx < len(self.current_filtered_prices):
                    self.initial_price = self.current_filtered_prices[idx]
                    self.initial_date = self.current_filtered_dates[idx]
                    fv = self.current_filtered_volumes
                    self.initial_volume = fv[idx] if fv and idx < len(fv) else None
        except Exception:
            pass

    def on_mouse_release(self, event):
        if event.button == 1:
            self.mouse_pressed = False

    def on_pick(self, event):
        try:
            all_points = (self.global_scatter_points + self.specific_scatter_points +
                          self.earning_scatter_points + self.buy_scatter_points +
                          self.sell_scatter_points)
            for scatter, date_v, price_v, text in all_points:
                if event.artist == scatter:
                    self.annot.xy = (date_v, price_v)
                    self.annot.set_text(f"{date_v.strftime('%Y-%m-%d')}\n{price_v}\n{text}")
                    self.annot.get_bbox_patch().set_alpha(0.8)
                    self.annot.set_fontsize(16)
                    midpoint = max(self.dates) - (max(self.dates) - min(self.dates)) / 2
                    self.annot.set_position((50, -20) if date_v < midpoint else (-150, -20))
                    self.annot.set_visible(True)
                    self.highlight_point.set_offsets([[mdates.date2num(date_v), price_v]])
                    self.highlight_point.set_visible(True)
                    self.fig.canvas.draw_idle()
                    break
        except Exception:
            pass

    def hide_annot_on_leave(self, event):
        try:
            self.annot.set_visible(False)
            self.highlight_point.set_visible(False)
            self.vline.set_visible(False)
            self.fig.canvas.draw_idle()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 一键加入 Firstrade 自选股分组
    # ------------------------------------------------------------------
    def _show_wl_status(self, text, color, ttl=6.0):
        try:
            self.wl_status_artist.set_text(text)
            self.wl_status_artist.set_color(color)
            self.wl_status_artist.set_visible(True)
            self._wl_hide_at = time.time() + ttl
            self.fig.canvas.draw_idle()
        except Exception:
            pass

    def _add_to_watchlist(self, group=None):
        if not FT_WL_ADD_OK:
            display_dialog("未找到 ft_watchlist_add.py，无法使用「一键加自选」")
            return
        sym = self.name
        if not sym:
            return
        if not group:
            group = choose_group_dialog(sym, watchlist_groups())
            if not group:
                self._show_wl_status("已取消", NORD_THEME['text_light'], ttl=1.5)
                return
        save_last_group(group)
        self._show_wl_status(f"⏳ 正在把 {sym} 加入「{group}」…（浏览器后台执行）",
                             NORD_THEME['accent_yellow'], ttl=90)
        add_symbol_async(sym, group, on_done=lambda res: self._wl_results.append(res), wait=45)

    def _drain_wl_results(self):
        now = time.time()
        while self._wl_results:
            res = self._wl_results.pop(0)
            ok = bool(res.get('ok'))
            msg = res.get('message') or ('成功' if ok else '失败')
            self._show_wl_status(("✅ " if ok else "❌ ") + msg,
                                 NORD_THEME['accent_green'] if ok else NORD_THEME['accent_red'], ttl=7.0)
            try:
                notify_mac("Firstrade 自选股", msg, subtitle=f"{res.get('symbol','')} → {res.get('group','')}")
            except Exception:
                pass
            print(f"[FT-WL] {'OK' if ok else 'FAIL'} {msg}")
        if self.wl_status_artist.get_visible() and self._wl_hide_at and now > self._wl_hide_at:
            self.wl_status_artist.set_visible(False)
            self._wl_hide_at = 0.0
            self.fig.canvas.draw_idle()

    def _draw_membership(self, force=False):
        """画「自选 [买] [Watch]」行；文件 mtime 或 symbol 没变则跳过，返回是否重画"""
        try:
            sig = (self.name, membership_signature())
        except Exception:
            sig = (self.name, None)
        if not force and sig == self._member_sig:
            return False
        self._member_sig = sig
        for a in self.member_artists:
            try: a.remove()
            except Exception: pass
        self.member_artists.clear()
        if not self.name:
            return True
        try:
            items = build_membership_items(self.name, NORD_THEME)
        except Exception as e:
            print(f"[FT] 分组归属读取失败: {e}")
            items = []
        if items:
            self.member_artists.extend(_ft_layout_text_row(self.fig, 0.045, 0.884, items, fontsize=12, x_limit=0.34))
        return True

    def _refresh_membership(self):
        if not FT_WL_ADD_OK:
            display_dialog("未找到 ft_watchlist_add.py，无法刷新分组归属")
            return
        self._show_wl_status("⏳ 正在让浏览器扫描全部自选分组…（约 10~90 秒）",
                             NORD_THEME['accent_yellow'], ttl=300)
        scan_groups_async(on_done=lambda res: self._wl_results.append(res),
                          groups=(watchlist_groups() or None), wait=300)

    # ------------------------------------------------------------------
    # 弹窗 / 外部脚本
    # ------------------------------------------------------------------
    def show_stock_etf_info(self):
        for source in ['stocks', 'etfs']:
            for item in (self.current_json_data['data'] or {}).get(source, []):
                sym = item['symbol']
                if sym == self.name or sym.replace('-', '.') == self.name.replace('-', '.'):
                    info = (f"{self.name}\n{item.get('name','')}\n\n{item.get('tag','')}\n\n"
                            f"{item.get('description1','')}\n\n{item.get('description2','')}")
                    InfoDialog("Information", info, 'Arial Unicode MS', 22, 700, 900).exec()
                    return
        display_dialog(f"未找到 {self.name} 的信息")

    def show_db_records(self):
        safe_name = str(self.name).replace("'", "''")
        result = query_database_text(self.db_path, self.table_name, f"name = '{safe_name}'")
        InfoDialog("数据库查询结果", result, "Courier", 14, 900, 600).exec()

    def close_window(self):
        """关闭图表；独立脚本模式 / panel 模式下同时结束事件循环（替代旧版 sys.exit）"""
        quit_app = self.panel or self.owns_loop
        try:
            plt.close(self.fig)
        except Exception:
            pass
        self.closed = True
        if quit_app:
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def _after_delete(self, return_code):
        if return_code == 0:
            if self.callback:
                self.callback('deleted')
            print("删除操作完成 (Code 0)，正在关闭窗口...")
            self.close_window()
        else:
            print(f"删除操作取消或失败 (Code {return_code})，保持窗口开启。")

    def launch_insert_then_delete_chain(self):
        name = self.name

        def on_insert_done(insert_return_code):
            if insert_return_code == 0:
                print("Panel 输入成功 (Code 0)，正在自动启动删除流程...")
                execute_external_script('panel_delete', name, on_done=self._after_delete, block=True)
            else:
                print(f"Panel 输入取消或未变更 (Code {insert_return_code})，停止连锁流程。")

        execute_external_script('panel_input', name, on_done=on_insert_done, block=True)

    def launch_and_close_for_y(self):
        execute_external_script('panel_delete', self.name, on_done=self._after_delete, block=True)

    def refresh_description_data_and_redraw(self):
        print("正在重新加载 description.json...")
        try:
            with open(self.DESCRIPTION_JSON_PATH, 'r', encoding='utf-8') as f:
                self.current_json_data['data'] = json.load(f)
            new_title_text, new_title_color, self.clickable = self.create_or_update_title()
            self.title_artist.set_text(new_title_text)
            self.title_artist.set_color(new_title_color)
            self.draw_subtitle(current_prices=self.current_filtered_prices,
                               pre_after_pct=self.current_pre_after_pct[0])
            self.create_markers_and_annotations()
            self.update_marker_visibility()
            self._draw_membership(force=True)
            self.fig.canvas.draw_idle()
            print("图表刷新完成。")
        except FileNotFoundError:
            display_dialog(f"错误: 未找到文件\n{self.DESCRIPTION_JSON_PATH}")
        except json.JSONDecodeError as e:
            display_dialog(f"错误: 解析JSON文件失败\n{e}")
        except Exception as e:
            display_dialog(f"刷新时发生未知错误:\n{e}")

    # ------------------------------------------------------------------
    def on_key(self, event):
        try:
            if event.key == 'escape':
                self.close_window()
                return

            actions = {'v': self.toggle_volume, 'r': self.toggle_global_markers, 'x': self.toggle_all_annotations,
                       'a': self.toggle_earning_markers,
                       'c': self.toggle_specific_markers,
                       'i': self.toggle_buy_markers,
                       'u': self.toggle_sell_markers,
                       'g': self.refresh_description_data_and_redraw,
                       'n': lambda: execute_external_script('earning_input', self.name),
                       'e': lambda: execute_external_script('earning_edit', self.name),
                       't': lambda: execute_external_script('tags_edit', self.name),
                       'w': lambda: execute_external_script('event_input', self.name),
                       'y': self.launch_insert_then_delete_chain,
                       'j': self.launch_and_close_for_y,
                       'm': self._refresh_membership,
                       's': self.toggle_colored_lines,
                       'f': lambda: self._add_to_watchlist(None),
                       'F': lambda: self._add_to_watchlist(last_group() or None),
                       'q': lambda: execute_external_script('event_edit', self.name),
                       'k': lambda: execute_external_script('check_kimi', self.name),
                       'z': lambda: execute_external_script('check_futu', self.name),
                       'o': lambda: execute_external_script('check_seekingalpha', self.name),
                       'p': lambda: execute_external_script('symbol_compare', self.name),
                       'l': lambda: execute_external_script('similar_tags', self.name),
                       'b': lambda: execute_external_script('check_history', self.name),
                       '/': lambda: execute_external_script('stock_chart', self.name),
                       '1': lambda: self.radio.set_active(7), '2': lambda: self.radio.set_active(1),
                       '3': lambda: self.radio.set_active(3), '4': lambda: self.radio.set_active(4),
                       '5': lambda: self.radio.set_active(5), '6': lambda: self.radio.set_active(6),
                       '7': lambda: self.radio.set_active(8), '8': lambda: self.radio.set_active(2),
                       '9': lambda: self.radio.set_active(0), '`': self.show_stock_etf_info,
                       'd': self.show_db_records}
            if event.key in actions:
                actions[event.key]()
                return

            current_index = list(TIME_OPTIONS.keys()).index(self.radio.value_selected)
            if event.key == 'up' and current_index > 0:
                self.radio.set_active(current_index - 1)
            elif event.key == 'down' and current_index < len(TIME_OPTIONS) - 1:
                self.radio.set_active(current_index + 1)
            elif event.key == 'right':
                if self.callback:
                    self.callback('next')
            elif event.key == 'left':
                if self.callback:
                    self.callback('prev')
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------
    def _ui_poll_realtime(self):
        try:
            self._drain_wl_results()
        except Exception:
            pass
        try:
            if self.name and self._draw_membership():
                self.fig.canvas.draw_idle()
        except Exception:
            pass
        try:
            if self.name is None or not self.prices or self.prices[-1] == 0:
                return
            rt_price = _RT_MANAGER.get_latest(self.name)
            if rt_price is None:
                return
            pct = ((rt_price - self.prices[-1]) / self.prices[-1]) * 100
            if self.current_pre_after_pct[0] is not None and abs(self.current_pre_after_pct[0] - pct) < 1e-9:
                return
            self.current_pre_after_pct[0] = pct
            if self.pa_text_artist[0] is not None:
                self.pa_text_artist[0].set_text(f"P/A:{pct:+.2f}%")
                self.pa_text_artist[0].set_color(NORD_THEME['accent_red'] if pct > 0 else NORD_THEME['accent_green'])
                self.fig.canvas.draw_idle()
        except Exception:
            pass

    def _on_close(self, evt):
        self.closed = True
        try:
            self.ui_timer.stop()
        except Exception:
            pass

    def discard(self):
        """丢弃一个尚未显示过的窗口（首次加载失败时使用）"""
        self.closed = True
        try:
            self.ui_timer.stop()
        except Exception:
            pass
        try:
            plt.close(self.fig)
        except Exception:
            pass

    def show(self):
        """非阻塞显示 / 前置窗口，并把键盘焦点交给画布"""
        try:
            mgr = self.fig.canvas.manager
            mgr.show()
            try:
                win = mgr.window
                if win.isMinimized():
                    win.showNormal()
                win.raise_()
                win.activateWindow()
            except Exception:
                pass
            try:
                self.fig.canvas.setFocus()
            except Exception:
                pass
        except Exception:
            pass


# ======================================================================
# 对外接口（签名兼容旧版两份文件）
# ======================================================================
_CHART_WINDOW = None


def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel=False, callback=None,
                        window_title_text=None, display_name=None, block=None):
    """
    block=None  自动判定：已有 Qt 事件循环 → 非阻塞复用窗口；否则阻塞直到窗口关闭
    block=True  强制阻塞（仅在没有事件循环时生效，避免嵌套事件循环）
    block=False 强制非阻塞
    返回 True 表示成功加载
    """
    global _CHART_WINDOW

    if QApplication.instance() is None:
        QApplication(sys.argv)

    loop_running = _qt_loop_running()
    if block is None:
        block = not loop_running
    run_own_loop = bool(block) and not loop_running

    reuse = (_CHART_WINDOW is not None) and (not _CHART_WINDOW.closed)
    if not reuse:
        _CHART_WINDOW = ChartWindow()

    ok = _CHART_WINDOW.load(
        db_path, table_name, name, compare, share, marketcap, pe, json_data,
        default_time_range=default_time_range, panel=panel, callback=callback,
        window_title_text=window_title_text, display_name=display_name
    )
    if not ok:
        if not reuse:
            _CHART_WINDOW.discard()
            _CHART_WINDOW = None
        return False

    _CHART_WINDOW.owns_loop = run_own_loop
    _CHART_WINDOW.show()
    print(f"图表已加载: {name}（窗口{'复用' if reuse else '新建'}，"
          f"{'阻塞独立模式' if run_own_loop else '嵌入模式'}）")

    if run_own_loop:
        plt.show(block=True)   # 运行 Qt 事件循环，直到窗口关闭
    return True