import sqlite3
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib

def plot_financial_data_panel(db_path, table_name, name, compare, default_time_range="1Y"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
        cursor.execute(query, (name,))
        data = cursor.fetchall()

    dates = []
    prices = []
    for row in data:
        try:
            date = datetime.strptime(row[0], "%Y-%m-%d")
            price = float(row[1]) if row[1] is not None else None
            # volume = row[2]  # 获取当前行的volume
            if price is not None:
                dates.append(date)
                prices.append(price)
        except ValueError:
            continue  # 跳过非法数据

    if not dates or not prices:
        print("没有有效的数据来绘制图表。")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.subplots_adjust(left=0.08, bottom=0.2, right=0.93, top=0.9)  # 根据需要调整这些值
    highlight_point = ax.scatter([], [], s=100, color='blue', zorder=5)  # s是点的大小
    line, = ax.plot(dates, prices, marker='o', markersize=1, linestyle='-', linewidth=2, color='b')
    
    ax.set_title(f'{name}   {compare}   {table_name}', fontsize=18)
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

    # 添加竖线
    vline = ax.axvline(x=dates[0], color='b', linestyle='--', linewidth=1, visible=False)
    update(default_time_range)
    radio.on_clicked(update)

    def on_key(event):
        try:
            if event.key == 'escape':
                plt.close()
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