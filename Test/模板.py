# ——————————————————————————————————————————————————————————————————————————————————————————
while change_date <= end_date:
        formatted_change_date = change_date.strftime('%Y-%m-%d')
        offset = 0
        has_data = True
        
        while has_data and not has_duplicate:  # 修改while条件
            url = f"https://finance.yahoo.com/calendar/earnings?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
            driver.get(url)
            
            # 使用显式等待确保元素加载
            wait = WebDriverWait(driver, 4)
            try:
                table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
                rows = table.find_elements(By.CSS_SELECTOR, "tbody > tr")
            except TimeoutException:
                rows = []
            
            if not rows:
                has_data = False
            else:
                for row in rows:
                    symbol = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]').get_attribute('title')

                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 3:
                        event_name = cells[2].text.strip()
                    else:
                        continue
                    
                    if "Earnings Release" in event_name or "Shareholders Meeting" in event_name:
                        # 如果发现symbol已存在，设置重复标志并跳出循环
                        if symbol in existing_content:
                            has_duplicate = True
                            break
                            
                        for category, symbols in data.items():
                            if symbol in symbols:
                                cursor.execute(f"SELECT volume FROM {category} WHERE name = ? ORDER BY date DESC LIMIT 1", (symbol,))
                                volume_row = cursor.fetchone()
                                volume = volume_row[0] if volume_row else "No volume data"
                                
                                original_symbol = symbol

                                suffix = ""
                                for color_group, group_symbols in color_data.items():
                                    if symbol in group_symbols and color_group != "red_keywords":
                                        suffix = color_suffix_map.get(color_group, "")
                                        break
                                
                                if suffix:
                                    symbol += f":{suffix}"

                                entry = f"{symbol:<7}: {volume:<10}: {formatted_change_date}"
                                if original_symbol not in existing_content:
                                    output_file.write(entry + "\n")
                                    new_content_added = True
                                    existing_content.add(original_symbol)  # 添加到已存在集合中
                
                if has_duplicate:
                    break  # 如果发现重复，跳出内层循环
                
                offset += 100  # 为下一个子页面增加 offset

        if has_duplicate:
            has_duplicate = False  # 重置重复标志
        
        change_date += delta  # 日期增加一天
# ——————————————————————————————————————————————————————————————————————————————————————————
def get_column_indexes(driver):
    """解析表头，获取各列的索引"""
    header = driver.find_elements(By.CSS_SELECTOR, "table thead tr th")
    column_mapping = {}
    for idx, th in enumerate(header, start=1):
        header_text = th.text.strip().lower()
        if 'volume' in header_text:
            column_mapping['volume'] = idx
        elif 'market cap' in header_text:
            column_mapping['market_cap'] = idx
        elif 'pe ratio' in header_text or 'p/e' in header_text:
            column_mapping['pe_ratio'] = idx
    return column_mapping

@retry_on_stale(max_attempts=5, delay=1)
def extract_row_data_dynamic(driver, index, column_mapping):
    """根据动态列映射提取单行数据"""
    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    if index >= len(rows):
        raise IndexError("Row index out of range")
    row = rows[index]
    
    symbol = row.find_element(By.CSS_SELECTOR, "a[data-testid='table-cell-ticker'] span.symbol").text.strip()
    name = row.find_element(By.CSS_SELECTOR, "div[title]").get_attribute("title").strip()
    price = row.find_element(By.CSS_SELECTOR, "fin-streamer[data-field='regularMarketPrice']").get_attribute("data-value").strip()
    
    volume = '--'
    market_cap = '--'
    pe_ratio = '--'
    
    if 'volume' in column_mapping:
        try:
            volume = row.find_element(By.XPATH, f"./td[{column_mapping['volume']}]").text.strip()
        except NoSuchElementException:
            pass
    
    if 'market_cap' in column_mapping:
        try:
            market_cap = row.find_element(By.XPATH, f"./td[{column_mapping['market_cap']}]").text.strip()
        except NoSuchElementException:
            pass
    
    if 'pe_ratio' in column_mapping:
        try:
            pe_ratio = row.find_element(By.XPATH, f"./td[{column_mapping['pe_ratio']}]").text.strip()
        except NoSuchElementException:
            pass
    
    return symbol, name, price, volume, market_cap, pe_ratio

