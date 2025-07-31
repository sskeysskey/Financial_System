import json

# 1. 读取原始 JSON
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 修改 Crypto 数组
to_add_crypto = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
#（示例：直接替换）
# data['Crypto'] = to_add_crypto

# 如果你想在原有 Crypto 基础上追加，可以这样做（并自动去重）：
existing_crypto = set(data.get('Crypto', []))
data['Crypto'] = list(existing_crypto.union(to_add_crypto))

# 4. 写回文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ 已将 Crypto 更新为：", data['Crypto'])
print("✅ 已将 Commodities 更新为：", data['Commodities'])