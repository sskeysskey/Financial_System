import pandas as pd
import numpy as np
import datetime
from io import StringIO

def regenerate_deals_data(csv_content_string):
    """
    根据特定规则重新生成Deals数据。

    规则：
    1. 前两个月：猛涨（剧烈波动，锯齿状上涨）
    2. 接下来两个月：暴跌（剧烈波动，锯齿状下跌）
    3. 后面平静三个月：细微波动（2-5%幅度），稳中有升
    4. 然后震荡上行至最后一天的数据：曲曲折折，无特定规律，混乱
    保持第一天和最后一天数据不变。
    """
    # 使用 StringIO 来模拟文件读取
    df = pd.read_csv(StringIO(csv_content_string))
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by='Date').reset_index(drop=True) # 确保数据按日期排序

    if len(df) < 4: # 需要足够的数据点来划分阶段
        print("数据点过少，无法按规则划分阶段。")
        return df.to_csv(index=False)

    original_df = df.copy()
    first_row = original_df.iloc[0].copy()
    last_row = original_df.iloc[-1].copy()

    # 定义新的数据列表，首先放入第一行
    new_data_rows = [{'Date': first_row['Date'], 'Value': first_row['Value']}]
    
    # 获取所有日期，用于确定阶段边界的索引
    all_dates = list(original_df['Date'])
    idx_first = 0
    idx_last = len(all_dates) - 1

    # --- 确定各阶段的结束日期索引 ---
    # 假设数据是连续的交易日数据
    # Phase 1 (猛涨): 前两个月. 找到原始数据中第二个月的最后一天
    # 我们需要找到数据中实际存在的日期来划分
    
    # 找到第一个日期
    start_date = all_dates[idx_first]

    # Phase 1 end: 第一个日期后推两个月，然后找到数据中不晚于此的最后一个日期
    # 注意：这里简单地按索引划分月份可能不精确，更精确的方法是按日期的月份
    # 为了简化，我们大致按数据点数量划分，或按实际月份
    
    # 找到第一个月结束后的索引 (近似)
    # 实际操作中，最好根据日期的月份来确定
    # 例如，如果第一个日期是 YYYY-MM-DD, 那么两个月后是 YYYY-(MM+2)-DD
    
    # 确定各阶段的结束日期在 all_dates 中的索引
    # Phase 1 (猛涨): 前两个月 (例如 Jan, Feb)
    # 找到 Feb 2023 在数据中的最后一天
    # 注意：这里假设数据从2023年开始，与示例数据一致
    try:
        p1_month_end_target = start_date.replace(month=start_date.month + 2, day=1) - datetime.timedelta(days=1)
    except ValueError: # 处理跨年情况，例如11月或12月开始
        if start_date.month == 11:
            p1_month_end_target = start_date.replace(year=start_date.year + 1, month=1, day=1) - datetime.timedelta(days=1)
        elif start_date.month == 12:
            p1_month_end_target = start_date.replace(year=start_date.year + 1, month=2, day=1) - datetime.timedelta(days=1)
        else: # Should not happen for Jan-Oct start
            p1_month_end_target = start_date + datetime.timedelta(days=60) # Fallback: approx 2 months

    idx_p1_end = idx_first
    for i in range(idx_first + 1, idx_last):
        if all_dates[i].year > p1_month_end_target.year or \
           (all_dates[i].year == p1_month_end_target.year and all_dates[i].month > p1_month_end_target.month):
            break
        idx_p1_end = i
    if idx_p1_end <= idx_first + 5: # 确保第一阶段至少有几个数据点
        idx_p1_end = min(idx_last - 4, idx_first + int((idx_last - idx_first) * 0.15)) # 大约占15%的数据

    # Phase 2 (暴跌): 接下来两个月 (例如 Mar, Apr)
    try:
        p2_month_end_target = all_dates[idx_p1_end].replace(month=all_dates[idx_p1_end].month + 2, day=1) - datetime.timedelta(days=1)
    except ValueError:
        if all_dates[idx_p1_end].month == 11:
             p2_month_end_target = all_dates[idx_p1_end].replace(year=all_dates[idx_p1_end].year + 1, month=1, day=1) - datetime.timedelta(days=1)
        elif all_dates[idx_p1_end].month == 12:
             p2_month_end_target = all_dates[idx_p1_end].replace(year=all_dates[idx_p1_end].year + 1, month=2, day=1) - datetime.timedelta(days=1)
        else:
            p2_month_end_target = all_dates[idx_p1_end] + datetime.timedelta(days=60)


    idx_p2_end = idx_p1_end
    for i in range(idx_p1_end + 1, idx_last):
        if all_dates[i].year > p2_month_end_target.year or \
           (all_dates[i].year == p2_month_end_target.year and all_dates[i].month > p2_month_end_target.month):
            break
        idx_p2_end = i
    if idx_p2_end <= idx_p1_end + 5:
         idx_p2_end = min(idx_last - 3, idx_p1_end + int((idx_last - idx_first) * 0.15))


    # Phase 3 (平静): 接下来三个月 (例如 May, Jun, Jul)
    try:
        p3_month_end_target = all_dates[idx_p2_end].replace(month=all_dates[idx_p2_end].month + 3, day=1) - datetime.timedelta(days=1)
    except ValueError: # Handle month overflow
        new_month = all_dates[idx_p2_end].month + 3
        new_year = all_dates[idx_p2_end].year
        if new_month > 12:
            new_year += (new_month -1) // 12
            new_month = (new_month -1) % 12 + 1
        p3_month_end_target = datetime.datetime(new_year, new_month, 1) - datetime.timedelta(days=1)


    idx_p3_end = idx_p2_end
    for i in range(idx_p2_end + 1, idx_last):
        if all_dates[i].year > p3_month_end_target.year or \
           (all_dates[i].year == p3_month_end_target.year and all_dates[i].month > p3_month_end_target.month):
            break
        idx_p3_end = i
    if idx_p3_end <= idx_p2_end + 5:
        idx_p3_end = min(idx_last - 2, idx_p2_end + int((idx_last - idx_first) * 0.25))
        
    # 确保索引不重复且有意义
    if not (idx_first < idx_p1_end < idx_p2_end < idx_p3_end < idx_last -1) :
        # 如果自动划分不理想，采用按比例划分
        total_intermediate_points = idx_last - idx_first - 1
        if total_intermediate_points < 4:
             print("中间数据点过少，无法有效划分阶段。")
             # 简单处理：线性插值或保持原样（除了首尾）
             for k_idx in range(idx_first + 1, idx_last):
                 frac = (k_idx - idx_first) / (idx_last - idx_first)
                 val = first_row['Value'] + frac * (last_row['Value'] - first_row['Value'])
                 new_data_rows.append({'Date': all_dates[k_idx], 'Value': round(val,2)})
             new_data_rows.append({'Date': last_row['Date'], 'Value': last_row['Value']})
             return pd.DataFrame(new_data_rows).to_csv(index=False)


        # 按大致比例划分，例如 P1: 2/10, P2: 2/10, P3: 3/10, P4: 3/10 of intermediate points
        p1_len = int(total_intermediate_points * 0.2) # 2 months out of ~10-11 working months
        p2_len = int(total_intermediate_points * 0.2)
        p3_len = int(total_intermediate_points * 0.25) # 3 months

        idx_p1_end = idx_first + p1_len
        idx_p2_end = idx_p1_end + p2_len
        idx_p3_end = idx_p2_end + p3_len
        
        # 确保最后阶段有足够点数
        if idx_p3_end >= idx_last - 2: # 至少为P4留2个点
            idx_p3_end = idx_last - 3
            if idx_p2_end >= idx_p3_end -1: idx_p2_end = idx_p3_end -2
            if idx_p1_end >= idx_p2_end -1: idx_p1_end = idx_p2_end -2
            if idx_p1_end <= idx_first: idx_p1_end = idx_first + 1 # 确保P1至少有一个点
        
        if not (idx_first < idx_p1_end < idx_p2_end < idx_p3_end < idx_last -1):
            print(f"警告: 阶段索引划分不理想。 idx_first:{idx_first}, p1:{idx_p1_end}, p2:{idx_p2_end}, p3:{idx_p3_end}, last-1:{idx_last-1}")
            # 进一步的应急处理：如果还是不行，就只能做最简单的处理了
            # （此处省略更复杂的应急，假设数据量足够形成阶段）


    current_value = first_row['Value']
    generated_intermediate_values = []

    # --- 设定各阶段目标值（这些是大致引导，实际会因波动而变化）---
    # 这些目标需要根据数据的实际范围和最终值来合理设定
    # 初始值: first_row['Value'], 最终值: last_row['Value']
    # 假设初始值较小，最终值较大
    target_p1_end_val = current_value * np.random.uniform(15, 40) # 猛涨15-40倍
    if last_row['Value'] > current_value * 5: # 如果最终值远大于初始值
        target_p1_end_val = max(current_value * np.random.uniform(5,15), min(last_row['Value']*0.2, current_value * 40)) # 猛涨，但不超过最终值的20%或初始值的40倍
    else: # 如果最终值和初始值差距不大
        target_p1_end_val = current_value * np.random.uniform(1.5, 3)


    target_p2_end_val = target_p1_end_val * np.random.uniform(0.1, 0.3) # 暴跌到P1峰值的10%-30%
    target_p2_end_val = max(target_p2_end_val, first_row['Value'] * 0.5, 1.0) # 不跌破初始值的一半或1

    target_p3_end_val = target_p2_end_val * np.random.uniform(1.1, 1.5) # 平稳上涨10%-50%
    target_p3_end_val = max(target_p3_end_val, 1.0)


    # --- Phase 1: 猛涨 (idx_first + 1 到 idx_p1_end) ---
    num_days_p1 = idx_p1_end - (idx_first + 1) + 1
    if num_days_p1 > 0:
        for i in range(num_days_p1):
            remaining_days = num_days_p1 - i
            # 目标每日增量，引导向 target_p1_end_val
            target_daily_increment = (target_p1_end_val - current_value) / remaining_days if remaining_days > 0 else 0
            
            # 剧烈波动：允许大幅正向波动，少量负向波动制造锯齿
            # 波动范围可以是当前值的百分比
            volatility = current_value * np.random.uniform(-0.10, 0.30) # 例如 -10% 到 +30%
            
            current_value += target_daily_increment + volatility
            if current_value <= 0.1: current_value = 0.1 # 防止过低
            generated_intermediate_values.append(current_value)

    # --- Phase 2: 暴跌 (idx_p1_end + 1 到 idx_p2_end) ---
    num_days_p2 = idx_p2_end - (idx_p1_end + 1) + 1
    if num_days_p2 > 0:
        for i in range(num_days_p2):
            remaining_days = num_days_p2 - i
            target_daily_increment = (target_p2_end_val - current_value) / remaining_days if remaining_days > 0 else 0
            
            # 剧烈波动：允许大幅负向波动，少量正向波动制造锯齿
            volatility = current_value * np.random.uniform(-0.30, 0.10) # 例如 -30% 到 +10%
            
            current_value += target_daily_increment + volatility
            if current_value <= 0.1: current_value = 0.1
            generated_intermediate_values.append(current_value)

    # --- Phase 3: 平静期 (idx_p2_end + 1 到 idx_p3_end) ---
    num_days_p3 = idx_p3_end - (idx_p2_end + 1) + 1
    if num_days_p3 > 0:
        for i in range(num_days_p3):
            remaining_days = num_days_p3 - i
            # 目标每日增量，引导向 target_p3_end_val (稳中有升)
            target_daily_increment = (target_p3_end_val - current_value) / remaining_days if remaining_days > 0 else 0
            
            # 细微波动 (2-5% 幅度): 日波动应更小
            # 幅度指整个阶段的波动范围，日波动控制在 +/- 0.5% 到 1.5%
            daily_fluctuation_pct = (np.random.rand() - 0.5) * 2 * np.random.uniform(0.005, 0.025) # +/- 0.5% to 2.5%
            fluctuation = current_value * daily_fluctuation_pct
            
            # 稳中有升的微小正向偏置
            slight_upward_bias = current_value * np.random.uniform(0.0005, 0.0015) # 每日0.05%-0.15%的微升
            
            current_value += target_daily_increment + fluctuation + slight_upward_bias
            if current_value <= 0.1: current_value = 0.1
            generated_intermediate_values.append(current_value)

    # --- Phase 4: 震荡上行至最后 (idx_p3_end + 1 到 idx_last - 1) ---
    num_days_p4 = (idx_last - 1) - (idx_p3_end + 1) + 1
    target_final_val_for_phase4 = last_row['Value'] # 最终目标是原始数据的最后一天数值
    
    if num_days_p4 > 0:
        for i in range(num_days_p4):
            remaining_days = num_days_p4 - i
            # 目标每日增量，引导向 target_final_val_for_phase4
            target_daily_increment = (target_final_val_for_phase4 - current_value) / remaining_days if remaining_days > 0 else 0
            
            # 混乱、曲曲折折的波动：幅度较大，方向不定，但整体受 target_daily_increment 牵引向上
            # 基础波动范围
            base_volatility_range = np.random.uniform(0.05, 0.20) # 例如 +/- 5% 到 20%
            volatility = current_value * base_volatility_range * np.random.choice([-1, 1])
            
            # 随机出现更大的冲击，增加混乱度
            if np.random.rand() < 0.15: # 15% 的概率发生更大冲击
                volatility *= np.random.uniform(1.5, 3.0)
            
            current_value += target_daily_increment + volatility
            
            # 防止跌得过低，尤其是在接近最终高值时
            if target_final_val_for_phase4 > 10 and current_value < 0.05 * target_final_val_for_phase4 :
                 current_value = previous_value * np.random.uniform(0.9,1.05) # 尝试恢复
                 if current_value <=0: current_value = 0.05 * target_final_val_for_phase4
            elif current_value <= 0.1:
                 current_value = 0.1 # 一般性保底

            generated_intermediate_values.append(current_value)
            previous_value = current_value # 用于极端情况下的恢复

    # --- 组装最终数据 ---
    # 添加生成的中间数据
    intermediate_dates = all_dates[idx_first + 1 : idx_last]
    if len(generated_intermediate_values) == len(intermediate_dates):
        for date_val, gen_val in zip(intermediate_dates, generated_intermediate_values):
            new_data_rows.append({'Date': date_val, 'Value': round(gen_val, 2)})
    else:
        # 如果长度不匹配（通常由于阶段划分问题导致某阶段天数为0），则进行线性插值作为后备
        print(f"警告: 生成数据点数量 ({len(generated_intermediate_values)}) 与预期中间日期数量 ({len(intermediate_dates)}) 不符。采用线性插值。")
        # 清理已添加的部分中间数据，重新插值
        new_data_rows = [{'Date': first_row['Date'], 'Value': first_row['Value']}] # 重置
        val_before_interp = first_row['Value']
        val_after_interp = last_row['Value']
        num_interp_points = idx_last - (idx_first + 1) +1 -1 # number of points to fill

        if num_interp_points > 0:
            for i_interp, date_val_interp in enumerate(intermediate_dates):
                fraction = (i_interp + 1) / (num_interp_points + 1)
                interpolated_value = val_before_interp + fraction * (val_after_interp - val_before_interp)
                new_data_rows.append({'Date': date_val_interp, 'Value': round(interpolated_value, 2)})


    # 添加最后一行原始数据
    new_data_rows.append({'Date': last_row['Date'], 'Value': last_row['Value']})

    final_df = pd.DataFrame(new_data_rows)
    return final_df.to_csv(index=False)

