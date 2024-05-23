def analyze_sector_impacts(filename):
    import re

    # 定义行业系数
    coefficients = {
        "Basic_Materials": 72,
        "Communication_Services": 62,
        "Consumer_Cyclical": 155,
        "Consumer_Defensive": 63,
        "Energy": 82,
        "Financial_Services": 187,
        "Healthcare": 131,
        "Industrials": 178,
        "Real_Estate": 62,
        "Technology": 195,
        "Utilities": 48
    }

    # 初始化字典来存储每个类别的数量，分开正负值
    positive_sector_counts = {}
    negative_sector_counts = {}
    positive_total = 0
    negative_total = 0

    # 打开并读取文件
    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            # 使用正则表达式提取类别和百分比
            match = re.search(r'^(.*?)\s+.*:\s+(-?\d+\.\d+)%$', line)
            if match:
                sector = match.group(1).strip()
                percentage = float(match.group(2))
                # 根据百分比正负分别处理
                if percentage <= -0.2:
                    if sector in negative_sector_counts:
                        negative_sector_counts[sector] += 1
                    else:
                        negative_sector_counts[sector] = 1
                    negative_total += 1
                elif percentage >= 0.5:
                    if sector in positive_sector_counts:
                        positive_sector_counts[sector] += 1
                    else:
                        positive_sector_counts[sector] = 1
                    positive_total += 1

    # 调整行业数量使用对应系数
    adjusted_positive_counts = {sector: count / coefficients.get(sector, 1) for sector, count in positive_sector_counts.items()}
    adjusted_negative_counts = {sector: count / coefficients.get(sector, 1) for sector, count in negative_sector_counts.items()}
    adjusted_positive_total = sum(adjusted_positive_counts.values())
    adjusted_negative_total = sum(adjusted_negative_counts.values())

    # 输出调整后的正值统计结果
    print("调整后的正值百分比的类别统计和占比（从大到小）：")
    print("{:<28} {:<8} {:<10}".format("类别", "数量", "占比(%)"))
    for sector, count in sorted(adjusted_positive_counts.items(), key=lambda item: item[1], reverse=True):
        percentage = (count / adjusted_positive_total) * 100 if adjusted_positive_total > 0 else 0
        print("{:<30} {:<10.2f} {:<10.2f}".format(sector, count, percentage))

    # 输出调整后的负值统计结果
    print("调整后的负值百分比的类别统计和占比（从大到小）：")
    print("{:<28} {:<8} {:<10}".format("类别", "数量", "占比(%)"))
    for sector, count in sorted(adjusted_negative_counts.items(), key=lambda item: item[1], reverse=True):
        percentage = (count / adjusted_negative_total) * 100 if adjusted_negative_total > 0 else 0
        print("{:<30} {:<10.2f} {:<10.2f}".format(sector, count, percentage))

# 调用函数
analyze_sector_impacts('/Users/yanzhang/Documents/News/CompareStock.txt')