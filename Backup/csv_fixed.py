import csv
from datetime import datetime, date, timedelta
import os

# 1. 原始数据表文本 (与之前相同)
data_text = """
2024.6.7	5000	1
2023.6.28	5000	1
2023.4.6	5000	1
2023.3.13	5000	1
2022.9.27	5000	1
2022.9.13	5000	1
2022.8.30	5000	1
2022.8.3	5000	1
2022.8.18	5000	1
2022.7.5	5000	1
2022.2.8	5000	1
2022.1.7	5000	1
2021.9.14	5000	1
2021.8.31	5000	1
2021.8.3	5000	1
2021.8.17	5000	1
2021.7.7	5000	1
2021.7.21	5000	1
2021.6.28	4000	1
2021.2.18	10000	1
2021.12.8	5000	1
2021.12.23	5000	1
2021.12.1	5000	1
2021.11.24	5000	1
2021.11.10	5000	1
2021.10.13	5000	1
2020.12.31	5000	1
2020.12.22	5000	1
2020.12.14	10000	1
2020.12.14	5000	1
2019.6.13	30000	1
2019.1.17	20000	1
2018.8.6	30000	1
2018.7.19	491.07	1
2018.3.14	29961.48	1
2018.2.28	29961.48	1
2018.2.27	14000	1
2018.12.12	1000	1
2017.10.27	6234	1
2017.1.3	29972	1
2017.1.18	19972	1
2016.7.5	12176.09	1
2016.5.31	15993	1
2016.5.31	49972	1
2016.3.21	24972	1
2016.3.21	49972	1
2016.10.17	19805.96	1
2015.7.2	212907	0
2016.5.12	152081	0
2016.11.27	70500	0
2015.12.3	107995	0
2017.3.14	40267.76	0
"""

# 新增的年度调整数据表文本
annual_adjustment_text = """
2017	16900
2018	47810
2019	-74912.14
2020	0
2021	1570
2022	-31617.86
2023	3520
2024	-2440
"""

def parse_data(text_data):
    """解析原始文本数据 (与之前相同)"""
    parsed_records = []
    lines = text_data.strip().split('\n')
    for line in lines:
        if not line.strip():
            continue
        parts = line.split('\t')
        try:
            date_str = parts[0]
            value = float(parts[1])
            flag = int(parts[2]) # 0 for add, 1 for subtract
            record_date = datetime.strptime(date_str, '%Y.%m.%d').date()
            parsed_records.append({
                "date": record_date,
                "value": value,
                "flag": flag
            })
        except (IndexError, ValueError) as e:
            print(f"警告：跳过格式错误的原始数据行: '{line}' - 错误: {e}")
            continue
    return parsed_records

def parse_annual_adjustments(text_data):
    """解析年度调整数据"""
    adjustments = {}
    lines = text_data.strip().split('\n')
    for line in lines:
        if not line.strip():
            continue
        parts = line.split('\t')
        try:
            year = int(parts[0])
            value = float(parts[1])
            adjustments[year] = value
        except (IndexError, ValueError) as e:
            print(f"警告：跳过格式错误的年度调整行: '{line}' - 错误: {e}")
            continue
    return adjustments

def is_leap(year):
    """判断是否为闰年"""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

def generate_daily_values_csv(records, annual_adjustments_data, output_filepath):
    """
    根据交易记录和年度调整生成每日累计值，并保存到 CSV 文件。
    """
    if not records:
        print("没有可处理的原始记录。")
        return

    # 2. 按日期排序原始记录
    records.sort(key=lambda r: r["date"])

    # 3. 计算每日交易变动总和 (与之前相同)
    daily_transaction_changes = {}
    for record in records:
        change = record["value"] if record["flag"] == 0 else -record["value"]
        if record["date"] in daily_transaction_changes:
            daily_transaction_changes[record["date"]] += change
        else:
            daily_transaction_changes[record["date"]] = change

    # 预计算每年的每日整数调整值 (针对2017年及以后)
    yearly_daily_integer_adjustment = {}
    for year, total_adjustment in annual_adjustments_data.items():
        if year >= 2017:
            days_in_year = 366 if is_leap(year) else 365
            # 计算每日调整值并取整数部分
            daily_adj_int = int(total_adjustment / days_in_year)
            yearly_daily_integer_adjustment[year] = daily_adj_int
            # print(f"调试：{year}年，总调整 {total_adjustment}, 每日整数调整 {daily_adj_int} (天数: {days_in_year})")


    # 4. 确定日期范围
    start_date = records[0]["date"] # 最早的交易日期
    end_date = date.today()         # 系统当前日期

    # 5. 生成每日数据
    all_daily_data = []
    current_total_value = 0.0
    current_date_iterator = start_date

    while current_date_iterator <= end_date:
        # A. 应用来自原始交易记录的变动
        if current_date_iterator in daily_transaction_changes:
            current_total_value += daily_transaction_changes[current_date_iterator]

        # B. 应用年度每日平均调整 (从2017年开始)
        current_year = current_date_iterator.year
        if current_year >= 2017 and current_year in yearly_daily_integer_adjustment:
            current_total_value += yearly_daily_integer_adjustment[current_year]

        all_daily_data.append({
            "date": current_date_iterator.strftime('%Y-%m-%d'),
            "value": round(current_total_value, 2) # 最终结果保留两位小数
        })

        current_date_iterator += timedelta(days=1)

    # 6. 写入 CSV 文件 (与之前相同)
    try:
        output_dir = os.path.dirname(output_filepath)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(output_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Date', 'Value']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row_data in all_daily_data:
                writer.writerow({'Date': row_data['date'], 'Value': row_data['value']})
        print(f"成功生成 CSV 文件: {output_filepath}")

    except IOError as e:
        print(f"写入 CSV 文件时发生错误: {e}")
    except Exception as e:
        print(f"发生意外错误: {e}")


if __name__ == "__main__":
    # 解析原始交易数据
    parsed_records = parse_data(data_text)

    # 解析年度调整数据
    annual_adjustments = parse_annual_adjustments(annual_adjustment_text)

    # 指定输出文件路径
    output_file = "/Users/yanzhang/Downloads/daily_data_adjusted.csv" # 修改了文件名以作区分
    
    # # 更通用的下载文件夹路径获取方式
    # from pathlib import Path
    # downloads_path = str(Path.home() / "Downloads")
    # output_file = os.path.join(downloads_path, "daily_data_adjusted.csv")
    # print(f"将尝试保存到: {output_file}")

    # 生成并保存 CSV
    if parsed_records: # 确保有数据可处理
        generate_daily_values_csv(parsed_records, annual_adjustments, output_file)
    else:
        print("没有解析到有效的原始交易数据，无法生成报告。")