import json

# 读取finance数据文件
def read_finance_file(filepath):
    finance_data = {}
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(', ')
                symbol = parts[0].split(': ')[0]
                sector = parts[-1]
                finance_data.setdefault(sector, []).append(symbol)
    return finance_data

# 读取sectors配置文件
def read_sectors_file(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

# 比较差异
def compare_differences(finance_data, sectors_data):
    differences = {}
    
    # 遍历finance数据中的每个部门
    for sector, symbols in finance_data.items():
        if sector in sectors_data:
            # 在finance中有，但在sectors_all中没有的symbols
            in_finance_not_in_sectors = set(symbols) - set(sectors_data[sector])
            # 在sectors_all中有，但在finance中没有的symbols
            in_sectors_not_in_finance = set(sectors_data[sector]) - set(symbols)
            
            if in_finance_not_in_sectors or in_sectors_not_in_finance:
                differences[sector] = {
                    'in_finance_not_in_sectors': list(in_finance_not_in_sectors),
                    'in_sectors_not_in_finance': list(in_sectors_not_in_finance)
                }
    
    return differences

# 主函数
def main():
    finance_file = '/Users/yanzhang/Downloads/finance_data_2025-03-25_09-02-23.txt'
    sectors_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    
    # 读取数据
    finance_data = read_finance_file(finance_file)
    sectors_data = read_sectors_file(sectors_file)
    
    # 比较差异
    differences = compare_differences(finance_data, sectors_data)
    
    # 打印结果
    for sector, diff in differences.items():
        print(f"\n部门: {sector}")
        if diff['in_finance_not_in_sectors']:
            print("在finance文件中有，但在sectors_all中没有的符号:")
            print(diff['in_finance_not_in_sectors'])
        if diff['in_sectors_not_in_finance']:
            print("在sectors_all中有，但在finance文件中没有的符号:")
            print(diff['in_sectors_not_in_finance'])

if __name__ == "__main__":
    main()