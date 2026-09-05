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
FIRSTRADE_POSITIONS_FILE = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "firstrade_positions.json")

# --- 导入 Tiger_API ---
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Selenium"))
try:
    from Tiger_API import _get_global_fetcher
except ImportError as e:
    print(f"导入 Tiger_API 失败: {e}")

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

# --- 定义Nord主题的调色板 ---
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

# ============ 读取 Firstrade 真实持仓缓存 ============
FT_DEBUG = os.environ.get("FT_DEBUG", "") == "1"
# 找不到数据时是否在图上显示灰色提示（调试很有用），不想看就 export FT_SHOW_MISS=0
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
                continue
    except Exception as e:
        pass
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

@lru_cache(maxsize=32)
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
            if result: return result
        except sqlite3.OperationalError:
            pass

        try:
            query = f'SELECT date, price, volume, open FROM "{table_name}" WHERE name = ? ORDER BY date;'
            result = cursor.execute(query, (name,)).fetchall()
            if result: return result
        except sqlite3.OperationalError:
            pass

        try:
            query = f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date;'
            result = cursor.execute(query, (name,)).fetchall()
            if result: return result
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
        date = datetime.strptime(row[0], "%Y-%m-%d")
        price = float(row[1]) if row[1] is not None else None
        volume = int(row[2]) if len(row) > 2 and row[2] is not None else None
        open_price = float(row[3]) if len(row) > 3 and row[3] is not None else None
        high_price = float(row[4]) if len(row) > 4 and row[4] is not None else None
        low_price = float(row[5]) if len(row) > 5 and row[5] is not None else None
        if price is not None:
            dates.append(date)
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
    if not dates or not prices:
        line1.set_data([], [])
        if volumes: line2.set_data([], [])
        ax1.set_xlim(datetime.now() - timedelta(days=1), datetime.now())
        ax1.set_ylim(0, 1)
        if show_volume: ax2.set_ylim(0, 1)
        line2.set_visible(show_volume and bool(volumes))
        if zero_line is not None: zero_line.set_visible(False)
        if gradient_image:
            gradient_image.set_visible(False)
            plt.gcf().canvas.draw_idle()
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
            if y1 < 0: ax1.set_ylim(y0, 0 + (top_pad if 'top_pad' in locals() else 0.1))
            elif y0 > 0:
                current_range = y1 - y0
                ax1.set_ylim(0 - (current_range * 0.05), y1)
        else:
            zero_line.set_visible(False)

    if show_volume:
        if volumes and any(v is not None for v in volumes):
            valid_v = [v for v in volumes if v is not None]
            ax2.set_ylim(0, np.max(valid_v) if valid_v else 1)
        else:
            ax2.set_ylim(0, 1)

    xlim = ax1.get_xlim()
    ylim = ax1.get_ylim()
    fill_base = 0 if np.max(prices) < 0 else ylim[0]
    line_x_nums = matplotlib.dates.date2num(dates)
    verts = [(line_x_nums[0], fill_base), *zip(line_x_nums, prices), (line_x_nums[-1], fill_base)]
    clip_path = Path(verts)

    if force_recreate or gradient_image is None:
        if gradient_image is not None: gradient_image.remove()
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
        if gradient_clip_patch is not None: gradient_clip_patch[0] = new_clip_patch
    else:
        gradient_image.set_extent([*xlim, *ylim])
        if gradient_clip_patch is not None and gradient_clip_patch[0] is not None:
            gradient_clip_patch[0].remove()
        new_clip_patch = PathPatch(clip_path, transform=ax1.transData, facecolor='none', edgecolor='none')
        ax1.add_patch(new_clip_patch)
        gradient_image.set_clip_path(new_clip_patch)
        if gradient_clip_patch is not None: gradient_clip_patch[0] = new_clip_patch

    line2.set_visible(show_volume and bool(volumes))
    plt.gcf().canvas.draw_idle()
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
                if callable(on_done): on_done()
            else:
                subprocess.Popen(['osascript', script_path, keyword])
                if callable(on_done): on_done()
        else:
            python_path = sys.executable
            if block:
                result = subprocess.run([python_path, script_path, keyword], check=False)
                if on_done and callable(on_done): on_done(result.returncode)
            else:
                result = subprocess.Popen([python_path, script_path, keyword])
                if on_done and callable(on_done): on_done(result.returncode)
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
            
        if len(rows) < 2: return None

        def parse_row(row):
            iv_s = row[0] if row[0] else "--"
            try:
                iv_v = float(iv_s.replace('%', '').replace(' ', '')) if ('%' in iv_s) else 0.0
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
    except Exception:
        return None

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel="False", callback=None, 
                        window_title_text=None, display_name=None):
    app = QApplication.instance() or QApplication(sys.argv)
    plt.close('all')
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    matplotlib.rcParams['toolbar'] = 'none'
    
    pa_text_artist = [None]
    current_pre_after_pct = [None]
    current_json_data = {'data': json_data}
    DESCRIPTION_JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")

    if isinstance(share, tuple):
        share_val, pb = share
        pb_text = f"{pb}" if pb not in [None, ""] else "--"
    else:
        share_val, pb_text = share, "--"

    show_volume = False
    mouse_pressed = False
    initial_price = None
    initial_volume = None
    initial_date = None
    gradient_image = None
    show_global_markers = False
    show_specific_markers = True
    show_earning_markers = True
    show_all_annotations = False
    show_colored_lines = True
    current_filtered_dates = []
    colored_lc = [None]
    current_filtered_prices = []
    current_filtered_volumes = []
    current_filtered_date_nums = []
    current_filtered_opens = []
    current_filtered_highs = []
    current_filtered_lows = []
    subtitle_artists = []
    
    last_hover_ts = [0.0]
    last_rebuild_ts = [0.0]
    HOVER_THROTTLE = 1 / 90.0
    REBUILD_THROTTLE = 0.15
    gradient_clip_patch = [None]

    try:
        data = fetch_data(db_path, table_name, name)
        dates, prices, volumes, opens, highs, lows = process_data(data)
        has_ohlc = any(o is not None for o in opens)
    except ValueError as e:
        display_dialog(f"{e}")
        return

    if not dates or not prices:
        display_dialog("没有有效的数据来绘制图表。")
        return

    turnovers = []
    if prices and volumes:
        for p, v in zip(prices, volumes):
            turnovers.append(p * v if (p is not None and v is not None) else 0.0)
    else:
        turnovers = [0.0] * len(dates)

    smooth_dates, smooth_prices = smooth_curve(dates, prices)
    date_nums = matplotlib.dates.date2num(dates)

    fig, ax1 = plt.subplots(figsize=(16, 8))
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.83, top=0.8)
    ax2 = ax1.twinx()
    ax2.axis('off')
    fig.patch.set_facecolor(NORD_THEME['background'])

    if window_title_text:
        fig.canvas.manager.set_window_title(window_title_text)
    else:
        fig.canvas.manager.set_window_title(name)
    
    earning_release_date = find_earning_release_date(name)
    purple_shade = None
    blue_shade = None
    
    if earning_release_date:
        week_start_3w, week_end_3w = calculate_three_weeks_before_range(earning_release_date)
        purple_shade = ax1.axvspan(week_start_3w, week_end_3w, facecolor=NORD_THEME['accent_purple'], alpha=0.15, zorder=0.5, visible=False)
        week_start_1w, week_end_1w = calculate_one_week_before_range(earning_release_date)
        blue_shade = ax1.axvspan(week_start_1w, week_end_1w, facecolor=NORD_THEME['accent_blue'], alpha=0.15, zorder=0.5, visible=False)

    post_earning_shade = None
    post_earning_shade_3w = None
    latest_db_earning_date = None

    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1", (name,))
            row = cursor.fetchone()
            if row:
                latest_db_earning_date = datetime.strptime(row[0], "%Y-%m-%d").date()
    except Exception:
        pass

    if latest_db_earning_date:
        pe_start, pe_end = calculate_five_weeks_after_range(latest_db_earning_date)
        post_earning_shade = ax1.axvspan(pe_start, pe_end, facecolor=NORD_THEME['accent_blue'], alpha=0.15, zorder=0.5, visible=False)
        pe_start_3w, pe_end_3w = calculate_three_weeks_after_range(latest_db_earning_date)
        post_earning_shade_3w = ax1.axvspan(pe_start_3w, pe_end_3w, facecolor=NORD_THEME['accent_purple'], alpha=0.15, zorder=0.5, visible=False)

    ax1.set_facecolor(NORD_THEME['background'])
    ax1.spines['bottom'].set_visible(True)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_visible(False)
    ax1.tick_params(axis='y', which='both', left=False, labelleft=False)
    ax1.tick_params(axis='x', colors=NORD_THEME['text_light'])
    ax1.spines['bottom'].set_color(NORD_THEME['border'])
    ax1.spines['bottom'].set_linewidth(1.0)
    ax2.axis('off')
    ax1.grid(True, axis='y', color=NORD_THEME['border'], alpha=0.06, linestyle='--')
    
    highlight_point = ax1.scatter([], [], s=100, color=NORD_THEME['accent_cyan'], zorder=5)
    line1, = ax1.plot(smooth_dates, smooth_prices, marker='', linestyle='-', linewidth=2, color=NORD_THEME['accent_cyan'], alpha=0.8, label='Price', zorder=2)
    if has_ohlc: line1.set_alpha(0)
    small_dot_scatter = ax1.scatter(dates, prices, s=5, color=NORD_THEME['text_bright'], zorder=1.5)
    line2, = ax2.plot(dates, turnovers, marker='o', markersize=2, linestyle='-', linewidth=2, color=NORD_THEME['accent_purple'], alpha=0.7, label='Turnover')
    line2.set_visible(show_volume)

    zero_line = ax1.axhline(y=0, color=NORD_THEME['text_bright'], linestyle=(0, (6, 3)), linewidth=1.8, alpha=0.95, zorder=3, visible=False)

    cyan_base_color = matplotlib.colors.to_rgb(NORD_THEME['accent_cyan'])
    cyan_transparent_cmap = LinearSegmentedColormap.from_list(
        'cyan_transparent_gradient',
        [(*cyan_base_color, 0.0), (*cyan_base_color, 0.5)]
    )

    global_markers, specific_markers, earning_markers = {}, {}, {}
    all_annotations = []
    
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date", (name,))
            for date_str, price_change in cursor.fetchall():
                try:
                    marker_date = datetime.strptime(date_str, "%Y-%m-%d")
                    closest_date = min(dates, key=lambda d: abs(d - marker_date))
                    index = dates.index(closest_date)
                    marker_price, latest_price = prices[index], prices[-1]
                    diff_percent = ((latest_price - marker_price) / marker_price) * 100 if marker_price else 0
                    earning_markers[marker_date] = f"昨日财报: {price_change}%\n最新价差: {diff_percent:.2f}%\n{date_str}"
                except Exception:
                    pass
    except sqlite3.OperationalError:
        pass

    global_scatter_points, specific_scatter_points, earning_scatter_points = [], [], []

    def launch_insert_then_delete_chain():
        def on_delete_done(delete_return_code):
            if delete_return_code == 0:
                if callback: callback('deleted')
                try: plt.close('all')
                except: pass
                try:
                    if panel: sys.exit(0)
                except: pass
        def on_insert_done(insert_return_code):
            if insert_return_code == 0:
                execute_external_script('panel_delete', name, on_done=on_delete_done, block=True)
        execute_external_script('panel_input', name, on_done=on_insert_done, block=True)
    
    def build_colored_line_collection(f_dates, f_prices, f_opens):
        if colored_lc[0] is not None:
            colored_lc[0].remove()
            colored_lc[0] = None

        if not has_ohlc or not f_dates or len(f_dates) < 2: return

        date_nums_lc = matplotlib.dates.date2num(f_dates)
        segments, seg_colors = [], []

        for i in range(len(f_dates) - 1):
            segments.append([(date_nums_lc[i], f_prices[i]), (date_nums_lc[i + 1], f_prices[i + 1])])
            if show_colored_lines:
                next_open = f_opens[i + 1] if (f_opens and i + 1 < len(f_opens)) else None
                next_close = f_prices[i + 1]
                if next_open is not None and next_close is not None:
                    if next_close > next_open: seg_colors.append(NORD_THEME['accent_red'])
                    elif next_close < next_open: seg_colors.append(NORD_THEME['accent_green'])
                    else: seg_colors.append(NORD_THEME['accent_cyan'])
                else:
                    seg_colors.append(NORD_THEME['accent_cyan'])
            else:
                seg_colors.append(NORD_THEME['accent_cyan'])

        lc = LineCollection(segments, colors=seg_colors, linewidths=2, zorder=2, alpha=0.8)
        ax1.add_collection(lc)
        colored_lc[0] = lc
        
    def create_markers_and_annotations():
        for scatter, _, _, _ in global_scatter_points + specific_scatter_points: scatter.remove()
        for annotation, _, _, _ in all_annotations: annotation.remove()
        
        global_markers.clear()
        specific_markers.clear()
        global_scatter_points.clear()
        specific_scatter_points.clear()
        all_annotations.clear()

        if 'global' in current_json_data['data']:
            for date_str, text in current_json_data['data']['global'].items():
                try: global_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                except ValueError: pass
        
        found_item = None
        for source in ['stocks', 'etfs']:
            for item in current_json_data['data'].get(source, []):
                # 兼容 BRK.B 与 BRK-B 格式
                sym = item['symbol']
                if sym == name or sym.replace('-', '.') == name.replace('-', '.'):
                    found_item = item
                    for date_obj in item.get('description3', []):
                        for date_str, text in date_obj.items():
                            try: specific_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                            except ValueError: pass
                    break
            if found_item: break

        for marker_date, text in global_markers.items():
            if min(dates) <= marker_date <= max(dates):
                idx = (np.abs(np.array(dates) - marker_date)).argmin()
                scatter = ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['accent_red'],
                                      alpha=0.7, zorder=4, picker=5, visible=show_global_markers)
                global_scatter_points.append((scatter, dates[idx], prices[idx], text))
        
        for marker_date, text in specific_markers.items():
            if min(dates) <= marker_date <= max(dates):
                idx = (np.abs(np.array(dates) - marker_date)).argmin()
                scatter = ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['text_bright'],
                                      alpha=0.7, zorder=4, picker=5, visible=show_specific_markers)
                specific_scatter_points.append((scatter, dates[idx], prices[idx], text))

        red_offsets = [(-60, 30),(50, -30), (-70, 45), (-50, -35)]
        for i, (scatter, date_v, price_v, text) in enumerate(global_scatter_points):
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
            except Exception: pass

            new_text = f"{text}\n{diff_line}\n{vol_line}\n{date_v.strftime('%Y-%m-%d')}"
            annotation = ax1.annotate(
                new_text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_red'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_red']),
                color=NORD_THEME['accent_red'], fontsize=12, visible=False
            )
            all_annotations.append((annotation, 'global', date_v, price_v))

        specific_offsets = [(-50, -50), (-100, 20)]
        for i, (scatter, date_v, price_v, text) in enumerate(specific_scatter_points):
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
            except Exception: pass

            new_text = f"{text}\n{diff_line}\n{vol_line}\n{date_v.strftime('%Y-%m-%d')}"
            annotation = ax1.annotate(
                new_text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['text_bright'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['text_bright']),
                color=NORD_THEME['text_bright'], fontsize=12,
                visible=show_specific_markers and show_all_annotations
            )
            all_annotations.append((annotation, 'specific', date_v, price_v))

        earning_offsets = [(50, -50), (-150, 25)]
        for i, (scatter, date_v, price_v, text) in enumerate(earning_scatter_points):
            offset = earning_offsets[i % len(earning_offsets)]
            final_text = text
            try:
                if turnovers:
                    idx = dates.index(date_v)
                    turnover_v = turnovers[idx]
                    latest_turnover = turnovers[-1]
                    if turnover_v and turnover_v > 0 and latest_turnover:
                        vol_msg = f"最新额差: {((latest_turnover - turnover_v) / turnover_v) * 100:.2f}%"
                    else:
                        vol_msg = "最新额差: --"
                    parts = text.split('\n')
                    if len(parts) >= 1:
                        parts.insert(-1, vol_msg)
                        final_text = "\n".join(parts)
                    else:
                        final_text = text + "\n" + vol_msg
            except Exception: pass

            annotation = ax1.annotate(
                final_text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_yellow'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_cyan']),
                color=NORD_THEME['accent_yellow'], fontsize=12,
                visible=show_earning_markers and show_all_annotations
            )
            all_annotations.append((annotation, 'earning', date_v, price_v))

    for marker_date, text in earning_markers.items():
        if min(dates) <= marker_date <= max(dates):
            idx = (np.abs(np.array(dates) - marker_date)).argmin()
            scatter = ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['pure_yellow'],
                                  alpha=0.7, zorder=4, picker=5, visible=show_earning_markers)
            earning_scatter_points.append((scatter, dates[idx], prices[idx], text))

    create_markers_and_annotations()

    def toggle_all_annotations():
        nonlocal show_all_annotations
        show_all_annotations = not show_all_annotations
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'global': annotation.set_visible(show_global_markers and show_all_annotations)
            elif anno_type == 'specific': annotation.set_visible(show_specific_markers and show_all_annotations)
            elif anno_type == 'earning': annotation.set_visible(show_earning_markers and show_all_annotations)
        fig.canvas.draw_idle()

    def clean_percentage_string(s):
        try: return float(s.strip('%'))
        except (ValueError, AttributeError): return None

    def create_or_update_title():
        turnover = (volumes[-1] * prices[-1]) / 1e6 if volumes and volumes[-1] is not None and prices[-1] is not None else None
        turnover_str = ""
        if turnover is not None:
            turnover_str = f"{turnover / 1000:.1f}B" if turnover >= 1000 else f"{turnover:.1f}M"

        compare_value = clean_percentage_string(re.sub(r'[\u4e00-\u9fff+]', '', compare))
        if turnover is not None and turnover < 100 and compare_value is not None and compare_value > 0:
            turnover_str = f"可疑{turnover_str}"

        try:
            share_int = int(share_val)
            turnover_rate = f"{(volumes[-1] / share_int) * 100:.2f}" if volumes and volumes[-1] is not None and share_int > 0 else "--"
        except (ValueError, TypeError):
            turnover_rate = "--"

        marketcap_in_billion = ""
        if marketcap not in [None, "N/A"]:
            mc_val = float(marketcap) / 1e9
            marketcap_in_billion = f"{int(mc_val)}B" if mc_val == int(mc_val) else f"{mc_val:.1f}B"

        pe_text = f"{pe}" if pe not in [None, "N/A"] else "--"

        tag_str, fullname, clickable = "", "", False
        for source in ['stocks', 'etfs']:
            for item in current_json_data['data'].get(source, []):
                sym = item['symbol']
                if sym == name or sym.replace('-', '.') == name.replace('-', '.'):
                    fullname = item.get('name', '')
                    tag_str = ','.join(item.get('tag', []))
                    if len(tag_str) > 45: tag_str = tag_str[:45] + '...'
                    clickable = True
                    break
            if clickable: break
        title_symbol = display_name if display_name else name

        if table_name == 'ETFs':
            title_color = NORD_THEME['accent_orange']
            title_text = f'{title_symbol}  {compare}  {turnover_str} "{table_name}" {fullname} {tag_str}'
        else:
            title_color = get_title_color_logic(db_path, name, table_name)
            title_text = f'{title_symbol}  {compare}  {turnover_str} {turnover_rate} {marketcap_in_billion} {pe_text} {pb_text} "{table_name}" {fullname} {tag_str}'
        
        return title_text, title_color, clickable
    
    def draw_subtitle(current_prices=None, pre_after_pct=None):
        for artist in subtitle_artists:
            artist.remove()
        subtitle_artists.clear()

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
                subtitle_artists.extend(
                    _ft_layout_text_row(fig, 0.045, 0.915, ft_items, fontsize=12)
                )
        elif FT_SHOW_MISS:
            t_miss = fig.text(0.045, 0.915, "持仓: 网页无数据",
                              color=NORD_THEME['border'], fontsize=10,
                              ha='left', va='top', fontname='Arial Unicode MS')
            subtitle_artists.append(t_miss)

        metrics_data = get_options_metrics(name)
        
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

            if latest_db_earning_date:
                try:
                    target_dt = datetime.combine(latest_db_earning_date, datetime.min.time())
                    closest_date = min(dates, key=lambda d: abs(d - target_dt))
                    idx = dates.index(closest_date)
                    earning_p = prices[idx]
                    
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
                color=pa_color, fontsize=12, fontweight='bold',
                ha='left', va='top')
        subtitle_artists.append(t_pa)
        pa_text_artist[0] = t_pa

        t_max = fig.text(base_x, y_pos, f"Max:{max_pct_str}",
                 color=NORD_THEME['accent_green'], fontsize=12, fontweight='normal',
                 ha='left', va='top')
        subtitle_artists.append(t_max)
        
        t_min = fig.text(base_x + 0.08, y_pos, f"Min:{min_pct_str}",
                 color=NORD_THEME['accent_green'], fontsize=12, fontweight='normal',
                 ha='left', va='top')
        subtitle_artists.append(t_min)

        t_er = fig.text(base_x + 0.16, y_pos, f"ER:{er_pct_str}",
                 color=er_color, fontsize=12, fontweight='normal',
                 ha='left', va='top')
        subtitle_artists.append(t_er)

        poly_pct = get_polymarket_percentage(name)
        if poly_pct:
            t_poly = fig.text(base_x + 0.24, y_pos, f"Polymarket: {poly_pct}",
                     color=er_color, fontsize=26, fontweight='bold',
                     ha='left', va='top')
            subtitle_artists.append(t_poly)

        if metrics_data is None: return

        target_date = date.today() - timedelta(days=1)
        row0_date = metrics_data.get('date1')
        iv1_data = metrics_data['iv1']
        sum1_data = metrics_data['sum1']

        if row0_date != target_date: return

        compare_str = str(compare[0]) if isinstance(compare, tuple) else str(compare)
        if compare_str == "nan": compare_str = "--"

        COLOR_PRI_UP = "#FF4500"
        COLOR_PRI_DN = "#00FA9A"
        COLOR_SEC_UP = "#E57373"
        COLOR_SEC_DN = "#81C784"
        COLOR_NULL   = "#DDDDDD"
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
        subtitle_artists.append(t_comp)

        iv2_v, iv2_s = metrics_data['iv2']
        c, w, s = get_style(iv2_v, 'secondary')
        t_iv2 = fig.text(center_x - spacing_inner, y_pos + 0.003, iv2_s,
                 color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                 ha='right', va='top')
        subtitle_artists.append(t_iv2)

        sum2_v = metrics_data['sum2']
        c, w, s = get_style(sum2_v, 'secondary')
        sum2_text = f"{sum2_v:.2f}" if isinstance(sum2_v, (int, float)) else str(sum2_v)
        t_sum2 = fig.text(center_x + spacing_inner, y_pos + 0.003, sum2_text,
                 color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                 ha='left', va='top')
        subtitle_artists.append(t_sum2)

        iv1_v, iv1_s = iv1_data
        c, w, s = get_style(iv1_v, 'primary')
        t_iv1 = fig.text(center_x - spacing_outer, y_pos, iv1_s,
                 color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                 ha='right', va='top')
        subtitle_artists.append(t_iv1)

        sum1_v = sum1_data
        c, w, s = get_style(sum1_v, 'primary')
        sum1_text = f"{sum1_v:.2f}" if isinstance(sum1_v, (int, float)) else str(sum1_v)
        t_sum1 = fig.text(center_x + spacing_outer, y_pos, sum1_text,
                 color=c, fontsize=s, fontweight=w, fontname='Arial Unicode MS',
                 ha='left', va='top')
        subtitle_artists.append(t_sum1)

    initial_title_text, initial_title_color, clickable = create_or_update_title()
    title_artist = fig.text(0.5, 0.95, initial_title_text, ha='center', va='top', color=initial_title_color,
                            fontsize=16, fontweight='bold', transform=fig.transFigure, picker=False)
    draw_subtitle() 

    def show_stock_etf_info(event=None):
        for source in ['stocks', 'etfs']:
            for item in current_json_data['data'].get(source, []):
                sym = item['symbol']
                if sym == name or sym.replace('-', '.') == name.replace('-', '.'):
                    info = f"{name}\n{item['name']}\n\n{item['tag']}\n\n{item['description1']}\n\n{item['description2']}"
                    dialog = InfoDialog("Information", info, 'Arial Unicode MS', 22, 700, 900)
                    dialog.exec()
                    return
        display_dialog(f"未找到 {name} 的信息")

    def toggle_colored_lines():
        nonlocal show_colored_lines
        show_colored_lines = not show_colored_lines
        build_colored_line_collection(current_filtered_dates, current_filtered_prices, current_filtered_opens)
        fig.canvas.draw_idle()

    def toggle_global_markers():
        nonlocal show_global_markers
        show_global_markers = not show_global_markers
        for scatter, _, _, _ in global_scatter_points: scatter.set_visible(show_global_markers)
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'global': annotation.set_visible(show_global_markers and show_all_annotations)
        fig.canvas.draw_idle()

    def toggle_specific_markers():
        nonlocal show_specific_markers
        show_specific_markers = not show_specific_markers
        for scatter, _, _, _ in specific_scatter_points: scatter.set_visible(show_specific_markers)
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'specific': annotation.set_visible(show_specific_markers and show_all_annotations)
        fig.canvas.draw_idle()

    def toggle_earning_markers():
        nonlocal show_earning_markers
        show_earning_markers = not show_earning_markers
        for scatter, _, _, _ in earning_scatter_points: scatter.set_visible(show_earning_markers)
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'earning': annotation.set_visible(show_earning_markers and show_all_annotations)
        fig.canvas.draw_idle()

    def update_marker_visibility():
        years = time_options[radio.value_selected]
        min_date = min(dates) if years == 0 else datetime.now() - timedelta(days=years * 365)
        for scatter, date_v, _, _ in global_scatter_points: scatter.set_visible((min_date <= date_v) and show_global_markers)
        for scatter, date_v, _, _ in specific_scatter_points: scatter.set_visible((min_date <= date_v) and show_specific_markers)
        for scatter, date_v, _, _ in earning_scatter_points: scatter.set_visible((min_date <= date_v) and show_earning_markers)

        for annotation, anno_type, date_v, _ in all_annotations:
            visible = False
            if min_date <= date_v:
                if anno_type == 'global': visible = show_global_markers and show_all_annotations
                elif anno_type == 'specific': visible = show_specific_markers and show_all_annotations
                elif anno_type == 'earning': visible = show_earning_markers and show_all_annotations
            annotation.set_visible(visible)
        fig.canvas.draw_idle()

    def on_pick(event):
        try:
            artists = [p[0] for p in global_scatter_points + specific_scatter_points + earning_scatter_points]
            if event.artist in artists:
                for scatter, date_v, price_v, text in global_scatter_points + specific_scatter_points + earning_scatter_points:
                    if event.artist == scatter:
                        annot.xy = (date_v, price_v)
                        annot.set_text(f"{datetime.strftime(date_v, '%Y-%m-%d')}\n{price_v}\n{text}")
                        annot.get_bbox_patch().set_alpha(0.8)
                        annot.set_fontsize(16)
                        midpoint = max(dates) - (max(dates) - min(dates)) / 2
                        annot.set_position((50, -20) if date_v < midpoint else (-150, -20))
                        annot.set_visible(True)
                        highlight_point.set_offsets([date_v, price_v])
                        highlight_point.set_visible(True)
                        fig.canvas.draw_idle()
                        break
        except Exception: pass

    def create_window_qt(content):
        dialog = InfoDialog("数据库查询结果", content, "Courier", 14, 900, 600)
        dialog.exec()

    def query_database(db_path, table_name, condition):
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

    def on_keyword_selected(db_path, table_name, name):
        result = query_database(db_path, table_name, f"name = '{name}'")
        create_window_qt(result)

    if clickable: fig.canvas.mpl_connect('pick_event', on_pick)

    ax1.grid(True, color=NORD_THEME['border'], alpha=0.1, linestyle='--')
    plt.xticks(rotation=45)

    annot = ax1.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
        bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_cyan']),
        arrowprops=dict(arrowstyle="->"), color=NORD_THEME['text_bright'], visible=False)

    time_options = {"1m":0.08, "3m":0.25, "6m":0.5, "1Y":1, "2Y":2, "3Y":3, "5Y":5, "10Y":10, "All":0}
    default_index = list(time_options.keys()).index(default_time_range)

    rax = plt.axes([0.95, 0.0, 0.05, 0.65], facecolor=NORD_THEME['background'])
    radio = RadioButtons(rax, list(time_options.keys()), active=default_index)
    rax.set_facecolor(NORD_THEME['background'])
    rax.set_frame_on(False)
    for spine in rax.spines.values(): spine.set_visible(False)
    
    for label in radio.labels:
        label.set_color(NORD_THEME['text_light'])
        label.set_fontsize(14)
    for circle in radio.circles:
        circle.set_edgecolor(NORD_THEME['border'])
        circle.set_facecolor(NORD_THEME['background'])
    radio.circles[default_index].set_facecolor(NORD_THEME['accent_red'])

    instructions = "N:新财报\nE:改财报\nT:改标签\nW:新事件\nQ:改事件\nK:查豆包\nZ:查富途\nP:做比较\nJ:加Panel\nL:查相似\nY:删除\nG:刷新\nO:查α\nB:存在"
    rax.text(0.5, 0.98, instructions, transform=rax.transAxes, ha="center", va="bottom",
             color=NORD_THEME['text_light'], fontsize=10, fontfamily="Arial Unicode MS")
    
    def update_annot(ind):
        try:
            x_data, y_data = line1.get_data()
            idx = ind["ind"][0] 
            xval, yval = x_data[idx], y_data[idx]

            if annot.xy != (xval, yval):
                annot.xy = (xval, yval)
                current_date = xval.replace(tzinfo=None)
                g_text, s_text, e_text = None, None, None
                for d, t in global_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400: g_text = t; break
                for d, t in specific_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400: s_text = t; break
                for d, t in earning_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400: e_text = t; break
                
                if mouse_pressed and initial_price is not None:
                    percent_change = ((yval - initial_price) / initial_price) * 100
                    text = f"{percent_change:.1f}%"
                    color = NORD_THEME['accent_cyan']
                    annot.get_bbox_patch().set_edgecolor(color)
                else:
                    current_vol = current_filtered_volumes[idx] if current_filtered_volumes and idx < len(current_filtered_volumes) else None
                    current_low = current_filtered_lows[idx] if current_filtered_lows and idx < len(current_filtered_lows) else None
                    current_high = current_filtered_highs[idx] if current_filtered_highs and idx < len(current_filtered_highs) else None
                    
                    price_display = f"{yval:.2f}"
                    if yval is not None and yval != 0:
                        low_str = f"{((current_low - yval) / yval) * 100:+.2f}%" if current_low is not None else "--"
                        high_str = f"{((current_high - yval) / yval) * 100:+.2f}%" if current_high is not None else "--"
                        if current_low is not None or current_high is not None:
                            price_display = f"{yval:.2f} | {low_str} | {high_str}"

                    turnover_str = "--"
                    if current_vol is not None and yval is not None:
                        turnover_val = current_vol * yval
                        if turnover_val >= 1e9: turnover_str = f"{turnover_val / 1e9:.2f}B"
                        elif turnover_val >= 1e6: turnover_str = f"{turnover_val / 1e6:.2f}M"
                        elif turnover_val >= 1e3: turnover_str = f"{turnover_val / 1e3:.1f}K"
                        else: turnover_str = f"{turnover_val:.1f}"
                    
                    days_diff = abs((dates[-1] - xval).days)
                    parts = [
                        f"{datetime.strftime(xval, '%Y-%m-%d')}",
                        price_display,
                        f"{turnover_str}",
                        f"{days_diff}天",
                        ""
                    ]

                    marker_texts = []
                    if g_text: marker_texts.append(g_text)
                    if s_text: marker_texts.append(s_text + "\n")
                    has_earning = False
                    if e_text:
                        for line in e_text.split('\n'):
                            if "昨日财报" in line: marker_texts.append(line); break
                        has_earning = True
                    if marker_texts: parts.extend(marker_texts)
                    
                    parts.append(f"最新价差: {((prices[-1] - yval) / yval) * 100:.2f}%")
                    
                    if current_filtered_volumes and idx < len(current_filtered_volumes) and turnovers:
                        sel_vol = current_filtered_volumes[idx]
                        sel_price = yval
                        sel_turnover = sel_vol * sel_price if (sel_vol is not None and sel_price is not None) else 0
                        latest_turnover = turnovers[-1]

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
                
                y_range = ax1.get_ylim()
                y_ratio = (yval - y_range[0]) / (y_range[1] - y_range[0] + 1e-12)
                x_range = ax1.get_xlim()
                x_ratio = (matplotlib.dates.date2num(xval) - x_range[0]) / (x_range[1] - x_range[0] + 1e-12)
                
                if y_ratio < 0.2: y_offset = 60
                elif y_ratio > 0.8: y_offset = -120
                else: y_offset = -70
                
                if x_ratio > 0.7: x_offset = -min(20 + len(annot.get_text()) * 6, 320)
                elif x_ratio < 0.3: x_offset = 50
                else: x_offset = -200
                annot.set_position((x_offset, y_offset))
        except Exception: pass

    def hover(event):
        try:
            now = time.time()
            if now - last_hover_ts[0] < HOVER_THROTTLE: return
            last_hover_ts[0] = now
            if event.inaxes in [ax1, ax2] and event.xdata and current_filtered_dates:
                vline.set_xdata([event.xdata, event.xdata])
                vline.set_visible(True)
                
                if mouse_pressed:
                    if len(current_filtered_date_nums) > 0:
                        idx = np.searchsorted(current_filtered_date_nums, event.xdata)
                        if idx >= len(current_filtered_date_nums): idx = len(current_filtered_date_nums) - 1
                        elif idx > 0:
                            if abs(current_filtered_date_nums[idx-1] - event.xdata) < abs(current_filtered_date_nums[idx] - event.xdata):
                                idx = idx - 1
                    else: idx = 0

                    x_data, y_data = line1.get_data()
                    if idx < len(x_data) and idx < len(y_data) and initial_price is not None:
                        sel_date, sel_price = x_data[idx], y_data[idx]
                        try: percent_change = ((sel_price - initial_price) / (initial_price + 1e-12)) * 100.0
                        except Exception: percent_change = 0.0

                        turnover_text = ""
                        if initial_volume is not None and current_filtered_volumes and idx < len(current_filtered_volumes):
                            sel_vol = current_filtered_volumes[idx]
                            if sel_vol is not None and initial_price is not None:
                                try:
                                    start_turnover = initial_price * initial_volume
                                    current_turnover = sel_price * sel_vol
                                    if start_turnover > 0:
                                        turnover_change = ((current_turnover - start_turnover) / start_turnover) * 100.0
                                        turnover_text = f"{turnover_change:.1f}%"
                                    else: turnover_text = "--%"
                                except: turnover_text = "--%"

                        date_start_str = initial_date.strftime('%Y-%m-%d')
                        date_end_str = sel_date.strftime('%Y-%m-%d')
                        days_diff = abs((sel_date - initial_date).days)

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
                        highlight_point.set_offsets([[sel_date, sel_price]])
                        highlight_point.set_visible(True)
                    fig.canvas.draw_idle()
                    return

                if len(current_filtered_date_nums) > 0:
                    idx = np.searchsorted(current_filtered_date_nums, event.xdata)
                    if idx >= len(current_filtered_date_nums): idx = len(current_filtered_date_nums) - 1
                    elif idx > 0:
                        if abs(current_filtered_date_nums[idx-1] - event.xdata) < abs(current_filtered_date_nums[idx] - event.xdata):
                            idx = idx - 1
                else: idx = 0

                x_data, y_data = line1.get_data()
                if idx < len(x_data) and idx < len(y_data):
                    sel_date, sel_price = x_data[idx], y_data[idx]
                    color = NORD_THEME['accent_cyan']
                    for _, d, _, _ in global_scatter_points:
                        if d == sel_date: color = NORD_THEME['accent_red']; break
                    else:
                        for _, d, _, _ in specific_scatter_points:
                            if d == sel_date: color = NORD_THEME['text_bright']; break
                        else:
                            for _, d, _, _ in earning_scatter_points:
                                if d == sel_date: color = NORD_THEME['accent_yellow']; break
                    
                    highlight_point.set_color(color)
                    dist = 0.2 * ((ax1.get_xlim()[1] - ax1.get_xlim()[0]) / 365)
                    if np.isclose(matplotlib.dates.date2num(sel_date), event.xdata, atol=dist):
                        update_annot({"ind": [idx]})
                        annot.set_visible(True)
                        highlight_point.set_offsets([[sel_date, sel_price]])
                        highlight_point.set_visible(True)
                    else:
                        annot.set_visible(False)
                        highlight_point.set_visible(False)
                fig.canvas.draw_idle()
            elif event.inaxes != rax:
                vline.set_visible(False)
                annot.set_visible(False)
                highlight_point.set_visible(False)
                fig.canvas.draw_idle()
        except Exception: pass

    def update(val):
        nonlocal gradient_image, current_filtered_dates, current_filtered_prices, current_filtered_volumes, current_filtered_date_nums, current_filtered_opens, current_filtered_highs, current_filtered_lows
        try:
            years = time_options[val]
            if years == 0:
                f_dates, f_prices, f_volumes = dates, prices, volumes
                f_turnovers = turnovers
                f_opens, f_highs, f_lows = opens, highs, lows
            else:
                min_date = datetime.now() - timedelta(days=years * 365)
                indices = [i for i, d in enumerate(dates) if d >= min_date]
                if not indices:
                    f_dates, f_prices = [dates[-1]], [prices[-1]]
                    f_volumes = [volumes[-1]] if volumes else None
                    f_turnovers = [turnovers[-1]] if turnovers else None
                    f_opens = [opens[-1]] if opens else None
                    f_highs = [highs[-1]] if highs else None
                    f_lows = [lows[-1]] if lows else None 
                else:
                    f_dates = [dates[i] for i in indices]
                    f_prices = [prices[i] for i in indices]
                    f_volumes = [volumes[i] for i in indices] if volumes else None
                    f_turnovers = [turnovers[i] for i in indices] if turnovers else None
                    f_opens = [opens[i] for i in indices]
                    f_highs = [highs[i] for i in indices]
                    f_lows = [lows[i] for i in indices] 

            current_filtered_dates = f_dates
            current_filtered_prices = f_prices
            current_filtered_volumes = f_volumes 
            current_filtered_date_nums = matplotlib.dates.date2num(current_filtered_dates) if current_filtered_dates else np.array([])
            current_filtered_opens = f_opens
            current_filtered_highs = f_highs
            current_filtered_lows = f_lows

            if f_dates:
                display_start = min(f_dates).date() if isinstance(min(f_dates), datetime) else min(f_dates)
                display_end = max(f_dates).date() if isinstance(max(f_dates), datetime) else max(f_dates)
                
                if earning_release_date:
                    if purple_shade:
                        week_start_3w, week_end_3w = calculate_three_weeks_before_range(earning_release_date)
                        purple_shade.set_visible(not (week_end_3w < display_start or week_start_3w > display_end))
                    if blue_shade:
                        week_start_1w, week_end_1w = calculate_one_week_before_range(earning_release_date)
                        blue_shade.set_visible(not (week_end_1w < display_start or week_start_1w > display_end))
                else:
                    if purple_shade: purple_shade.set_visible(False)
                    if blue_shade: blue_shade.set_visible(False)

                if latest_db_earning_date:
                    if post_earning_shade:
                        pe_start, pe_end = calculate_five_weeks_after_range(latest_db_earning_date)
                        post_earning_shade.set_visible(not (pe_end < display_start or pe_start > display_end))
                    if post_earning_shade_3w:
                        pe_start_3w, pe_end_3w = calculate_three_weeks_after_range(latest_db_earning_date)
                        post_earning_shade_3w.set_visible(not (pe_end_3w < display_start or pe_start_3w > display_end))
                else:
                    if post_earning_shade: post_earning_shade.set_visible(False)
                    if post_earning_shade_3w: post_earning_shade_3w.set_visible(False)

            now = time.time()
            force_flag = False
            if (now - last_rebuild_ts[0]) > REBUILD_THROTTLE:
                force_flag = True
                last_rebuild_ts[0] = now

            gradient_image = update_plot(
                line1, gradient_image, line2,
                f_dates, f_prices, f_turnovers,
                ax1, ax2, show_volume,
                cyan_transparent_cmap,
                force_recreate=force_flag,
                gradient_clip_patch=gradient_clip_patch,
                zero_line=zero_line
            )

            build_colored_line_collection(f_dates, f_prices, f_opens)
            draw_subtitle(current_prices=f_prices, pre_after_pct=current_pre_after_pct[0])

            for i, circle in enumerate(radio.circles):
                circle.set_facecolor(NORD_THEME['accent_red'] if list(time_options.keys())[i] == val else NORD_THEME['background'])
            small_dot_scatter.set_visible(val in ["1m", "3m", "6m"])
            update_marker_visibility()
            fig.canvas.draw_idle()
        except Exception: pass

    def toggle_volume():
        nonlocal show_volume, current_filtered_dates, current_filtered_prices, current_filtered_volumes, current_filtered_date_nums, current_filtered_opens, current_filtered_highs, current_filtered_lows
        try:
            show_volume = not show_volume
            years = time_options[radio.value_selected]
            if years == 0:
                f_dates, f_prices = dates, prices 
                f_turnovers = turnovers
                f_opens, f_highs, f_lows = opens, highs, lows
            else:
                min_date = datetime.now() - timedelta(days=years * 365)
                indices = [i for i, d in enumerate(dates) if d >= min_date]
                if indices:
                    f_dates = [dates[i] for i in indices]
                    f_prices = [prices[i] for i in indices]
                    f_turnovers = [turnovers[i] for i in indices] if turnovers else None
                    f_opens = [opens[i] for i in indices] 
                    f_highs = [highs[i] for i in indices]
                    f_lows = [lows[i] for i in indices] 
                else:
                    f_dates = [dates[-1]]
                    f_prices = [prices[-1]]
                    f_turnovers = [turnovers[-1]] if turnovers else None
                    f_opens = [opens[-1]] if opens else None
                    f_highs = [highs[-1]] if highs else None
                    f_lows = [lows[-1]] if lows else None 
            
            current_filtered_dates = f_dates
            current_filtered_prices = f_prices
            current_filtered_date_nums = matplotlib.dates.date2num(current_filtered_dates) if current_filtered_dates else np.array([])
            current_filtered_opens = f_opens
            current_filtered_highs = f_highs
            current_filtered_lows = f_lows

            update_plot(
                line1, gradient_image, line2,
                f_dates, f_prices, f_turnovers,
                ax1, ax2, show_volume,
                cyan_transparent_cmap,
                force_recreate=False,
                gradient_clip_patch=gradient_clip_patch,
                zero_line=zero_line
            )
            build_colored_line_collection(f_dates, f_prices, f_opens)
            fig.canvas.draw_idle()
        except Exception: pass

    def launch_and_close_for_y():
        def on_done(return_code):
            if return_code == 0:
                if callback: callback('deleted')
                try: plt.close('all')
                except: pass
                try:
                    if panel: sys.exit(0)
                except: pass
        execute_external_script('panel_delete', name, on_done=on_done, block=True)
    
    def refresh_description_data_and_redraw():
        nonlocal title_artist, clickable
        try:
            with open(DESCRIPTION_JSON_PATH, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            current_json_data['data'] = new_data
            new_title_text, new_title_color, clickable = create_or_update_title()
            title_artist.set_text(new_title_text)
            draw_subtitle() 
            create_markers_and_annotations()
            update_marker_visibility()
            fig.canvas.draw_idle()
        except Exception as e:
            display_dialog(f"刷新出错: {e}")

    def on_key(event):
        try:
            actions = {'v': toggle_volume, 'r': toggle_global_markers, 'x': toggle_all_annotations,
                       'a': toggle_earning_markers,
                       'c': toggle_specific_markers,
                       'g': refresh_description_data_and_redraw,
                       'n': lambda: execute_external_script('earning_input', name),
                       'e': lambda: execute_external_script('earning_edit', name),
                       't': lambda: execute_external_script('tags_edit', name),
                       'w': lambda: execute_external_script('event_input', name),
                       'y': launch_insert_then_delete_chain, 
                       'j': launch_and_close_for_y,
                       's': toggle_colored_lines,
                       'q': lambda: execute_external_script('event_edit', name),
                       'k': lambda: execute_external_script('check_kimi', name),
                       'z': lambda: execute_external_script('check_futu', name),
                       'o': lambda: execute_external_script('check_seekingalpha', name),
                       'p': lambda: execute_external_script('symbol_compare', name),
                       'l': lambda: execute_external_script('similar_tags', name),
                       'b': lambda: execute_external_script('check_history', name),
                       '/': lambda: execute_external_script('stock_chart', name),
                       '1': lambda: radio.set_active(7), '2': lambda: radio.set_active(1),
                       '3': lambda: radio.set_active(3), '4': lambda: radio.set_active(4),
                       '5': lambda: radio.set_active(5), '6': lambda: radio.set_active(6),
                       '7': lambda: radio.set_active(8), '8': lambda: radio.set_active(2),
                       '9': lambda: radio.set_active(0), '`': show_stock_etf_info,
                       'd': lambda: on_keyword_selected(db_path, table_name, name)}
            if event.key in actions: actions[event.key]()
            current_index = list(time_options.keys()).index(radio.value_selected)
            if event.key == 'up' and current_index > 0: radio.set_active(current_index - 1)
            elif event.key == 'down' and current_index < len(time_options) - 1: radio.set_active(current_index + 1)
            elif event.key == 'right':
                plt.close('all')
                if callback: callback('next')
            elif event.key == 'left':
                plt.close('all')
                if callback: callback('prev')
        except Exception: pass

    def close_everything(event, panel_flag):
        if event.key == 'escape':
            plt.close('all')
            if panel_flag: sys.exit(0)

    def on_mouse_press(event):
        nonlocal mouse_pressed, initial_price, initial_volume, initial_date
        try:
            if event.button == 1 and event.xdata is not None and current_filtered_dates:
                mouse_pressed = True
                if len(current_filtered_date_nums) > 0:
                    idx = np.searchsorted(current_filtered_date_nums, event.xdata)
                    if idx >= len(current_filtered_date_nums): idx = len(current_filtered_date_nums) - 1
                    elif idx > 0:
                        if abs(current_filtered_date_nums[idx-1] - event.xdata) < abs(current_filtered_date_nums[idx] - event.xdata):
                            idx = idx - 1
                else: idx = 0
                if idx < len(current_filtered_prices):
                    initial_price, initial_date = current_filtered_prices[idx], current_filtered_dates[idx]
                    initial_volume = current_filtered_volumes[idx] if (current_filtered_volumes and idx < len(current_filtered_volumes)) else None
        except Exception: pass

    def on_mouse_release(event):
        nonlocal mouse_pressed
        try:
            if event.button == 1: mouse_pressed = False
        except Exception: pass

    vline = ax1.axvline(x=dates[0], color=NORD_THEME['accent_cyan'], linestyle='--', linewidth=1, visible=False)
    
    plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
    plt.gcf().canvas.mpl_connect('key_press_event', on_key)
    plt.gcf().canvas.mpl_connect('key_press_event', lambda e: close_everything(e, panel))
    plt.gcf().canvas.mpl_connect('button_press_event', on_mouse_press)
    plt.gcf().canvas.mpl_connect('button_release_event', on_mouse_release)
    radio.on_clicked(update)

    def hide_annot_on_leave(event):
        try:
            annot.set_visible(False)
            highlight_point.set_visible(False)
            vline.set_visible(False)
            fig.canvas.draw_idle()
        except Exception: pass

    plt.gcf().canvas.mpl_connect('figure_leave_event', hide_annot_on_leave)

    _RT_MANAGER.set_symbol(name)

    def _ui_poll_realtime():
        rt_price = _RT_MANAGER.get_latest(name)
        if rt_price is None or not prices or prices[-1] == 0: return
        pct = ((rt_price - prices[-1]) / prices[-1]) * 100
        if current_pre_after_pct[0] is not None and abs(current_pre_after_pct[0] - pct) < 1e-9: return
        current_pre_after_pct[0] = pct
        if pa_text_artist[0] is not None:
            pa_color = NORD_THEME['accent_red'] if pct > 0 else NORD_THEME['accent_green']
            pa_text_artist[0].set_text(f"P/A:{pct:+.2f}%")
            pa_text_artist[0].set_color(pa_color)
            fig.canvas.draw_idle()

    ui_timer = fig.canvas.new_timer(interval=1000)
    ui_timer.add_callback(_ui_poll_realtime)
    ui_timer.start()
    fig._ui_timer = ui_timer

    def _on_close(evt):
        try: ui_timer.stop()
        except Exception: pass

    fig.canvas.mpl_connect('close_event', _on_close)

    try: fig.canvas.toolbar_visible = False
    except Exception: pass

    update(default_time_range)
    plt.show()