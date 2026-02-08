import json
import os
import sys

# ================= 配置区域 =================
# 指定要回溯处理的日期
TARGET_DATE = "2026-02-04"

# 路径配置
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
MODULES_DIR = os.path.join(BASE_CODING_DIR, 'Financial_System', 'Modules')

PATHS = {
    "history": os.path.join(MODULES_DIR, 'Earning_History.json'),
    "tags_setting": os.path.join(MODULES_DIR, 'tags_filter.json'),
    "description": os.path.join(MODULES_DIR, 'description.json'),
}
# ===========================================

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {path}")
        return None
    except json.JSONDecodeError:
        print(f"错误: 文件格式错误 {path}")
        return None

def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功保存文件: {path}")
    except Exception as e:
        print(f"保存文件失败: {e}")

def get_blacklist_tags():
    data = load_json(PATHS["tags_setting"])
    if data:
        return set(data.get("BLACKLIST_TAGS", []))
    return set()

def get_symbol_tags_map():
    data = load_json(PATHS["description"])
    mapping = {}
    if data:
        # 合并 stocks 和 etfs 的标签信息
        for category in ["stocks", "etfs"]:
            for item in data.get(category, []):
                sym = item.get("symbol")
                tags = item.get("tag", [])
                if sym:
                    mapping[sym] = set(tags)
    return mapping

def run_retroactive_filter():
    print(f"--- 开始执行回溯过滤，目标日期: {TARGET_DATE} ---")

    # 1. 加载基础数据
    history_data = load_json(PATHS["history"])
    if not history_data: return

    blacklist_tags = get_blacklist_tags()
    symbol_tags_map = get_symbol_tags_map()

    if not blacklist_tags:
        print("警告: 黑名单标签为空，未执行任何过滤。")
        return

    print(f"加载了 {len(blacklist_tags)} 个黑名单标签。")

    # 2. 收集指定日期下所有分组的 Symbol
    all_symbols_on_date = set()
    
    # 遍历 history 中的每一个分组 (PE_W, OverSell_W, etc.)
    for group_name, dates_dict in history_data.items():
        # 跳过我们自己（_Tag_Blacklist），避免重复计算，虽然逻辑上也没问题
        if group_name == "_Tag_Blacklist":
            continue
            
        if isinstance(dates_dict, dict):
            # 获取该分组在目标日期的列表
            symbols = dates_dict.get(TARGET_DATE, [])
            if symbols:
                all_symbols_on_date.update(symbols)

    print(f"在日期 {TARGET_DATE} 下，共扫描到 {len(all_symbols_on_date)} 个不重复的 Symbol (来自所有分组)。")

    # 3. 过滤命中黑名单的 Symbol
    blocked_symbols = []
    for sym in all_symbols_on_date:
        # 获取该 symbol 的 tags
        my_tags = symbol_tags_map.get(sym, set())
        
        # 检查交集
        intersect = my_tags.intersection(blacklist_tags)
        if intersect:
            # print(f"  -> 命中: {sym} (Tags: {list(intersect)})")
            blocked_symbols.append(sym)

    if not blocked_symbols:
        print("没有发现命中黑名单标签的 Symbol。")
        return

    # 去重并排序
    blocked_symbols = sorted(list(set(blocked_symbols)))
    print(f"--- 筛选结果: 共有 {len(blocked_symbols)} 个 Symbol 命中黑名单 ---")
    print(f"Symbols: {blocked_symbols}")

    # 4. 写入 _Tag_Blacklist 分组
    target_group_name = "_Tag_Blacklist"
    
    # 确保分组存在
    if target_group_name not in history_data:
        history_data[target_group_name] = {}
    
    # 获取该日期已有的数据 (如果有的话，进行合并)
    existing_blocked = history_data[target_group_name].get(TARGET_DATE, [])
    final_list = sorted(list(set(existing_blocked) | set(blocked_symbols)))
    
    # 更新数据
    history_data[target_group_name][TARGET_DATE] = final_list

    # 5. 保存回文件
    save_json(PATHS["history"], history_data)
    print("回溯处理完成。")

if __name__ == "__main__":
    run_retroactive_filter()
