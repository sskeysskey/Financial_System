import json
import re

def extract_and_remove_chinese_characters(text):
    # 使用正则表达式提取中文字符
    chinese_characters = re.findall(r'[\u4e00-\u9fff]+', text)
    # 检查name是否只有中文字符
    if ''.join(chinese_characters) == text.strip():
        return [], text  # 如果是，则不移动
    # 否则，从原始文本中去除中文字符及其左边的空格
    for char in chinese_characters:
        text = re.sub(r'\s*' + char, '', text)
    return chinese_characters, text

def process_json_file(file_path):
    # 读取JSON文件
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 遍历stocks中的每个项目
    for stock in data['stocks']:
        original_name = stock['name']
        # 提取并移除name中的中文字符
        chinese_tags, new_name = extract_and_remove_chinese_characters(original_name)
        # 如果有中文字符且不是仅有中文字符，插入到tag列表的开头
        if chinese_tags:
            stock['tag'] = chinese_tags + stock['tag']
        # 更新name为去除中文字符后的字符串
        stock['name'] = new_name

    # 输出修改后的JSON数据
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

# 指定文件路径
file_path = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
process_json_file(file_path)