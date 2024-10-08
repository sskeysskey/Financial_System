import re
import sqlite3
import subprocess
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
import tkinter as tk
from tkinter import simpledialog, scrolledtext, font as tkFont
from functools import lru_cache
from scipy.interpolate import interp1d

@lru_cache(maxsize=None)
def fetch_data(db_path, table_name, name):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
            # 为查询字段添加索引
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_name ON {table_name} (name);")
            query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? ORDER BY date;"
            result = cursor.execute(query, (name,)).fetchall()
            if not result:
                raise ValueError("没有查询到可用数据")
            return result
        except sqlite3.OperationalError:
            query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
            result = cursor.execute(query, (name,)).fetchall()
            if not result:
                raise ValueError("没有查询到可用数据")
            return result

def smooth_curve(dates, prices, num_points=500):
    """
    通过插值生成更多的点来让曲线更平滑。
    如果数据点少于四个，使用线性插值；否则使用三次插值。
    :param dates: 原始日期数据
    :param prices: 原始价格数据
    :param num_points: 插值生成的点数，默认值为500
    """
    # 将日期转化为数值
    date_nums = matplotlib.dates.date2num(dates)

    # 如果数据点不足四个，使用线性插值；否则使用三次插值
    if len(dates) < 4:
        interp_func = interp1d(date_nums, prices, kind='linear')
    else:
        interp_func = interp1d(date_nums, prices, kind='cubic')

    # 生成更多的日期点
    new_date_nums = np.linspace(min(date_nums), max(date_nums), num_points)

    # 计算插值后的价格
    new_prices = interp_func(new_date_nums)

    # 将数值转化回日期
    new_dates = matplotlib.dates.num2date(new_date_nums)

    return new_dates, new_prices

def process_data(data):
    if not data:
        raise ValueError("没有可供处理的数据")
        
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
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

def draw_underline(text_obj, fig, ax1):
    x, y = text_obj.get_position()
    text_renderer = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
    linewidth = text_renderer.width
    line = matplotlib.lines.Line2D([x, x + linewidth], [y - 2, y - 2], transform=ax1.transData, color='blue', linewidth=2)
    ax1.add_line(line)

