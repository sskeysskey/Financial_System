import yfinance as yf

# 定义股票代码和时间范围
ticker_symbol = "AAPL"
start_date = "1978-12-14"
end_date = "2024-05-01"

# 使用 yfinance 下载数据
data = yf.download(ticker_symbol, start=start_date, end=end_date)

# 将数据保存为 CSV 文件
csv_file_path = "/Users/yanzhang/Downloads/aapl.csv"
data.to_csv(csv_file_path)

print(f"数据已保存至 {csv_file_path}")