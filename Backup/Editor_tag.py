import json
import shutil
from datetime import datetime

FILE_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"

KEYWORD = "私募"        # 要找的标签
NEW_TAG = "利率敏感"     # 要加的标签
FUZZY_MATCH = False     # False: 标签必须完全等于“私募”
                        # True:  标签里包含“私募”就算，比如“私募股权”“私募信贷”


def has_keyword(tags):
    if FUZZY_MATCH:
        return any(KEYWORD in t for t in tags)
    return KEYWORD in tags


def main():
    # 1. 先备份原文件
    backup_path = f"{FILE_PATH}.{datetime.now():%Y%m%d_%H%M%S}.bak"
    shutil.copy(FILE_PATH, backup_path)
    print(f"已备份到: {backup_path}")

    # 2. 读取 JSON
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated, skipped = [], []

    # 3. 遍历 stocks 和 etfs
    for category in ("stocks", "etfs"):
        for item in data.get(category, []):
            tags = item.get("tag", [])
            if not has_keyword(tags):
                continue
            if NEW_TAG in tags:
                skipped.append(item["symbol"])
            else:
                tags.append(NEW_TAG)
                item["tag"] = tags
                updated.append(f"{category}:{item['symbol']}")

    # 4. 写回文件（保留中文、保持缩进）
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"新增“{NEW_TAG}”标签的 symbol ({len(updated)} 个): {updated}")
    print(f"已有该标签、跳过的 symbol ({len(skipped)} 个): {skipped}")


if __name__ == "__main__":
    main()