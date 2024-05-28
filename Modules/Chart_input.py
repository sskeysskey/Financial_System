import sqlite3
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
import json
import tkinter as tk
from tkinter import simpledialog, scrolledtext

def plot_financial_data(db_path, table_name, name, compare, share, fullname, marketcap, pe, json_data, default_time_range="1Y"):
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
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
    for row in data:
        date = datetime.strptime(row[0], "%Y-%m-%d")
        price = float(row[1]) if row[1] is not None else None
        if price is not None:
            dates.append(date)
            prices.append(price)
        if len(row) > 2 and row[2] is not None:
            volume = row[2]  # 安全检查是否存在volume
        else:
            volume = None

    if not dates or not prices:
        print("没有有效的数据来绘制图表。")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.subplots_adjust(left=0.08, bottom=0.2, right=0.93, top=0.9)  # 根据需要调整这些值

    highlight_point = ax.scatter([], [], s=100, color='blue', zorder=5)  # s是点的大小

    line, = ax.plot(dates, prices, marker='o', markersize=1, linestyle='-', linewidth=2, color='b', picker=5)
    
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

    def show_stock_info(name, descriptions):
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
        info = f"{name}:{descriptions['description1']}\n\n{descriptions['description2']}"
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
                if stock['name'] == stock_name:
                    show_stock_info(stock_name, stock)
                    break
    def draw_underline(text_obj):
        x, y = text_obj.get_position()
        text_renderer = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
        linewidth = text_renderer.width
        line = matplotlib.lines.Line2D([x, x + linewidth], [y - 2, y - 2], transform=ax.transData,
                                    color='blue', linewidth=2)
        ax.add_line(line)
    
    # 判断是否应该使标题可点击
    if json_data and 'stocks' in json_data and any(stock['name'] == name for stock in json_data['stocks']):
        clickable = True
        title_style = {'color': 'blue', 'fontsize': 16, 'fontweight': 'bold', 'picker': True}
    else:
        clickable = False
        title_style = {'color': 'black', 'fontsize': 15, 'fontweight': 'bold', 'picker': False}
    
    tag_str = ""  # 如果没有找到tag，默认显示N/A
    for stock in json_data.get('stocks', []):  # 从stocks列表中查找
        if stock['name'] == name:
            tags = stock.get('tag', [])
            tag_str = ','.join(tags)  # 将tag列表转换为逗号分隔的字符串
            break
    # 添加交互性标题
    title_text = f'{name} {compare}  {turnover}M/{turnover_rate}  {marketcap_in_billion}  {pe_text} {table_name} {fullname} {tag_str}'
    
    title = ax.set_title(title_text, **title_style)  # 使用 title_style 中的样式

    if clickable:
        draw_underline(title)  # 如果标题可点击，添加下划线

    fig.canvas.mpl_connect('pick_event', on_pick if clickable else lambda event: None)

    ax.grid(True)
    plt.xticks(rotation=45)

    # 注释初始化
    annot = ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
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
        x, y = line.get_data()
        xval = x[ind["ind"][0]]
        yval = y[ind["ind"][0]]
        annot.xy = (xval, yval)
        text = f"{datetime.strftime(xval, '%Y-%m-%d')}\n{yval}"
        annot.set_text(text)
        annot.get_bbox_patch().set_alpha(0.4)

        # 检查数据点的位置，动态调整浮窗的位置
        if xval >= (max(x) - (max(x) - min(x)) / 2):  # 如果数据点在图表右侧5%范围内
            annot.set_position((-100, -20))  # 向左偏移
        else:
            annot.set_position((-50, 0))  # 默认偏移

    def hover(event):
        if event.inaxes == ax:
            if event.xdata is not None:
                current_date = matplotlib.dates.num2date(event.xdata).replace(tzinfo=None)
                vline.set_xdata(current_date)
                vline.set_visible(True)
                fig.canvas.draw_idle()

                x_min, x_max = ax.get_xlim()
                time_span = x_max - x_min

                dynamic_atol = 0.05 * (time_span / 365)

                xdata, ydata = line.get_data()
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
        else:
            min_date = datetime.now() - timedelta(days=years * 365)
            filtered_dates = [date for date in dates if date >= min_date]
            filtered_prices = [price for date, price in zip(dates, prices) if date >= min_date]
        line.set_data(filtered_dates, filtered_prices)
        ax.set_xlim(min(filtered_dates), max(filtered_dates))  # 更新x轴范围
        ax.set_ylim(min(filtered_prices), max(filtered_prices))  # 更新y轴范围
        plt.draw()

    def close_app(root):
        if root:
            root.quit()  # 更安全的关闭方式
            root.destroy()  # 使用destroy来确保彻底关闭所有窗口和退出

    # 添加竖线
    vline = ax.axvline(x=dates[0], color='b', linestyle='--', linewidth=1, visible=False)
    update(default_time_range)
    radio.on_clicked(update)

    def on_key(event):
        try:
            if event.key == 'escape':
                plt.close()
                close_app()
        except Exception as e:
            print(f"处理键盘事件时发生错误: {str(e)}")

    plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
    plt.gcf().canvas.mpl_connect('key_press_event', on_key)
    def hide_annot_on_leave(event):
        annot.set_visible(False)
        highlight_point.set_visible(False)
        vline.set_visible(False)  # 新增代码行，用于隐藏竖线
        fig.canvas.draw_idle()

    plt.gcf().canvas.mpl_connect('figure_leave_event', hide_annot_on_leave)

    print("图表绘制完成，等待用户操作...")
    plt.show()