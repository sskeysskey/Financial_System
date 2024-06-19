import sqlite3
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
import json
import tkinter as tk
from tkinter import simpledialog, scrolledtext

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data, default_time_range="1Y"):
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']

    # 初始化 show_volume 状态
    show_volume = False
    # 初始化鼠标按下状态和初始价格点
    mouse_pressed = False
    initial_price = None
    initial_date = None

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            try:
                query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? ORDER BY date;"
                cursor.execute(query, (name,))
            except sqlite3.OperationalError as e:
                if 'no such column: volume' in str(e):
                    print("警告: 数据库表中不存在'volume'列，将不显示成交量信息。")
                    # 当 volume 列不存在时，只查询 date 和 price
                    query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
                    cursor.execute(query, (name,))
                else:
                    raise
            data = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"数据库错误: {e}")
        return

    dates = []
    prices = []
    volumes = []  # 用于存储 volume 数据
    for row in data:
        date = datetime.strptime(row[0], "%Y-%m-%d")
        price = float(row[1]) if row[1] is not None else None
        volume = int(row[2]) if len(row) > 2 and row[2] is not None else None
        if price is not None:
            dates.append(date)
            prices.append(price)
            volumes.append(volume)  # 添加 volume 数据

    if not dates or not prices:
        print("没有有效的数据来绘制图表。")
        return

    fig, ax1 = plt.subplots(figsize=(13, 6)) # 调整整个窗口大小，前面是X，后面是Y
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.91, top=0.9)  # 根据图标窗口距离上下左右的距离

    ax2 = ax1.twinx()  # 创建双 y 轴
    
    highlight_point = ax1.scatter([], [], s=100, color='blue', zorder=5)  # s是点的大小

    line1, = ax1.plot(dates, prices, marker='o', markersize=1, linestyle='-', linewidth=2, color='b', picker=5, label='Price')
    line2, = ax2.plot(dates, volumes, marker='o', markersize=1, linestyle='-', linewidth=2, color='r', picker=5, label='Volume')

    # 隐藏 volume 曲线
    line2.set_visible(show_volume)

    if volume is not None and price is not None:
        turnover = f"{(volume * float(price)) / 1000000:.1f}"
    else:
        turnover = "N/A"

    if volume is not None and share is not None and share != "N/A":
        turnover_rate = f"{(volume / int(share))*100:.2f}"
    else:
        turnover_rate = "N/A"

    marketcap_in_billion = f"{float(marketcap) / 1e9:.1f}B" if marketcap is not None else "N/A"
    pe_text = f"{pe}" if pe is not None else "N/A"

    def show_stock_info(symbol, descriptions):
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        
        # 创建一个新的顶级窗口
        top = tk.Toplevel(root)
        top.title("Stock Information")
        
        # 设置窗口尺寸
        top.geometry("600x750")
        
        # 设置字体大小
        font_size = ('Arial', 22)
        
        # 创建一个滚动文本框
        text_box = scrolledtext.ScrolledText(top, wrap=tk.WORD, font=font_size)
        text_box.pack(expand=True, fill='both')
        
        # 插入股票信息
        info = f"{symbol}:{descriptions['description1']}\n\n{descriptions['description2']}"
        text_box.insert(tk.END, info)
        
        # 设置文本框为只读
        text_box.config(state=tk.DISABLED)
        
        top.bind('<Escape>', lambda event: root.destroy())
        root.mainloop()

    # 添加 pick 事件处理器，仅在 clickable 为 True 时激活
    def on_pick(event):
        if event.artist == title and clickable:
            stock_name = name
            for stock in json_data['stocks']:
                if stock['symbol'] == stock_name:
                    show_stock_info(stock_name, stock)
                    break
    def draw_underline(text_obj):
        x, y = text_obj.get_position()
        text_renderer = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
        linewidth = text_renderer.width
        line = matplotlib.lines.Line2D([x, x + linewidth], [y - 2, y - 2], transform=ax1.transData,
                                    color='blue', linewidth=2)
        ax1.add_line(line)
    
    # 判断是否应该使标题可点击
    if json_data and 'stocks' in json_data and any(stock['symbol'] == name for stock in json_data['stocks']):
        clickable = True
        title_style = {'color': 'blue', 'fontsize': 16, 'fontweight': 'bold', 'picker': True}
    else:
        clickable = False
        title_style = {'color': 'black', 'fontsize': 15, 'fontweight': 'bold', 'picker': False}
    
    tag_str = ""  # 如果没有找到tag，默认显示N/A
    fullname = ""
    for stock in json_data.get('stocks', []):  # 从stocks列表中查找
        if stock['symbol'] == name:
            tags = stock.get('tag', [])
            fullname = stock.get('name', [])
            tag_str = ','.join(tags)  # 将tag列表转换为逗号分隔的字符串
            break
    # 添加交互性标题
    title_text = f'{name} {compare}  {turnover}M/{turnover_rate}  {marketcap_in_billion}  {pe_text} "{table_name}" {fullname} {tag_str}'
    
    title = ax1.set_title(title_text, **title_style)  # 使用 title_style 中的样式

    if clickable:
        draw_underline(title)  # 如果标题可点击，添加下划线

    fig.canvas.mpl_connect('pick_event', on_pick if clickable else lambda event: None)

    ax1.grid(True)
    plt.xticks(rotation=45)

    # 注释初始化
    annot = ax1.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                        bbox=dict(boxstyle="round", fc="black"),
                        arrowprops=dict(arrowstyle="->"), color='yellow')
    annot.set_visible(False)

    time_options = {
        "1m": 0.08,
        "3m": 0.25,
        "6m": 0.5,
        "1Y": 1,
        "2Y": 2,
        "3Y": 3,
        "5Y": 5,
        "10Y": 10,
        "All": 0,
    }
    # 确定默认选项的索引
    default_index = list(time_options.keys()).index(default_time_range)

    rax = plt.axes([0.95, 0.005, 0.05, 0.8], facecolor='lightgoldenrodyellow')
    options = list(time_options.keys())
    radio = RadioButtons(rax, options, active=default_index)

    for label in radio.labels:
        label.set_fontsize(14)

    def update_annot(ind):
        x, y = line1.get_data()
        xval = x[ind["ind"][0]]
        yval = y[ind["ind"][0]]
        annot.xy = (xval, yval)

        if mouse_pressed and initial_price is not None:
            percentage_change = ((yval - initial_price) / initial_price) * 100
            # text = f"{datetime.strftime(xval, '%Y-%m-%d')}\nPrice: {yval}\nInitial: {initial_price}\nChange: {percentage_change:.2f}%"
            text = f"{percentage_change:.1f}%"
        else:
            text = f"{datetime.strftime(xval, '%Y-%m-%d')}\n  {yval}"
        
        annot.set_text(text)
        annot.get_bbox_patch().set_alpha(0.4)

        # 设置字体大小
        annot.set_fontsize(16)  # 你可以根据需要调整这个值

        # 检查数据点的位置，动态调整浮窗的位置
        if xval >= (max(x) - (max(x) - min(x)) / 2):  # 如果数据点在图表右侧5%范围内
            annot.set_position((-130, -20))  # 向左偏移
        else:
            # annot.set_position((-50, 0))  # 默认偏移
            annot.set_position((50, -20))  # 默认偏移

    def hover(event):
        if event.inaxes in [ax1, ax2]:
            if event.xdata is not None:
                current_date = matplotlib.dates.num2date(event.xdata).replace(tzinfo=None)
                vline.set_xdata(current_date)
                vline.set_visible(True)
                fig.canvas.draw_idle()

                x_min, x_max = ax1.get_xlim()
                time_span = x_max - x_min

                dynamic_atol = 0.05 * (time_span / 365)

                xdata, ydata = line1.get_data()
                nearest_index = (np.abs(np.array(xdata) - current_date)).argmin()
                if np.isclose(matplotlib.dates.date2num(xdata[nearest_index]), matplotlib.dates.date2num(current_date), atol=dynamic_atol):
                    update_annot({"ind": [nearest_index]})
                    annot.set_visible(True)
                    # 更新highlight点的位置并显示
                    highlight_point.set_offsets([xdata[nearest_index], ydata[nearest_index]])
                    highlight_point.set_visible(True)
                    fig.canvas.draw_idle()
                else:
                    annot.set_visible(False)
                    highlight_point.set_visible(False)  # 无接触时隐藏highlight点
                    fig.canvas.draw_idle()
            else:
                vline.set_visible(False)
                annot.set_visible(False)
                highlight_point.set_visible(False)
                fig.canvas.draw_idle()
        elif event.inaxes == rax:
            # 隐藏所有元素
            vline.set_visible(False)
            annot.set_visible(False)
            highlight_point.set_visible(False)
            fig.canvas.draw_idle()

    def update(val):
        years = time_options[val]
        if years == 0:
            filtered_dates = dates
            filtered_prices = prices
            filtered_volumes = volumes
        else:
            min_date = datetime.now() - timedelta(days=years * 365)
            filtered_dates = [date for date in dates if date >= min_date]
            filtered_prices = [price for date, price in zip(dates, prices) if date >= min_date]
            filtered_volumes = [volume for date, volume in zip(dates, volumes) if date >= min_date]
        line1.set_data(filtered_dates, filtered_prices)
        line2.set_data(filtered_dates, filtered_volumes)
        ax1.set_xlim(min(filtered_dates), max(filtered_dates))  # 更新x轴范围
        ax1.set_ylim(min(filtered_prices), max(filtered_prices))  # 更新y轴范围
        if show_volume:
            ax2.set_ylim(0, max(filtered_volumes))  # 更新y轴范围
        line2.set_visible(show_volume)
        plt.draw()

    def close_app(root):
        if root:
            root.quit()  # 更安全的关闭方式
            root.destroy()  # 使用destroy来确保彻底关闭所有窗口和退出

    # 添加竖线
    vline = ax1.axvline(x=dates[0], color='b', linestyle='--', linewidth=1, visible=False)
    update(default_time_range)
    radio.on_clicked(update)

    def on_key(event):
        nonlocal show_volume
        try:
            if event.key == 'escape':
                plt.close()
                close_app()
            elif event.key == 'v':  # 使用 'v' 键切换 volume 曲线的显示状态
                show_volume = not show_volume
                update(radio.value_selected)
        except Exception as e:
            print(f"处理键盘事件时发生错误: {str(e)}")

    def on_mouse_press(event):
        nonlocal mouse_pressed, initial_price, initial_date
        if event.button == 1:  # 左键按下
            mouse_pressed = True
            nearest_index = (np.abs(np.array(dates) - matplotlib.dates.num2date(event.xdata).replace(tzinfo=None))).argmin()
            initial_price = prices[nearest_index]
            initial_date = dates[nearest_index]

    def on_mouse_release(event):
        nonlocal mouse_pressed
        if event.button == 1:  # 左键释放
            mouse_pressed = False
        
    def on_key(event):
        nonlocal show_volume
        try:
            if event.key == 'escape':
                plt.close()
                close_app()
            elif event.key == 'v':  # 使用 'v' 键切换 volume 曲线的显示状态
                show_volume = not show_volume
                update(radio.value_selected)
            elif event.key == '1':  # 使用 'c' 键切换到 "3m" 时间跨度
                radio.set_active(options.index("1m"))
                update("1m")
            elif event.key == '2':  # 使用 'c' 键切换到 "3m" 时间跨度
                radio.set_active(options.index("3m"))
                update("3m")
            elif event.key == '3':  # 使用 'f' 键切换到 "10Y" 时间跨度
                radio.set_active(options.index("6m"))
                update("6m")
            elif event.key == '4':  # 使用 'f' 键切换到 "10Y" 时间跨度
                radio.set_active(options.index("1Y"))
                update("1Y")
            elif event.key == '5':  # 使用 'f' 键切换到 "10Y" 时间跨度
                radio.set_active(options.index("5Y"))
                update("5Y")
            elif event.key == '6':  # 使用 'f' 键切换到 "10Y" 时间跨度
                radio.set_active(options.index("10Y"))
                update("10Y")
            elif event.key == '7':  # 使用 'f' 键切换到 "10Y" 时间跨度
                radio.set_active(options.index("All"))
                update("All")
            
        except Exception as e:
            print(f"处理键盘事件时发生错误: {str(e)}")

    plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
    plt.gcf().canvas.mpl_connect('key_press_event', on_key)
    plt.gcf().canvas.mpl_connect('button_press_event', on_mouse_press)
    plt.gcf().canvas.mpl_connect('button_release_event', on_mouse_release)
    
    def hide_annot_on_leave(event):
        annot.set_visible(False)
        highlight_point.set_visible(False)
        vline.set_visible(False)  # 新增代码行，用于隐藏竖线
        fig.canvas.draw_idle()

    plt.gcf().canvas.mpl_connect('figure_leave_event', hide_annot_on_leave)

    print("图表绘制完成，等待用户操作...")
    plt.show()