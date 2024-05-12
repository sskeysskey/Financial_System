import json

# 原始JSON数据
data = """
{"Utilities": {
    "Mega": [],
    "Large": [
      "NEE",
      "SO",
      "DUK",
      "CEG",
      "NGG",
      "SRE",
      "AEP",
      "PCG",
      "D",
      "EXC",
      "PEG",
      "ED",
      "VST",
      "XEL",
      "EIX",
      "WEC",
      "AWK",
      "ETR",
      "DTE",
      "FE",
      "ES",
      "PPL",
      "FTS"
    ],
    "Middle": [
      "AEE",
      "CNP",
      "CMS",
      "BEP",
      "ATO",
      "EBR",
      "NRG",
      "AGR",
      "BIP",
      "AES",
      "LNT",
      "NI",
      "EVRG",
      "WTRG",
      "SBS",
      "KEP",
      "PNW",
      "OGE",
      "CIG",
      "BEPC",
      "NFE",
      "SWX",
      "CWEN",
      "ELP",
      "UGI"
    ]
  }
}
"""

# 转换JSON字符串为Python字典
original_data = json.loads(data)

# 新JSON结构的初始化
transformed_data = {}

# 遍历原始数据，并填充新数据结构
for sector, categories in original_data.items():
    transformed_data[sector] = {}
    for category, symbols in categories.items():
        transformed_data[sector][category] = [
            {"symbol": symbol, "marketcap": "100B", "pe_ratio": "10"} for symbol in symbols
        ]

# 将转换后的字典转换为JSON字符串
output_json = json.dumps(transformed_data, indent=2)
print(output_json)