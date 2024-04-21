import sqlite3
import matplotlib.pyplot as plt

# 数据库连接
conn = sqlite3.connect('/Users/yanzhang/Stocks.db')  # 替换为你的数据库文件路径
cursor = conn.cursor()

# SQL查询，按日期排序获取NASDAQ的数据
query = """
SELECT date, price
FROM Stocks WHERE name = 'NASDAQ'
ORDER BY date;
"""
cursor.execute(query)

# 获取数据
data = cursor.fetchall()

# 关闭数据库连接
cursor.close()
conn.close()

# 提取日期和价格
dates = [row[0] for row in data]
prices = [row[1] for row in data]

# 绘制曲线图
plt.figure(figsize=(10, 5))
plt.plot(dates, prices, marker='o', linestyle='-', color='b')
plt.title('NASDAQ Price Over Time')
plt.xlabel('Date')
plt.ylabel('Price')
plt.grid(True)
plt.xticks(rotation=45)

# 设置Y轴的间隔
# plt.yticks(range(int(min(prices)), int(max(prices)) + 500, 500))

plt.tight_layout()

# 定义键盘事件处理函数
def on_key(event):
    if event.key == 'escape':
        plt.close()

# 连接键盘事件处理函数
plt.gcf().canvas.mpl_connect('key_press_event', on_key)

plt.show()