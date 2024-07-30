import re
import sqlite3
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
import tkinter as tk
from tkinter import simpledialog, scrolledtext, messagebox
from functools import lru_cache

@lru_cache(maxsize=None)
def fetch_data(db_path, table_name, name):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
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

def show_error_message(message):
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    messagebox.showerror("错误", message)
    root.destroy()

def draw_underline(text_obj, fig, ax1):
    x, y = text_obj.get_position()
    text_renderer = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
    linewidth = text_renderer.width
    line = matplotlib.lines.Line2D([x, x + linewidth], [y - 2, y - 2], transform=ax1.transData, color='blue', linewidth=2)
    ax1.add_line(line)

def update_plot(line1, line2, dates, prices, volumes, ax1, ax2, show_volume):
    line1.set_data(dates, prices)
    if volumes:
        line2.set_data(dates, volumes)
    ax1.set_xlim(np.min(dates), np.max(dates))
    ax1.set_ylim(np.min(prices), np.max(prices))
    if show_volume and volumes:
        ax2.set_ylim(0, np.max(volumes))
    line2.set_visible(show_volume)
    plt.draw()

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data, default_time_range="1Y", panel="False"):
    plt.close('all')  # 关闭所有图表

    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    show_volume = False
    mouse_pressed = False
    initial_price = None
    initial_date = None

    try:
        data = fetch_data(db_path, table_name, name)
    except ValueError as e:
        show_error_message(f"{e}")
        return

    try:
        dates, prices, volumes = process_data(data)
    except ValueError as e:
        show_error_message(f"{e}")
        return

    if not dates or not prices:
        show_error_message("没有有效的数据来绘制图表。")
        return

    fig, ax1 = plt.subplots(figsize=(13, 6))
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.91, top=0.9)
    ax2 = ax1.twinx()

    fig.patch.set_facecolor('black')
    ax1.set_facecolor('black')
    

    ax1.tick_params(axis='x', colors='white')
    ax1.tick_params(axis='y', colors='white')
    ax2.tick_params(axis='y', colors='white')
    
    # ax2.spines['bottom'].set_color('white')
    # ax2.spines['top'].set_color('white') 
    # ax2.spines['right'].set_color('white')
    # ax2.spines['left'].set_color('white')

    highlight_point = ax1.scatter([], [], s=100, color='red', zorder=5)
    # line1, = ax1.plot(dates, prices, marker='o', markersize=1, linestyle='-', linewidth=2, color='b', picker=5, label='Price')
    line1, = ax1.plot(dates, prices, marker='o', markersize=1, linestyle='-', linewidth=1, color='gold', picker=5, label='Price')
    line2, = ax2.plot(dates, volumes, marker='o', markersize=1, linestyle='-', linewidth=1, color='r', picker=5, label='Volume')
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
        show_error_message(f"未找到 {name} 的信息")

    def on_pick(event):
        if event.artist == title:  # 只有当点击的是标题时才执行
            show_stock_etf_info()
        
    if clickable:
        draw_underline(title, fig, ax1)
        fig.canvas.mpl_connect('pick_event', on_pick)

    # ax1.grid(True)
    ax1.grid(True, color='white', alpha=0.2)
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
        update_plot(line1, line2, filtered_dates, filtered_prices, filtered_volumes, ax1, ax2, show_volume)

        radio.circles[list(time_options.keys()).index(val)].set_facecolor('red')

    def on_key(event):
        actions = {
            'v': toggle_volume,
            '1': lambda: radio.set_active(7),
            '2': lambda: radio.set_active(1),
            '3': lambda: radio.set_active(2),
            '4': lambda: radio.set_active(3),
            '5': lambda: radio.set_active(4),
            '6': lambda: radio.set_active(5),
            '7': lambda: radio.set_active(6),
            '8': lambda: radio.set_active(0),
            '9': lambda: radio.set_active(8),
            '`': show_stock_etf_info
        }
        action = actions.get(event.key)
        if action:
            action()

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