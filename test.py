import json

# 数字的英文名 -> 数值，下标即数字
DIGIT_WORDS = ["zero", "one", "two", "three", "four",
               "five", "six", "seven", "eight", "nine"]

# 符号按键盘位置排列（可按需调整）
SYMBOL_ORDER = [
    "grave",         # `
    "minus",         # -
    "equal",         # =
    "leftBracket",   # [
    "rightBracket",  # ]
    "backslash",     # \
    "semicolon",     # ;
    "quote",         # '
    "comma",         # ,
    "period",        # .
    "slash",         # /
]


def key_rank(key: str):
    """返回排序元组：(大类, 大类内的次序, 名字)"""
    k = key.lower()

    # 数字：'0'~'9' 或 'zero'~'nine'
    if len(k) == 1 and k.isdigit():
        return (0, int(k), "")
    if k in DIGIT_WORDS:
        return (0, DIGIT_WORDS.index(k), "")

    # 字母：单个字母 a~z
    if len(k) == 1 and k.isalpha():
        return (1, 0, k)

    # 符号：按 SYMBOL_ORDER 的顺序
    if k in SYMBOL_ORDER:
        return (2, SYMBOL_ORDER.index(k), "")

    # 其他（功能键等）：放最后，按名字排序
    return (3, 0, k)


# 读取
with open("/Users/yanzhang/Coding/Financial_System/Modules/config.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 按 key 的排序值排序（稳定排序，同一个 key 内部顺序不变）
result = sorted(data, key=lambda item: key_rank(item["key"]))

# 保存
with open("shortcuts_sorted.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

# 打印 key 的出现顺序，方便检查
seen = []
for item in result:
    if item["key"] not in seen:
        seen.append(item["key"])
print("key 顺序：", " ".join(seen))
print(f"完成，共 {len(result)} 项，已保存到 shortcuts_sorted.json")