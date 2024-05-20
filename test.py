import json

def load_sector_data():
    # 读取JSON文件
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_test.json', 'r') as file:
        sector_data = json.load(file)
    
    # 打印整个sector_data的内容
    print("完整的sector_data内容:")
    print(json.dumps(sector_data, indent=4, ensure_ascii=False))
    
    # 遍历每一个sector，打印每一个name
    print("\n遍历打印每个sector及其对应的names:")
    for sector, names in sector_data.items():
        for name in names:
            print(f"Sector: {sector}, Name: {name}")

# 调用函数
load_sector_data()