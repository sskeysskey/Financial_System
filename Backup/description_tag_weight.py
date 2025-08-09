import json
from collections import Counter
from pathlib import Path

def load_json(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # 1. 定义文件路径
    desc_path = Path('/Users/yanzhang/Coding/Financial_System/Modules/description.json')
    weight_path = Path('/Users/yanzhang/Coding/Financial_System/Modules/tags_weight.json')
    output_path = Path('/Users/yanzhang/Downloads/a.txt')

    # 2. 读取 JSON
    desc = load_json(desc_path)
    tag_weight = load_json(weight_path)

    # 3. 从 description.json 中提取所有 tag（stocks 和 etfs 两块）
    all_tags = []
    # for section in ('stocks', 'etfs'):
    #     for item in desc.get(section, []):
    #         # item['tag'] 是一个 list
    #         all_tags.extend(item.get('tag', []))
    for item in desc.get('stocks', []):
        all_tags.extend(item.get('tag', []))

    # 4. 从 tags_weight.json 中提取所有已定义的 tag
    weighted_tags = set()
    for tag_list in tag_weight.values():
        weighted_tags.update(tag_list)

    # 5. 统计所有出现过的 tag 的频次
    counter = Counter(all_tags)

    # 6. 找出出现在 description 中但不在 weight 表里的 tag，并保留它们的次数
    missing = {tag: cnt for tag, cnt in counter.items() if tag not in weighted_tags}

    # 7. 按次数从大到小排序
    sorted_missing = sorted(missing.items(), key=lambda x: x[1], reverse=True)

    # 8. 写入输出文件
    with output_path.open('w', encoding='utf-8') as f:
        f.write("以下是出现在 description.json 中但未在 tags_weight.json 中定义的 tag 及其出现次数：\n")
        for tag, cnt in sorted_missing:
            # 格式: 标签: 次数
            f.write(f"{tag}: {cnt}\n")

    print(f"已将结果写入 {output_path}")

if __name__ == '__main__':
    main()