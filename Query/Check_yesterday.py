import json
import sqlite3
import os
import subprocess
from datetime import datetime, timedelta

# ———— 请根据实际情况修改下面这几个路径 ———— #
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'
SECTORS_ALL_JSON = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
SECTOR_EMPTY_JSON = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
ERROR_FILE = '/Users/yanzhang/Documents/News/Today_error.txt'

# 不需要写入 empty 的 symbol
FILTER_LIST = {
    'USInterest', 'USGDP', 'USCPI', 'USNonFarmA', 'USRetailM', 'USUnemploy',
    'USNonFarm', 'USConfidence', 'USInitial', 'USPPI', 'USNonPMI', 'CorePPI',
    'PCEY', 'CorePCEY', 'CorePCEM', 'CoreCPI', 'USConspending', 'ImportPriceM',
    'ImportPriceY', 'USTrade', 'CNYI', 'JPYI', 'EURI', 'CHFI', 'GBPI'
}

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


def read_json(path):
    """读取 JSON 文件并返回 Python 对象"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(path, data):
    """将 Python 对象写回 JSON，保持易读格式"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def query_data(table, name):
    """查询 SQLite，看表 table 中 name 和昨天日期的数据是否存在"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM {table} WHERE name = ? AND date = ?", (name, yesterday))
    found = cur.fetchone() is not None
    conn.close()
    return found


def write_error(msg):
    """追加写入错误日志"""
    with open(ERROR_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def show_alert(message):
    """
    如果 Today_error.txt 不存在，则弹出 macOS 对话框警告，
    避免脚本无声卡住。
    """
    # 转义双引号，免得 AppleScript 语法错
    safe_msg = message.replace('"', '\\"')
    applescript = (
        f'display dialog "{safe_msg}" buttons {{"OK"}} default button "OK" '
        f'with title "脚本提示"'
    )
    subprocess.run(['osascript', '-e', applescript], check=True)


def open_error_file():
    """
    尝试打开 ERROR_FILE；若不存在，就弹对话框提示。
    macOS 下用 open，Windows 下可改为 notepad。
    """
    if os.path.exists(ERROR_FILE):
        os.system(f"open {ERROR_FILE}")
    else:
        show_alert("所有数据都已成功入库，没有遗漏。")


def main():
    # 1. 读入 sectors 全量表 & empty 模板
    sectors_all = read_json(SECTORS_ALL_JSON)
    sector_empty = read_json(SECTOR_EMPTY_JSON)

    # 确保 empty 中至少有和 sectors_all 一一对应的 key
    for tbl in sectors_all:
        sector_empty.setdefault(tbl, [])

    # 2. 遍历各表、各 symbol
    for table, names in sectors_all.items():
        for name in names:
            if name in FILTER_LIST:
                continue
            if not query_data(table, name):
                # 写入 Today_error.txt
                err = f"在表 {table} 中找不到名称为 {name} 且日期为 {yesterday} 的数据"
                write_error(err)
                # 追加到 sector_empty.json（去重）
                if name not in sector_empty[table]:
                    sector_empty[table].append(name)

    # 3. 写回 sector_empty.json
    write_json(SECTOR_EMPTY_JSON, sector_empty)

    # 4. 打开错误文件以便查看
    open_error_file()


if __name__ == '__main__':
    main()