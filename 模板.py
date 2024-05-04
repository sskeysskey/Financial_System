options.add_argument('--headless')  # 无界面模式
driver = webdriver.Chrome(service=service, options=options)
# ——————————————————————————————————————————————————————————————————————————————————————————
import json # 首先得import json
# 创建一个JSON文件，例如命名为 config_all.json
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
    with open('config_all.json', 'r') as file:
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
def create_window(parent, content):
    top = tk.Toplevel(parent)
    top.bind('<Escape>', quit_app)  # 在新创建的窗口上也绑定 ESC 键

    # 更新窗口状态以获取准确的屏幕尺寸
    # top.update_idletasks()
    # w = top.winfo_screenwidth()  # 获取屏幕宽度
    # h = top.winfo_screenheight()  # 获取屏幕高度
    # size = (800, 600)  # 定义窗口大小
    # x = w - size[0]  # 窗口右边缘与屏幕右边缘对齐
    # y = h - size[1] - 30 # 窗口下边缘与屏幕下边缘对齐
    # 设置窗口出现在屏幕右下角
    # top.geometry("%dx%d+%d+%d" % (size[0], size[1], x, y))

    # 更新窗口状态以获取准确的屏幕尺寸
    top.update_idletasks()
    w = top.winfo_screenwidth()  # 获取屏幕宽度
    h = top.winfo_screenheight()  # 获取屏幕高度
    size = (800, 800)  # 定义窗口大小
    x = (w // 2) - (size[0] // 2)  # 计算窗口左上角横坐标
    y = (h // 2) - (size[1] // 2)  # 计算窗口左上角纵坐标
    # 设置窗口出现在屏幕中央
    top.geometry("%dx%d+%d+%d" % (size[0], size[1], x, y))

    # 定义字体
    clickable_font = tkFont.Font(family='Courier', size=23, weight='bold')  # 可点击项的字体
    text_font = tkFont.Font(family='Courier', size=20)  # 文本项的字体

    # 创建滚动文本区域，但不直接插入文本，而是插入带有点击事件的Label
    container = tk.Canvas(top)
    scrollbar = tk.Scrollbar(top, command=container.yview)
    scrollable_frame = tk.Frame(container)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: container.configure(
            scrollregion=container.bbox("all")
        )
    )

    container.create_window((0, 0), window=scrollable_frame, anchor="nw")
    container.configure(yscrollcommand=scrollbar.set)

    # 解析内容并为每个name创建一个可点击的Label
    for line in content.split('\n'):
        if ':' in line:
            name, message = line.split(':', 1)
            lbl = tk.Label(scrollable_frame, text=name, fg="gold", cursor="hand2", font=clickable_font)
            lbl.pack(anchor='w')
            lbl.bind("<Button-1>", lambda e, idx=name: show_grapher(idx))
            tk.Label(scrollable_frame, text=message, font=text_font).pack(anchor='w')
        elif '#' in line:
            line = line.replace('#', '')
            tk.Label(scrollable_frame, text=line, fg="red", font=text_font).pack(anchor='w')
        elif '@' in line:
            line = line.replace('@', '')
            tk.Label(scrollable_frame, text=line, fg="orange", font=text_font).pack(anchor='w')
        else:
            tk.Label(scrollable_frame, text=line, font=text_font).pack(anchor='w')

    container.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
# ——————————————————————————————————————————————————————————————————————————————————————————
def compare_today_yesterday(cursor, table_name, name, output, today):
    yesterday = today - timedelta(days=1)
    # 判断昨天是周几
    day_of_week = yesterday.weekday()  # 周一为0，周日为6

    if day_of_week == 0:  # 昨天是周一
        ex_yesterday = today - timedelta(days=4)  # 取上周六
    elif day_of_week == 5:  # 昨天是周六
        yesterday = today - timedelta(days=2)  # 取周五
        ex_yesterday = yesterday  - timedelta(days=1)
    elif day_of_week == 6:  # 昨天是周日
        yesterday = today - timedelta(days=3)  # 取上周五
        ex_yesterday = yesterday  - timedelta(days=1) #取上周四
    else:
        ex_yesterday = yesterday  - timedelta(days=1)

    query = f"""
    SELECT date, price FROM {table_name} 
    WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
    """
    results, error = execute_query(cursor, query, (name, yesterday.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d")))
    if error:
        output.append(error)
        return

    if len(results) == 2:
        yesterday_price = results[0][1]
        ex_yesterday_price = results[1][1]
        change = yesterday_price - ex_yesterday_price
        percentage_change = (change / ex_yesterday_price) * 100

        if change > 0:
            output.append(f"{name}:今天 {yesterday_price} 比昨天涨了 {abs(percentage_change):.2f}%。")
        elif change < 0:
            output.append(f"{name}:今天 {yesterday_price} 比昨天跌了 {abs(percentage_change):.2f}%。")
        else:
            output.append(f"{name}:今天 {yesterday_price} 与昨天持平。")

        # 检查是否浮动超过10%
        if abs(percentage_change) > 5:
            output.append("#提醒：浮动超过了5%！！")

    elif len(results) == 1:
        result_date = results[0][0]
        result_price = results[0][1]  # 提取价格
        if result_date == yesterday.strftime("%Y-%m-%d"):
            output.append(f"{name}:仅找到今天的数据{result_price}，无法比较。")
        else:
            output.append(f"{name}:仅找到昨天的数据{result_price}，无法比较。")
    else:
        output.append(f"{name}:没有找到今天和昨天的数据。")
# ——————————————————————————————————————————————————————————————————————————————————————————
