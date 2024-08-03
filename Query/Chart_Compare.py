import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 数据库路径
db_path = '/Users/yanzhang/Documents/Database/Finance.db'

# 配置表或集合，包含表名和股票名称
stock_config = [
    {'table': 'Indices', 'name': 'NASDAQ'},
    {'table': 'Technology', 'name': 'NVDA'},
    {'table': 'Technology', 'name': 'AAPL'},
    {'table': 'ETFs', 'name': 'CCOR'}
]

# 自动分配颜色
colors = ['tab:blue', 'tab:red', 'tab:green', 'tab:purple', 'tab:pink', 'tab:brown', 'tab:gray', 'tab:olive', 'tab:cyan']

# 连接到数据库并读取数据
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

# 筛选共同日期范围内的数据
for name in dfs:
    dfs[name] = (dfs[name][0].loc[start_date:end_date], dfs[name][1])

# 创建图表
fig, ax1 = plt.subplots(figsize=(12, 6))

# 设置中文字体
zh_font = fm.FontProperties(fname='/Users/yanzhang/Library/Fonts/FangZhengHeiTiJianTi-1.ttf')

# 绘制第一个股票价格曲线
first_name, (first_df, first_color) = next(iter(dfs.items()))
ax1.set_xlabel('日期', fontproperties=zh_font)
ax1.set_ylabel(f"{first_name} 价格", color=first_color, fontproperties=zh_font)
ax1.plot(first_df.index, first_df['price'], label=first_name, color=first_color, linewidth=2)
ax1.tick_params(axis='y', labelcolor=first_color)

# 绘制其他股票价格曲线
second_axes = [ax1]
for i, (name, (df, color)) in enumerate(list(dfs.items())[1:], 1):
    ax = ax1.twinx()
    if i > 1:
        ax.spines['right'].set_position(('outward', 60 * (i - 1)))
    ax.set_ylabel(f"{name} 价格", color=color, fontproperties=zh_font)
    ax.plot(df.index, df['price'], label=name, color=color, linewidth=2)
    ax.tick_params(axis='y', labelcolor=color)
    second_axes.append(ax)

# 设置图例
lines_labels = [ax.get_legend_handles_labels() for ax in second_axes]
lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
ax1.legend(lines, labels, loc='upper left', prop=zh_font)

# 图表标题
plt.grid(True)

# 定义按键事件处理函数
def on_key(event):
    if event.key == 'escape':
        plt.close(fig)

# 连接事件处理函数
fig.canvas.mpl_connect('key_press_event', on_key)

# 显示图表
plt.tight_layout()
plt.show()