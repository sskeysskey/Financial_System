import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

# 数据库文件路径
db_path = '/Users/yanzhang/Documents/Database/Analysis.db'

# 创建数据库连接
conn = sqlite3.connect(db_path)

# 读取数据
query = "SELECT date, name, rate FROM Date_compare"  # 请替换tablename为您的实际表名
df = pd.read_sql(query, conn)

# 确保'date'列是日期格式
df['date'] = pd.to_datetime(df['date'])

# 关闭数据库连接
conn.close()

# 设置图形大小
plt.figure(figsize=(14, 8))

# 对每一个name分别绘制曲线
for label, grp in df.groupby('name'):
    plt.plot(grp['date'], grp['rate'], label=label, marker='o')  # marker='o'提供了数据点的可视化

# 添加图例
plt.legend(title='Sector Name', loc='upper left')

# 添加标题和坐标轴标签
plt.title('Rate Change by Sector Over Dates')
plt.xlabel('Date')
plt.ylabel('Rate')

# 优化日期显示
plt.gcf().autofmt_xdate()  # 自动调整日期显示的格式

# 定义键盘事件处理函数
def close_figure(event):
    if event.key == 'escape':
        plt.close(event.canvas.figure)

# 绑定键盘事件
plt.gcf().canvas.mpl_connect('key_press_event', close_figure)

# 显示图形
plt.show()