def update_plot(line1, fill, line2, dates, prices, volumes, ax1, ax2, show_volume):
    line1.set_data(dates, prices)
    fill.remove()
    fill = ax1.fill_between(dates, prices, color='lightblue', alpha=0.3)
    if volumes:
        line2.set_data(dates, volumes)
    ax1.set_xlim(np.min(dates), np.max(dates))
    ax1.set_ylim(np.min(prices), np.max(prices))
    if show_volume and volumes:
        ax2.set_ylim(0, np.max(volumes))
    line2.set_visible(show_volume)
    plt.draw()
    return fill

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data, default_time_range="1Y", panel="False"):
    plt.close('all')  # 关闭所有图表

    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    show_volume = False
    mouse_pressed = False
    initial_price = None
    initial_date = None
    fill = None  # 添加这行

    try:
        data = fetch_data(db_path, table_name, name)
    except ValueError as e:
        display_dialog(f"{e}")
        return

    try:
        dates, prices, volumes = process_data(data)
    except ValueError as e:
        display_dialog(f"{e}")
        return

    if not dates or not prices:
        display_dialog("没有有效的数据来绘制图表。")
        return

    # 使用插值函数生成更多的平滑数据点
    smooth_dates, smooth_prices = smooth_curve(dates, prices)

    fig, ax1 = plt.subplots(figsize=(13, 6))
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.91, top=0.9)
    ax2 = ax1.twinx()

    fig.patch.set_facecolor('black')
    ax1.set_facecolor('black')
    
    ax1.tick_params(axis='x', colors='white')
    ax1.tick_params(axis='y', colors='white')
    ax2.tick_params(axis='y', colors='white')

    highlight_point = ax1.scatter([], [], s=100, color='red', zorder=5)
    
    # 绘制插值后的平滑曲线
    line1, = ax1.plot(smooth_dates, smooth_prices, marker='', linestyle='-', linewidth=2, color='cyan', alpha=0.7, label='Price')
    line2, = ax2.plot(dates, volumes, marker='o', markersize=2, linestyle='-', linewidth=2, color='magenta', alpha=0.7, label='Volume')
    fill = ax1.fill_between(dates, prices, color='cyan', alpha=0.2)
    line2.set_visible(show_volume)

    def clean_percentage_string(percentage_str):
        try:
            return float(percentage_str.strip('%'))
        except ValueError:
            return None

    turnover = (volumes[-1] * prices[-1]) / 1e6 if volumes and volumes[-1] is not None and prices[-1] is not None else None
    turnover_str = f"{turnover:.1f}" if turnover is not None else ""
    
    # 过滤掉compare中的所有中文字符和+，也能执行，就是怪异，备份用
    filtered_compare = re.sub(r'[\u4e00-\u9fff+]', '', compare)

    # 过滤掉compare中的所有中文及中文之前的符号，然后再过滤加号+
    # filtered_compare = re.sub(r'^.*[\u4e00-\u9fff]', '', compare)
    # filtered_compare = re.sub(r'\+', '', filtered_compare)
    compare_value = clean_percentage_string(filtered_compare)
    if turnover is not None and turnover < 100 and compare_value is not None and compare_value > 0:
        turnover_str = f"可疑{turnover_str}"

    turnover_rate = f"{(volumes[-1] / int(share))*100:.2f}" if volumes and volumes[-1] is not None and share is not None and share != "N/A" else ""
    marketcap_in_billion = f"{float(marketcap) / 1e9:.1f}B" if marketcap is not None else ""
    pe_text = f"{pe}" if pe is not None and pe != "N/A" else ""

    clickable = False
    tag_str = ""
    fullname = ""
    data_sources = ['stocks', 'etfs']
    found = False

    for source in data_sources:
        for item in json_data.get(source, []):
            if item['symbol'] == name:
                tags = item.get('tag', [])
                fullname = item.get('name', '')
                tag_str = ','.join(tags)
                if len(tag_str) > 25:
                    tag_str = tag_str[:25] + '...'  # 限制tag_str长度为15字符，超出部分用...表示
                clickable = True
                found = True
                break
        if found:
            break
    
    title_text = f'{name}  {compare}  {turnover_str}M/{turnover_rate} {marketcap_in_billion} {pe_text}"{table_name}" {fullname} {tag_str}'
    title_style = {'color': 'orange' if clickable else 'lightgray', 'fontsize': 16 if clickable else 15, 'fontweight': 'bold', 'picker': clickable}
    title = ax1.set_title(title_text, **title_style)

    def show_stock_etf_info(event=None):
        for source in data_sources:
            for item in json_data.get(source, []):
                if item['symbol'] == name:
                    descriptions = item
                    root = tk.Tk()
                    root.withdraw()  # 隐藏主窗口
                    top = tk.Toplevel(root)
                    top.title("Information")
                    top.geometry("600x750")
                    font_size = ('Arial', 22)
                    text_box = scrolledtext.ScrolledText(top, wrap=tk.WORD, font=font_size)
                    text_box.pack(expand=True, fill='both')
                    info = f"{name}\n{descriptions['name']}\n\n{descriptions['tag']}\n\n{descriptions['description1']}\n\n{descriptions['description2']}"
                    text_box.insert(tk.END, info)
                    text_box.config(state=tk.DISABLED)
                    top.bind('<Escape>', lambda event: root.destroy())
                    root.mainloop()
                    return
        display_dialog(f"未找到 {name} 的信息")

    def on_pick(event):
        if event.artist == title:  # 只有当点击的是标题时才执行
            show_stock_etf_info()

    def on_keyword_selected(db_path, table_name, name):
        condition = f"name = '{name}'"
        result = query_database(db_path, table_name, condition)
        create_window(result)
            
    def query_database(db_path, table_name, condition):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
            cursor.execute(query)
            rows = cursor.fetchall()
            if not rows:
                return "今天没有数据可显示。\n"
            columns = [description[0] for description in cursor.description]
            col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]
            output_text = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
            output_text += '-' * len(output_text) + '\n'
            for row in rows:
                output_text += ' | '.join([str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)]) + '\n'
            return output_text
            
    def create_window(content):
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        top = tk.Toplevel(root)
        top.title("数据库查询结果")
        window_width, window_height = 900, 600
        center_x = (top.winfo_screenwidth() - window_width) // 2
        center_y = (top.winfo_screenheight() - window_height) // 2
        top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        top.bind('<Escape>', lambda event: root.destroy())

        text_font = tkFont.Font(family="Courier", size=20)
        text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
        text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        text_area.insert(tk.INSERT, content)
        text_area.configure(state='disabled')        
        root.mainloop()
    
    if clickable:
        draw_underline(title, fig, ax1)
        fig.canvas.mpl_connect('pick_event', on_pick)

    # ax1.grid(False)
    ax1.grid(True, color='gray', alpha=0.1, linestyle='--')

    plt.xticks(rotation=45)

    annot = ax1.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points", bbox=dict(boxstyle="round", fc="black"), arrowprops=dict(arrowstyle="->"), color='white')
    annot.set_visible(False)

    time_options = {"1m": 0.08, "3m": 0.25, "6m": 0.5, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "10Y": 10, "All": 0}
    default_index = list(time_options.keys()).index(default_time_range)

    rax = plt.axes([0.95, 0.005, 0.05, 0.8], facecolor='black')
    radio = RadioButtons(rax, list(time_options.keys()), active=default_index)
        
    for label in radio.labels:
        label.set_color('white')
        label.set_fontsize(14)

    radio.circles[default_index].set_facecolor('red')

    def update_annot(ind):
        x, y = line1.get_data()
        xval, yval = x[ind["ind"][0]], y[ind["ind"][0]]
        annot.xy = (xval, yval)
        text = f"{((yval - initial_price) / initial_price) * 100:.1f}%" if mouse_pressed and initial_price is not None else f"{datetime.strftime(xval, '%Y-%m-%d')}\n{yval}"
        annot.set_text(text)
        annot.get_bbox_patch().set_alpha(0.4)
        annot.set_fontsize(16)
        annot.set_position((50, -20) if xval < (max(x) - (max(x) - min(x)) / 2) else (-130, -20))

    def hover(event):
        if event.inaxes in [ax1, ax2]:
            if event.xdata:
                current_date = matplotlib.dates.num2date(event.xdata).replace(tzinfo=None)
                vline.set_xdata(current_date)
                vline.set_visible(True)
                fig.canvas.draw_idle()
                xdata, ydata = line1.get_data()
                nearest_index = (np.abs(np.array(xdata) - current_date)).argmin()
                if np.isclose(matplotlib.dates.date2num(xdata[nearest_index]), matplotlib.dates.date2num(current_date), atol=0.05 * ((ax1.get_xlim()[1] - ax1.get_xlim()[0]) / 365)):
                    update_annot({"ind": [nearest_index]})
                    annot.set_visible(True)
                    highlight_point.set_offsets([xdata[nearest_index], ydata[nearest_index]])
                    highlight_point.set_visible(True)
                else:
                    annot.set_visible(False)
                    highlight_point.set_visible(False)
                fig.canvas.draw_idle()
            else:
                vline.set_visible(False)
                annot.set_visible(False)
                highlight_point.set_visible(False)
                fig.canvas.draw_idle()
        elif event.inaxes == rax:
            vline.set_visible(False)
            annot.set_visible(False)
            highlight_point.set_visible(False)
            fig.canvas.draw_idle()

    def update(val):
        years = time_options[val]
        if years == 0:
            filtered_dates, filtered_prices, filtered_volumes = dates, prices, volumes
        else:
            min_date = datetime.now() - timedelta(days=years * 365)
            filtered_dates = [date for date in dates if date >= min_date]
            filtered_prices = [price for date, price in zip(dates, prices) if date >= min_date]
            filtered_volumes = [volume for date, volume in zip(dates, volumes) if date >= min_date] if volumes else None
        nonlocal fill
        fill = update_plot(line1, fill, line2, filtered_dates, filtered_prices, filtered_volumes, ax1, ax2, show_volume)

        radio.circles[list(time_options.keys()).index(val)].set_facecolor('red')

    def on_key(event):
        actions = {
            'v': toggle_volume,
            '1': lambda: radio.set_active(7),
            '2': lambda: radio.set_active(1),
            '3': lambda: radio.set_active(3),
            '4': lambda: radio.set_active(4),
            '5': lambda: radio.set_active(5),
            '6': lambda: radio.set_active(6),
            '7': lambda: radio.set_active(8),
            '8': lambda: radio.set_active(2),
            '9': lambda: radio.set_active(0),
            '`': show_stock_etf_info,
            'd': lambda: on_keyword_selected(db_path, table_name, name)  # 添加快捷键'D'的功能
        }
        if event.key in actions:
            actions[event.key]()

        # 获取当前选中的索引
        current_index = list(time_options.keys()).index(radio.value_selected)

        # 处理方向键
        if event.key == 'up' and current_index > 0:
            # 上键：向更长时间范围移动，但不超过3个月
            radio.set_active(current_index - 1)
        elif event.key == 'down' and current_index < len(time_options) - 1:
            # 下键：向更短时间范围移动，但不超过All
            radio.set_active(current_index + 1)

    def close_everything(event, panel):
        if event.key == 'escape':
            plt.close('all')
            if panel:
                import sys
                sys.exit(0)

    def toggle_volume():
        nonlocal show_volume
        show_volume = not show_volume
        update(radio.value_selected)

    def on_mouse_press(event):
        nonlocal mouse_pressed, initial_price, initial_date
        if event.button == 1:
            mouse_pressed = True
            nearest_index = (np.abs(np.array(dates) - matplotlib.dates.num2date(event.xdata).replace(tzinfo=None))).argmin()
            initial_price = prices[nearest_index]
            initial_date = dates[nearest_index]

    def on_mouse_release(event):
        nonlocal mouse_pressed
        if event.button == 1:
            mouse_pressed = False

    plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
    plt.gcf().canvas.mpl_connect('key_press_event', on_key)
    plt.gcf().canvas.mpl_connect('key_press_event', lambda event: close_everything(event, panel))
    plt.gcf().canvas.mpl_connect('button_press_event', on_mouse_press)
    plt.gcf().canvas.mpl_connect('button_release_event', on_mouse_release)

    # vline = ax1.axvline(x=dates[0], color='b', linestyle='--', linewidth=1, visible=False)
    vline = ax1.axvline(x=dates[0], color='red', linestyle='--', linewidth=1, visible=False)
    update(default_time_range)
    radio.on_clicked(update)

    def hide_annot_on_leave(event):
        annot.set_visible(False)
        highlight_point.set_visible(False)
        vline.set_visible(False)
        fig.canvas.draw_idle()

    plt.gcf().canvas.mpl_connect('figure_leave_event', hide_annot_on_leave)

    print("图表绘制完成，等待用户操作...")
    plt.show()