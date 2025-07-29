from collections import defaultdict

def remove_duplicates(input_filename, output_filename):
    prefix_lines = defaultdict(list)
    
    # 读取文件并存储每个前缀的所有行
    with open(input_filename, 'r') as file:
        for line in file:
            if ':' in line:
                prefix = line.split(':', 1)[0].strip()
                prefix_lines[prefix].append(line)

    # 写入结果到新文件，只保留每个前缀的最后一行
    with open(output_filename, 'w') as outfile:
        for lines in prefix_lines.values():
            outfile.write(lines[-1])

    # 统计重复的前缀
    duplicates = {prefix: len(lines) for prefix, lines in prefix_lines.items() if len(lines) > 1}
    return duplicates

# 使用示例
input_filename = '/Users/yanzhang/Documents/News/backup/ETFs.txt'
output_filename = '/Users/yanzhang/Documents/News/backup/ETFs_no_duplicates.txt'
result = remove_duplicates(input_filename, output_filename)

if result:
    print("发现并处理了以下重复的前缀:")
    for prefix, count in result.items():
        print(f"{prefix}: 原有{count}行，保留了最后一行")
    print(f"处理后的文件已保存为: {output_filename}")
else:
    print("没有发现重复的前缀")