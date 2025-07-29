# 读取原始文本文件
with open('/Users/yanzhang/Downloads/xiaoxie.txt', 'r', encoding='utf-8') as file:
    text = file.read()

# 转换文本为大写
upper_text = text.upper()

# 将转换后的大写文本写入新的文件
with open('/Users/yanzhang/Downloads/daxie.txt', 'w', encoding='utf-8') as file:
    file.write(upper_text)