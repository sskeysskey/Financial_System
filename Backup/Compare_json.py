import json
import os

def compare_json_files(path1, path2):
    # 检查文件是否存在
    if not os.path.exists(path1):
        print(f"错误: 找不到文件 {path1}")
        return
    if not os.path.exists(path2):
        print(f"错误: 找不到文件 {path2}")
        return

    # 读取 JSON 内容
    with open(path1, 'r', encoding='utf-8') as f1, open(path2, 'r', encoding='utf-8') as f2:
        try:
            data1 = json.load(f1)
            data2 = json.load(f2)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return

    # 获取所有的分组键名（取并集）
    all_keys = sorted(set(data1.keys()) | set(data2.keys()))

    print(f"{'Group Name':<20} | {'Status'}")
    print("-" * 50)

    has_difference = False

    for key in all_keys:
        list1 = data1.get(key, [])
        list2 = data2.get(key, [])

        # 转换为集合进行比较
        set1 = set(list1)
        set2 = set(list2)

        if set1 == set2:
            print(f"{key:<20} | ✅ 完全一致")
        else:
            has_difference = True
            print(f"{key:<20} | ❌ 存在差异")
            
            # 找出具体的差异
            only_in_1 = set1 - set2
            only_in_2 = set2 - set1

            if only_in_1:
                print(f"    - 只在文件 1 (Modules) 中有的: {sorted(list(only_in_1))}")
            if only_in_2:
                print(f"    - 只在文件 2 (Backup) 中有的: {sorted(list(only_in_2))}")
        print("-" * 50)

    if not has_difference:
        print("结论：两个文件内容完全相同。")
    else:
        print("结论：两个文件存在上述差异。")

# 定义路径
path_modules = "/Users/yanzhang/Coding/Financial_System/Modules/Colors.json"
path_backup = "/Users/yanzhang/Downloads/电影/backup/update_compare/Colors.json"

if __name__ == "__main__":
    compare_json_files(path_modules, path_backup)