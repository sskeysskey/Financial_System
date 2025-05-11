import json

# 1. 读取原始 JSON
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 修改 Crypto 数组
to_add = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]

# 如果要替换原有内容：
data['Crypto'] = to_add

# 如果要在原有基础上追加（避免重复可以先做去重）：
# existing = set(data.get('Crypto', []))
# data['Crypto'] = list(existing.union(to_add))

# 3. 写回文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ 已将 Crypto 更新为：", data['Crypto'])