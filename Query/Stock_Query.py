import yfinance as yf
import matplotlib.pyplot as plt

# 下载特斯拉和苹果的股票数据
tesla_stock = yf.download('TSLA', start='2024-01-01', end='2024-04-19')
apple_stock = yf.download('AAPL', start='2024-01-01', end='2024-04-19')

# 绘制股票收盘价
plt.plot(tesla_stock['Close'], label='Tesla')
plt.plot(apple_stock['Close'], label='Apple')

# 设置图表的标题和坐标轴标签
plt.xlabel('Date')
plt.ylabel('Stock Price')
plt.title('Tesla and Apple Stock Prices (2024)')

# 添加图例
plt.legend()

# 显示图表
plt.show()