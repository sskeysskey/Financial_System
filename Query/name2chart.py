import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib

def plot_financial_data(product_name):
    # 数据库信息
    database_info = {
        'StocksDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks'},
        'CryptoDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto'},
        'CurrencyDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies'},
        'CommodityDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'},
        'BondsDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Bonds'}
    }

    # 将数据库信息键映射到一组关键字
    database_mapping = {
        'StocksDB': {'NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX'},
        'CryptoDB': {"Bitcoin", "Ether", "Binance", "Bitcoin Cash", "Solana", "Monero", "Litecoin"},
        'CurrencyDB': {'DXY', 'CNYEUR', 'USDJPY', 'USDCNY', 'USDBRL', 'USDRUB', 'USDKRW', 'USDTRY', 'USDSGD', 'CNYJPY'},
        'CommodityDB': {'Crude Oil', 'Brent', 'Natural gas', 'Coal', 'Uranium', 'Gold', 'Silver', 'Copper', 'Steel',
                        'Iron Ore', 'Lithium', 'Soybeans', 'Wheat', 'Lumber', 'Palm Oil', 'Rubber', 'Coffee', 'Cotton', 'Cocoa',
                        'Rice', 'Canola', 'Corn', 'Bitumen', 'Cobalt', 'Lead', 'Aluminum', 'Nickel', 'Tin', 'Zinc', 'Lean Hogs',
                        'Beef', 'Poultry', 'Salmon'},
        'BondsDB': {'United States', 'United Kingdom', 'Japan', 'Russia', 'Brazil', 'India', 'Turkey'}
    }

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
        ax.set_title(f'{product_name} Price Over Time')
        ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.grid(True)
        plt.xticks(rotation=45)

        time_options = {
            "全部时间": 0,
            "10年": 10,
            "5年": 5,
            "2年": 2,
            "1年": 1,
            "6个月": 0.5,
            "3个月": 0.25,
        }

        rax = plt.axes([0.09, 0.6, 0.1, 0.4])
        options = list(time_options.keys())
        initial_state = options.index("3个月")
        radio = RadioButtons(rax, options, active=initial_state)

        for label in radio.labels:
            label.set_fontsize(14)

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

        update("3个月")
        radio.on_clicked(update)

        def on_key(event):
            if event.key == 'escape':
                plt.close()

        plt.gcf().canvas.mpl_connect('key_press_event', on_key)

        print("图表绘制完成，等待用户操作...")
        plt.show()
    else:
        print(f"未找到产品名为 {product_name} 的相关数据库信息。")