import re
import json
import sqlite3
import matplotlib
import tkinter as tk
import tkinter.font as tkFont
import matplotlib.pyplot as plt
from tkinter import scrolledtext
from datetime import datetime, timedelta
from matplotlib.widgets import RadioButtons

def plot_financial_data(product_name):
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
                            bbox=dict(boxstyle="round", fc="w"),
                            arrowprops=dict(arrowstyle="->"))
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
            yval = y[ind["ind"][0]]
            annot.xy = (x[ind["ind"][0]], yval)
            text = f"{yval}"
            annot.set_text(text)
            annot.get_bbox_patch().set_alpha(0.4)

            # 检查数据点的位置，动态调整浮窗的位置
            if x[ind["ind"][0]] >= (max(x) - (max(x) - min(x)) / 10):  # 如果数据点在图表右侧10%范围内
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
                    close_app()
            except Exception as e:
                print(f"处理键盘事件时发生错误: {str(e)}")
        
        plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
        plt.gcf().canvas.mpl_connect('key_press_event', on_key)

        print("图表绘制完成，等待用户操作...")
        plt.show()
    else:
        print(f"未找到产品名为 {product_name} 的相关数据库信息。")

def input_mapping():
    # 获取用户输入
    prompt = "请输入关键字查询数据库:"
    user_input = get_user_input_custom(root, prompt)
    
    if user_input is None:
        print("未输入任何内容，程序即将退出。")
        close_app()
    else:
        normalized_input = user_input.strip().lower()  # 移除首尾空格并转换为小写
        # 查找匹配项
        found = False
        for db, items in database_mapping.items():
            for item in items:
                if re.search(normalized_input, item.lower()):  # 使用正则表达式进行不区分大小写的部分匹配
                    plot_financial_data(item)  # 找到匹配项，调用绘图函数
                    found = True
                    break
            if found:
                break

        if not found:
            print("未找到匹配的数据项，请确保输入的名称正确无误。")
            close_app()

def get_user_input_custom(root, prompt):
    # 创建一个新的顶层窗口
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    # 设置窗口大小和位置
    window_width = 280
    window_height = 90
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 3 - window_height / 2)  # 将窗口位置提升到屏幕1/3高度处
    input_dialog.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # 添加输入框，设置较大的字体和垂直填充
    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)  # 增加内部垂直填充
    entry.focus_set()

    # 设置确认按钮，点击后销毁窗口并返回输入内容
    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()

    # 绑定回车键和ESC键
    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())

    # 运行窗口，等待用户输入
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input

def close_app(event=None):
    root.destroy()  # 使用destroy来确保彻底关闭所有窗口和退出

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    root.bind('<Escape>', close_app)  # 同样绑定ESC到关闭程序的函数

    # 读取配置文件
    with open('/Users/yanzhang/Documents/Financial_System/Modules/config.json', 'r') as file:
        config = json.load(file)
    
    database_info = config['database_info']
    database_mapping = {k: set(v) for k, v in config['database_mapping'].items()}

    input_mapping()

    root.mainloop()  # 主事件循环