# 在主程序中使用动态列映射
def fetch_data_dynamic(driver, url, blacklist, column_mapping):
    driver.get(url)
    results = []
    
    try:
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr")))
        
        for index in range(len(driver.find_elements(By.CSS_SELECTOR, "table tbody tr"))):
            try:
                symbol, name, price, volume, market_cap, pe_ratio = extract_row_data_dynamic(driver, index, column_mapping)
                
                if is_blacklisted(symbol, blacklist):
                    continue
                
                # 数据处理
                price_parsed = parse_number(price)
                volume_parsed = parse_volume(volume)
                market_cap_parsed = parse_market_cap(market_cap)
                pe_ratio_parsed = parse_number(pe_ratio)
                
                if market_cap_parsed != '--':
                    results.append((
                        symbol,
                        market_cap_parsed,
                        pe_ratio_parsed,
                        name,
                        price_parsed,
                        volume_parsed
                    ))
                    
            except Exception as e:
                print(f"处理行时出错: {str(e)}")
                continue
                
        write_results_to_files(results)
        return results
        
    except TimeoutException:
        print("页面加载超时")
        return []
    except Exception as e:
        print(f"获取数据时出错: {str(e)}")
        return []

# 在主程序中初始化列映射
try:
    driver.get(urls[0][0])  # 访问第一个URL以获取表头
    column_mapping = get_column_indexes(driver)
    print(f"列映射: {column_mapping}")
except Exception as e:
    print(f"初始化列映射时出错: {str(e)}")
    column_mapping = {}

# 使用动态列映射抓取数据
def process_sector_dynamic(driver, url, sector, output, output_500, output_5000, blacklist, column_mapping):
    data = fetch_data_dynamic(driver, url, blacklist, column_mapping)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', output, log_enabled=True, market_cap_threshold=5000000000, write_symbols=True)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', output, log_enabled=False, market_cap_threshold=5000000000)
    
    # 处理 500 亿和 5000 亿市值
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json', output_500, log_enabled=True, market_cap_threshold=50000000000)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_5000.json', output_5000, log_enabled=True, market_cap_threshold=500000000000)

# 在循环中使用动态处理函数
for url, sector in urls:
    process_sector_dynamic(driver, url, sector, output, output_500, output_5000, blacklist, column_mapping)
# ——————————————————————————————————————————————————————————————————————————————————————————
# 检查该 symbol 是否存在于 colors.json 中的其他分组，且不在 red_keywords 中
symbol_exists_elsewhere = any(
    name in symbols for group, symbols in colors.items() if group != category_list
)

if symbol_exists_elsewhere:
    print(f"Symbol {name} 已存在于Colors其他分组中，跳过添加到 {category_list}")
    continue  # 跳过当前 symbol 的添加

if name not in colors.get(category_list, []):
    # if name in existing_symbols:
        # 如果 symbol 已存在于 sectors_panel.json 中，打印日志
    # else:
    if category_list in colors:
        colors[category_list].append(name)
        print(f"将 '{name}' 添加到Colors已存在的 '{category_list}' 类别中")
    else:
        colors[category_list] = [name]
        print(f"'{name}' 被添加到新的 '{category_list}' 类别中")
else:
    print(f"Symbol {name} 已存在于 {category_list} 中。")
# ——————————————————————————————————————————————————————————————————————————————————————————
for group_name, tickers in stock_groups.items():
    data_count = 0  # 初始化计数器
    for ticker_symbol in tickers:
        try:
            # 使用 yfinance 下载股票数据
            data = yf.download(ticker_symbol, start=start_date, end=end_date)
            if data.empty:
                raise ValueError(f"{group_name} {ticker_symbol}: No price data found for the given date range.")

            # 插入数据到相应的表中
            table_name = group_name.replace(" ", "_")  # 确保表名没有空格
            mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)  # 从映射字典获取名称，如果不存在则使用原始 ticker_symbol
            for index, row in data.iterrows():
                date = index.strftime('%Y-%m-%d')
                # date = "2024-06-11"
                if group_name in ["Currencies", "Bonds"]:
                    price = round(row['Close'], 4)
                elif group_name in ["Crypto"]:
                    price = round(row['Close'], 1)
                elif group_name in ["Commodities"]:
                    price = round(row['Close'], 3)
                else:
                    price = round(row['Close'], 2)

                if group_name in special_groups:
                    c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", (date, mapped_name, price))
                else:
                    volume = int(row['Volume'])
                    c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", (date, mapped_name, price, volume))
                
                data_count += 1  # 成功插入一条数据，计数器增加
        except Exception as e:
            with open('/Users/yanzhang/Documents/News/Today_error1.txt', 'a') as error_file:
                error_file.write(log_error_with_timestamp(str(e)))

    # 在完成每个group_name后打印信息
    print(f"{group_name} 数据处理完成，总共下载了 {data_count} 条数据。")
