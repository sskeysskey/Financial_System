import datetime
import random
import csv
import os
import holidays # pip install holidays

def get_actual_trading_day(year, month, day, us_holidays):
    """
    获取指定日期或其后的第一个有效交易日。
    """
    current_date = datetime.date(year, month, day)
    # 确保 current_date 至少是 (year, month, day)
    # 如果 (year, month, day) 本身就是交易日，则直接返回
    if current_date.weekday() < 5 and current_date not in us_holidays:
        pass # 将在下面的循环中被正确处理或跳过
        
    while current_date.weekday() >= 5 or current_date in us_holidays: # 5=Saturday, 6=Sunday
        current_date += datetime.timedelta(days=1)
    return current_date

def generate_financial_data(output_path, start_data_tuple, end_data_tuple):
    """
    生成模拟的财务数据并保存为CSV文件。

    Args:
        output_path (str): CSV文件的输出路径。
        start_data_tuple (tuple): (年, 月, 日, 初始值) e.g., (2022, 1, 1, 31635.72)
        end_data_tuple (tuple): (年, 月, 日, 最终值) e.g., (2023, 1, 1, 17.86)
    """
    # --- 配置参数 ---
    # 从元组中解包数据
    start_year, start_month, start_day, start_value = start_data_tuple
    end_year, end_month, end_day, end_value = end_data_tuple

    # 获取美国2022年和2023年的节假日
    # 为了更准确，包含起始年份和结束年份
    relevant_years = list(range(start_year, end_year + 1))
    us_holidays = holidays.US(years=relevant_years)

    # 确定实际的开始和结束交易日
    # actual_start_date 是 2022.1.1 或其后的第一个交易日
    actual_start_date = get_actual_trading_day(start_year, start_month, start_day, us_holidays)
    # actual_end_date 是 2023.1.1 或其后的第一个交易日
    actual_end_date = get_actual_trading_day(end_year, end_month, end_day, us_holidays)


    print(f"数据将从实际交易日 {actual_start_date} (值: {start_value}) 开始")
    print(f"到实际交易日 {actual_end_date} (值: {end_value}) 结束")

    # 生成此期间的所有交易日
    # 交易日列表应包含 actual_start_date，并一直到 actual_end_date（包含）
    trading_dates = []
    current_iter_date = actual_start_date
    while current_iter_date <= actual_end_date: # 包含 actual_end_date
        if current_iter_date.weekday() < 5 and current_iter_date not in us_holidays: # 周一到周五且非假期
            trading_dates.append(current_iter_date)
        current_iter_date += datetime.timedelta(days=1)

    if not trading_dates:
        print("在指定日期范围内没有找到交易日。")
        return
    
    # 校验 trading_dates 是否正确地以 actual_start_date 开始，并以 actual_end_date 结束
    if trading_dates[0] != actual_start_date:
        print(f"警告: 生成的交易日列表的第一个日期 {trading_dates[0]} 与期望的开始交易日 {actual_start_date} 不符。请检查节假日逻辑。")
        # 如果 actual_start_date 本身是交易日但未被包含，则强制加入
        if actual_start_date.weekday() < 5 and actual_start_date not in us_holidays and actual_start_date not in trading_dates:
            trading_dates.insert(0, actual_start_date)
            trading_dates.sort() # 保持有序
        # return # 或者直接退出，因为这可能表示逻辑错误

    if trading_dates[-1] != actual_end_date:
        print(f"警告: 生成的交易日列表的最后一个日期 {trading_dates[-1]} 与期望的结束交易日 {actual_end_date} 不符。请检查节假日逻辑。")
        # 如果 actual_end_date 本身是交易日但未被包含，则强制加入
        if actual_end_date.weekday() < 5 and actual_end_date not in us_holidays and actual_end_date not in trading_dates:
            trading_dates.append(actual_end_date)
            trading_dates.sort() # 保持有序
        # return

    print(f"共找到 {len(trading_dates)} 个交易日，从 {trading_dates[0]} 到 {trading_dates[-1]}")
    if len(trading_dates) < 2:
        print("交易日数量不足以生成数据（至少需要两个交易日：开始和结束）。")
        if len(trading_dates) == 1 and trading_dates[0] == actual_start_date and actual_start_date == actual_end_date:
             # 如果开始和结束是同一天，只输出一个数据点
             data_points = [(actual_start_date, start_value)] # 或者应该是 end_value，取决于如何定义
             # 按照题目，如果2022.1.1和2023.1.1是同一个交易日，那么值应该是17.86
             # 但这里 start_value 和 end_value 不同，所以这种情况不应该发生
             # 如果它们解析为同一个交易日，则以 end_value 为准（因为是“到达”目标）
             # 但我们的 actual_start_date 和 actual_end_date 是不同的年份，所以不会是同一个交易日
        else:
            return


    # --- 数据生成 ---
    data_points = []
    current_value = start_value
    # 第一个数据点是 actual_start_date 和 start_value
    data_points.append((trading_dates[0], round(start_value, 2)))

    num_steps = len(trading_dates) - 1 # 从第一个点到最后一个点需要的步数

    for i in range(num_steps):
        value_today = current_value # 这是 trading_dates[i] 的值
        # date_today = trading_dates[i] # 当前日期

        # 下一个目标日期是 trading_dates[i+1]
        # 如果这是最后一步 (i == num_steps - 1)，那么 trading_dates[i+1] 就是 actual_end_date
        # 它的值必须是 end_value
        if i == num_steps - 1:
            next_value = end_value
        else:
            # 对于中间的每一步
            remaining_steps_to_target = num_steps - i # 到达最终目标 end_value 还有多少步
            
            # 几何目标因子：为了在剩余步骤中从当前值平滑过渡到最终值 end_value
            if value_today <= 0.0001 and end_value > 0:
                geometric_target_factor = 1.01 # 从极小值/零/负值恢复到正数，尝试小幅增加
            elif value_today <= 0.0001 and end_value <= 0:
                geometric_target_factor = 1.0 # 保持不变或小幅变化
            elif value_today > 0 and (end_value / value_today) < 0 and remaining_steps_to_target % 2 == 0:
                # 当前正，目标负，偶数步，难以平滑开方。股票价格通常不为负。
                # 鉴于题目给的都是正值，此情况理论上不会因几何因子本身发生。
                # 若因波动导致value_today变负，则下面max(next_value, 0.01)会处理。
                # 为避免计算错误，采用绝对值比率并稍后调整方向，或简化为向0衰减。
                # 鉴于目标是17.86，我们假设价格不应为负。
                # 如果value_today意外变为负数，我们希望它能回到正数轨道。
                geometric_target_factor = (abs(end_value / value_today)) ** (1 / remaining_steps_to_target)
                if end_value < value_today: # 如果目标比当前低（通常是这样）
                    geometric_target_factor = min(geometric_target_factor, 1 / geometric_target_factor) # 确保是衰减因子
            elif value_today == 0: # 避免除以零
                if end_value > 0: geometric_target_factor = 1.1 
                elif end_value < 0: geometric_target_factor = 0.9 # 虽然价格不应为负
                else: geometric_target_factor = 1.0
            else: # 正常情况
                ratio = end_value / value_today
                if ratio < 0 and remaining_steps_to_target % 2 == 0:
                    # 再次处理，如果value_today因波动变负，而end_value为正
                    # 尝试让其向正方向恢复
                    geometric_target_factor = (abs(ratio)) ** (1 / remaining_steps_to_target)
                    # 如果 value_today < 0 and end_value > 0, ratio < 0. 我们希望因子 > 1 来增加它
                    # 如果 value_today > 0 and end_value < 0, ratio < 0. 我们希望因子 < 1 来减小它
                    # 这个逻辑复杂，依赖于价格不为负的假设。
                    # 鉴于 start_value 和 end_value 都是正数，主要目标是平滑过渡。
                    # 如果 value_today 意外地因波动变得非常小或负，下面的 max(0.01) 会处理。
                    # 为简化，如果 ratio < 0, 我们用一个小的固定因子使其向0靠近或反弹
                    if value_today < 0 and end_value > 0:
                        geometric_target_factor = 1.05 # 尝试增加
                    elif value_today > 0 and end_value < 0: # 理论上不会发生
                        geometric_target_factor = 0.95 # 尝试减少
                    else: # 同号或其一为0
                         geometric_target_factor = ratio ** (1 / remaining_steps_to_target) if ratio > 0 else 1.0

                else: # ratio >= 0 or remaining_steps_to_target is odd
                    if ratio <=0 : # e.g. end_value is 0, value_today is positive
                        geometric_target_factor = 0.99 # Default to decay if ratio is 0 or negative
                    else:
                        geometric_target_factor = ratio ** (1 / remaining_steps_to_target)


            # 随机波动
            is_volatile_day = random.random() < 0.3 # 30% 的概率为大波动日
            if is_volatile_day:
                pct_dev = random.uniform(0.02, 0.10) # 2% - 10% 波动
            else:
                pct_dev = random.uniform(0.0, 0.01)  # 0% - 1% 波动
            
            direction = random.choice([-1, 1]) # 波动方向

            # 计算下一个值：
            # 波动是基于几何目标的调整值
            # next_value = (value_today * geometric_target_factor) * (1 + pct_dev * direction)
            # 或者波动是独立于几何目标的，但几何目标提供一个基线
            # next_value = value_today * (geometric_target_factor + pct_dev * direction)
            # 后者可能导致因子为负，如果 geometric_target_factor 接近 pct_dev 且方向为负
            
            # 使用乘性波动更为常见
            base_next_value = value_today * geometric_target_factor
            next_value = base_next_value * (1 + pct_dev * direction)


            # 确保值不低于某个非常小的正数 (例如 0.01, 如果这是价格数据)
            # 鉴于最终值是17.86，这个下限可能不需要太严格，但避免变为0或负数
            if end_value > 0: # 如果最终目标是正数
                 next_value = max(next_value, 0.01) # 至少为1分钱
            elif end_value == 0:
                 next_value = max(next_value, 0.0) # 可以到0
            # 如果 end_value < 0 (题目中不是这种情况)，则不需要这个max处理

        current_value = next_value
        # 添加下一个数据点 (trading_dates[i+1] 的值)
        data_points.append((trading_dates[i+1], round(current_value, 2)))


    # --- 写入CSV ---
    # 确保目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir: # 检查 output_dir 是否为空（如果 output_path 只是文件名）
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter='\t') # 使用制表符分隔
        writer.writerow(['date', 'value']) # 写入表头
        for date_obj, val in data_points:
            # 格式化日期为 YYYY.M.D (无前导零的月和日)
            date_str = f"{date_obj.year}.{date_obj.month}.{date_obj.day}"
            writer.writerow([date_str, val])

    print(f"数据已成功生成到: {output_path}")
    if data_points:
        print(f"第一个数据点: {data_points[0][0].strftime('%Y.%m.%d')} \t {data_points[0][1]}")
        print(f"最后一个数据点: {data_points[-1][0].strftime('%Y.%m.%d')} \t {data_points[-1][1]}")
        if abs(data_points[-1][1] - end_value) > 0.001 :
            print(f"警告: 最终生成值 {data_points[-1][1]} 与目标值 {end_value} 不完全匹配。差额: {abs(data_points[-1][1] - end_value)}")
    else:
        print("没有生成数据点。")


if __name__ == '__main__':
    # 用户指定的固定数据
    start_data_config = (2022, 1, 1, 31635.72) # (年, 月, 日, 值)
    end_data_config = (2023, 1, 1, 17.86)     # (年, 月, 日, 值)

    # 输出文件路径
    home_dir = os.path.expanduser("~")
    # 确保 Downloads 目录存在，如果不存在，脚本会尝试创建它
    output_file_path = os.path.join(home_dir, 'Downloads', 'simulated_stock_data.csv')
    
    generate_financial_data(output_file_path, start_data_config, end_data_config)

    # 验证一下输出文件的前几行和后几行（可选）
    try:
        line_count = 0
        with open(output_file_path, 'r') as f_check:
            for _ in f_check:
                line_count += 1
        
        with open(output_file_path, 'r') as f:
            print("\nCSV文件内容预览:")
            for i, line in enumerate(f):
                if i < 5 or (line_count > 10 and i >= line_count - 5) : # 打印前5行和后5行
                    print(line.strip())
                elif i == 5 and line_count > 10:
                    print("...")
    except FileNotFoundError:
        print(f"错误: 文件 {output_file_path} 未找到。")
    except Exception as e:
        print(f"读取预览时发生错误: {e}")