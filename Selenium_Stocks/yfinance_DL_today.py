import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta

# 获取当前时间
now = datetime.now()

# 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
if now.weekday() in (0, 6):
    print("Today is either Sunday or Monday. The script will not run.")
else:
    # 读取JSON文件
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', 'r') as file:
        stock_groups = json.load(file)

    today = now.date()
    yesterday = today - timedelta(days=1)

    # 定义时间范围
    start_date = yesterday.strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')

    # 连接到SQLite数据库
    conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
    c = conn.cursor()

    symbol_mapping = {
        "CC=F": "Cocoa", "KC=F": "Coffee", "CT=F": "Cotton", "OJ=F": "OrangeJuice",
        "SB=F": "Sugar", "ZO=F": "Oat", "HE=F": "LeanHogs", "CL=F": "CrudeOil",
        "BZ=F": "Brent", "LE=F": "LiveCattle", "HG=F": "Copper", "ZC=F": "Corn",
        "GC=F": "Gold", "SI=F": "Silver", "NG=F": "Naturalgas", "ZR=F": "Rice", "ZS=F": "Soybean",
        
        "^TNX": "US10Y",
        
        "DX-Y.NYB": "DXY", "EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "JPY=X": "USDJPY",
        "CNYEUR=X": "CNYEUR", "CNYGBP=X": "CNYGBP", "CNYJPY=X": "CNYJPY", "CNYUSD=X": "CNYUSD",
        "EURCNY=X": "EURCNY", "CNY=X": "USDCNY", "GBPCNY=X": "GBPCNY", "AUDCNY=X": "AUDCNY",
        "INR=X": "USDINR", "BRL=X": "USDBRL", "RUB=X": "USDRUB", "KRW=X": "USDKRW", "TRY=X": "USDTRY",
        "SGD=X": "USDSGD", "TWD=X": "USDTWD", "IDR=X": "USDIDR", "PHP=X": "USDPHP", "EGP=X": "USDEGP",
        "ARS=X": "USDARS",
        
        "BTC-USD": "Bitcoin", "ETH-USD": "Ether", "SOL-USD": "Solana", "BNB-USD": "Binance",
        
        "^HSI": "HANGSENG", "^IXIC": "NASDAQ", "000001.SS": "Shanghai", "399001.SZ": "Shenzhen",
        "^VIX": "VIX", "^BVSP": "Brazil", "^N225": "Nikkei", "^RUT": "Russell", "^GSPC": "S&P500",
        "^BSESN": "India", "IMOEX.ME": "Russian"
    }

    # 定义需要特殊处理的group_name
    special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]

    # 遍历所有组和子组
    for group_name, subgroups in stock_groups.items():
        subgroup_counter = {subgroup_name: 0 for subgroup_name in subgroups}  # 初始化计数器
        for subgroup_name, tickers in subgroups.items():
            for ticker_symbol in tickers:
                # 使用 yfinance 下载股票数据
                data = yf.download(ticker_symbol, start=start_date, end=end_date)

                # 插入数据到相应的表中
                table_name = group_name.replace(" ", "_")  # 确保表名没有空格
                mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)  # 从映射字典获取名称，如果不存在则使用原始 ticker_symbol
                for index, row in data.iterrows():
                    date = index.strftime('%Y-%m-%d')
                    if group_name in ["Currencies", "Bonds", "Crypto"]:
                        price = round(row['Close'], 6)
                    elif group_name in ["Commodities", "Indices"]:
                        price = round(row['Close'], 4)
                    else:
                        price = round(row['Close'], 2)

                    if group_name in special_groups:
                        c.execute(f"INSERT INTO {table_name} (date, name, price) VALUES (?, ?, ?)",
                                (date, mapped_name, price))
                    else:
                        volume = int(row['Volume'])
                        c.execute(f"INSERT INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)",
                                (date, mapped_name, price, volume))
                subgroup_counter[subgroup_name] += 1  # 更新计数器

        # 使用print输出每个大组的统计信息
        print(f"{group_name} statistics:")
        for subgroup_name, count in subgroup_counter.items():
            print(f"  {subgroup_name}: {count} stocks inserted.")

    # 提交事务
    conn.commit()
    # 关闭连接
    conn.close()

    print("所有数据已成功写入数据库")