# ——————————————————————————————————————————————————————————————————————————————————————————
def fetch_data(driver, url, blacklist):
    driver.get(url)
    results = []
    
    try:
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr")))
        
        total_rows = len(driver.find_elements(By.CSS_SELECTOR, "table tbody tr"))

        for index in range(total_rows):
            try:
                symbol, name, price, volume, market_cap, pe_ratio = extract_row_data(driver, index)
                
                if is_blacklisted(symbol, blacklist):
                    continue
                
                # 数据处理
                price_parsed = parse_number(price)
                volume_parsed = parse_volume(volume)
                market_cap_parsed = parse_market_cap(market_cap)
                pe_ratio_parsed = parse_number(pe_ratio)
                
                if market_cap_parsed != '--':
                    results.append((
                        symbol,
                        market_cap_parsed,
                        pe_ratio_parsed,
                        name,
                        price_parsed,
                        volume_parsed
                    ))
                    
            except StaleElementReferenceException as e:
                print(f"StaleElementReferenceException on URL: {url}, row index: {index} - {str(e)}")
                continue
            except Exception as e:
                print(f"处理行时出错: {str(e)}")
                continue
                
        write_results_to_files(results)
        return results
        
    except TimeoutException:
        print("页面加载超时")
        return []
    except Exception as e:
        print(f"获取数据时出错: {str(e)}")
        return []
# ——————————————————————————————————————————————————————————————————————————————————————————
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
# 不爬取时间配置
no_crawl_periods = {
    "SSE Composite Index": [('2024-05-02', '2024-05-05')],
    "Shenzhen Index": [('2024-05-02', '2024-05-05')],
    # 可以添加更多指数和对应的时间段
}

def is_within_no_crawl_period(current_date, name):
    """检查当前日期是否在指定指数的不爬取时间内"""
    periods = no_crawl_periods.get(name, [])
    for start, end in periods:
        if start <= current_date <= end:
            return True
    return False

for name in names:
    indice_name = name.text
    if indice_name in indices:
        if is_within_no_crawl_period(today_str, indice_name):
            continue  # 如果当前日期在不爬取时间内，跳过此指数
# ——————————————————————————————————————————————————————————————————————————————————————————
from datetime import datetime
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
# ——————————————————————————————————————————————————————————————————————————————————————————
# 定义parent_id的映射
parent_ids = {
    "Basic_Materials": 13,
    "Communication_Services": 20,
    "Consumer_Cyclical": 15,
    "Consumer_Defensive": 16,
    "Energy": 12,
    "Financial_Services": 18,
    "Healthcare": 17,
    "Industrials": 14,
    "Real_Estate": 22,
    "Technology": 19,
    "Utilities": 21
}
# ——————————————————————————————————————————————————————————————————————————————————————————
def get_parent_id(commodity):
    if commodity in ["Crude Oil", "Brent", "Natural gas", "Coal", "Uranium"]:
        return 5
    elif commodity in ["Gold", "Silver", "Copper", "Steel", "Lithium"]:
        return 6
    elif commodity in ["Soybeans", "Wheat", "Palm Oil", "Orange Juice", "Cocoa",
        "Rice", "Corn", "Coffee", "Sugar", "Cotton", "Oat"]:
        return 7
    elif commodity in ["Aluminum", "Nickel", "Tin", "Zinc", "Palladium"]:
        return 8
    elif commodity in ["Live Cattle", "Lean Hogs", "Poultry", "Salmon"]:
        return 9
    elif commodity in ["CRB Index", "LME Index", "Nuclear Energy Index", "Solar Energy Index", "EU Carbon Permits",
        "Containerized Freight Index"]:
        return 23
    return None
