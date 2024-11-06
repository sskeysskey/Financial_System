import sqlite3
import json
import time
import pyperclip
import subprocess
from PyQt5.QtWidgets import QMessageBox

def get_clipboard_content():
    """获取剪贴板内容，包含错误处理"""
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception:
        return ""

def find_sector_for_symbol(sector_file, symbol):
    """在sector文件中查找symbol所属的sector"""
    try:
        with open(sector_file, 'r') as f:
            sectors_data = json.load(f)
        
        for sector, symbols in sectors_data.items():
            if symbol in symbols:
                return sector
        return None
    except Exception as e:
        print(f"读取sector文件时出错: {e}")
        return None

def delete_from_json_file(file_path, symbol):
    """从JSON文件中删除指定的symbol
    
    Args:
        file_path (str): JSON文件路径
        symbol (str): 要删除的符号
    
    Returns:
        bool: 操作是否成功
    """
    try:
        # 读取JSON文件
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 记录是否有修改
        modified = False
        
        # 遍历所有sector
        for sector, symbols in data.items():
            if symbol in symbols:
                symbols.remove(symbol)
                modified = True
                print(f"已从 {file_path} 的 {sector} 中删除 {symbol}")
        
        # 如果有修改，写回文件
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
            
        return False
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False

def delete_records_by_names(db_file, table_name, stock_names):
    """从数据库中删除记录"""
    if not stock_names:
        print("没有提供要删除的股票代码")
        return
        
    conn = sqlite3.connect(db_file)
    
    try:
        cur = conn.cursor()
        placeholders = ', '.join('?' for _ in stock_names)
        sql = f"DELETE FROM {table_name} WHERE name IN ({placeholders});"
        cur.execute(sql, stock_names)
        conn.commit()
        print(f"成功从表 {table_name} 中删除 {stock_names} 的 {cur.rowcount} 条记录。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        conn.close()

def main():
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    sector_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    sector_today_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json'  # 添加sector_today.json路径
    
    # 获取剪贴板内容
    symbol = get_clipboard_content()
    if not symbol:
        print("剪贴板为空")
        return
    
    # 1. 数据库操作
    sector = find_sector_for_symbol(sector_file, symbol)
    if sector:
        delete_records_by_names(db_path, sector, [symbol])
    else:
        print(f"未找到股票代码 {symbol} 对应的sector")
    
    # 2. JSON文件操作
    # 处理 Sectors_All.json
    delete_result1 = delete_from_json_file(sector_file, symbol)
    
    # 处理 sector_today.json
    delete_result2 = delete_from_json_file(sector_today_file, symbol)
    
    # 输出总结
    if delete_result1 or delete_result2:
        print(f"JSON文件更新完成:")
        if delete_result1:
            print("- Sectors_All.json 已更新")
        if delete_result2:
            print("- sector_today.json 已更新")
    else:
        print("在JSON文件中未找到匹配项")

if __name__ == "__main__":
    main()