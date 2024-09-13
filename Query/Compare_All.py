from datetime import datetime, timedelta
import sqlite3
import json
import shutil  # 在文件最开始导入shutil模块
import re
import os

def copy_database_to_backup():
    source_path = '/Users/yanzhang/Documents/Database/Finance.db'
    destination_path = '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db'
    shutil.copy2(source_path, destination_path)  # 使用copy2来复制文件，并覆盖同名文件
    print(f"文件已从{source_path}复制到{destination_path}。")

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

def read_latest_date_info(gainer_loser_path):
    if not os.path.exists(gainer_loser_path):
        return {"gainer": [], "loser": []}

    with open(gainer_loser_path, 'r') as f:
        data = json.load(f)
    latest_date = max(data.keys())
    return latest_date, data[latest_date]

def read_earnings_release(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}

    earnings_companies = {}

    # 修改后的正则表达式
    pattern_colon = re.compile(r'([\w-]+)(?::[\w]+)?\s*:\s*\d+\s*:\s*(\d{4}-\d{2}-\d{2})')

    with open(filepath, 'r') as file:
        for line in file:
            match = pattern_colon.search(line)
            company = match.group(1).strip()
            date = match.group(2)
            day = date.split('-')[2]  # 只取日期的天数
            earnings_companies[company] = day
    return earnings_companies

