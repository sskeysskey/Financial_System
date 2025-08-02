from collections import defaultdict

def check_duplicates(filename):
    prefix_count = defaultdict(int)
    duplicates = {}

    with open(filename, 'r') as file:
        for line in file:
            if ':' in line:
                prefix = line.split(':')[0].strip()
                prefix_count[prefix] += 1
                if prefix_count[prefix] > 1:
                    duplicates[prefix] = prefix_count[prefix]

    return duplicates

# 使用示例
filename = '/Users/yanzhang/Coding/News/Earnings_Release_next.txt'
# filename = '/Users/yanzhang/Coding/News/backup/marketcap_pe.txt'
result = check_duplicates(filename)

if result:
    print("发现重复的前缀及其出现次数:")
    for prefix, count in result.items():
        print(f"{prefix}: {count}次")
else:
    print("没有发现重复的前缀")