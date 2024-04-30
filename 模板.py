options.add_argument('--headless')  # 无界面模式
driver = webdriver.Chrome(service=service, options=options)
# ——————————————————————————————————————————————————————————————————————————————————————————
import json # 首先得import json
# 针对data_compare.py文件的配置文件优化
# 创建一个JSON文件，例如命名为 config.json
{
    "databases": [
        {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Stocks",
            "names": ["NASDAQ", "S&P 500", "SSE Composite Index", "Shenzhen Index", "Nikkei 225", "S&P BSE SENSEX", "HANG SENG INDEX"]
        },
        {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Crypto",
            "names": ["Bitcoin", "Ether", "Binance", "Bitcoin Cash", "Solana", "Monero", "Litecoin"]
        }
    ]
}

def load_config():
    """加载配置文件"""
    with open('config.json', 'r') as file:
        config = json.load(file)
    return config

def main():
    config = load_config()
    today = datetime.now()
    output = []

    for db_config in config['databases']:
        db_path = db_config['path']
        table_name = db_config['table']
        index_names = db_config['names']

        with create_connection(db_path) as conn:
            cursor = conn.cursor()

            #for index_name in index_names:
                # 假设对每个指数执行的操作保持不变，这里省略具体操作的代码
# ——————————————————————————————————————————————————————————————————————————————————————————
databases = [
    {'path': '/Users/yanzhang/Stocks.db', 'table': 'Stocks', 'index_names': ('NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX')},
    {'path': '/Users/yanzhang/Crypto.db', 'table': 'Crypto', 'index_names': ('Bitcoin', 'Ether', 'Binance', 'Bitcoin Cash', 'Solana', 'Monero', 'Litecoin')},
    {'path': '/Users/yanzhang/Currencies.db', 'table': 'Currencies', 'index_names': ('DXY', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHY', 'USDINR', 'USDBRL', 'USDRUB', 'USDKRW', 'USDTRY', 'USDSGD', 'USDHKD')},
    {'path': '/Users/yanzhang/Commodities.db', 'table': 'Commodities', 'index_names': ('Crude Oil', 'Brent', 'Natural gas', 'Coal', 'Uranium', 'Gold', 'Silver', 'Copper', 'Steel', 'Iron Ore', 'Lithium', 'Soybeans', 'Wheat', 'Lumber', 'Palm Oil', 'Rubber', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Canola', 'Corn', 'Bitumen', 'Cobalt', 'Lead', 'Aluminum', 'Nickel', 'Tin', 'Zinc', 'Lean Hogs', 'Beef', 'Poultry', 'Salmon')},
]
# ——————————————————————————————————————————————————————————————————————————————————————————
def query_db2chart(self, path, table, condition, parent_window, value):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    query = f"""
    SELECT date, price
    FROM {table}
    WHERE {condition}
    ORDER BY date;
    """
    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()
    conn.close()

    if not data:
        print("No data found.")
        return

    def update(val):
        current_option = val
        years = time_options[current_option]
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

    matplotlib.rcParams['font.family'] = 'sans-serif'
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    matplotlib.rcParams['font.size'] = 14

    dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
    prices = [row[1] for row in data]

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    line, = ax.plot(dates, prices, marker='o', linestyle='-', color='b')
    ax.set_title(f'{value}')
    # ax.set_xlabel('Date')
    # ax.set_ylabel('Price')
    ax.grid(True)
    plt.xticks(rotation=45)
    # 调整子图参数，特别是底部边距
    # plt.subplots_adjust(bottom=0.2)

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

    rax = plt.axes([0.08, 0.65, 0.07, 0.3], facecolor='lightgoldenrodyellow')
    radio = RadioButtons(rax, list(time_options.keys()), activecolor='blue', active=6)  # 设置默认选中“3月”

    for label in radio.labels:
        label.set_fontsize(14)

    update("3月")  # 默认选择“3个月”
    radio.on_clicked(update)

    def on_key(event):
        if event.key == 'escape':
            plt.close()
    
    plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
    plt.gcf().canvas.mpl_connect('key_press_event', on_key)

    plt.show()
# ——————————————————————————————————————————————————————————————————————————————————————————
lower_input = user_input.lower()  # 用户输入转为小写
# 使用反向映射表查询数据库信息
matched_keys = [key for key in reverse_mapping if lower_input in key]  # 搜索包含输入的所有关键字
if matched_keys:
    db_key = reverse_mapping[matched_keys[0]]  # 选择第一个匹配的关键字
    db_info = database_info[db_key]
    condition = f"name LIKE '%{matched_keys[0]}%'"  # 使用LIKE进行模糊匹配
    result = query_database(db_info['path'], db_info['table'], condition)
    create_window(root, result)
else:
    print("输入值无效或未配置数据库信息。程序退出。")
    close_app()
# ——————————————————————————————————————————————————————————————————————————————————————————
