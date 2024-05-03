import json
import sqlite3
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib

# 设置支持中文的字体
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
matplotlib.rcParams['font.size'] = 14

def plot_financial_data(name):
    with open('/Users/yanzhang/Documents/Financial_System/Modules/config.json', 'r') as file:
        config = json.load(file)
    
    database_info = config['database_info']
    database_mapping = {k: set(v) for k, v in config['database_mapping'].items()}

    # 反向映射，从关键字到数据库信息键
    reverse_mapping = {keyword: db_key for db_key, keywords in database_mapping.items() for keyword in keywords}

    if name in reverse_mapping:
        db_key = reverse_mapping[name]
        db_path = database_info[db_key]['path']
        table_name = database_info[db_key]['table']
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
            cursor.execute(query, (name,))
            data = cursor.fetchall()

        dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
        prices = [row[1] for row in data]

        fig, ax = plt.subplots(figsize=(10, 5))
        fig.subplots_adjust(left=0.1, bottom=0.2, right=0.95, top=0.9)  # 根据需要调整这些值
        
        highlight_point = ax.scatter([], [], s=100, color='blue', zorder=5)  # s是点的大小

        line, = ax.plot(dates, prices, marker='o', markersize=1, linestyle='-', linewidth=2, color='b')
        ax.set_title(f'{name}')
        ax.grid(True)
        plt.xticks(rotation=45)

        # 注释初始化
        annot = ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="black"),
                            arrowprops=dict(arrowstyle="->"), color='yellow')
        annot.set_visible(False)

        time_options = {
            "3m": 0.25,
            "6m": 0.5,
            "1Y": 1,
            "2Y": 2,
            "5Y": 5,
            "10Y": 10,
            "All": 0,
        }

        rax = plt.axes([0.005, 0.01, 0.05, 0.5], facecolor='lightgoldenrodyellow')
        options = list(time_options.keys())
        radio = RadioButtons(rax, options, active=0)

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
        update("3m")
        radio.on_clicked(update)

        def on_key(event):
            try:
                if event.key == 'escape':
                    plt.close()
            except Exception as e:
                print(f"处理键盘事件时发生错误: {str(e)}")
        
        plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
        plt.gcf().canvas.mpl_connect('key_press_event', on_key)

        print("图表绘制完成，等待用户操作...")
        plt.show()
    else:
        print(f"未找到产品名为 {name} 的相关数据库信息。三次成功点")