import json
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib

def plot_financial_data(product_name):
    with open('/Users/yanzhang/Documents/Financial_System/Modules/config.json', 'r') as file:
        config = json.load(file)
    
    database_info = config['database_info']
    database_mapping = {k: set(v) for k, v in config['database_mapping'].items()}

    # 反向映射，从关键字到数据库信息键
    reverse_mapping = {}
    for db_key, keywords in database_mapping.items():
        for keyword in keywords:
            reverse_mapping[keyword] = db_key

    if product_name in reverse_mapping:
        db_key = reverse_mapping[product_name]
        db_path = database_info[db_key]['path']
        table_name = database_info[db_key]['table']
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
        cursor.execute(query, (product_name,))
        data = cursor.fetchall()
        cursor.close()
        conn.close()

        dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
        prices = [row[1] for row in data]

        # 设置支持中文的字体
        matplotlib.rcParams['font.family'] = 'sans-serif'
        matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
        matplotlib.rcParams['font.size'] = 14

        fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
        line, = ax.plot(dates, prices, marker='o', linestyle='-', color='b')
        ax.set_title(f'{product_name}')
        # ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.grid(True)
        plt.xticks(rotation=45)

        # 注释初始化
        annot = ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="black"),
                            arrowprops=dict(arrowstyle="->"), color='yellow')
        annot.set_visible(False)

        time_options = {
            "全部": 0,
            "10年": 10,
            "5年": 5,
            "2年": 2,
            "1年": 1,
            "6月": 0.5,
            "3月": 0.25,
        }

        rax = plt.axes([0.09, 0.7, 0.07, 0.3], facecolor='lightgoldenrodyellow')
        options = list(time_options.keys())
        radio = RadioButtons(rax, options, active=6)

        for label in radio.labels:
            label.set_fontsize(14)

        def update_annot(ind):
            x, y = line.get_data()
            xval = x[ind["ind"][0]]
            yval = y[ind["ind"][0]]
            annot.xy = (xval, yval)
            text = f"{datetime.strftime(xval, '%m-%d')}: {yval}"
            annot.set_text(text)
            annot.get_bbox_patch().set_alpha(0.4)

            # 检查数据点的位置，动态调整浮窗的位置
            if xval >= (max(x) - (max(x) - min(x)) / 5):  # 如果数据点在图表右侧10%范围内
                annot.set_position((-100, 20))  # 向左偏移
            else:
                annot.set_position((20, 20))  # 默认偏移

        def hover(event):
            vis = annot.get_visible()
            if event.inaxes == ax:
                cont, ind = line.contains(event)
                if cont:
                    update_annot(ind)
                    annot.set_visible(True)
                    fig.canvas.draw_idle()
                else:
                    if vis:
                        annot.set_visible(False)
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
            ax.relim()
            ax.autoscale_view()
            plt.draw()

        update("3月")
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
        print(f"未找到产品名为 {product_name} 的相关数据库信息。")

# product_name = "NASDAQ"
# plot_financial_data(product_name)