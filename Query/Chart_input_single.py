import os
import re
import sys
import sqlite3
import subprocess
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, date
from matplotlib.widgets import RadioButtons
from functools import lru_cache
from scipy.interpolate import interp1d
import json
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.collections import LineCollection
import glob
import time
import threading

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 导入 Tiger_API ---
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Selenium"))
try:
    from Tiger_API import _get_global_fetcher
except ImportError as e:
    print(f"导入 Tiger_API 失败: {e}")

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

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

# ============ 读取 Firstrade 真实持仓缓存 ============
FIRSTRADE_POSITIONS_FILE = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "firstrade_positions.json")
FT_DEBUG = os.environ.get("FT_DEBUG", "") == "1"
FT_SHOW_MISS = os.environ.get("FT_SHOW_MISS", "1") == "1"


def _ft_norm_sym(s):
    """AAPL / brk.b / BRK-B 统一成大写且以 '-' 为分隔的形式"""
    return str(s).strip().upper().replace('.', '-')


def get_firstrade_position(symbol):
    """读取 Chrome 插件回传的真实持仓数据，返回 dict 或 None"""
    if not symbol:
        return None
    path = FIRSTRADE_POSITIONS_FILE
    if not os.path.exists(path):
        if FT_DEBUG:
            print(f"[FT] 持仓文件不存在: {path}")
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[FT] 读取持仓数据失败: {e}")
        return None
    if not isinstance(data, dict):
        return None

    target = _ft_norm_sym(symbol)
    for k, v in data.items():
        if str(k).startswith('_') or not isinstance(v, dict):
            continue
        if _ft_norm_sym(k) == target:
            if FT_DEBUG:
                print(f"[FT] 命中持仓 {k}: {v}")
            return v
    if FT_DEBUG:
        keys = [k for k in data.keys() if not str(k).startswith('_')]
        print(f"[FT] 未找到 {symbol}（文件里有 {len(keys)} 条）: {keys[:25]}")
    return None


def _ft_layout_text_row(fig, x0, y, items, fontsize=12, gap_px=14, x_limit=0.32):
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

# ============ 全局实时价格管理器（整个进程共用一个线程 + 一个 fetcher） ============
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

# ============ Earning Release 全量缓存 ============
_EARNING_RELEASE_CACHE = None

def _load_all_earning_releases(txt_dir=None):
    global _EARNING_RELEASE_CACHE
    if _EARNING_RELEASE_CACHE is not None:
        return _EARNING_RELEASE_CACHE
    if txt_dir is None:
        txt_dir = os.path.join(BASE_CODING_DIR, "News")
    result = {}
    try:
        pattern = os.path.join(txt_dir, 'Earnings_Release_*.txt')
        for file_path in glob.glob(pattern):
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
                continue
    except Exception as e:
        print(f"查找 earning release 日期时出错: {e}")
    _EARNING_RELEASE_CACHE = result
    return result

def find_earning_release_date(symbol, txt_dir=None):
    return _load_all_earning_releases(txt_dir).get(symbol)

@lru_cache(maxsize=1)
def _load_polymarket_data():
    file_path = os.path.join(BASE_CODING_DIR, "News", "earning_polymarket.txt")
    data = {}
    if not os.path.exists(file_path):
        return data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
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

def get_polymarket_percentage(symbol):
    return _load_polymarket_data().get(symbol)

def calculate_three_weeks_before_range(target_date):
    three_weeks_before = target_date - timedelta(days=21)
    weekday = three_weeks_before.weekday()
    week_start = three_weeks_before - timedelta(days=weekday)
    week_end = week_start + timedelta(days=4)
    return week_start, week_end

def calculate_one_week_before_range(target_date):
    one_week_before = target_date - timedelta(days=7)
    weekday = one_week_before.weekday()
    week_start = one_week_before - timedelta(days=weekday)
    week_end = week_start + timedelta(days=4)
    return week_start, week_end

def calculate_five_weeks_after_range(target_date):
    weekday = target_date.weekday()
    current_week_start = target_date - timedelta(days=weekday)
    target_week_start = current_week_start + timedelta(weeks=5)
    target_week_end = target_week_start + timedelta(days=4)
    return target_week_start, target_week_end

def calculate_three_weeks_after_range(target_date):
    weekday = target_date.weekday()
    current_week_start = target_date - timedelta(days=weekday)
    target_week_start = current_week_start + timedelta(weeks=3)
    target_week_end = target_week_start + timedelta(days=4)
    return target_week_start, target_week_end

