def check_duplicates(filename):
    prefixes = set()
    duplicates = []

    with open(filename, 'r') as file:
        for line in file:
            if ':' in line:
                prefix = line.split(':')[0].strip()
                if prefix in prefixes:
                    duplicates.append(prefix)
                else:
                    prefixes.add(prefix)

    return duplicates

# 使用示例
filename = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'  # 替换为你的文件名
result = check_duplicates(filename)

if result:
    print("发现重复的前缀:")
    for dup in result:
        print(dup)
else:
    print("没有发现重复的前缀")