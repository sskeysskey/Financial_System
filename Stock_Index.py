import pyperclip
import sqlite3
import re
from datetime import datetime

def get_clipboard_content():
    return pyperclip.paste()

def clean_data(raw_data):
    lines = raw_data.split('\n')
    cleaned_lines = [line for line in lines if line.strip() and not re.match(r'^[^\w\d]*$', line)]
    return cleaned_lines

def extract_data(cleaned_lines, index_list):
    results = []
    for i, line in enumerate(cleaned_lines):
        # 使用完整匹配而不是部分匹配
        if any(line.strip() == idx for idx in index_list):
            name = line
            # 从下一行开始查找包含纯数字或数字+符号的行
            for next_line in cleaned_lines[i+1:]:
                if re.search(r'^[\d,.-]+$', next_line.strip()):
                    price = next_line
                    results.append((name.strip(), price.strip()))
                    break
    return results

def store_data_to_db(data):
    conn = sqlite3.connect('/Users/yanzhang/Stocks.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Stocks (date TEXT, name TEXT, price REAL, parent_id INTEGER)''')
    # 插入数据时加入当前日期和parent_id
    today = datetime.now().strftime('%Y-%m-%d')
    data_with_extra_fields = [(today, name, price, 10) for name, price in data]
    c.executemany('INSERT INTO Stocks (date, name, price, parent_id) VALUES (?, ?, ?, ?)', data_with_extra_fields)
    conn.commit()
    conn.close()

def main():
    raw_data = get_clipboard_content()
    cleaned_lines = clean_data(raw_data)
    Indexs = [
        "NASDAQ", "S&P 500", "HYG", "SSE Composite Index", "Shenzhen Index",
        "Nikkei 225", "S&P BSE SENSEX", "HANG SENG INDEX"
    ]
    extracted_data = extract_data(cleaned_lines, Indexs)
    store_data_to_db(extracted_data)
    print("数据已存入数据库。")

if __name__ == '__main__':
    main()