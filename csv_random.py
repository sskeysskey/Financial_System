import pandas as pd
import datetime
import random

def generate_financial_data_csv(fixed_data_str, overall_start_str, overall_end_str):
    """
    生成符合规则的金融数据CSV内容。

    Args:
        fixed_data_str (str): 包含固定日期和数值的多行字符串。
        overall_start_str (str): 数据生成的总体开始日期字符串 (YYYY.M.D)。
        overall_end_str (str): 数据生成的总体结束日期字符串 (YYYY.M.D)。

    Returns:
        str: CSV格式的字符串。
    """

    def parse_date_str(date_str):
        return datetime.datetime.strptime(date_str, "%Y.%m.%d").date()

    raw_fixed_data = {}
    for line in fixed_data_str.strip().split('\n'):
        if '\t' in line:
            date_str, value_str = line.split('\t')
            try:
                raw_fixed_data[parse_date_str(date_str)] = float(value_str)
            except ValueError:
                print(f"警告: 无法解析固定数据行: {line}")
                continue
    
    overall_start_date = parse_date_str(overall_start_str)
    overall_end_date = parse_date_str(overall_end_str)

    # 确保总体开始和结束日期也在固定数据中（如果它们有预设值）
    # 如果 overall_start_date 或 overall_end_date 不在 raw_fixed_data 中，
    # 并且它们是整个数据范围的边界，我们需要确保它们被视为锚点。
    # 题目已提供 overall_end_date 的值，start_date 也是。
    # 所以 raw_fixed_data 应该已经包含了它们。

    def is_business_day(date_obj):
        if date_obj.weekday() >= 5:  # 0是周一, 5是周六, 6是周日
            return False
        if date_obj.month == 12 and date_obj.day == 25:  # 圣诞节
            return False
        return True

    # 最终数据存储，以日期对象为键，方便去重和排序
    final_data_points = {}

    # 1. 将所有固定数据点加入，这些是最高优先级的
    for date_obj, value in raw_fixed_data.items():
        if overall_start_date <= date_obj <= overall_end_date:
            final_data_points[date_obj] = round(value, 2)

    # 2. 创建锚点日期列表：包括所有固定日期点以及总体起止日期，并排序去重
    anchor_dates = sorted(list(set(
        [overall_start_date] +
        [d for d in raw_fixed_data.keys() if overall_start_date <= d <= overall_end_date] +
        [overall_end_date]
    )))
    
    # 确保所有锚点都有值，对于 overall_start_date 和 overall_end_date，如果它们没有在
    # raw_fixed_data 中提供，则需要特殊处理（但根据题目，它们是提供的）
    if overall_start_date not in final_data_points and overall_start_date in raw_fixed_data:
         final_data_points[overall_start_date] = round(raw_fixed_data[overall_start_date],2)
    if overall_end_date not in final_data_points and overall_end_date in raw_fixed_data:
         final_data_points[overall_end_date] = round(raw_fixed_data[overall_end_date],2)


    # 3. 遍历每两个相邻锚点日期之间的时段进行插值
    for i in range(len(anchor_dates) - 1):
        period_start_anchor_date = anchor_dates[i]
        period_end_anchor_date = anchor_dates[i+1]

        # 获取这两个锚点的值
        # 如果锚点不存在于 final_data_points (理论上不应该，因为已经预填充)，则跳过
        if period_start_anchor_date not in final_data_points or period_end_anchor_date not in final_data_points:
            print(f"警告: 锚点 {period_start_anchor_date} 或 {period_end_anchor_date} 缺失数值，跳过此区间。")
            continue
            
        val_start_period = final_data_points[period_start_anchor_date]
        val_end_target_period = final_data_points[period_end_anchor_date]

        # 收集这两个锚点之间所有需要填充的工作日
        # 从 period_start_anchor_date 的后一天开始，到 period_end_anchor_date 的前一天结束
        business_days_to_fill_in_period = []
        current_iter_date = period_start_anchor_date + datetime.timedelta(days=1)
        while current_iter_date < period_end_anchor_date:
            if is_business_day(current_iter_date):
                business_days_to_fill_in_period.append(current_iter_date)
            current_iter_date += datetime.timedelta(days=1)

        if not business_days_to_fill_in_period: # 如果两个锚点间没有需要填充的工作日
            continue

        current_interpolated_value = val_start_period
        num_days_to_fill = len(business_days_to_fill_in_period)

        if abs(val_start_period - val_end_target_period) < 0.001 : # 值基本不变的区间
            for day_to_fill in business_days_to_fill_in_period:
                final_data_points[day_to_fill] = round(val_start_period, 2)
        else: # 值变化的区间
            for idx, day_to_fill in enumerate(business_days_to_fill_in_period):
                # 剩余的插值“步骤”数：包括当前正在计算的日期，以及到目标锚点前的所有其他待填充日，
                # 再加上从最后一个待填充日到目标锚点日的“一步”。
                # 例如：S D1 D2 D3 E。 若当前计算D1，则current_interpolated_value是S的值。
                # 目标是E。步骤有 D1, D2, D3, 及 E对D3的最后一步。共4步。
                # (num_days_to_fill - idx) 是剩余的待填充日数 (D1,D2,D3 -> 3个)
                # +1 是指从最后一个填充日 (D3) 到目标锚点 (E) 的那一步。
                num_change_intervals_remaining = (num_days_to_fill - idx) + 1
                
                required_avg_daily_change = (val_end_target_period - current_interpolated_value) / num_change_intervals_remaining

                # 决定随机变动幅度类型
                if random.random() < 0.7: # 70% 的概率小幅波动
                    percentage_variation = random.uniform(0, 0.01) # 0% 到 1%
                else: # 30% 的概率较大幅度波动
                    percentage_variation = random.uniform(0.02, 0.05) # 2% 到 5%
                
                random_direction = random.choice([-1, 1])
                # 随机扰动基于 current_interpolated_value (即前一天的值)
                random_perturbation = current_interpolated_value * percentage_variation * random_direction
                
                next_value = current_interpolated_value + required_avg_daily_change + random_perturbation
                
                # 确保数值合理性，例如不为负 (如果业务逻辑要求)
                if next_value < 0 and val_start_period >=0 and val_end_target_period >=0 : # 假设原始数据非负
                    next_value = max(0.01, next_value + abs(random_perturbation)) # 尝试修正，至少为0.01或取消部分扰动

                final_data_points[day_to_fill] = round(next_value, 2)
                current_interpolated_value = next_value
    
    # 4. 转换成 DataFrame 并排序输出
    if not final_data_points:
        return "date\tvalue\n" # 返回头部，如果没有任何数据点

    output_list = []
    for date_obj in sorted(final_data_points.keys()):
        output_list.append({
            "date": date_obj.strftime("%Y.%m.%d"),
            "value": final_data_points[date_obj]
        })
    
    df = pd.DataFrame(output_list)
    
    # 确保最终输出的日期范围符合 overall_start_date 和 overall_end_date
    # (尽管逻辑上应该已经是这样了，因为锚点包含了它们)
    # 此处不需要再次过滤，因为 final_data_points 的key已经是在范围内了

    return df.to_csv(index=False, sep='\t')

