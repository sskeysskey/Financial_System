def has_duplicates(items):
    # 去除列表中的空白字符，生成一个新的列表
    cleaned_items = [item.strip() for item in items]
    
    # 将列表转换为集合
    items_set = set(cleaned_items)
    
    # 比较集合和列表的长度
    return len(items_set) != len(cleaned_items)

# 给定的列表
items = [
    "Initial Jobless Clm*", "GDP 2nd Estimate*",
    "Non-Farm Payrolls*", "Core PCE Price Index MM *",
    "Core PCE Price Index YY*", "ISM Manufacturing PMI",
    "ADP National Employment*", "International Trade $ *",
    "ISM N-Mfg PMI", "CPI YY, NSA*", "Core CPI MM, SA*",
    "CPI MM, SA*", "Core CPI YY, NSA*", "Fed Funds Tgt Rate *",
    "PPI Final Demand YY*", "PPI exFood/Energy MM*", "PPI ex Food/Energy/Tr MM*",
    "PPI Final Demand MM*", "Retail Sales MM *", "GDP Final*", "Core PCE Prices Fnal*"
]

# 判断是否有重复项
if has_duplicates(items):
    print("列表中有重复项")
else:
    print("列表中没有重复项")