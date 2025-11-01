import re
import sys
import sqlite3
import subprocess
import numpy as np
from datetime import datetime, timedelta, date
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
from functools import lru_cache
from scipy.interpolate import interp1d
import json

from matplotlib.patches import PathPatch
from matplotlib.path import Path
from matplotlib.colors import LinearSegmentedColormap

from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import glob
import os

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

# 在文件开头添加这个函数
def find_earning_release_date(symbol, txt_dir='/Users/yanzhang/Coding/News/'):
    """
    在 Earnings_Release_*.txt 文件中查找 symbol 对应的日期
    返回找到的第一个日期，如果没找到返回 None
    """
    try:
        # 查找所有匹配的文件
        pattern = os.path.join(txt_dir, 'Earnings_Release_*.txt')
        files = glob.glob(pattern)
        
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # 解析格式: "SYMBOL : TIME : DATE"
                        parts = [p.strip() for p in line.split(':')]
                        if len(parts) >= 3:
                            file_symbol = parts[0]
                            date_str = parts[2]
                            if file_symbol == symbol:
                                # 解析日期
                                try:
                                    return datetime.strptime(date_str, "%Y-%m-%d").date()
                                except ValueError:
                                    print(f"日期格式错误: {date_str}")
                                    continue
            except Exception as e:
                print(f"读取文件 {file_path} 时出错: {e}")
                continue
        
        return None
    except Exception as e:
        print(f"查找 earning release 日期时出错: {e}")
        return None


def calculate_three_weeks_before_range(target_date):
    """
    计算目标日期往前推三周的那一周的区间范围
    返回 (start_date, end_date) 元组
    """
    # 往前推 3 周 = 21 天
    three_weeks_before = target_date - timedelta(days=21)
    
    # 找到这一天所在周的周一（weekday: 0=周一, 6=周日）
    weekday = three_weeks_before.weekday()
    week_start = three_weeks_before - timedelta(days=weekday)
    
    # 周五是本周的结束
    week_end = week_start + timedelta(days=4)
    
    return week_start, week_end

def calculate_one_week_before_range(target_date):
    """
    计算目标日期往前推一周的那一周的区间范围
    返回 (start_date, end_date) 元组
    """
    # 往前推 1 周 = 7 天
    one_week_before = target_date - timedelta(days=7)
    
    # 找到这一天所在周的周一（weekday: 0=周一, 6=周日）
    weekday = one_week_before.weekday()
    week_start = one_week_before - timedelta(days=weekday)
    
    # 周五是本周的结束
    week_end = week_start + timedelta(days=4)
    
    return week_start, week_end

def get_title_color_logic(db_path, symbol, table_name):
    """
    获取决定标题颜色所需的所有数据，并返回最终的颜色字符串。
    如果任何步骤失败或不满足条件，则返回默认颜色 'white'。
    """
    try:
        with sqlite3.connect(db_path) as conn:
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

            with sqlite3.connect(db_path) as conn:
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
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_name ON {table_name} (name);")
            query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? ORDER BY date;"
            result = cursor.execute(query, (name,)).fetchall()
            if not result: raise ValueError("没有查询到可用数据")
            return result
        except sqlite3.OperationalError:
            query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
            result = cursor.execute(query, (name,)).fetchall()
            if not result: raise ValueError("没有查询到可用数据")
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
    dates, prices, volumes = [], [], []
    for row in data:
        date = datetime.strptime(row[0], "%Y-%m-%d")
        price = float(row[1]) if row[1] is not None else None
        volume = int(row[2]) if len(row) > 2 and row[2] is not None else None
        if price is not None:
            dates.append(date)
            prices.append(price)
            volumes.append(volume)
    return dates, prices, volumes

def display_dialog(message):
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

