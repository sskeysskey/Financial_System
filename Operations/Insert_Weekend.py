import json
import os

# 动态获取当前用户的家目录 (例如 /Users/yanzhang)
home_path = os.path.expanduser("~")
file_path = os.path.join(home_path, 'Coding/Financial_System/Modules/Sectors_empty.json')

# 1. 读取原始 JSON
with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 修改 Crypto 数组
to_add_crypto = ["Bitcoin",
                 "Ether",
                "Solana",
                "Binance",
                "XRP"]

# 3. 在原有 Crypto 基础上追加并自动去重
existing_crypto = set(data.get('Crypto', []))
data['Crypto'] = list(existing_crypto.union(to_add_crypto))

# 4. 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ 已将 Crypto 更新为：", data['Crypto'])
print("✅ 已将 Commodities 更新为：", data['Commodities'])