@lru_cache(maxsize=128)
def get_title_color_logic(db_path, symbol, table_name):
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
                cursor.execute(f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?', (symbol, latest_earning_date.isoformat()))
                latest_stock_price_row = cursor.fetchone()
                cursor.execute(f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?', (symbol, previous_earning_date.isoformat()))
                previous_stock_price_row = cursor.fetchone()
            if not latest_stock_price_row or not previous_stock_price_row:
                return NORD_THEME['text_bright']
            latest_stock_price = float(latest_stock_price_row[0])
            previous_stock_price = float(previous_stock_price_row[0])
            price_trend = 'rising' if latest_stock_price > previous_stock_price else 'falling'
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

@lru_cache(maxsize=None)
def fetch_data(db_path, table_name, name):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_name ON "{table_name}" (name);')
        except sqlite3.OperationalError:
            pass
        try:
            query = f'SELECT date, price, volume, open, high, low FROM "{table_name}" WHERE name = ? ORDER BY date;'
            result = cursor.execute(query, (name,)).fetchall()
            if result:
                return result
        except sqlite3.OperationalError:
            pass
        try:
            query = f'SELECT date, price, volume, open FROM "{table_name}" WHERE name = ? ORDER BY date;'
            result = cursor.execute(query, (name,)).fetchall()
            if result:
                return result
        except sqlite3.OperationalError:
            pass
        try:
            query = f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date;'
            result = cursor.execute(query, (name,)).fetchall()
            if result:
                return result
        except sqlite3.OperationalError:
            pass
        query = f'SELECT date, price FROM "{table_name}" WHERE name = ? ORDER BY date;'
        result = cursor.execute(query, (name,)).fetchall()
        if not result:
            raise ValueError("没有查询到可用数据")
        return result

def smooth_curve(dates, prices, num_points=500):
    date_nums = matplotlib.dates.date2num(dates)
    if len(dates) < 4:
        interp_func = interp1d(date_nums, prices, kind='linear')
    else:
        interp_func = interp1d(date_nums, prices, kind='cubic')
    new_date_nums = np.linspace(min(date_nums), max(date_nums), num_points)
    new_prices = interp_func(new_date_nums)
    new_dates = matplotlib.dates.num2date(new_date_nums)
    return new_dates, new_prices

def process_data(data):
    if not data: raise ValueError("没有可供处理的数据")
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

def display_dialog(message):
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def update_plot(line1, gradient_image, line2, dates, prices, volumes, ax1, ax2, show_volume, cmap, force_recreate=False, gradient_clip_patch=None, zero_line=None):
    """
    更新图表，使用 imshow 和 clip_path 实现渐变填充。
    此版本包含针对高价股的视觉比例优化。
    """
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
        date_range = date_max_val - date_min_val
        right_margin = date_range * 0.01
        ax1.set_xlim(date_min_val, date_max_val + right_margin)

    min_p, max_p = np.min(prices), np.max(prices)
    MIN_DISPLAY_PCT = 0.15
    actual_span = max_p - min_p
    min_required_span = abs(max_p) * MIN_DISPLAY_PCT

    if min_p == max_p:
        buffer = abs(min_p * 0.1) if min_p != 0 else 0.1
        ax1.set_ylim(min_p - buffer, max_p + buffer)
    elif actual_span < min_required_span:
        center_price = (max_p + min_p) / 2
        half_span = min_required_span / 2
        new_min = center_price - half_span
        new_max = center_price + half_span
        top_pad = abs(max_p) * 0.02
        ax1.set_ylim(new_min, new_max + top_pad)
    else:
        y_range = actual_span
        top_pad = max(y_range * 0.03, 0.02 * max(1.0, abs(max_p)))
        bottom_pad = y_range * 0.01
        ax1.set_ylim(min_p - bottom_pad, max_p + top_pad)

    if zero_line is not None:
        if np.min(prices) < 0.0:
            zero_line.set_visible(True)
            y0, y1 = ax1.get_ylim()
            if y1 < 0:
                ax1.set_ylim(y0, 0 + top_pad if 'top_pad' in locals() else 0.1)
            elif y0 > 0:
                current_range = y1 - y0
                ax1.set_ylim(0 - (current_range * 0.05), y1)
        else:
            zero_line.set_visible(False)

    if show_volume:
        if volumes and any(v is not None for v in volumes):
            valid_v = [v for v in volumes if v is not None]
            if valid_v:
                max_v = np.max(valid_v)
                ax2.set_ylim(0, max_v)
            else:
                ax2.set_ylim(0, 1)
        else:
            ax2.set_ylim(0, 1)

    xlim = ax1.get_xlim()
    ylim = ax1.get_ylim()
    fill_base = 0 if np.max(prices) < 0 else ylim[0]

    line_x_nums = matplotlib.dates.date2num(dates)
    verts = [(line_x_nums[0], fill_base), *zip(line_x_nums, prices), (line_x_nums[-1], fill_base)]
    clip_path = Path(verts)

    if force_recreate or gradient_image is None:
        if gradient_image is not None:
            gradient_image.remove()
        if gradient_clip_patch is not None and gradient_clip_patch[0] is not None:
            gradient_clip_patch[0].remove()
        gradient = np.linspace(1.0, 0.0, 256).reshape(-1, 1)
        gradient_image = ax1.imshow(
            gradient, aspect='auto', cmap=cmap, extent=[*xlim, *ylim],
            origin='lower', zorder=1, interpolation='nearest'
        )
        new_clip_patch = PathPatch(clip_path, transform=ax1.transData, facecolor='none', edgecolor='none')
        ax1.add_patch(new_clip_patch)
        gradient_image.set_clip_path(new_clip_patch)
        if gradient_clip_patch is not None:
            gradient_clip_patch[0] = new_clip_patch
    else:
        gradient_image.set_extent([*xlim, *ylim])
        if gradient_clip_patch is not None and gradient_clip_patch[0] is not None:
            gradient_clip_patch[0].remove()
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
        if event.key() == Qt.Key.Key_Escape: self.close()

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def apply_nord_style(self, font_size):
        qss = f"""
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
        """
        self.setStyleSheet(qss)

def execute_external_script(script_type, keyword, on_done=None, block=False):
    script_configs = {
        'earning_input': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Earning_Manual.py'),
        'earning_edit': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Earning_DB.py'),
        'tags_edit': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'event_input': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Events.py'),
        'event_edit': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Events.py'),
        'symbol_compare': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Compare_Chart.py'),
        'panel_input': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Panel.py'),
        'panel_delete': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Delete_Panel.py'),
        'similar_tags': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Search_Similar_Tag.py'),
        'check_history': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Check_Earning_history.py'),
        'check_kimi': os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Check_Earning.scpt'),
        'check_futu': os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'check_seekingalpha': os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_seekingalpha.scpt'),
        'stock_chart': os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_Chart.scpt')
    }
    script_path = script_configs.get(script_type)
    if not script_path:
        display_dialog(f"未知的脚本类型: {script_type}")
        return
    try:
        if script_path.endswith('.scpt'):
            if block:
                subprocess.run(['osascript', script_path, keyword], check=False)
                if callable(on_done):
                    on_done()
            else:
                subprocess.Popen(['osascript', script_path, keyword])
                if callable(on_done):
                    on_done()
        else:
            python_path = sys.executable
            if block:
                result = subprocess.run([python_path, script_path, keyword], check=False)
                if callable(on_done):
                    on_done(result.returncode)
            else:
                result = subprocess.Popen([python_path, script_path, keyword])
                if callable(on_done):
                    on_done(result.returncode)
    except Exception as e:
        display_dialog(f"启动程序失败: {e}")

@lru_cache(maxsize=64)
def get_options_metrics(symbol):
    db_path = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
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
                if isinstance(iv_s, str) and '%' in iv_s:
                    iv_v = float(iv_s.replace('%', '').replace(' ', ''))
                else:
                    iv_v = 0.0
            except:
                iv_v = 0.0
            p = float(row[1]) if row[1] is not None else 0.0
            c = float(row[2]) if row[2] is not None else 0.0
            sum_v = p + c
            try:
                d_obj = datetime.strptime(row[3], "%Y-%m-%d").date()
            except:
                d_obj = None
            return iv_v, iv_s, sum_v, d_obj

        iv1_val, iv1_str, sum1_val, date1 = parse_row(rows[0])
        iv2_val, iv2_str, sum2_val, date2 = parse_row(rows[1])
        return {
            'iv1': (iv1_val, iv1_str),
            'iv2': (iv2_val, iv2_str),
            'sum1': sum1_val,
            'sum2': sum2_val,
            'date1': date1,
            'date2': date2
        }
    except Exception as e:
        print(f"读取 Options 表出错: {e}")
        return None

def clean_percentage_string(s):
    try: return float(s.strip('%'))
    except (ValueError, AttributeError): return None

def query_database_text(db_path, table_name, condition):
    with sqlite3.connect(db_path, timeout=60.0) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;")
        rows = cursor.fetchall()
        if not rows: return "今天没有数据可显示。\n"
        cols = [d[0] for d in cursor.description]
        widths = [max(len(str(r[i])) for r in rows + [cols]) for i in range(len(cols))]
        header = ' | '.join([c.ljust(widths[i]) for i, c in enumerate(cols)])
        lines = [header, '-' * len(header)]
        for row in rows:
            lines.append(' | '.join([str(item).ljust(widths[i]) for i, item in enumerate(row)]))
        return '\n'.join(lines)


# ======================================================================
# 核心重构：可复用的图表窗口（进程级单例，切换 symbol 只更新数据不重建窗口）
# ======================================================================
class ChartWindow:
    def __init__(self):
        self.closed = False
        matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
        matplotlib.rcParams['toolbar'] = 'none'

        # ---------- 静态部分：只创建一次 ----------
        self.fig, self.ax1 = plt.subplots(figsize=(16, 8))
        self.fig.subplots_adjust(left=0.05, bottom=0.1, right=0.83, top=0.8)
        self.ax2 = self.ax1.twinx()
        self.ax2.axis('off')
        self.fig.patch.set_facecolor(NORD_THEME['background'])

        self.ax1.set_facecolor(NORD_THEME['background'])
        self.ax1.spines['bottom'].set_visible(True)
        self.ax1.spines['top'].set_visible(False)
        self.ax1.spines['right'].set_visible(False)
        self.ax1.spines['left'].set_visible(False)
        self.ax1.tick_params(axis='y', which='both', left=False, labelleft=False)
        self.ax1.tick_params(axis='x', colors=NORD_THEME['text_light'], rotation=45)
        self.ax1.spines['bottom'].set_color(NORD_THEME['border'])
        self.ax1.spines['bottom'].set_linewidth(1.0)
        self.ax1.grid(True, color=NORD_THEME['border'], alpha=0.1, linestyle='--')

        self.highlight_point = self.ax1.scatter([], [], s=100, color=NORD_THEME['accent_cyan'], zorder=5)
        self.line1, = self.ax1.plot(
            [], [], marker='', linestyle='-', linewidth=2,
            color=NORD_THEME['accent_cyan'], alpha=0.8, label='Price', zorder=2
        )
        self.small_dot_scatter = self.ax1.scatter([], [], s=5, color=NORD_THEME['text_bright'], zorder=1.5)
        self.line2, = self.ax2.plot(
            [], [], marker='o', markersize=2, linestyle='-', linewidth=2,
            color=NORD_THEME['accent_purple'], alpha=0.7, label='Turnover'
        )
        self.line2.set_visible(False)

        self.zero_line = self.ax1.axhline(
            y=0, color=NORD_THEME['text_bright'], linestyle=(0, (6, 3)),
            linewidth=1.8, alpha=0.95, zorder=3, visible=False
        )

        cyan_base_color = matplotlib.colors.to_rgb(NORD_THEME['accent_cyan'])
        self.cyan_transparent_cmap = LinearSegmentedColormap.from_list(
            'cyan_transparent_gradient',
            [(*cyan_base_color, 0.0), (*cyan_base_color, 0.5)]
        )

        self.annot = self.ax1.annotate(
            "", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
            bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_cyan']),
            arrowprops=dict(arrowstyle="->"), color=NORD_THEME['text_bright'], visible=False
        )
        self.vline = self.ax1.axvline(x=0, color=NORD_THEME['accent_cyan'], linestyle='--',
                                      linewidth=1, visible=False)

        # 标题（fig.text 只建一次，之后 set_text）
        self.title_artist = self.fig.text(0.5, 0.95, "", ha='center', va='top',
                                          color=NORD_THEME['text_bright'], fontsize=16,
                                          fontweight='bold', transform=self.fig.transFigure)

        # RadioButtons 只建一次
        self.rax = self.fig.add_axes([0.95, 0.0, 0.05, 0.65], facecolor=NORD_THEME['background'])
        self.radio = RadioButtons(self.rax, list(TIME_OPTIONS.keys()), active=3)
        self.rax.set_facecolor(NORD_THEME['background'])
        self.rax.set_frame_on(False)
        for spine in self.rax.spines.values():
            spine.set_visible(False)
        for label in self.radio.labels:
            label.set_color(NORD_THEME['text_light'])
            label.set_fontsize(14)
        for circle in self.radio.circles:
            circle.set_edgecolor(NORD_THEME['border'])
            circle.set_facecolor(NORD_THEME['background'])

        instructions = "N:新财报\nE:改财报\nT:改标签\nW:新事件\nQ:改事件\nK:查豆包\nZ:查富途\nP:做比较\nJ:加Panel\nL:查相似\nY:删除\nG:刷新\nO:查α\nB:存在"
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

        self.last_hover_ts = 0.0
        self.last_rebuild_ts = 0.0

        self.DESCRIPTION_JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")

        # ---------- 事件只绑定一次 ----------
        c = self.fig.canvas
        c.mpl_connect("motion_notify_event", self.hover)
        c.mpl_connect('key_press_event', self.on_key)
        c.mpl_connect('button_press_event', self.on_mouse_press)
        c.mpl_connect('button_release_event', self.on_mouse_release)
        c.mpl_connect('pick_event', self.on_pick)
        c.mpl_connect('figure_leave_event', self.hide_annot_on_leave)
        c.mpl_connect('close_event', self._on_close)
        self.radio.on_clicked(self.update)

        # 实时价格 UI 定时器（只建一次）
        self.ui_timer = c.new_timer(interval=1000)
        self.ui_timer.add_callback(self._ui_poll_realtime)
        self.ui_timer.start()

        try:
            c.toolbar_visible = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 加载 / 切换 symbol：只更新数据和少量 artist
    # ------------------------------------------------------------------
    def load(self, db_path, table_name, name, compare, share, marketcap, pe, json_data,
             default_time_range="1Y", panel=False, callback=None,
             window_title_text=None, display_name=None):
        self.db_path = db_path
        self.table_name = table_name
        self.name = name
        self.compare = compare
        self.marketcap = marketcap
        self.pe = pe
        self.panel = panel
        self.callback = callback
        self.display_name = display_name
        self.current_json_data = {'data': json_data}

        if isinstance(share, tuple):
            self.share_val, pb = share
            self.pb_text = f"{pb}" if pb not in [None, ""] else "--"
        else:
            self.share_val, self.pb_text = share, "--"

        # 每次打开重置为默认交互状态（与旧行为一致）
        self.show_volume = False
        self.mouse_pressed = False
        self.initial_price = None
        self.initial_volume = None
        self.initial_date = None
        self.show_global_markers = False
        self.show_specific_markers = True
        self.show_earning_markers = True
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

        # 取数
        try:
            data = fetch_data(db_path, table_name, name)
            self.dates, self.prices, self.volumes, self.opens, self.highs, self.lows = process_data(data)
        except ValueError as e:
            display_dialog(f"{e}")
            return False
        if not self.dates or not self.prices:
            display_dialog("没有有效的数据来绘制图表。")
            return False

        self.has_ohlc = any(o is not None for o in self.opens)
        self.line1.set_alpha(0 if self.has_ohlc else 0.8)

        # Turnover
        self.turnovers = []
        if self.prices and self.volumes:
            for p, v in zip(self.prices, self.volumes):
                self.turnovers.append(p * v if (p is not None and v is not None) else 0.0)
        else:
            self.turnovers = [0.0] * len(self.dates)

        self.date_nums = matplotlib.dates.date2num(self.dates)
        self.small_dot_scatter.set_offsets(np.column_stack([self.date_nums, self.prices]))

        # 窗口标题
        try:
            self.fig.canvas.manager.set_window_title(window_title_text if window_title_text else name)
        except Exception:
            pass

        # 清掉上一个 symbol 的动态 artist
        self._clear_symbol_artists()

        # 遮罩
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

        for marker_date, text in self.earning_markers.items():
            if min(self.dates) <= marker_date <= max(self.dates):
                idx = (np.abs(np.array(self.dates) - marker_date)).argmin()
                scatter = self.ax1.scatter([self.dates[idx]], [self.prices[idx]], s=100,
                                           color=NORD_THEME['pure_yellow'], alpha=0.7, zorder=4,
                                           picker=5, visible=self.show_earning_markers)
                self.earning_scatter_points.append((scatter, self.dates[idx], self.prices[idx], text))

        # global / specific 标记与所有注释
        self.create_markers_and_annotations()

        # 标题
        title_text, title_color, self.clickable = self.create_or_update_title()
        self.title_artist.set_text(title_text)
        self.title_artist.set_color(title_color)

        # 隐藏残留的悬浮元素
        self.annot.set_visible(False)
        self.highlight_point.set_visible(False)
        self.vline.set_visible(False)

        # 实时价格：换 symbol
        _RT_MANAGER.set_symbol(name)

        # 触发一次时间范围更新（radio.set_active 会调用 self.update）
        default_index = list(TIME_OPTIONS.keys()).index(default_time_range)
        self.radio.set_active(default_index)
        self.update(default_time_range)  # <--- 加上这行显式调用，防止切换股票时默认范围相同时不触发副标题重绘
        return True

    # ------------------------------------------------------------------
    def _clear_symbol_artists(self):
        for attr in ('purple_shade', 'blue_shade', 'post_earning_shade', 'post_earning_shade_3w'):
            s = getattr(self, attr, None)
            if s is not None:
                try: s.remove()
                except Exception: pass
                setattr(self, attr, None)

        for lst in (self.global_scatter_points, self.specific_scatter_points, self.earning_scatter_points):
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

    # ------------------------------------------------------------------
    def _setup_shades(self):
        self.earning_release_date = find_earning_release_date(self.name)
        if self.earning_release_date:
            week_start_3w, week_end_3w = calculate_three_weeks_before_range(self.earning_release_date)
            self.purple_shade = self.ax1.axvspan(
                week_start_3w, week_end_3w, facecolor=NORD_THEME['accent_purple'],
                alpha=0.15, zorder=0.5, visible=False)
            week_start_1w, week_end_1w = calculate_one_week_before_range(self.earning_release_date)
            self.blue_shade = self.ax1.axvspan(
                week_start_1w, week_end_1w, facecolor=NORD_THEME['accent_blue'],
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
            pe_start, pe_end = calculate_five_weeks_after_range(self.latest_db_earning_date)
            self.post_earning_shade = self.ax1.axvspan(
                pe_start, pe_end, facecolor=NORD_THEME['accent_blue'],
                alpha=0.15, zorder=0.5, visible=False)
            pe_start_3w, pe_end_3w = calculate_three_weeks_after_range(self.latest_db_earning_date)
            self.post_earning_shade_3w = self.ax1.axvspan(
                pe_start_3w, pe_end_3w, facecolor=NORD_THEME['accent_purple'],
                alpha=0.15, zorder=0.5, visible=False)

    # ------------------------------------------------------------------
    def build_colored_line_collection(self, f_dates, f_prices, f_opens):
        if self.colored_lc[0] is not None:
            self.colored_lc[0].remove()
            self.colored_lc[0] = None
        if not self.has_ohlc or not f_dates or len(f_dates) < 2:
            return
        date_nums_lc = matplotlib.dates.date2num(f_dates)
        segments = []
        seg_colors = []
        for i in range(len(f_dates) - 1):
            segments.append([
                (date_nums_lc[i], f_prices[i]),
                (date_nums_lc[i + 1], f_prices[i + 1])
            ])
            if self.show_colored_lines:
                next_open = f_opens[i + 1] if (f_opens and i + 1 < len(f_opens)) else None
                next_close = f_prices[i + 1]
                if next_open is not None and next_close is not None:
                    if next_close > next_open:
                        seg_colors.append(NORD_THEME['accent_red'])
                    elif next_close < next_open:
                        seg_colors.append(NORD_THEME['accent_green'])
                    else:
                        seg_colors.append(NORD_THEME['accent_cyan'])
                else:
                    seg_colors.append(NORD_THEME['accent_cyan'])
            else:
                seg_colors.append(NORD_THEME['accent_cyan'])
        lc = LineCollection(segments, colors=seg_colors, linewidths=2, zorder=2, alpha=0.8)
        self.ax1.add_collection(lc)
        self.colored_lc[0] = lc

    # ------------------------------------------------------------------
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

        if 'global' in self.current_json_data['data']:
            for date_str, text in self.current_json_data['data']['global'].items():
                try:
                    self.global_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                except ValueError:
                    print(f"无法解析全局标记日期: {date_str}")

        found_item = None
        for source in ['stocks', 'etfs']:
            for item in self.current_json_data['data'].get(source, []):
                if item['symbol'] == self.name and 'description3' in item:
                    found_item = item
                    for date_obj in item.get('description3', []):
                        for date_str, text in date_obj.items():
                            try:
                                self.specific_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                            except ValueError:
                                print(f"无法解析特定标记日期: {date_str}")
                    break
            if found_item: break

        for marker_date, text in self.global_markers.items():
            if min(dates) <= marker_date <= max(dates):
                idx = (np.abs(np.array(dates) - marker_date)).argmin()
                scatter = self.ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['accent_red'],
                                           alpha=0.7, zorder=4, picker=5, visible=self.show_global_markers)
                self.global_scatter_points.append((scatter, dates[idx], prices[idx], text))

        for marker_date, text in self.specific_markers.items():
            if min(dates) <= marker_date <= max(dates):
                idx = (np.abs(np.array(dates) - marker_date)).argmin()
                scatter = self.ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['text_bright'],
                                           alpha=0.7, zorder=4, picker=5, visible=self.show_specific_markers)
                self.specific_scatter_points.append((scatter, dates[idx], prices[idx], text))

        red_offsets = [(-60, 30), (50, -30), (-70, 45), (-50, -35)]
        for i, (scatter, date_v, price_v, text) in enumerate(self.global_scatter_points):
            offset = red_offsets[i % len(red_offsets)]
            diff_line, vol_line = "", ""
            try:
                latest_price = prices[-1]
                diff_percent = ((latest_price - price_v) / price_v) * 100 if price_v else 0
                diff_line = f"{diff_percent:.2f}%"
                if turnovers:
                    idx = dates.index(date_v)
                    turnover_v = turnovers[idx]
                    latest_turnover = turnovers[-1]
                    if turnover_v and turnover_v > 0 and latest_turnover:
                        v_diff = ((latest_turnover - turnover_v) / turnover_v) * 100
                        vol_line = f"{v_diff:.2f}%"
                    else:
                        vol_line = "最新额差: --"
            except Exception:
                pass
            new_text = f"{text}\n{diff_line}\n{vol_line}\n{date_v.strftime('%Y-%m-%d')}"
            annotation = self.ax1.annotate(
                new_text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_red'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_red']),
                color=NORD_THEME['accent_red'], fontsize=12, visible=False
            )
            self.all_annotations.append((annotation, 'global', date_v, price_v))

        specific_offsets = [(-50, -50), (-100, 20)]
        for i, (scatter, date_v, price_v, text) in enumerate(self.specific_scatter_points):
            offset = specific_offsets[i % len(specific_offsets)]
            diff_line, vol_line = "", ""
            try:
                latest_price = prices[-1]
                diff_percent = ((latest_price - price_v) / price_v) * 100 if price_v else 0
                diff_line = f"{diff_percent:.2f}%"
                if turnovers:
                    idx = dates.index(date_v)
                    turnover_v = turnovers[idx]
                    latest_turnover = turnovers[-1]
                    if turnover_v and turnover_v > 0 and latest_turnover:
                        v_diff = ((latest_turnover - turnover_v) / turnover_v) * 100
                        vol_line = f"{v_diff:.2f}%"
                    else:
                        vol_line = "Vol: --"
            except Exception:
                pass
            new_text = f"{text}\n{diff_line}\n{vol_line}\n{date_v.strftime('%Y-%m-%d')}"
            annotation = self.ax1.annotate(
                new_text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['text_bright'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['text_bright']),
                color=NORD_THEME['text_bright'], fontsize=12,
                visible=self.show_specific_markers and self.show_all_annotations
            )
            self.all_annotations.append((annotation, 'specific', date_v, price_v))

        earning_offsets = [(50, -50), (-150, 25)]
        for i, (scatter, date_v, price_v, text) in enumerate(self.earning_scatter_points):
            offset = earning_offsets[i % len(earning_offsets)]
            final_text = text
            try:
                if turnovers:
                    idx = dates.index(date_v)
                    turnover_v = turnovers[idx]
                    latest_turnover = turnovers[-1]
                    if turnover_v and turnover_v > 0 and latest_turnover:
                        v_diff = ((latest_turnover - turnover_v) / turnover_v) * 100
                        vol_msg = f"最新额差: {v_diff:.2f}%"
                    else:
                        vol_msg = "最新额差: --"
                    parts = text.split('\n')
                    if len(parts) >= 1:
                        parts.insert(-1, vol_msg)
                        final_text = "\n".join(parts)
                    else:
                        final_text = text + "\n" + vol_msg
            except Exception:
                pass
            annotation = self.ax1.annotate(
                final_text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_yellow'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_cyan']),
                color=NORD_THEME['accent_yellow'], fontsize=12,
                visible=self.show_earning_markers and self.show_all_annotations
            )
            self.all_annotations.append((annotation, 'earning', date_v, price_v))

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
            mc_val = float(self.marketcap) / 1e9
            marketcap_in_billion = f"{int(mc_val)}B" if mc_val == int(mc_val) else f"{mc_val:.1f}B"

        pe_text = f"{self.pe}" if self.pe not in [None, "N/A"] else "--"

        tag_str, fullname, clickable = "", "", False
        for source in ['stocks', 'etfs']:
            for item in self.current_json_data['data'].get(source, []):
                if item['symbol'] == self.name:
                    fullname = item.get('name', '')
                    tag_str = ','.join(item.get('tag', []))
                    if len(tag_str) > 45: tag_str = tag_str[:45] + '...'
                    clickable = True
                    break
            if clickable: break

        title_symbol = self.display_name if self.display_name else self.name

        if self.table_name == 'ETFs':
            title_color = NORD_THEME['accent_orange']
            title_text = f'{title_symbol}  {self.compare}  {turnover_str} "{self.table_name}" {fullname} {tag_str}'
        else:
            title_color = get_title_color_logic(self.db_path, self.name, self.table_name)
            title_text = f'{title_symbol}  {self.compare}  {turnover_str} {turnover_rate} {marketcap_in_billion} {pe_text} {self.pb_text} "{self.table_name}" {fullname} {tag_str}'
        return title_text, title_color, clickable

    def draw_subtitle(self, current_prices=None, pre_after_pct=None):
        for artist in self.subtitle_artists:
            try: artist.remove()
            except Exception: pass
        self.subtitle_artists.clear()

        fig = self.fig
        name = self.name

        # ========= 第二行最左侧：Chrome 插件从 Firstrade 网页回传的真实持仓 =========
        pos = get_firstrade_position(name)
        if pos:
            raw = pos.get('raw') or {}

            def _pick(*keys):
                for k in keys:
                    v = pos.get(k)
                    if v not in (None, '', '--'):
                        return str(v)
                for k in keys:
                    v = raw.get(k)
                    if v not in (None, '', '--'):
                        return str(v)
                return None

            def _num(s):
                try:
                    m = re.search(r'[-+]?\d[\d,]*\.?\d*', str(s).replace(' ', ''))
                    return float(m.group(0).replace(',', '')) if m else None
                except Exception:
                    return None

            def _sign_color(s):
                v = _num(s)
                if v is None:
                    return NORD_THEME['text_bright']
                if v > 0:
                    return NORD_THEME['accent_red']      # 红涨
                if v < 0:
                    return NORD_THEME['accent_green']    # 绿跌
                return NORD_THEME['text_bright']

            def _fmt_money(s):
                v = _num(s)
                if v is None:
                    return str(s)
                if abs(v) >= 1e6:
                    return f"{v/1e6:.2f}M"
                if abs(v) >= 1e3:
                    return f"{v/1e3:.1f}K"
                return f"{v:.0f}"

            cost_val = _pick('cost', 'totalCost')
            day_val = _pick('day_change', 'changePercent')
            gl_val = _pick('gainloss', 'gainlossPercent')
            # qty_val = _pick('quantity')
            alloc_val = _pick('allocation', 'allocationPercent')

            ft_items = []
            if cost_val:
                ft_items.append((f"成本 {_fmt_money(cost_val)}",
                                 NORD_THEME['accent_yellow'], 'bold'))
            # if qty_val:
            #     q = _num(qty_val)
            #     ft_items.append((f"×{q:.0f}" if q is not None else f"×{qty_val}",
            #                      NORD_THEME['text_light'], 'normal'))
            if day_val:
                ft_items.append((f"日{day_val}", _sign_color(day_val), 'bold'))
            if gl_val:
                ft_items.append((f"总{gl_val}", _sign_color(gl_val), 'bold'))
            if alloc_val:
                ft_items.append((f"仓{alloc_val}", NORD_THEME['accent_cyan'], 'normal'))

            # 数据太旧时给个提示（插件回传的时间戳是毫秒）
            try:
                ts = pos.get('updated_at')
                if ts:
                    age_h = (time.time() - float(ts) / 1000.0) / 3600.0
                    if age_h > 20:
                        ft_items.append((f"({age_h/24:.0f}天前)", NORD_THEME['border'], 'normal'))
            except Exception:
                pass

            if ft_items:
                self.subtitle_artists.extend(
                    _ft_layout_text_row(fig, 0.045, 0.915, ft_items, fontsize=12)
                )
        elif FT_SHOW_MISS:
            t_miss = fig.text(0.045, 0.915, "持仓: 网页无数据",
                              color=NORD_THEME['border'], fontsize=10,
                              ha='left', va='top', fontname='Arial Unicode MS')
            self.subtitle_artists.append(t_miss)

        er_pct_str, max_pct_str, min_pct_str = "--", "--", "--"
        er_color = NORD_THEME['text_bright']

        if current_prices and len(current_prices) > 0:
            latest_p = current_prices[-1]
            max_p = max(current_prices)
            min_p = min(current_prices)
            if max_p != 0:
                max_pct = (max_p - latest_p) / max_p * 100
                max_pct_str = f"{max_pct:.1f}%"
            if min_p != 0:
                min_pct = (latest_p - min_p) / min_p * 100
                min_pct_str = f"{min_pct:.1f}%"
            if self.latest_db_earning_date:
                try:
                    target_dt = datetime.combine(self.latest_db_earning_date, datetime.min.time())
                    closest_date = min(self.dates, key=lambda d: abs(d - target_dt))
                    idx = self.dates.index(closest_date)
                    earning_p = self.prices[idx]
                    if earning_p != 0:
                        er_pct = (latest_p - earning_p) / earning_p * 100
                        er_pct_str = f"{er_pct:.1f}%"
                        er_color = NORD_THEME['accent_red'] if er_pct > 0 else NORD_THEME['accent_green']
                except Exception:
                    pass

        y_pos = 0.915
        center_x = 0.35  # 自适应错开持仓区域
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

        t_max = fig.text(base_x, y_pos, f"Max:{max_pct_str}",
                         color=NORD_THEME['accent_green'], fontsize=12, fontweight='normal',
                         ha='left', va='top')
        self.subtitle_artists.append(t_max)

        t_min = fig.text(base_x + 0.08, y_pos, f"Min:{min_pct_str}",
                         color=NORD_THEME['accent_green'], fontsize=12, fontweight='normal',
                         ha='left', va='top')
        self.subtitle_artists.append(t_min)

        t_er = fig.text(base_x + 0.16, y_pos, f"ER:{er_pct_str}",
                        color=er_color, fontsize=12, fontweight='normal', ha='left', va='top')
        self.subtitle_artists.append(t_er)

        poly_pct = get_polymarket_percentage(name)
        if poly_pct:
            t_poly = fig.text(base_x + 0.24, y_pos, f"Polymarket: {poly_pct}",
                              color=er_color, fontsize=26, fontweight='bold', ha='left', va='top')
            self.subtitle_artists.append(t_poly)

        try:
            metrics_data = get_options_metrics(name)
        except Exception as e:
            print(f"DEBUG: 获取 {name} 期权数据时发生异常: {e}")
            metrics_data = None
        if metrics_data is None:
            return

        target_date = date.today() - timedelta(days=1)
        row0_date = metrics_data.get('date1')
        iv1_data = metrics_data['iv1']
        sum1_data = metrics_data['sum1']
        if row0_date != target_date:
            return

        compare_str = str(self.compare[0]) if isinstance(self.compare, tuple) else str(self.compare)
        if compare_str == "nan": compare_str = "--"

        COLOR_PRI_UP = "#FF4500"
        COLOR_PRI_DN = "#00FA9A"
        COLOR_SEC_UP = "#E57373"
        COLOR_SEC_DN = "#81C784"
        COLOR_NULL = "#DDDDDD"
        COLOR_BADGE_BG = "#2c3e50"

        def get_style(val, role):
            if val == 0 or val is None or isinstance(val, str):
                return COLOR_NULL, 'normal', 13
            is_up = val > 0
            if role == 'primary':
                return (COLOR_PRI_UP if is_up else COLOR_PRI_DN), 'bold', 18
            elif role == 'secondary':
                return (COLOR_SEC_UP if is_up else COLOR_SEC_DN), 'normal', 12
            return COLOR_NULL, 'normal', 13

        spacing_inner = 0.08

        t_comp = fig.text(center_x, y_pos, compare_str,
                          color='white', fontsize=13, fontweight='bold', fontname='Arial Unicode MS',
                          ha='center', va='top',
                          bbox=dict(boxstyle="round,pad=0.3", fc=COLOR_BADGE_BG, ec="none", alpha=0.9))
        self.subtitle_artists.append(t_comp)

        iv2_v, iv2_s = metrics_data['iv2']
        c, w, s = get_style(iv2_v, 'secondary')
        t_iv2 = fig.text(center_x - spacing_inner, y_pos + 0.003, iv2_s,
                         color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                         ha='right', va='top')
        self.subtitle_artists.append(t_iv2)

        sum2_v = metrics_data['sum2']
        c, w, s = get_style(sum2_v, 'secondary')
        sum2_text = f"{sum2_v:.2f}" if isinstance(sum2_v, (int, float)) else str(sum2_v)
        t_sum2 = fig.text(center_x + spacing_inner, y_pos + 0.003, sum2_text,
                          color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                          ha='left', va='top')
        self.subtitle_artists.append(t_sum2)

        iv1_v, iv1_s = iv1_data
        c, w, s = get_style(iv1_v, 'primary')
        t_iv1 = fig.text(center_x - spacing_outer, y_pos, iv1_s,
                         color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                         ha='right', va='top')
        self.subtitle_artists.append(t_iv1)

        sum1_v = sum1_data
        c, w, s = get_style(sum1_v, 'primary')
        sum1_text = f"{sum1_v:.2f}" if isinstance(sum1_v, (int, float)) else str(sum1_v)
        t_sum1 = fig.text(center_x + spacing_outer, y_pos, sum1_text,
                          color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                          ha='left', va='top')
        self.subtitle_artists.append(t_sum1)

    # ------------------------------------------------------------------
    # 交互切换
    # ------------------------------------------------------------------
    def toggle_all_annotations(self):
        self.show_all_annotations = not self.show_all_annotations
        for annotation, anno_type, _, _ in self.all_annotations:
            if anno_type == 'global': annotation.set_visible(self.show_global_markers and self.show_all_annotations)
            elif anno_type == 'specific': annotation.set_visible(self.show_specific_markers and self.show_all_annotations)
            elif anno_type == 'earning': annotation.set_visible(self.show_earning_markers and self.show_all_annotations)
        self.fig.canvas.draw_idle()

    def toggle_colored_lines(self):
        self.show_colored_lines = not self.show_colored_lines
        self.build_colored_line_collection(self.current_filtered_dates, self.current_filtered_prices, self.current_filtered_opens)
        self.fig.canvas.draw_idle()

    def toggle_global_markers(self):
        self.show_global_markers = not self.show_global_markers
        for scatter, _, _, _ in self.global_scatter_points: scatter.set_visible(self.show_global_markers)
        for annotation, anno_type, _, _ in self.all_annotations:
            if anno_type == 'global': annotation.set_visible(self.show_global_markers and self.show_all_annotations)
        self.fig.canvas.draw_idle()

    def toggle_specific_markers(self):
        self.show_specific_markers = not self.show_specific_markers
        for scatter, _, _, _ in self.specific_scatter_points: scatter.set_visible(self.show_specific_markers)
        for annotation, anno_type, _, _ in self.all_annotations:
            if anno_type == 'specific': annotation.set_visible(self.show_specific_markers and self.show_all_annotations)
        self.fig.canvas.draw_idle()

    def toggle_earning_markers(self):
        self.show_earning_markers = not self.show_earning_markers
        for scatter, _, _, _ in self.earning_scatter_points: scatter.set_visible(self.show_earning_markers)
        for annotation, anno_type, _, _ in self.all_annotations:
            if anno_type == 'earning': annotation.set_visible(self.show_earning_markers and self.show_all_annotations)
        self.fig.canvas.draw_idle()

    def update_marker_visibility(self):
        years = TIME_OPTIONS[self.radio.value_selected]
        min_date = min(self.dates) if years == 0 else datetime.now() - timedelta(days=years * 365)
        for scatter, date_v, _, _ in self.global_scatter_points: scatter.set_visible((min_date <= date_v) and self.show_global_markers)
        for scatter, date_v, _, _ in self.specific_scatter_points: scatter.set_visible((min_date <= date_v) and self.show_specific_markers)
        for scatter, date_v, _, _ in self.earning_scatter_points: scatter.set_visible((min_date <= date_v) and self.show_earning_markers)
        for annotation, anno_type, date_v, _ in self.all_annotations:
            visible = False
            if min_date <= date_v:
                if anno_type == 'global': visible = self.show_global_markers and self.show_all_annotations
                elif anno_type == 'specific': visible = self.show_specific_markers and self.show_all_annotations
                elif anno_type == 'earning': visible = self.show_earning_markers and self.show_all_annotations
            annotation.set_visible(visible)
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

    def update(self, val):
        try:
            years = TIME_OPTIONS[val]
            f_dates, f_prices, f_volumes, f_turnovers, f_opens, f_highs, f_lows = self._filter_by_years(years)

            self.current_filtered_dates = f_dates
            self.current_filtered_prices = f_prices
            self.current_filtered_volumes = f_volumes
            self.current_filtered_date_nums = matplotlib.dates.date2num(f_dates) if f_dates else np.array([])
            self.current_filtered_opens = f_opens
            self.current_filtered_highs = f_highs
            self.current_filtered_lows = f_lows

            # 遮罩显隐
            if f_dates:
                display_start = min(f_dates).date() if isinstance(min(f_dates), datetime) else min(f_dates)
                display_end = max(f_dates).date() if isinstance(max(f_dates), datetime) else max(f_dates)
                if self.earning_release_date:
                    if self.purple_shade:
                        ws, we = calculate_three_weeks_before_range(self.earning_release_date)
                        self.purple_shade.set_visible(not (we < display_start or ws > display_end))
                    if self.blue_shade:
                        ws, we = calculate_one_week_before_range(self.earning_release_date)
                        self.blue_shade.set_visible(not (we < display_start or ws > display_end))
                else:
                    if self.purple_shade: self.purple_shade.set_visible(False)
                    if self.blue_shade: self.blue_shade.set_visible(False)
                if self.latest_db_earning_date:
                    if self.post_earning_shade:
                        ps, pe_ = calculate_five_weeks_after_range(self.latest_db_earning_date)
                        self.post_earning_shade.set_visible(not (pe_ < display_start or ps > display_end))
                    if self.post_earning_shade_3w:
                        ps, pe_ = calculate_three_weeks_after_range(self.latest_db_earning_date)
                        self.post_earning_shade_3w.set_visible(not (pe_ < display_start or ps > display_end))
                else:
                    if self.post_earning_shade: self.post_earning_shade.set_visible(False)
                    if self.post_earning_shade_3w: self.post_earning_shade_3w.set_visible(False)
            else:
                for s in (self.purple_shade, self.blue_shade, self.post_earning_shade, self.post_earning_shade_3w):
                    if s: s.set_visible(False)

            now = time.time()
            force_flag = False
            if (now - self.last_rebuild_ts) > REBUILD_THROTTLE:
                force_flag = True
                self.last_rebuild_ts = now

            self.gradient_image = update_plot(
                self.line1, self.gradient_image, self.line2,
                f_dates, f_prices, f_turnovers,
                self.ax1, self.ax2, self.show_volume,
                self.cyan_transparent_cmap,
                force_recreate=force_flag,
                gradient_clip_patch=self.gradient_clip_patch,
                zero_line=self.zero_line
            )

            self.build_colored_line_collection(f_dates, f_prices, f_opens)
            self.draw_subtitle(current_prices=f_prices, pre_after_pct=self.current_pre_after_pct[0])

            for i, circle in enumerate(self.radio.circles):
                circle.set_facecolor(NORD_THEME['accent_red'] if list(TIME_OPTIONS.keys())[i] == val else NORD_THEME['background'])
            self.small_dot_scatter.set_visible(val in ["1m", "3m", "6m"])
            self.update_marker_visibility()
            self.fig.canvas.draw_idle()
        except Exception:
            pass

    def toggle_volume(self):
        try:
            self.show_volume = not self.show_volume
            years = TIME_OPTIONS[self.radio.value_selected]
            f_dates, f_prices, f_volumes, f_turnovers, f_opens, f_highs, f_lows = self._filter_by_years(years)

            self.current_filtered_dates = f_dates
            self.current_filtered_prices = f_prices
            self.current_filtered_volumes = f_volumes
            self.current_filtered_date_nums = matplotlib.dates.date2num(f_dates) if f_dates else np.array([])
            self.current_filtered_opens = f_opens
            self.current_filtered_highs = f_highs
            self.current_filtered_lows = f_lows

            self.gradient_image = update_plot(
                self.line1, self.gradient_image, self.line2,
                f_dates, f_prices, f_turnovers,
                self.ax1, self.ax2, self.show_volume,
                self.cyan_transparent_cmap,
                force_recreate=False,
                gradient_clip_patch=self.gradient_clip_patch,
                zero_line=self.zero_line
            )
            self.build_colored_line_collection(f_dates, f_prices, f_opens)
            self.fig.canvas.draw_idle()
        except Exception:
            pass

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
        elif idx > 0:
            if abs(nums[idx - 1] - xdata) < abs(nums[idx] - xdata):
                idx -= 1
        return idx

    def update_annot(self, ind):
        try:
            annot = self.annot
            x_data, y_data = self.line1.get_data()
            idx = ind["ind"][0]
            xval, yval = x_data[idx], y_data[idx]

            if annot.xy != (xval, yval):
                annot.xy = (xval, yval)
                current_date = xval.replace(tzinfo=None)
                g_text, s_text, e_text = None, None, None
                for d, t in self.global_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400:
                        g_text = t; break
                for d, t in self.specific_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400:
                        s_text = t; break
                for d, t in self.earning_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400:
                        e_text = t; break

                if self.mouse_pressed and self.initial_price is not None:
                    percent_change = ((yval - self.initial_price) / self.initial_price) * 100
                    text = f"{percent_change:.1f}%"
                    color = NORD_THEME['accent_cyan']
                    annot.get_bbox_patch().set_edgecolor(color)
                else:
                    current_vol = self.current_filtered_volumes[idx] if self.current_filtered_volumes and idx < len(self.current_filtered_volumes) else None
                    current_low = self.current_filtered_lows[idx] if self.current_filtered_lows and idx < len(self.current_filtered_lows) else None
                    current_high = self.current_filtered_highs[idx] if self.current_filtered_highs and idx < len(self.current_filtered_highs) else None

                    price_display = f"{yval:.2f}"
                    if yval is not None and yval != 0:
                        low_str = f"{((current_low - yval) / yval) * 100:+.2f}%" if current_low is not None else "--"
                        high_str = f"{((current_high - yval) / yval) * 100:+.2f}%" if current_high is not None else "--"
                        if current_low is not None or current_high is not None:
                            price_display = f"{yval:.2f} | {low_str} | {high_str}"

                    turnover_str = "--"
                    if current_vol is not None and yval is not None:
                        turnover_val = current_vol * yval
                        if turnover_val >= 1e9:
                            turnover_str = f"{turnover_val / 1e9:.2f}B"
                        elif turnover_val >= 1e6:
                            turnover_str = f"{turnover_val / 1e6:.2f}M"
                        elif turnover_val >= 1e3:
                            turnover_str = f"{turnover_val / 1e3:.1f}K"
                        else:
                            turnover_str = f"{turnover_val:.1f}"

                    days_diff = abs((self.dates[-1] - xval).days)
                    parts = [
                        f"{datetime.strftime(xval, '%Y-%m-%d')}",
                        price_display,
                        f"{turnover_str}",
                        f"{days_diff}天",
                        ""
                    ]

                    marker_texts = []
                    if g_text:
                        marker_texts.append(g_text)
                    if s_text: marker_texts.append(s_text + "\n")
                    has_earning = False
                    if e_text:
                        for line in e_text.split('\n'):
                            if "昨日财报" in line:
                                marker_texts.append(line); break
                        has_earning = True
                    if marker_texts: parts.extend(marker_texts)

                    parts.append(f"最新价差: {((self.prices[-1] - yval) / yval) * 100:.2f}%")

                    if self.current_filtered_volumes and idx < len(self.current_filtered_volumes) and self.turnovers:
                        sel_vol = self.current_filtered_volumes[idx]
                        sel_price = yval
                        sel_turnover = sel_vol * sel_price if (sel_vol is not None and sel_price is not None) else 0
                        latest_turnover = self.turnovers[-1]
                        if sel_turnover > 0 and latest_turnover > 0:
                            vol_diff = ((latest_turnover - sel_turnover) / sel_turnover) * 100
                            parts.append(f"最新额差: {vol_diff:.2f}%")
                        else:
                            parts.append("最新额差: --")
                    text = "\n".join(parts)

                    if has_earning and not (g_text or s_text): color = NORD_THEME['accent_yellow']
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
                x_ratio = (matplotlib.dates.date2num(xval) - x_range[0]) / (x_range[1] - x_range[0] + 1e-12)

                if y_ratio < 0.2:
                    y_offset = 60
                elif y_ratio > 0.8:
                    y_offset = -120
                else:
                    y_offset = -70

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

                if self.mouse_pressed:
                    idx = self._nearest_idx(event.xdata)
                    x_data, y_data = self.line1.get_data()
                    if idx < len(x_data) and idx < len(y_data) and self.initial_price is not None:
                        sel_date, sel_price = x_data[idx], y_data[idx]
                        try:
                            percent_change = ((sel_price - self.initial_price) / (self.initial_price + 1e-12)) * 100.0
                        except Exception:
                            percent_change = 0.0

                        turnover_text = ""
                        if self.initial_volume is not None and self.current_filtered_volumes and idx < len(self.current_filtered_volumes):
                            sel_vol = self.current_filtered_volumes[idx]
                            if sel_vol is not None and self.initial_price is not None:
                                try:
                                    start_turnover = self.initial_price * self.initial_volume
                                    current_turnover = sel_price * sel_vol
                                    if start_turnover > 0:
                                        turnover_change = ((current_turnover - start_turnover) / start_turnover) * 100.0
                                        turnover_text = f"{turnover_change:.1f}%"
                                    else:
                                        turnover_text = "--%"
                                except:
                                    turnover_text = "--%"

                        date_start_str = self.initial_date.strftime('%Y-%m-%d')
                        date_end_str = sel_date.strftime('%Y-%m-%d')
                        days_diff = abs((sel_date - self.initial_date).days)

                        final_display_text = (
                            f"{date_start_str}\n"
                            f"{date_end_str}\n"
                            f"{days_diff}\n"
                            f"{percent_change:.1f}%\n"
                            f"{turnover_text}"
                        )

                        annot.xy = (sel_date, sel_price)
                        annot.set_text(final_display_text)
                        drag_color = NORD_THEME['accent_red'] if percent_change > 0 else NORD_THEME['accent_green']
                        annot.set_color(drag_color)
                        annot.get_bbox_patch().set_edgecolor(drag_color)
                        annot.get_bbox_patch().set_alpha(0.8)
                        annot.set_fontsize(16)

                        y_range, x_range = ax1.get_ylim(), ax1.get_xlim()
                        y_ratio = (sel_price - y_range[0]) / (y_range[1] - y_range[0] + 1e-12)
                        x_ratio = (matplotlib.dates.date2num(sel_date) - x_range[0]) / (x_range[1] - x_range[0] + 1e-12)
                        y_offset = 60 if y_ratio < 0.2 else -160 if y_ratio > 0.8 else -100
                        x_offset = -120 if x_ratio > 0.7 else 50 if x_ratio < 0.3 else -100
                        annot.set_position((x_offset, y_offset))

                        annot.set_visible(True)
                        self.highlight_point.set_offsets([[sel_date, sel_price]])
                        self.highlight_point.set_visible(True)
                    fig.canvas.draw_idle()
                    return

                # 正常 hover
                idx = self._nearest_idx(event.xdata)
                x_data, y_data = self.line1.get_data()
                if idx < len(x_data) and idx < len(y_data):
                    sel_date, sel_price = x_data[idx], y_data[idx]
                    color = NORD_THEME['accent_cyan']
                    for _, d, _, _ in self.global_scatter_points:
                        if d == sel_date:
                            color = NORD_THEME['accent_red']; break
                    else:
                        for _, d, _, _ in self.specific_scatter_points:
                            if d == sel_date:
                                color = NORD_THEME['text_bright']; break
                        else:
                            for _, d, _, _ in self.earning_scatter_points:
                                if d == sel_date:
                                    color = NORD_THEME['accent_yellow']; break

                    self.highlight_point.set_color(color)
                    dist = 0.2 * ((ax1.get_xlim()[1] - ax1.get_xlim()[0]) / 365)
                    if np.isclose(matplotlib.dates.date2num(sel_date), event.xdata, atol=dist):
                        self.update_annot({"ind": [idx]})
                        annot.set_visible(True)
                        self.highlight_point.set_offsets([[sel_date, sel_price]])
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
            if event.button == 1 and event.xdata is not None and self.current_filtered_dates:
                self.mouse_pressed = True
                idx = self._nearest_idx(event.xdata)
                if idx < len(self.current_filtered_prices):
                    self.initial_price = self.current_filtered_prices[idx]
                    self.initial_date = self.current_filtered_dates[idx]
                    if self.current_filtered_volumes and idx < len(self.current_filtered_volumes):
                        self.initial_volume = self.current_filtered_volumes[idx]
                    else:
                        self.initial_volume = None
        except Exception:
            pass

    def on_mouse_release(self, event):
        try:
            if event.button == 1:
                self.mouse_pressed = False
        except Exception:
            pass

    def on_pick(self, event):
        try:
            all_points = self.global_scatter_points + self.specific_scatter_points + self.earning_scatter_points
            artists = [p[0] for p in all_points]
            if event.artist in artists:
                for scatter, date_v, price_v, text in all_points:
                    if event.artist == scatter:
                        self.annot.xy = (date_v, price_v)
                        self.annot.set_text(f"{datetime.strftime(date_v, '%Y-%m-%d')}\n{price_v}\n{text}")
                        self.annot.get_bbox_patch().set_alpha(0.8)
                        self.annot.set_fontsize(16)
                        midpoint = max(self.dates) - (max(self.dates) - min(self.dates)) / 2
                        self.annot.set_position((50, -20) if date_v < midpoint else (-150, -20))
                        self.annot.set_visible(True)
                        self.highlight_point.set_offsets([date_v, price_v])
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
    # 弹窗 / 外部脚本
    # ------------------------------------------------------------------
    def show_stock_etf_info(self):
        for source in ['stocks', 'etfs']:
            for item in self.current_json_data['data'].get(source, []):
                if item['symbol'] == self.name:
                    info = f"{self.name}\n{item['name']}\n\n{item['tag']}\n\n{item['description1']}\n\n{item['description2']}"
                    dialog = InfoDialog("Information", info, 'Arial Unicode MS', 22, 700, 900)
                    dialog.exec()
                    return
        display_dialog(f"未找到 {self.name} 的信息")

    def show_db_records(self):
        result = query_database_text(self.db_path, self.table_name, f"name = '{self.name}'")
        dialog = InfoDialog("数据库查询结果", result, "Courier", 14, 900, 600)
        dialog.exec()

    def launch_insert_then_delete_chain(self):
        name = self.name

        def on_delete_done(delete_return_code):
            if delete_return_code == 0:
                if self.callback:
                    self.callback('deleted')
                print("删除操作完成 (Code 0)，正在关闭窗口...")
                try:
                    plt.close('all')
                except:
                    pass
                try:
                    if self.panel:
                        sys.exit(0)
                except:
                    pass
            else:
                print(f"删除操作取消或失败 (Code {delete_return_code})，保持窗口开启。")

        def on_insert_done(insert_return_code):
            if insert_return_code == 0:
                print("Panel 输入成功 (Code 0)，正在自动启动删除流程...")
                execute_external_script('panel_delete', name, on_done=on_delete_done, block=True)
            else:
                print(f"Panel 输入取消或未变更 (Code {insert_return_code})，停止连锁流程。")

        execute_external_script('panel_input', name, on_done=on_insert_done, block=True)

    def launch_and_close_for_y(self):
        name = self.name

        def on_done(return_code):
            if return_code == 0:
                if self.callback:
                    self.callback('deleted')
                print("删除操作完成 (Code 0)，正在关闭窗口...")
                try:
                    plt.close('all')
                except:
                    pass
                try:
                    if self.panel:
                        sys.exit(0)
                except:
                    pass
            else:
                print(f"用户取消了删除操作（返回码: {return_code}）")

        execute_external_script('panel_delete', name, on_done=on_done, block=True)

    def refresh_description_data_and_redraw(self):
        print("正在重新加载 description.json...")
        try:
            with open(self.DESCRIPTION_JSON_PATH, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            self.current_json_data['data'] = new_data
            print("description.json 加载成功。正在刷新图表...")
            new_title_text, new_title_color, self.clickable = self.create_or_update_title()
            self.title_artist.set_text(new_title_text)
            self.title_artist.set_color(new_title_color)
            self.draw_subtitle(current_prices=self.current_filtered_prices,
                               pre_after_pct=self.current_pre_after_pct[0])
            self.create_markers_and_annotations()
            self.update_marker_visibility()
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
                plt.close(self.fig)
                if self.panel:
                    sys.exit(0)
                return

            actions = {'v': self.toggle_volume, 'r': self.toggle_global_markers, 'x': self.toggle_all_annotations,
                       'a': self.toggle_earning_markers,
                       'c': self.toggle_specific_markers,
                       'g': self.refresh_description_data_and_redraw,
                       'n': lambda: execute_external_script('earning_input', self.name),
                       'e': lambda: execute_external_script('earning_edit', self.name),
                       't': lambda: execute_external_script('tags_edit', self.name),
                       'w': lambda: execute_external_script('event_input', self.name),
                       'y': self.launch_insert_then_delete_chain,
                       'j': self.launch_and_close_for_y,
                       's': self.toggle_colored_lines,
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

            current_index = list(TIME_OPTIONS.keys()).index(self.radio.value_selected)
            if event.key == 'up' and current_index > 0:
                self.radio.set_active(current_index - 1)
            elif event.key == 'down' and current_index < len(TIME_OPTIONS) - 1:
                self.radio.set_active(current_index + 1)
            # >>>>>>> 核心变化：左右键不再关闭窗口，直接回调，由调用方复用本窗口加载新 symbol <<<<<<<
            elif event.key == 'right':
                if self.callback:
                    self.callback('next')
            elif event.key == 'left':
                if self.callback:
                    self.callback('prev')
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _ui_poll_realtime(self):
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
                pa_color = NORD_THEME['accent_red'] if pct > 0 else NORD_THEME['accent_green']
                self.pa_text_artist[0].set_text(f"P/A:{pct:+.2f}%")
                self.pa_text_artist[0].set_color(pa_color)
                self.fig.canvas.draw_idle()
        except Exception:
            pass

    def _on_close(self, evt):
        self.closed = True
        try:
            self.ui_timer.stop()
        except Exception:
            pass

    def show(self):
        """非阻塞显示 / 前置窗口，并把键盘焦点交给画布"""
        try:
            mgr = self.fig.canvas.manager
            mgr.show()
            try:
                win = mgr.window
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
# 对外接口：签名保持不变。窗口存活时复用，只更新数据；不存在时才创建。
# ======================================================================
_CHART_WINDOW = None

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel=False, callback=None,
                        window_title_text=None, display_name=None):
    global _CHART_WINDOW

    app = QApplication.instance()
    created_app = False
    if app is None:
        app = QApplication(sys.argv)
        created_app = True

    reuse = (_CHART_WINDOW is not None) and (not _CHART_WINDOW.closed)
    if not reuse:
        _CHART_WINDOW = ChartWindow()

    ok = _CHART_WINDOW.load(
        db_path, table_name, name, compare, share, marketcap, pe, json_data,
        default_time_range=default_time_range, panel=panel, callback=callback,
        window_title_text=window_title_text, display_name=display_name
    )
    if not ok:
        return

    _CHART_WINDOW.show()
    print(f"图表已加载: {name}（窗口{'复用' if reuse else '新建'}）")

    # 只有在完全独立运行（外部没有 Qt 事件循环）时才阻塞
    if created_app:
        plt.show()