# ——————————————————————————————————————————————————————————————————————————————————————————
{"database_info": {
        "Commodities": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Commodities"
        },
        "Indices": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Indices"
        },
        "Crypto": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Crypto"
        },
        "Currencies": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Currencies"
        },
        "Basic_Materials": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Basic_Materials"
        },
        "Communication_Services": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Communication_Services"
        },
        "Consumer_Cyclical": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Consumer_Cyclical"
        },
        "Consumer_Defensive": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Consumer_Defensive"
        },
        "Energy": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Energy"
        },
        "Financial_Services": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Financial_Services"
        },
        "Healthcare": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Healthcare"
        },
        "Industrials": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Industrials"
        },
        "Real_Estate": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Real_Estate"
        },
        "Technology": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Technology"
        },
        "Utilities": {
            "path": "/Users/yanzhang/Documents/Database/Finance.db",
            "table": "Utilities"
        }
    }}
# ——————————————————————————————————————————————————————————————————————————————————————————
def Copy_Command_C():
    script = '''
    tell application "System Events"
	    keystroke "c" using command down
        delay 0.5
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])
# ——————————————————————————————————————————————————————————————————————————————————————————
def create_custom_style():
    style = ttk.Style()
    # 尝试使用不同的主题，如果默认主题不支持背景颜色的更改
    # style.theme_use('clam')
    style.theme_use('alt')

    # 为不同的按钮定义颜色
    style.configure("Green.TButton", background="green", foreground="white", font=('Helvetica', 16))
    style.configure("White.TButton", background="white", foreground="black", font=('Helvetica', 16))
    style.configure("Purple.TButton", background="purple", foreground="white", font=('Helvetica', 16))
    style.configure("Yellow.TButton", background="yellow", foreground="black", font=('Helvetica', 16))
    style.configure("Orange.TButton", background="orange", foreground="black", font=('Helvetica', 16))
    style.configure("Blue.TButton", background="blue", foreground="white", font=('Helvetica', 16))
    style.configure("Red.TButton", background="red", foreground="black", font=('Helvetica', 16))
    style.configure("Black.TButton", background="black", foreground="white", font=('Helvetica', 16))
    style.configure("Default.TButton", background="gray", foreground="black", font=('Helvetica', 16))

    # 确保按钮的背景颜色被填充
    style.map("TButton",
              background=[('active', '!disabled', 'pressed', 'focus', 'hover', 'alternate', 'selected', 'background')]
              )
# ——————————————————————————————————————————————————————————————————————————————————————————
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver
# ——————————————————————————————————————————————————————————————————————————————————————————
def plot_financial_data(db_path, table_name, name, compare, marketcap, pe, json_data):
    # 设置支持中文的字体
    matplotlib.rcParams['font.family'] = 'sans-serif'
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    matplotlib.rcParams['font.size'] = 14
# ——————————————————————————————————————————————————————————————————————————————————————————
def parse_changes(filename):
    changes = {}
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                if ':' in line:
                    key, value = line.split(':')
                    changes[key.strip()] = value.strip()
    except FileNotFoundError:
        print("文件未找到")
    return changes
# ——————————————————————————————————————————————————————————————————————————————————————————
sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from Message_AppleScript import display_dialog

display_dialog("未找到匹配的数据项。")
# ——————————————————————————————————————————————————————————————————————————————————————————
import subprocess

applescript_code = 'display dialog "整个字幕文件翻译完毕。" buttons {"OK"} default button "OK"'
process = subprocess.run(['osascript', '-e', applescript_code], check=True)
# ——————————————————————————————————————————————————————————————————————————————————————————
from log_config import setup_logger

logger = setup_logger()

logger.info("这是一条信息日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志")
# ——————————————————————————————————————————————————————————————————————————————————————————
def search_category_for_tag(category):
    return [
        (item['symbol'], ' '.join(item.get('tag', []))) for item in data.get(category, [])
        if all(any(fuzzy_match(tag, keyword) for tag in item.get('tag', [])) for keyword in keywords_lower)
    ]

def search_category_for_name(category):
    return [
        (item['symbol'], ' '.join(item.get('tag', []))) for item in data.get(category, [])
        if all(fuzzy_match(item['name'], keyword) for keyword in keywords_lower)
    ]

return (
    search_category_for_tag('stocks'), search_category_for_tag('etfs'),
    search_category_for_name('stocks'), search_category_for_name('etfs')
)
# ——————————————————————————————————————————————————————————————————————————————————————————
# ——————————————————————————————————————————————————————————————————————————————————————————