def generate_html_output(config_path, compare_results, output_html_path):
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>金融数据比较</title>
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Roboto', sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f4f4f4;
                margin: 0;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                padding: 30px;
            }
            h1 {
                color: #2c3e50;
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.5em;
            }
            h2 {
                color: #3498db;
                padding-bottom: 10px;
                margin-top: 40px;
            }
            .category {
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
            }
            .item {
                background-color: #ecf0f1;
                border-radius: 6px;
                padding: 15px;
                margin: 10px 0;
                width: calc(50% - 10px);
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
            }
            .item:hover {
                transform: translateY(-5px);
            }
            .item-name {
                font-weight: bold;
                color: #2c3e50;
            }
            .item-value {
                color: #27ae60;
                font-size: 1.1em;
                margin-top: 5px;
            }
            .item-value.negative {
                color: #c0392b;
            }
            @media (max-width: 768px) {
                .item {
                    width: 100%;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>金融数据比较</h1>
    """

    for category, items in config.items():
        # 检查该分组是否有任何符号项目
        has_symbols = any(item for item in items if next((r for r in compare_results if r.startswith(f"{item}:")), None))
        
        if has_symbols:
            html_content += f'<h2>{category}</h2>\n<div class="category">\n'
            for item, description in items.items():
                result = next((r for r in compare_results if r.startswith(f"{item}:")), None)
                if result:
                    change = result.split(': ')[1]
                    display_name = description if description else item
                    value_class = "item-value negative" if "-" in change else "item-value"
                    html_content += f'''
                    <div class="item">
                        <div class="item-name">{display_name}</div>
                        <div class="{value_class}">{change}</div>
                    </div>
                    '''
            html_content += '</div>\n'

    html_content += """
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', (event) => {
                document.querySelectorAll('.item').forEach((item) => {
                    item.style.opacity = '0';
                    item.style.transform = 'translateY(20px)';
                });

                function showItems() {
                    let delay = 0;
                    document.querySelectorAll('.item').forEach((item) => {
                        setTimeout(() => {
                            item.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                            item.style.opacity = '1';
                            item.style.transform = 'translateY(0)';
                        }, delay);
                        delay += 50;
                    });
                }

                showItems();
            });
        </script>
    </body>
    </html>
    """

    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

def compare_today_yesterday(config_path, config_path2, output_file, gainer_loser_path, earning_file, error_file_path, output_html_path):
    latest_date, latest_info = read_latest_date_info(gainer_loser_path)
    gainers = latest_info.get("gainer", [])
    losers = latest_info.get("loser", [])
    earnings_data = read_earnings_release(earning_file, error_file_path)

    # 检查 gainer_loser.json 中的日期是否为今天或昨天
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    latest_date = datetime.strptime(latest_date, "%Y-%m-%d").date()
    is_recent = latest_date in (today, yesterday)

    if not os.path.exists(config_path):
        log_error_with_timestamp(f"文件 {config_path} 不存在。", error_file_path)
        return

    with open(config_path, 'r') as f:
        config = json.load(f)
    
    output = []
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    
    for table_name, keywords in config.items():
        for keyword in sorted(keywords):
            try:
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()

                    query_two_closest_dates = f"""
                    SELECT date FROM {table_name}
                    WHERE name = ? ORDER BY date DESC LIMIT 2
                    """
                    cursor.execute(query_two_closest_dates, (keyword,))
                    results = cursor.fetchall()

                    if len(results) < 2:
                        raise Exception(f"错误：无法找到{table_name}下的{keyword}的两个有效数据日期。")

                    latest_date = results[0][0]
                    second_latest_date = results[1][0]

                    query = f"""
                    SELECT date, price FROM {table_name} 
                    WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                    """
                    cursor.execute(query, (keyword, latest_date, second_latest_date))
                    results = cursor.fetchall()

                    if len(results) == 2:
                        latest_price = float(results[0][1]) if results[0][1] is not None else 0
                        second_latest_price = float(results[1][1]) if results[1][1] is not None else 0
                        change = latest_price - second_latest_price
                        if second_latest_price != 0:
                            percentage_change = (change / second_latest_price) * 100
                            change_text = f"{percentage_change:.2f}%"
                        else:
                            # 处理除以零的情况
                            if latest_price > 0:
                                change_text = "∞%"  # 正无穷
                            elif latest_price < 0:
                                change_text = "-∞%"  # 负无穷
                            else:
                                change_text = "0%"  # 两个价格都为零
                            raise ValueError(f" {table_name} 下的 {keyword}的 second_latest_price 为零")

                        # 检查是否连续两天或三天上涨
                        consecutive_rise = 0
                        consecutive_fall = 0
                        if keyword in config.get(table_name, {}):
                            query_four_days = f"""
                            SELECT date, price FROM {table_name} 
                            WHERE name = ? ORDER BY date DESC LIMIT 4
                            """
                            cursor.execute(query_four_days, (keyword,))
                            four_day_results = cursor.fetchall()
                            if len(four_day_results) == 4:
                                if (four_day_results[0][1] > four_day_results[1][1] and 
                                    four_day_results[1][1] > four_day_results[2][1]):
                                    consecutive_rise = 2
                                    if four_day_results[2][1] > four_day_results[3][1]:
                                        consecutive_rise = 3
                                # 检查连续下跌
                                elif (four_day_results[0][1] < four_day_results[1][1] and
                                      four_day_results[1][1] < four_day_results[2][1]):
                                    consecutive_fall = 2
                                    if four_day_results[2][1] < four_day_results[3][1]:
                                        consecutive_fall = 3

                            if consecutive_rise == 2:
                                change_text += "+"
                            elif consecutive_rise == 3:
                                change_text += "++"
                            
                            if consecutive_fall == 2:
                                change_text += "-"
                            elif consecutive_fall == 3:
                                change_text += "--"

                        if is_recent and keyword in gainers:
                            if keyword in earnings_data:
                                output.append(f"{keyword}: {earnings_data[keyword]}财{change_text}涨")
                            else:
                                output.append(f"{keyword}: {change_text}涨")
                        elif is_recent and keyword in losers:
                            if keyword in earnings_data:
                                output.append(f"{keyword}: {earnings_data[keyword]}财{change_text}跌")
                            else:
                                output.append(f"{keyword}: {change_text}跌")
                        else:
                            if keyword in earnings_data:
                                output.append(f"{keyword}: {earnings_data[keyword]}财{change_text}")
                            else:
                                output.append(f"{keyword}: {change_text}")
                    else:
                        raise Exception(f"错误：无法比较{table_name}下的{keyword}，因为缺少必要的数据。")
            except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e))
                with open(error_file_path, 'a') as error_file:
                    error_file.write(formatted_error_message)

    with open(output_file, 'w') as file:
        for line in output:
            file.write(line + '\n')

    # 生成 HTML 输出
    generate_html_output(config_path2, output, output_html_path)

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    config_path2 = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
    output_file = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'
    gainer_loser_path = '/Users/yanzhang/Documents/Financial_System/Modules/Gainer_Loser.json'
    earning_file = '/Users/yanzhang/Documents/News/Earnings_Release_new.txt'
    error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'
    output_html_path = '/Users/yanzhang/Documents/sskeysskey.github.io/economics/finance_comparison.html'

    try:
        # 运行主逻辑
        compare_today_yesterday(config_path, config_path2, output_file, gainer_loser_path, earning_file, error_file_path, output_html_path)
        print(f"{output_file} 和 {output_html_path} 已生成。")

        # 备份数据库
        copy_database_to_backup()
    except Exception as e:
        error_message = log_error_with_timestamp(f"未预期的错误: {str(e)}")
        with open(error_file_path, 'a') as error_file:
            error_file.write(error_message)
        print(f"发生错误，详情请查看 {error_file_path}")