import re
from pathlib import Path
import shutil

def remove_markdown_citations(text: str) -> str:
    """
    删除形如 [[数字]](http...一长串) 的 Markdown 链接式引用。
    例：[[1]](https://example.com/abc) -> ''
    """
    # 说明：
    # \[\[\d+\]\]    匹配 [[数字]]
    # \(https?://    匹配以 http:// 或 https:// 开头的括号
    # [^)\s]+        至少一个非右括号且非空白字符（避免立刻遇到 ) 或空格）
    # [^)]*          其后任意非右括号字符，直到遇到右括号
    # \)             右括号
    pattern = re.compile(r'\[\[\d+\]\]\(https?://[^)\s]+[^)]*\)', flags=re.IGNORECASE)
    return pattern.sub('', text)

def truncate_from_learn_more(text: str) -> str:
    """
    一旦发现 '--- Learn more:'，删除从该标记起直至文本末尾的所有内容。
    匹配大小写严格一致，避免误删相似但非目标的文本。
    """
    # 使用非贪婪前缀匹配，捕获 '--- Learn more:' 之前的所有内容
    # (?s) 等价于 DOTALL，使 '.' 跨行
    pattern = re.compile(r'(?s)(.*?)--- Learn more:.*$')
    m = pattern.match(text)
    if m:
        return m.group(1)
    return text

def process_file(file_path: str, make_backup: bool = True) -> None:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f'文件不存在：{p}')

    # 备份
    if make_backup:
        backup_path = p.with_suffix(p.suffix + '.bak')
        shutil.copy2(p, backup_path)
        print(f'已创建备份：{backup_path}')

    # 读取原文本（保持换行）
    original = p.read_text(encoding='utf-8')

    # 步骤1：清理 [[数字]](http/https... )
    step1 = remove_markdown_citations(original)

    # 步骤2：从 '--- Learn more:' 起截断到末尾
    cleaned = truncate_from_learn_more(step1)

    # 仅在有改动时写回
    if cleaned != original:
        p.write_text(cleaned, encoding='utf-8', newline='')
        print(f'已清理并写回：{p}')
    else:
        print('未发现需要清理或截断的内容，文件未改动。')

if __name__ == '__main__':
    # 请修改为你的实际路径
    target = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
    process_file(target, make_backup=True)