import yfinance as yf
# from datetime import datetime
# import matplotlib.pyplot as plt

# # 下载特斯拉和苹果的股票数据
# tesla_stock = yf.download('TSLA', start='2024-01-01', end='2024-04-19')
# apple_stock = yf.download('AAPL', start='2024-01-01', end='2024-04-19')

# # 绘制股票收盘价
# plt.plot(tesla_stock['Close'], label='Tesla')
# plt.plot(apple_stock['Close'], label='Apple')

# # 设置图表的标题和坐标轴标签
# plt.xlabel('Date')
# plt.ylabel('Stock Price')
# plt.title('Tesla and Apple Stock Prices (2024)')

# # 添加图例
# plt.legend()

# # 显示图表
# plt.show()

# 定义股票代码和时间范围
ticker_symbol = "^GSPC"
start_date = "1978-12-14"
end_date = "2024-05-01"
# end_date = datetime.now().strftime("%Y-%m-%d")  # 获取当前日期并格式化为字符串

# 使用 yfinance 下载数据
data = yf.download(ticker_symbol, start=start_date, end=end_date)

# 将数据保存为 CSV 文件
csv_file_path = "/Users/yanzhang/Downloads/sp500.csv"
data.to_csv(csv_file_path)

print(f"数据已保存至 {csv_file_path}")