# 您提供的固定数据
fixed_data_input = """2025.5.23	1097.86
2025.1.1	1097.86
2024.1.1	3537.86
2023.1.1	17.86
2022.1.1	31635.72
2021.1.1	30065.72
2020.1.1	30065.72
2019.1.1	104977.86
2018.1.1	57167.86
2017.1.1	40267.86
2016.1.1	40267.86
2015.1.1	40267.86"""

# 设定的总体时间范围
overall_start_date_str = "2015.1.1"
overall_end_date_str = "2025.5.23"

# 生成CSV数据
csv_output = generate_financial_data_csv(fixed_data_input, overall_start_date_str, overall_end_date_str)

# 打印CSV内容 (在实际应用中，您会将其保存到文件)
# print(csv_output)

# 为了让您可以下载，我会将内容包装在一个可下载的链接中
# (注意：实际的下载功能需要前端HTML和可能的服务器端支持，这里仅提供文件内容)
# 如果在Jupyter Notebook或类似环境中，可以直接操作文件。
# 在这个文本界面，我将提供CSV内容，您可以复制粘贴到文件中。

file_content_for_download = csv_output

# 生成CSV数据
csv_output = generate_financial_data_csv(fixed_data_input, overall_start_date_str, overall_end_date_str)

# 保存到文件
file_name = "/Users/yanzhang/Downloads/generated_financial_data.csv"
with open(file_name, "w", encoding="utf-8") as f:
    f.write(csv_output)
print(f"数据已生成并保存到文件: {file_name}")