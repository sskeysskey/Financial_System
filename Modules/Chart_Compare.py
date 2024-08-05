import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.dates import DateFormatter

import matplotlib
# 使用TkAgg后端
matplotlib.use('TkAgg')

db_path = '/Users/yanzhang/Documents/Database/Finance.db'

stock_config = [
    # {'table': 'Indices', 'name': 'NASDAQ'},
    {'table': 'Indices', 'name': 'S&P500'},
    # {'table': 'Technology', 'name': 'NVDA'},
    {'table': 'ETFs', 'name': 'TLT'},
    # {'table': 'Currencies', 'name': 'DXY'},
    # {'table': 'Bonds', 'name': 'US10Y'},
    {'table': 'Economics', 'name': 'USInterest'},
]

# 自动分配颜色
colors = ['tab:blue', 'tab:red', 'tab:green', 'tab:purple', 'tab:pink', 'tab:brown', 'tab:gray', 'tab:olive', 'tab:cyan']

# 自定义时间范围
# custom_start_date = '2000-01-01'

custom_start_date = '2019-11-01'
custom_end_date = '2024-08-05'

dfs = {}
with sqlite3.connect(db_path) as conn:
    for i, config in enumerate(stock_config):
        query = f"SELECT date, price FROM {config['table']} WHERE name='{config['name']}'"
        df = pd.read_sql_query(query, conn)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        dfs[config['name']] = (df, colors[i % len(colors)])

# 找出共同的日期范围
start_date = max(df[0].index.min() for df in dfs.values())
end_date = min(df[0].index.max() for df in dfs.values())

# 确定最终的日期范围
final_start_date = max(pd.to_datetime(custom_start_date), start_date)
final_end_date = min(pd.to_datetime(custom_end_date), end_date) if pd.to_datetime(custom_end_date) <= end_date else pd.to_datetime(custom_end_date)

# 筛选共同日期范围内的数据
for name in dfs:
    dfs[name] = (dfs[name][0].reindex(pd.date_range(final_start_date, final_end_date)).fillna(method='ffill'), dfs[name][1])

# 创建图表
fig, ax1 = plt.subplots(figsize=(16, 6))

# 设置中文字体
zh_font = fm.FontProperties(fname='/Users/yanzhang/Library/Fonts/FangZhengHeiTiJianTi-1.ttf')

# 绘制第一个股票价格曲线
first_name, (first_df, first_color) = next(iter(dfs.items()))

line1, = ax1.plot(first_df.index, first_df['price'], label=first_name, color=first_color, linewidth=2)
ax1.tick_params(axis='y', labelcolor=first_color)

# 绘制其他股票价格曲线
second_axes = [ax1]
lines = [line1]
for i, (name, (df, color)) in enumerate(list(dfs.items())[1:], 1):
    ax = ax1.twinx()
    if i > 1:
        ax.spines['right'].set_position(('outward', 60 * (i - 1)))
    
    line, = ax.plot(df.index, df['price'], label=name, color=color, linewidth=2)
    ax.tick_params(axis='y', labelcolor=color)
    second_axes.append(ax)
    lines.append(line)

# 设置图例
lines_labels = [ax.get_legend_handles_labels() for ax in second_axes]
lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
ax1.legend(lines, labels, loc='upper left', prop=zh_font)

# 设置图表标题
plt.grid(True)

# 添加竖直虚线
vline = ax1.axvline(x=final_start_date, color='gray', linestyle='--', linewidth=1)

# 添加显示日期的文本注释，并初始化位置
date_text = fig.text(0.5, 0.005, '', ha='center', va='bottom', fontproperties=zh_font)

# 定义鼠标移动事件处理函数
def on_mouse_move(event):
    if event.inaxes:
        vline.set_xdata(event.xdata)
        # 获取当前日期并更新文本注释
        current_date = pd.to_datetime(event.xdata, unit='D').strftime('%m-%d')
        date_text.set_text(current_date)
        # 更新文本位置
        date_text.set_position((event.x / fig.dpi / fig.get_size_inches()[0], 0.005))
        fig.canvas.draw_idle()

# 定义按键事件处理函数
def on_key(event):
    if event.key == 'escape':
        plt.close(fig)

# 连接事件处理函数
fig.canvas.mpl_connect('motion_notify_event', on_mouse_move)
fig.canvas.mpl_connect('key_press_event', on_key)

# 显示图表
plt.tight_layout()
plt.show()