# --- 优化: 简化的update_plot函数，减少重复创建渐变 ---
def update_plot(line1, gradient_image, line2, dates, prices, volumes, ax1, ax2, show_volume, cmap, force_recreate=False, gradient_clip_patch=None, zero_line=None):
    """
    更新图表，使用 imshow 和 clip_path 实现渐变填充。
    此版本修复了快速切换时渐变区域不同步的问题。
    """
    # 1. 处理没有数据的情况
    if not dates or not prices:
        line1.set_data([], [])
        if volumes: line2.set_data([], [])
        ax1.set_xlim(datetime.now() - timedelta(days=1), datetime.now())
        ax1.set_ylim(0, 1)
        if show_volume: ax2.set_ylim(0, 1)
        line2.set_visible(show_volume and bool(volumes))
        # 隐藏零线
        if zero_line is not None:
            zero_line.set_visible(False)
        # 如果之前有渐变图，则隐藏它
        if gradient_image:
            gradient_image.set_visible(False)
        plt.gcf().canvas.draw_idle()
        return gradient_image

    # 如果之前因无数据而隐藏，现在恢复显示
    if gradient_image and not gradient_image.get_visible():
        gradient_image.set_visible(True)

    # 2. 更新主价格曲线和成交量曲线的数据
    line1.set_data(dates, prices)
    if volumes:
        line2.set_data(dates, volumes)
    else:
        line2.set_data([], [])

    # 3. 动态调整坐标轴范围
    date_min_val, date_max_val = np.min(dates), np.max(dates)
    if date_min_val == date_max_val:
        ax1.set_xlim(date_min_val - timedelta(days=1), date_max_val + timedelta(days=1))
    else:
        date_range = date_max_val - date_min_val
        right_margin = date_range * 0.01
        ax1.set_xlim(date_min_val, date_max_val + right_margin)

    min_p, max_p = np.min(prices), np.max(prices)
    if min_p == max_p:
        # 当所有点相等时给一个对称 buffer
        buffer = abs(min_p * 0.1) if min_p != 0 else 0.1
        buffer = max(buffer, 1e-6)
        min_p -= buffer
        max_p += buffer
    # 在正常情况下，对上限加一点“呼吸空间”
    y_range = max_p - min_p
    # 比例式 padding（顶部多一点），可根据需要调整比例
    top_pad = max(y_range * 0.03, 0.02 * max(1.0, abs(max_p)))   # 至少给一个相对最小值
    bottom_pad = y_range * 0.01
    ax1.set_ylim(min_p - bottom_pad, max_p + top_pad)

    # 新增：零线显隐与范围保障
    if zero_line is not None:
        # 使用原始价格数据判断是否存在负值
        if np.min(prices) < 0.0:
            zero_line.set_visible(True)
            y0, y1 = ax1.get_ylim()
            # 如果 0 不在当前 Y 轴范围内，则扩展范围以包含 0
            if y1 < 0:  # 所有数据都为负
                ax1.set_ylim(y0, 0 + top_pad)
            elif y0 > 0: # 所有数据都为正，但由于某种原因（例如，极小的负值被padding覆盖），0 不可见
                ax1.set_ylim(0 - bottom_pad, y1)
        else: # 所有数据均为正或零
            zero_line.set_visible(False)

    if show_volume:
        if volumes and any(v is not None for v in volumes):
            max_v = np.max([v for v in volumes if v is not None])
            ax2.set_ylim(0, max_v)
        else:
            ax2.set_ylim(0, 1)

    # --- 4. 修改核心逻辑：创建或更新渐变与剪切 ---
    
    # 获取更新后的坐标轴范围
    xlim = ax1.get_xlim()
    ylim = ax1.get_ylim()

    # ==================== 这是核心修改 ====================
    # 动态确定填充区域的基线
    # 如果所有价格都小于0，则基线为0。否则，基线为Y轴的底部。
    fill_base = 0 if np.max(prices) < 0 else ylim[0]

    # 创建剪切路径所需的顶点
    line_x_nums = matplotlib.dates.date2num(dates)
    # 使用动态确定的 fill_base 作为填充区域的底部
    verts = [(line_x_nums[0], fill_base), *zip(line_x_nums, prices), (line_x_nums[-1], fill_base)]
    clip_path = Path(verts)

    if force_recreate or gradient_image is None:
        # --- 场景A: 强制重建或首次创建 ---
        # 安全移除旧的图像和旧的剪切补丁
        if gradient_image is not None:
            gradient_image.remove()
        if gradient_clip_patch is not None and gradient_clip_patch[0] is not None:
            gradient_clip_patch[0].remove()
        
        # 创建一个垂直的渐变数组
        gradient = np.linspace(1.0, 0.0, 256).reshape(-1, 1)

        # 创建新的渐变图像，范围直接使用新的 xlim, ylim
        gradient_image = ax1.imshow(
            gradient, aspect='auto', cmap=cmap, extent=[*xlim, *ylim],
            origin='lower', zorder=1, interpolation='nearest'
        )

        # 创建新的剪切补丁
        new_clip_patch = PathPatch(clip_path, transform=ax1.transData, facecolor='none', edgecolor='none')
        ax1.add_patch(new_clip_patch)
        gradient_image.set_clip_path(new_clip_patch)

        # 更新引用
        if gradient_clip_patch is not None:
            gradient_clip_patch[0] = new_clip_patch

    else:
        # --- 场景B: 节流生效，仅更新现有对象 ---
        # 1. 更新现有渐变图像的范围
        gradient_image.set_extent([*xlim, *ylim])

        # 2. 移除旧的剪切补丁
        if gradient_clip_patch is not None and gradient_clip_patch[0] is not None:
            gradient_clip_patch[0].remove()

        # 3. 创建并应用新的剪切补丁
        new_clip_patch = PathPatch(clip_path, transform=ax1.transData, facecolor='none', edgecolor='none')
        ax1.add_patch(new_clip_patch)
        gradient_image.set_clip_path(new_clip_patch)
        
        # 4. 更新引用
        if gradient_clip_patch is not None:
            gradient_clip_patch[0] = new_clip_patch

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
        if event.key() == Qt.Key_Escape: self.close()

    def center_on_screen(self):
        screen_geometry = QApplication.desktop().screenGeometry()
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
    base_path = '/Users/yanzhang/Coding/Financial_System'
    script_configs = {
        'earning_input': f'{base_path}/Operations/Insert_Earning_Manual.py',
        'earning_edit': f'{base_path}/Operations/Editor_Earning_DB.py',
        'tags_edit': f'{base_path}/Operations/Editor_Tags.py',
        'event_input': f'{base_path}/Operations/Insert_Events.py',
        'event_edit': f'{base_path}/Operations/Editor_Events.py',
        'symbol_compare': f'{base_path}/Query/Compare_Chart.py',
        'panel_input': f'{base_path}/Operations/Insert_Panel.py',
        'panel_delete': f'{base_path}/Operations/Delete_Panel.py',
        'empty_input': f'{base_path}/Operations/Insert_Sector.py',
        'similar_tags': f'{base_path}/Query/Search_Similar_Tag.py',
        'check_kimi': '/Users/yanzhang/Coding/ScriptEditor/Check_Earning.scpt',
        'check_futu': '/Users/yanzhang/Coding/ScriptEditor/Stock_CheckFutu.scpt',
        'check_seekingalpha': '/Users/yanzhang/Coding/ScriptEditor/Stock_seekingalpha.scpt',
        'stock_chart': '/Users/yanzhang/Coding/ScriptEditor/Stock_Chart.scpt'
    }
    script_path = script_configs.get(script_type)
    if not script_path:
        display_dialog(f"未知的脚本类型: {script_type}")
        return

    try:
        if script_path.endswith('.scpt'):
            # AppleScript
            if block:
                # 阻塞等待，适用于需要等用户确认的流程
                subprocess.run(['osascript', script_path, keyword], check=False)
                if callable(on_done):
                    on_done()
            else:
                p = subprocess.Popen(['osascript', script_path, keyword])
                if callable(on_done):
                    # 不阻塞：异步场景中直接回调
                    on_done()
        else:
            # Python 脚本
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            if block:
                subprocess.run([python_path, script_path, keyword], check=False)
                if callable(on_done):
                    on_done()
            else:
                p = subprocess.Popen([python_path, script_path, keyword])
                if callable(on_done):
                    on_done()
    except Exception as e:
        display_dialog(f"启动程序失败: {e}")

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel="False"):
    app = QApplication.instance() or QApplication(sys.argv)
    plt.close('all')
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    matplotlib.rcParams['toolbar'] = 'none'

    # --- 新增修改 1: 将传入的json_data存入可变容器，并定义文件路径 ---
    # 使用字典包装，以便在内部函数中修改其内容
    current_json_data = {'data': json_data}
    DESCRIPTION_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'

    if isinstance(share, tuple):
        share_val, pb = share
        pb_text = f"{pb}" if pb not in [None, ""] else "--"
    else:
        share_val, pb_text = share, "--"

    show_volume = False
    mouse_pressed = False
    initial_price = None
    initial_date = None
    gradient_image = None
    show_global_markers = False
    show_specific_markers = True
    show_earning_markers = True
    show_all_annotations = False

    current_filtered_dates = []
    current_filtered_prices = []
    current_filtered_date_nums = []

    import time
    last_hover_ts = [0.0]
    last_rebuild_ts = [0.0]
    HOVER_THROTTLE = 1 / 90.0  # 每秒最多触发 90 次 hover
    REBUILD_THROTTLE = 0.15    # 渐变重建最小间隔 150ms
    gradient_clip_patch = [None]  # 当前剪切补丁引用

    try:
        data = fetch_data(db_path, table_name, name)
        dates, prices, volumes = process_data(data)
    except ValueError as e:
        display_dialog(f"{e}")
        return

    if not dates or not prices:
        display_dialog("没有有效的数据来绘制图表。")
        return

    smooth_dates, smooth_prices = smooth_curve(dates, prices)
    date_nums = matplotlib.dates.date2num(dates)

    fig, ax1 = plt.subplots(figsize=(16, 8))
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.83, top=0.8)
    ax2 = ax1.twinx()
    ax2.axis('off')

    fig.patch.set_facecolor(NORD_THEME['background'])
    # === 添加 Earning Release 紫色和蓝色遮罩背板 ===
    earning_release_date = find_earning_release_date(name)
    purple_shade = None  # 三周前的紫色遮罩
    blue_shade = None    # 一周前的蓝色遮罩
    
    if earning_release_date:
        # 三周前的周区间（紫色）
        week_start_3w, week_end_3w = calculate_three_weeks_before_range(earning_release_date)
        print(f"找到 {name} 的 earning release 日期: {earning_release_date}")
        print(f"三周前的周区间: {week_start_3w} 到 {week_end_3w}")
        
        purple_shade = ax1.axvspan(
            week_start_3w, 
            week_end_3w,
            facecolor=NORD_THEME['accent_purple'],
            alpha=0.15,
            zorder=0.5,
            visible=False
        )
        
        # 一周前的周区间（蓝色）
        week_start_1w, week_end_1w = calculate_one_week_before_range(earning_release_date)
        print(f"一周前的周区间: {week_start_1w} 到 {week_end_1w}")
        
        blue_shade = ax1.axvspan(
            week_start_1w,
            week_end_1w,
            facecolor=NORD_THEME['accent_blue'],
            alpha=0.15,
            zorder=0.5,
            visible=False
        )
    else:
        print(f"未找到 {name} 的 earning release 日期")

    ax1.set_facecolor(NORD_THEME['background'])
    # 只保留 X 轴：显示底部脊柱，隐藏其余脊柱
    ax1.spines['bottom'].set_visible(True)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_visible(False)

    # 隐藏 Y 轴刻度与标签（左轴）
    ax1.tick_params(axis='y', which='both', left=False, labelleft=False)

    # 保留 X 轴刻度与标签
    ax1.tick_params(axis='x', colors=NORD_THEME['text_light'])

    # 如果还想让 X 轴线更明显一些（可选）
    ax1.spines['bottom'].set_color(NORD_THEME['border'])
    ax1.spines['bottom'].set_linewidth(1.0)

    # 隐藏 ax2（成交量轴）的一切（你已有 ax2.axis('off')）
    ax2.axis('off')

    # 可选：弱化网格或仅保留纵向/横向
    ax1.grid(True, axis='y', color=NORD_THEME['border'], alpha=0.06, linestyle='--')  # 或者关闭：ax1.grid(False)
    
    highlight_point = ax1.scatter([], [], s=100, color=NORD_THEME['accent_cyan'], zorder=5)

    line1, = ax1.plot(
        smooth_dates, smooth_prices, marker='', linestyle='-', linewidth=2,
        color=NORD_THEME['accent_cyan'], alpha=0.8, label='Price', zorder=2
    )
    small_dot_scatter = ax1.scatter(dates, prices, s=5, color=NORD_THEME['text_bright'], zorder=1.5)

    line2, = ax2.plot(
        dates, volumes, marker='o', markersize=2, linestyle='-', linewidth=2,
        color=NORD_THEME['accent_purple'], alpha=0.7, label='Volume'
    )
    line2.set_visible(show_volume)

    # 新增：零值参考线（默认隐藏，由 update_plot 控制显示）
    zero_line = ax1.axhline(
        y=0,
        color=NORD_THEME['text_bright'],   # 从 border 改为更亮的颜色
        linestyle=(0, (6, 3)),             # 更明显的虚线样式（dash pattern）
        linewidth=1.8,                     # 加粗
        alpha=0.95,                        # 提高不透明度
        zorder=3,                          # 置于曲线之上更显眼
        visible=False
    )

    # --- 新增: 创建自定义的渐变色图 (Colormap) ---
    # 效果：顶部为半透明的青色(alpha=0.5)，底部为完全透明的青色(alpha=0.0)
    cyan_base_color = matplotlib.colors.to_rgb(NORD_THEME['accent_cyan'])
    cyan_transparent_cmap = LinearSegmentedColormap.from_list(
        'cyan_transparent_gradient',
        [
            (*cyan_base_color, 0.0), # 颜色位置0 (底部): 完全透明
            (*cyan_base_color, 0.5)  # 颜色位置1 (顶部): 50%透明度
        ]
    )

    # 标记点和注释
    global_markers, specific_markers, earning_markers = {}, {}, {}
    all_annotations = []
    
    try:
        with sqlite3.connect(db_path) as conn:
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
                except (ValueError, IndexError):
                    print(f"无法解析或处理收益公告日期: {date_str}")
    except sqlite3.OperationalError as e:
        print(f"获取收益数据失败: {e}")

    # 这三个列表将存储matplotlib的scatter对象，以便后续可以移除它们
    global_scatter_points, specific_scatter_points, earning_scatter_points = [], [], []

    # --- 新增修改 2: 将标记和注释的创建逻辑封装成一个函数 ---
    # 这个函数将在初始化和刷新时被调用
    def create_markers_and_annotations():
        # 清理旧的标记和注释
        for scatter, _, _, _ in global_scatter_points + specific_scatter_points:
            scatter.remove()
        for annotation, _, _, _ in all_annotations:
            annotation.remove()
        
        global_markers.clear()
        specific_markers.clear()
        global_scatter_points.clear()
        specific_scatter_points.clear()
        all_annotations.clear()

        # 重新从 current_json_data['data'] 加载 global 和 specific 标记
        if 'global' in current_json_data['data']:
            for date_str, text in current_json_data['data']['global'].items():
                try:
                    global_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                except ValueError:
                    print(f"无法解析全局标记日期: {date_str}")

        found_item = None
        for source in ['stocks', 'etfs']:
            for item in current_json_data['data'].get(source, []):
                if item['symbol'] == name and 'description3' in item:
                    found_item = item
                    for date_obj in item.get('description3', []):
                        for date_str, text in date_obj.items():
                            try:
                                specific_markers[datetime.strptime(date_str, "%Y-%m-%d")] = text
                            except ValueError:
                                print(f"无法解析特定标记日期: {date_str}")
                    break
            if found_item: break

        # 重新创建 Scatter 对象
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
        
        # 注意：Earning scatter points 不在这里重新创建，因为它们的数据源是固定的。
        # 我们只在第一次绘制时创建它们。

        # 重新创建 Annotations (包括earning的，因为all_annotations被清空了)
        red_offsets = [(-60, 30),(50, -30), (-70, 45), (-50, -35)]
        for i, (scatter, date_v, price_v, text) in enumerate(global_scatter_points):
            offset = red_offsets[i % len(red_offsets)]
            new_text = f"{text}\n{date_v.strftime('%Y-%m-%d')}"
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
            try:
                latest_price = prices[-1]
                diff_percent = ((latest_price - price_v) / price_v) * 100 if price_v else 0
                diff_line = f"{diff_percent:.2f}%"
            except Exception:
                diff_line = ""
            new_text = f"{text}\n{diff_line}\n{date_v.strftime('%Y-%m-%d')}"
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
            annotation = ax1.annotate(
                text, xy=(date_v, price_v), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_yellow'], alpha=0.8),
                arrowprops=dict(arrowstyle="->", color=NORD_THEME['accent_cyan']),
                color=NORD_THEME['accent_yellow'], fontsize=12,
                visible=show_earning_markers and show_all_annotations
            )
            all_annotations.append((annotation, 'earning', date_v, price_v))

    # 在主流程中，首次创建earning的scatter points (这部分只执行一次)
    for marker_date, text in earning_markers.items():
        if min(dates) <= marker_date <= max(dates):
            idx = (np.abs(np.array(dates) - marker_date)).argmin()
            scatter = ax1.scatter([dates[idx]], [prices[idx]], s=100, color=NORD_THEME['pure_yellow'],
                                  alpha=0.7, zorder=4, picker=5, visible=show_earning_markers)
            earning_scatter_points.append((scatter, dates[idx], prices[idx], text))

    # 首次调用创建函数
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

    # --- 新增修改 3: 将标题创建逻辑也封装成一个函数 ---
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
        # 使用 current_json_data['data']
        for source in ['stocks', 'etfs']:
            for item in current_json_data['data'].get(source, []):
                if item['symbol'] == name:
                    fullname = item.get('name', '')
                    tag_str = ','.join(item.get('tag', []))
                    if len(tag_str) > 45: tag_str = tag_str[:45] + '...'
                    clickable = True
                    break
            if clickable: break

        if table_name == 'ETFs':
            title_color = NORD_THEME['accent_orange']
            title_text = f'{name}  {compare}  {turnover_str} "{table_name}" {fullname} {tag_str}'
        else:
            title_color = get_title_color_logic(db_path, name, table_name)
            title_text = f'{name}  {compare}  {turnover_str} {turnover_rate} {marketcap_in_billion} {pe_text} {pb_text} "{table_name}" {fullname} {tag_str}'
        
        return title_text, title_color, clickable

    # 首次创建标题，并保存对标题对象的引用
    initial_title_text, initial_title_color, clickable = create_or_update_title()
    title_artist = fig.text(0.5, 0.95, initial_title_text, ha='center', va='top', color=initial_title_color,
                            fontsize=16, fontweight='bold', transform=fig.transFigure, picker=False)

    def show_stock_etf_info(event=None):
        # 使用 current_json_data['data']
        for source in ['stocks', 'etfs']:
            for item in current_json_data['data'].get(source, []):
                if item['symbol'] == name:
                    info = f"{name}\n{item['name']}\n\n{item['tag']}\n\n{item['description1']}\n\n{item['description2']}"
                    dialog = InfoDialog("Information", info, 'Arial Unicode MS', 22, 700, 900)
                    dialog.exec_()
                    return
        display_dialog(f"未找到 {name} 的信息")

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
        except Exception as e:
            # 防护
            # print(f"pick error: {e}")
            pass

    def create_window_qt(content):
        dialog = InfoDialog("数据库查询结果", content, "Courier", 14, 900, 600)
        dialog.exec_()

    def query_database(db_path, table_name, condition):
        with sqlite3.connect(db_path) as conn:
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

    # --- 修改 #1: 在这里为 bbox 添加默认的边框颜色 ec ---
    annot = ax1.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
        bbox=dict(boxstyle="round", fc=NORD_THEME['widget_bg'], ec=NORD_THEME['accent_cyan']),
        arrowprops=dict(arrowstyle="->"), color=NORD_THEME['text_bright'], visible=False)

    time_options = {"1m":0.08, "3m":0.25, "6m":0.5, "1Y":1, "2Y":2, "3Y":3, "5Y":5, "10Y":10, "All":0}
    default_index = list(time_options.keys()).index(default_time_range)

    rax = plt.axes([0.95, 0.0, 0.05, 0.65], facecolor=NORD_THEME['background'])
    radio = RadioButtons(rax, list(time_options.keys()), active=default_index)
    rax.set_facecolor(NORD_THEME['background'])
    rax.set_frame_on(False)
    for spine in rax.spines.values():
        spine.set_visible(False)
    for label in radio.labels:
        label.set_color(NORD_THEME['text_light'])
        label.set_fontsize(14)
    for circle in radio.circles:
        circle.set_edgecolor(NORD_THEME['border'])
        circle.set_facecolor(NORD_THEME['background'])
    radio.circles[default_index].set_facecolor(NORD_THEME['accent_red'])

    instructions = "N:新财报\nE:改财报\nT:改标签\nW:新事件\nQ:改事件\nK:查豆包\nZ:查富途\nP:做比较\nJ:加Panel\nH:加empty\nL:查相似\nY:删除\nG:刷新\nO:查α" # 新增 G
    rax.text(0.5, 0.98, instructions, transform=rax.transAxes, ha="center", va="bottom",
             color=NORD_THEME['text_light'], fontsize=10, fontfamily="Arial Unicode MS")
    
    # --- 优化：缓存查找结果，减少重复计算 ---
    @lru_cache(maxsize=1000)
    def find_closest_index(target_date_num):
        return np.argmin(np.abs(date_nums - target_date_num))

    def update_annot(ind):
        try:
            x_data, y_data = line1.get_data()
            xval, yval = x_data[ind["ind"][0]], y_data[ind["ind"][0]]

            if annot.xy != (xval, yval):
                annot.xy = (xval, yval)

                current_date = xval.replace(tzinfo=None)
                g_text, s_text, e_text = None, None, None

                for d, t in global_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400:
                        g_text = t; break
                for d, t in specific_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400:
                        s_text = t; break
                for d, t in earning_markers.items():
                    if abs((d - current_date).total_seconds()) < 86400:
                        e_text = t; break

                # 先构造文本和颜色
                if mouse_pressed and initial_price is not None:
                    percent_change = ((yval - initial_price) / initial_price) * 100
                    text = f"{percent_change:.1f}%"
                    color = NORD_THEME['accent_cyan']
                    annot.get_bbox_patch().set_edgecolor(color)
                else:
                    parts = [f"{datetime.strftime(xval, '%Y-%m-%d')}", f"{yval:.2f}", ""]
                    marker_texts = []
                    if g_text: marker_texts.append(g_text)
                    if s_text: marker_texts.append(s_text + "\n")

                    has_earning = False
                    if e_text:
                        for line in e_text.split('\n'):
                            if "昨日财报" in line:
                                marker_texts.append(line); break
                        has_earning = True

                    if marker_texts: parts.extend(marker_texts)
                    parts.append(f"最新价差: {((prices[-1] - yval) / yval) * 100:.2f}%")
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

                # 决定偏移后再设置位置
                y_range = ax1.get_ylim()
                y_ratio = (yval - y_range[0]) / (y_range[1] - y_range[0] + 1e-12)
                x_range = ax1.get_xlim()
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
        except Exception as e:
            # 避免更新异常卡死
            # print(f"update_annot error: {e}")
            pass

    def hover(event):
        try:
            now = time.time()
            if now - last_hover_ts[0] < HOVER_THROTTLE:
                return
            last_hover_ts[0] = now

            if event.inaxes in [ax1, ax2] and event.xdata and current_filtered_dates:
                vline.set_xdata([event.xdata, event.xdata])
                vline.set_visible(True)

                # 拖拽中降级：不更新注释内容，仅移动高亮
                if mouse_pressed:
                    idx = np.argmin(np.abs(current_filtered_date_nums - event.xdata)) if len(current_filtered_date_nums) else 0
                    x_data, y_data = line1.get_data()
                    if idx < len(x_data) and idx < len(y_data) and initial_price is not None:
                        sel_date, sel_price = x_data[idx], y_data[idx]

                        # 计算与按下点的百分比变化
                        try:
                            percent_change = ((sel_price - initial_price) / (initial_price + 1e-12)) * 100.0
                        except Exception:
                            percent_change = 0.0

                        # 轻量注释：只显示百分比，避免昂贵排版
                        annot.xy = (sel_date, sel_price)
                        annot.set_text(f"{percent_change:.1f}%")
                        drag_color = NORD_THEME['accent_red'] if percent_change > 0 else NORD_THEME['accent_green']
                        annot.set_color(drag_color)
                        annot.get_bbox_patch().set_edgecolor(drag_color)
                        annot.get_bbox_patch().set_alpha(0.8)
                        annot.set_fontsize(16)
                        y_range, x_range = ax1.get_ylim(), ax1.get_xlim()
                        y_ratio = (sel_price - y_range[0]) / (y_range[1] - y_range[0] + 1e-12)
                        x_ratio = (matplotlib.dates.date2num(sel_date) - x_range[0]) / (x_range[1] - x_range[0] + 1e-12)
                        y_offset = 60 if y_ratio < 0.2 else -120 if y_ratio > 0.8 else -70
                        x_offset = -120 if x_ratio > 0.7 else 50 if x_ratio < 0.3 else -100
                        annot.set_position((x_offset, y_offset))
                        annot.set_visible(True)

                        # 高亮点跟随
                        highlight_point.set_offsets([[sel_date, sel_price]])
                        highlight_point.set_visible(True)

                    fig.canvas.draw_idle()
                    return

                # 正常 hover
                idx = np.argmin(np.abs(current_filtered_date_nums - event.xdata)) if len(current_filtered_date_nums) else 0
                x_data, y_data = line1.get_data()
                if idx < len(x_data) and idx < len(y_data):
                    sel_date, sel_price = x_data[idx], y_data[idx]

                    color = NORD_THEME['accent_cyan']
                    for _, d, _, _ in global_scatter_points:
                        if d == sel_date:
                            color = NORD_THEME['accent_red']; break
                    else:
                        for _, d, _, _ in specific_scatter_points:
                            if d == sel_date:
                                color = NORD_THEME['text_bright']; break
                        else:
                            for _, d, _, _ in earning_scatter_points:
                                if d == sel_date:
                                    color = NORD_THEME['accent_yellow']; break
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
        except Exception as e:
            # print(f"hover error: {e}")
            pass

    def update(val):
        nonlocal gradient_image, current_filtered_dates, current_filtered_prices, current_filtered_date_nums
        try:
            years = time_options[val]
            if years == 0:
                f_dates, f_prices, f_volumes = dates, prices, volumes
            else:
                min_date = datetime.now() - timedelta(days=years * 365)
                indices = [i for i, d in enumerate(dates) if d >= min_date]
                if not indices:
                    f_dates, f_prices = [dates[-1]], [prices[-1]]
                    f_volumes = [volumes[-1]] if volumes else None
                else:
                    f_dates = [dates[i] for i in indices]
                    f_prices = [prices[i] for i in indices]
                    f_volumes = [volumes[i] for i in indices] if volumes else None

            # 更新当前筛选数据与缓存
            current_filtered_dates = f_dates
            current_filtered_prices = f_prices
            current_filtered_date_nums = matplotlib.dates.date2num(current_filtered_dates) if current_filtered_dates else np.array([])

            # === 修改：控制紫色和蓝色遮罩的显示 ===
            if earning_release_date and f_dates:
                display_start = min(f_dates).date() if isinstance(min(f_dates), datetime) else min(f_dates)
                display_end = max(f_dates).date() if isinstance(max(f_dates), datetime) else max(f_dates)
                
                # 控制紫色遮罩（三周前）
                if purple_shade:
                    week_start_3w, week_end_3w = calculate_three_weeks_before_range(earning_release_date)
                    has_overlap_3w = not (week_end_3w < display_start or week_start_3w > display_end)
                    purple_shade.set_visible(has_overlap_3w)
                
                # 控制蓝色遮罩（一周前）
                if blue_shade:
                    week_start_1w, week_end_1w = calculate_one_week_before_range(earning_release_date)
                    has_overlap_1w = not (week_end_1w < display_start or week_start_1w > display_end)
                    blue_shade.set_visible(has_overlap_1w)
            else:
                if purple_shade:
                    purple_shade.set_visible(False)
                if blue_shade:
                    blue_shade.set_visible(False)

            # 渐变重建节流
            now = time.time()
            force_flag = False
            if (now - last_rebuild_ts[0]) > REBUILD_THROTTLE:
                force_flag = True
                last_rebuild_ts[0] = now

            gradient_image = update_plot(
                line1, gradient_image, line2,
                f_dates, f_prices, f_volumes,
                ax1, ax2, show_volume,
                cyan_transparent_cmap,
                force_recreate=force_flag,
                gradient_clip_patch=gradient_clip_patch,
                zero_line=zero_line
            )

            for i, circle in enumerate(radio.circles):
                circle.set_facecolor(NORD_THEME['accent_red'] if list(time_options.keys())[i] == val else NORD_THEME['background'])

            small_dot_scatter.set_visible(val in ["1m", "3m", "6m"])
            update_marker_visibility()
            fig.canvas.draw_idle()
        except Exception as e:
            # print(f"update error: {e}")
            pass

    def toggle_volume():
        nonlocal show_volume, current_filtered_dates, current_filtered_prices, current_filtered_date_nums
        try:
            show_volume = not show_volume
            years = time_options[radio.value_selected]
            if years == 0:
                f_dates, f_prices, f_volumes = dates, prices, volumes
            else:
                min_date = datetime.now() - timedelta(days=years * 365)
                indices = [i for i, d in enumerate(dates) if d >= min_date]
                f_dates = [dates[i] for i in indices] if indices else [dates[-1]]
                f_prices = [prices[i] for i in indices] if indices else [prices[-1]]
                f_volumes = [volumes[i] for i in indices] if volumes and indices else ([volumes[-1]] if volumes else None)

            current_filtered_dates = f_dates
            current_filtered_prices = f_prices
            current_filtered_date_nums = matplotlib.dates.date2num(current_filtered_dates) if current_filtered_dates else np.array([])

            update_plot(
                line1, gradient_image, line2,
                f_dates, f_prices, f_volumes,
                ax1, ax2, show_volume,
                cyan_transparent_cmap,
                force_recreate=False,
                gradient_clip_patch=gradient_clip_patch,
                zero_line=zero_line
            )
            fig.canvas.draw_idle()
        except Exception as e:
            # print(f"toggle_volume error: {e}")
            pass

    def launch_and_close_for_y():
        # 定义确认后的收尾逻辑：关闭所有图形并退出（结束功能）
        def on_done():
            try: plt.close('all')
            except: pass
            try:
                if panel: sys.exit(0)
            except: pass
        execute_external_script('panel_delete', name, on_done=on_done, block=True)
    
    # --- 新增修改 4: 创建刷新函数，并将其绑定到 'g' 键 ---
    def refresh_description_data_and_redraw():
        """
        重新加载 description.json 文件并更新图表的相关部分。
        """
        nonlocal title_artist, clickable
        print("正在重新加载 description.json...")
        try:
            with open(DESCRIPTION_JSON_PATH, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            current_json_data['data'] = new_data
            print("description.json 加载成功。正在刷新图表...")

            # 1. 更新标题
            new_title_text, new_title_color, clickable = create_or_update_title()
            title_artist.set_text(new_title_text)
            # 标题颜色逻辑与description无关，所以不用更新颜色
            
            # 2. 重新创建标记和注释
            create_markers_and_annotations()

            # 3. 更新标记的可见性以匹配当前的时间范围
            update_marker_visibility()
            
            # 4. 重绘画布
            fig.canvas.draw_idle()
            print("图表刷新完成。")

        except FileNotFoundError:
            print(f"错误: 未找到文件 {DESCRIPTION_JSON_PATH}")
            display_dialog(f"错误: 未找到文件\n{DESCRIPTION_JSON_PATH}")
        except json.JSONDecodeError as e:
            print(f"错误: 解析JSON文件失败: {e}")
            display_dialog(f"错误: 解析JSON文件失败\n{e}")
        except Exception as e:
            print(f"刷新时发生未知错误: {e}")
            display_dialog(f"刷新时发生未知错误:\n{e}")

    def on_key(event):
        try:
            actions = {'v': toggle_volume, 'r': toggle_global_markers, 'x': toggle_all_annotations,
                       'a': toggle_earning_markers, 'c': toggle_specific_markers,
                       'g': refresh_description_data_and_redraw, # 新增 'g' 快捷键
                       'n': lambda: execute_external_script('earning_input', name),
                       'e': lambda: execute_external_script('earning_edit', name),
                       't': lambda: execute_external_script('tags_edit', name),
                       'w': lambda: execute_external_script('event_input', name),
                       'j': lambda: execute_external_script('panel_input', name),
                       'y': launch_and_close_for_y,
                       'h': lambda: execute_external_script('empty_input', name),
                       'q': lambda: execute_external_script('event_edit', name),
                       'k': lambda: execute_external_script('check_kimi', name),
                       'z': lambda: execute_external_script('check_futu', name),
                       'o': lambda: execute_external_script('check_seekingalpha', name),
                       'p': lambda: execute_external_script('symbol_compare', name),
                       'l': lambda: execute_external_script('similar_tags', name),
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
        except Exception as e:
            # print(f"on_key error: {e}")
            pass

    def close_everything(event, panel_flag):
        if event.key == 'escape':
            plt.close('all')
            if panel_flag: sys.exit(0)

    def on_mouse_press(event):
        nonlocal mouse_pressed, initial_price, initial_date
        try:
            if event.button == 1 and event.xdata is not None and current_filtered_dates:
                mouse_pressed = True
                idx = np.argmin(np.abs(current_filtered_date_nums - event.xdata)) if len(current_filtered_date_nums) else 0
                if idx < len(current_filtered_prices):
                    initial_price, initial_date = current_filtered_prices[idx], current_filtered_dates[idx]
        except Exception as e:
            # print(f"mouse_press error: {e}")
            pass

    def on_mouse_release(event):
        nonlocal mouse_pressed
        try:
            if event.button == 1:
                mouse_pressed = False
        except Exception:
            pass

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
        except Exception:
            pass
    plt.gcf().canvas.mpl_connect('figure_leave_event', hide_annot_on_leave)

    # 首次更新，建立初始筛选与渐变
    update(default_time_range)

    print("图表绘制完成，等待用户操作...")
    # Matplotlib 3.8+ 支持
    try:
        fig.canvas.toolbar_visible = False
    except Exception:
        pass
    plt.show()