# --- 使用您提供的 Deals.csv 内容 ---
deals_csv_content = """Date,Value
2023-01-03,18.37
2023-01-04,18.62
2023-01-05,18.34
2023-01-06,18.63
2023-01-09,18.88
2023-01-10,19.33
2023-01-11,20.65
2023-01-12,21.12
2023-01-13,21.68
2023-01-17,22.07
2023-01-18,22.33
2023-01-19,22.73
2023-01-20,23.41
2023-01-23,23.92
2023-01-24,24.65
2023-01-25,25.06
2023-01-26,25.4
2023-01-27,28.38
2023-01-30,31.5
2023-01-31,32.22
2023-02-01,33.15
2023-02-02,36.87
2023-02-03,40.66
2023-02-06,41.82
2023-02-07,40.29
2023-02-08,41.07
2023-02-09,41.73
2023-02-10,42.82
2023-02-13,43.59
2023-02-14,40.2
2023-02-15,42.26
2023-02-16,38.95
2023-02-17,39.61
2023-02-21,44.39
2023-02-22,45.32
2023-02-23,46.13
2023-02-24,46.88
2023-02-27,49.2
2023-02-28,50.34
2023-03-01,55.2
2023-03-02,56.78
2023-03-03,54.15
2023-03-06,54.98
2023-03-07,59.31
2023-03-08,60.46
2023-03-09,61.89
2023-03-10,63.0
2023-03-13,64.55
2023-03-14,66.23
2023-03-15,72.72
2023-03-16,74.68
2023-03-17,75.81
2023-03-20,77.33
2023-03-21,79.47
2023-03-22,81.74
2023-03-23,82.61
2023-03-24,83.9
2023-03-27,85.19
2023-03-28,83.91
2023-03-29,84.93
2023-03-30,86.86
2023-03-31,88.54
2023-04-03,88.2
2023-04-04,89.2
2023-04-05,91.82
2023-04-06,93.32
2023-04-10,109.43
2023-04-11,104.34
2023-04-12,106.28
2023-04-13,101.17
2023-04-14,98.29
2023-04-17,100.73
2023-04-18,110.41
2023-04-19,112.83
2023-04-20,119.87
2023-04-21,122.3
2023-04-24,120.13
2023-04-25,122.33
2023-04-26,125.22
2023-04-27,126.99
2023-04-28,139.31
2023-05-01,143.05
2023-05-02,151.39
2023-05-03,153.11
2023-05-04,156.1
2023-05-05,160.14
2023-05-08,164.19
2023-05-09,167.72
2023-05-10,171.27
2023-05-11,169.77
2023-05-12,174.59
2023-05-15,177.75
2023-05-16,181.75
2023-05-17,173.59
2023-05-18,189.31
2023-05-19,192.83
2023-05-22,195.48
2023-05-23,182.1
2023-05-24,184.5
2023-05-25,186.69
2023-05-26,203.09
2023-05-30,207.51
2023-05-31,210.88
2023-06-01,213.59
2023-06-02,215.74
2023-06-05,218.83
2023-06-06,223.1
2023-06-07,224.56
2023-06-08,228.1
2023-06-09,230.57
2023-06-12,231.92
2023-06-13,235.15
2023-06-14,238.54
2023-06-15,242.32
2023-06-16,253.41
2023-06-20,259.98
2023-06-21,266.48
2023-06-22,271.26
2023-06-23,276.9
2023-06-26,284.29
2023-06-27,290.59
2023-06-28,296.93
2023-06-29,302.91
2023-06-30,308.15
2023-07-03,297.11
2023-07-05,302.64
2023-07-06,309.92
2023-07-07,313.16
2023-07-10,316.65
2023-07-11,322.04
2023-07-12,327.86
2023-07-13,333.81
2023-07-14,324.22
2023-07-17,303.85
2023-07-18,307.46
2023-07-19,311.41
2023-07-20,288.1
2023-07-21,295.45
2023-07-24,300.77
2023-07-25,310.55
2023-07-26,297.39
2023-07-27,307.18
2023-07-28,312.01
2023-07-31,319.75
2023-08-01,328.37
2023-08-02,368.86
2023-08-03,365.75
2023-08-04,372.05
2023-08-07,378.82
2023-08-08,390.71
2023-08-09,401.76
2023-08-10,410.39
2023-08-11,399.87
2023-08-14,391.13
2023-08-15,404.04
2023-08-16,412.35
2023-08-17,424.01
2023-08-18,470.33
2023-08-21,479.39
2023-08-22,487.9
2023-08-23,464.12
2023-08-24,513.69
2023-08-25,522.78
2023-08-28,535.8
2023-08-29,499.0
2023-08-30,514.6
2023-08-31,523.88
2023-09-01,538.91
2023-09-05,554.6
2023-09-06,563.35
2023-09-07,564.59
2023-09-08,598.65
2023-09-11,609.02
2023-09-12,629.4
2023-09-13,670.05
2023-09-14,687.95
2023-09-15,702.51
2023-09-18,723.55
2023-09-19,745.92
2023-09-20,739.76
2023-09-21,763.34
2023-09-22,753.86
2023-09-25,738.39
2023-09-26,761.35
2023-09-27,762.12
2023-09-28,774.45
2023-09-29,799.91
2023-10-02,815.76
2023-10-03,775.3
2023-10-04,797.46
2023-10-05,811.79
2023-10-06,851.85
2023-10-10,879.06
2023-10-11,899.02
2023-10-12,871.42
2023-10-13,832.64
2023-10-16,906.11
2023-10-17,970.28
2023-10-18,987.64
2023-10-19,1010.72
2023-10-20,1084.01
2023-10-23,1104.9
2023-10-24,1102.16
2023-10-25,1027.59
2023-10-26,1056.5
2023-10-27,1084.67
2023-10-30,1039.79
2023-10-31,1079.61
2023-11-01,1006.1
2023-11-02,1042.84
2023-11-03,1070.49
2023-11-06,1096.35
2023-11-07,1223.56
2023-11-08,1254.77
2023-11-09,1252.25
2023-11-13,1358.61
2023-11-14,1520.42
2023-11-15,1565.19
2023-11-16,1599.26
2023-11-17,1500.39
2023-11-20,1560.19
2023-11-21,1621.67
2023-11-22,1670.49
2023-11-24,1726.78
2023-11-27,1665.59
2023-11-28,1761.01
2023-11-29,1825.87
2023-11-30,1881.06
2023-12-01,1924.16
2023-12-04,1978.46
2023-12-05,2026.47
2023-12-06,2087.9
2023-12-07,2170.14
2023-12-08,2047.15
2023-12-11,2025.12
2023-12-12,2254.73
2023-12-13,2338.64
2023-12-14,2224.47
2023-12-15,2312.15
2023-12-18,2406.5
2023-12-19,2325.5
2023-12-20,2483.26
2023-12-21,2645.79
2023-12-22,2981.32
2023-12-26,3093.99
2023-12-27,3128.1
2023-12-28,3276.04
2023-12-29,3537.86
"""

# 调用函数并打印结果
# np.random.seed(42) # 如果需要可复现的结果，可以设置随机种子
new_csv_data = regenerate_deals_data(deals_csv_content)
print("\n调整后的数据 (CSV格式):\n")
print(new_csv_data)

# 如果想将结果保存到文件：
with open("/Users/yanzhang/Downloads/Deals_modified.csv", "w") as f:
    f.write(new_csv_data)
    print("\n数据已保存到 Deals_modified.csv")

# 也可以将结果转换为 DataFrame 进行查看或绘图
result_df = pd.read_csv(StringIO(new_csv_data))
print("\n调整后的数据 (DataFrame):\n")
print(result_df.head())
print("...")
print(result_df.tail())

import matplotlib.pyplot as plt
if 'Date' in result_df.columns and 'Value' in result_df.columns:
    result_df['Date'] = pd.to_datetime(result_df['Date'])
    plt.figure(figsize=(12,6))
    plt.plot(result_df['Date'], result_df['Value'])
    plt.title("调整后的数据走势")
    plt.xlabel("日期")
    plt.ylabel("数值")
    plt.grid(True)
    plt.show()