import json
import re
from pathlib import Path
import shutil
from typing import Any

# 规则1：删除 [[数字]](http/https…)
RE_CITATION = re.compile(r'\[\[\d+\]\]\(https?://[^)\s]+[^)]*\)', flags=re.IGNORECASE)

# 规则2：匹配中文字符（基本汉字区）。若需要也可扩展至更多区段。
RE_FIRST_CJK = re.compile(r'[\u4e00-\u9fff]')

def clean_string_value(s: str) -> str:
    """
    清理单个字符串值：
    1) 删除形如 [[数字]](http/https...) 的引用片段；
    2) 若出现 '*Thinking...*'，从其位置起删除到后续出现的第一个中文字符（该中文字符保留）；
       - 如果 '*Thinking...*' 后没有中文字符，则从 '*Thinking...*' 起删到字符串末尾。
    3) 若出现 '--- Learn more:'，从该短语起截断到字符串末尾。
    """
    # 1) 删除引用
    s = RE_CITATION.sub('', s)

    # 2) 处理 '*Thinking...*' -> 删除至第一个中文字符（中文保留）
    thinking_idx = s.find('*Thinking...*')
    if thinking_idx != -1:
        # 从 thinking 段落之后寻找第一个中文字符
        after = s[thinking_idx + len('*Thinking...*'):]
        m = RE_FIRST_CJK.search(after)
        if m:
            # 保留中文及其后内容，丢弃 '*Thinking...*' 到该中文之前
            cut_pos = thinking_idx + len('*Thinking...*') + m.start()
            s = s[:thinking_idx] + s[cut_pos:]
        else:
            # 没有中文，安全删除从 '*Thinking...*' 到末尾
            s = s[:thinking_idx]

    # 3) 截断 '--- Learn more:'（精确匹配）
    lm_idx = s.find('--- Learn more:')
    if lm_idx != -1:
        s = s[:lm_idx]

    return s

def walk_and_clean(obj: Any) -> Any:
    """
    递归遍历 JSON 结构，仅清理字符串值。
    """
    if isinstance(obj, dict):
        return {k: walk_and_clean(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [walk_and_clean(v) for v in obj]
    elif isinstance(obj, str):
        return clean_string_value(obj)
    else:
        # 其他类型（数值、布尔、null）不动
        return obj

def process_json_file(file_path: str, make_backup: bool = True) -> None:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f'文件不存在：{p}')

    original_text = p.read_text(encoding='utf-8')

    # 尝试解析为 JSON，若失败则不进行破坏性修改
    try:
        data = json.loads(original_text)
    except json.JSONDecodeError as e:
        raise ValueError(f'JSON 解析失败，已停止操作：{e}')

    # 备份原文件
    if make_backup:
        backup_path = p.with_suffix(p.suffix + '.bak')
        shutil.copy2(p, backup_path)
        print(f'已创建备份：{backup_path}')

    # 清理
    cleaned_data = walk_and_clean(data)

    # 若无变化则不写回
    if cleaned_data == data:
        print('未发现需要清理的内容，文件未改动。')
        return

    # 回写为合法 JSON
    # 注意：indent 可按需调整；ensure_ascii=False 以保留中文；sort_keys=False 保留键顺序（Python 3.7+保持插入序）
    p.write_text(
        json.dumps(cleaned_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
        newline=''
    )
    print(f'已清理并写回：{p}')

if __name__ == '__main__':
    target = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
    process_json_file(target, make_backup=True)