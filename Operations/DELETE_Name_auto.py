import sqlite3
import json
import pyperclip
import subprocess
import os
import platform
import tkinter as tk
from tkinter import messagebox

USER_HOME = os.path.expanduser("~")

def show_alert(message):
    if platform.system() == "Darwin":
        # AppleScript代码模板
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        # 使用subprocess调用osascript
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    else:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()

def get_clipboard_content():
    """获取剪贴板内容，包含错误处理，仅去除首尾空格，不再强制大写"""
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception:
        return ""

def find_sector_for_symbol(sector_file, symbol):
    """在sector文件中查找symbol所属的sector"""
    try:
        with open(sector_file, 'r', encoding='utf-8') as f:
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
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
            
        return False
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False

def add_to_blacklist(blacklist_file, symbol):
    try:
        # 读取blacklist文件
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if symbol in data.get('screener', []):
            print(f"{symbol} 已经在blacklist的screener列表中")
            return False
        
        data.setdefault('screener', []).append(symbol)
        with open(blacklist_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        print(f"成功将 {symbol} 添加到blacklist的screener列表中")
        return True
    except Exception as e:
        print(f"处理blacklist文件时出错: {e}")
        return False

def delete_records_by_names(db_file, table_name, stock_names):
    """从数据库中删除记录"""
    if not stock_names:
        print("没有提供要删除的股票代码")
        return
    conn = sqlite3.connect(db_file, timeout=60.0)
    try:
        cur = conn.cursor()
        cur.execute('PRAGMA foreign_keys = ON;')
        placeholders = ', '.join('?' for _ in stock_names)
        # 为表名加引号以避免特殊字符或保留字问题
        sql = f'DELETE FROM "{table_name}" WHERE name IN ({placeholders});'
        cur.execute(sql, stock_names)
        conn.commit()
        print(f"成功从表 {table_name} 中删除 {stock_names} 的 {cur.rowcount} 条记录。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        conn.close()

def is_in_etfs_sector(symbol, sector_files):
    """
    检查symbol是否在ETFs分组中
    """
    try:
        for file_path in sector_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'ETFs' in data and symbol in data['ETFs']:
                    return True
        return False
    except Exception as e:
        print(f"检查ETFs分组时出错: {e}")
        return False

def delete_from_description_json(description_file, symbol):
    """从description.json文件中删除指定symbol的项目（优先找etfs，找不到再去stocks找）"""
    try:
        # 读取JSON文件
        with open(description_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        deleted_category = None
        
        # 1. 尝试从 etfs 中删除
        original_etfs_length = len(data.get('etfs', []))
        data['etfs'] = [item for item in data.get('etfs', []) if item.get('symbol') != symbol]
        
        if len(data['etfs']) < original_etfs_length:
            deleted_category = 'etfs'
        else:
            # 2. 如果 etfs 中没有，尝试从 stocks 中删除
            original_stocks_length = len(data.get('stocks', []))
            data['stocks'] = [item for item in data.get('stocks', []) if item.get('symbol') != symbol]
            
            if len(data['stocks']) < original_stocks_length:
                deleted_category = 'stocks'
        
        # 检查是否有删除操作
        if deleted_category:
            # 写回文件
            with open(description_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"已从description.json的 {deleted_category} 列表中删除: {symbol}")
            return deleted_category
            
        return None
    except Exception as e:
        print(f"处理description.json文件时出错: {e}")
        return None

# ==============================================================================
# 新增函数：用于处理 Compare_All.txt 文件
# ==============================================================================
def delete_from_compare_all(file_path, symbol_to_delete):
    """
    从 Compare_All.txt 文件中删除指定 symbol 所在的行。
    匹配逻辑是检查行是否以 "symbol:" 开头。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 使用列表推导式筛选出所有不以 "symbol:" 开头的行
        # line.strip() 用于去除每行首尾的空白字符，确保匹配的准确性
        kept_lines = [line for line in lines if not line.strip().startswith(symbol_to_delete + ':')]

        # 如果筛选后的行数少于原始行数，说明有内容被删除
        if len(kept_lines) < len(lines):
            # 将保留的行写回原文件，实现删除
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(kept_lines)
            print(f"已从 {file_path} 中删除包含 {symbol_to_delete} 的行。")
            return True
        else:
            print(f"在 {file_path} 中未找到以 {symbol_to_delete}: 开头的行。")
            return False

    except FileNotFoundError:
        print(f"错误: 文件 {file_path} 未找到。")
        return False
    except Exception as e:
        print(f"处理 {file_path} 时出错: {e}")
        return False
    
def add_to_blacklist_etf(blacklist_file, symbol):
    try:
        # 读取blacklist文件
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault('etf', [])
        # 检查symbol是否已经在etf列表中
        if symbol in data['etf']:
            show_alert(f"{symbol} 已经在blacklist的etf列表中")
            return False
        
        # 添加symbol到etf列表
        data['etf'].append(symbol)
        
        # 写回文件
        with open(blacklist_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功！ 已将{symbol}写入黑名单的ETFs分组下。")
        return True
    except Exception as e:
        show_alert(f"处理blacklist文件时出错: {e}")
        return False

def main():
    db_path = os.path.join(USER_HOME, 'Coding/Database/Finance.db')
    sector_file = os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_All.json')
    sector_today_file = os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_today.json')
    sector_500_file = os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_500.json')
    sector_empty_file = os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_empty.json')
    blacklist_file = os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Blacklist.json')
    description_file = os.path.join(USER_HOME, 'Coding/Financial_System/Modules/description.json')
    
    # 新增：Compare_All.txt 文件路径
    compare_all_file = os.path.join(USER_HOME, 'Coding/News/backup/Compare_All.txt')
    
    # 获取剪贴板内容（原大小写）
    symbol = get_clipboard_content()
    if not symbol:
        show_alert("剪贴板为空")
        return

    # 1. 检查是否在 Sectors_All.json 中存在
    exists_in_sectors = False
    try:
        with open(sector_file, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
            
            # 第一次尝试：按照剪贴板原内容查找
            exists_in_sectors = any(symbol in symbols for symbols in sectors_data.values())
            
            # 如果原内容找不到，尝试转换为全大写查找
            if not exists_in_sectors:
                upper_symbol = symbol.upper()
                exists_in_upper = any(upper_symbol in symbols for symbols in sectors_data.values())
                
                if exists_in_upper:
                    # 如果全大写能找到，就将 symbol 替换为全大写版本
                    symbol = upper_symbol
                    exists_in_sectors = True
                else:
                    # 如果都找不到，为了兼容之前的逻辑，默认转为全大写继续后续操作
                    # (如果你希望找不到时保持原样，可以注释掉下面这行)
                    symbol = upper_symbol

    except Exception as e:
        print(f"检查 {sector_file} 时出错: {e}")
        return
    
    print(f"当前处理的 Symbol 为: {symbol}")

    # 2. 首先检查是否在ETFs分组中
    add_result_etf = False
    sector_files = [sector_file, sector_today_file]
    is_etf = is_in_etfs_sector(symbol, sector_files)
    if is_etf:
        add_result_etf = add_to_blacklist_etf(blacklist_file, symbol)
    
    # 3. 数据库删除
    sector = find_sector_for_symbol(sector_file, symbol)
    if sector:
        delete_records_by_names(db_path, sector, [symbol])
    else:
        print(f"未找到股票代码 {symbol} 对应的sector")

    # 4. 删除所有 sector JSON 文件中的记录
    delete_result1 = delete_from_json_file(sector_file, symbol)
    
    # 处理 sector_today.json
    delete_result2 = delete_from_json_file(sector_today_file, symbol)

    # 添加对sector_500的处理
    delete_result3 = delete_from_json_file(sector_500_file, symbol)
    delete_result4 = delete_from_json_file(sector_empty_file, symbol)

    # 5. 非ETF且原本在任何 sector 中，添加到黑名单
    add_result = False
    if exists_in_sectors and not is_etf:
        add_result = add_to_blacklist(blacklist_file, symbol)
    
    # 6. 新增：从 Compare_All.txt 中删除匹配行
    delete_compare_result = delete_from_compare_all(compare_all_file, symbol)

    # 7. 更新 description.json 中的 etfs/stocks 列表
    deleted_category = delete_from_description_json(description_file, symbol)
    
    # 8. 输出总结 (更新了总结部分)
    print("\n操作总结:")
    if delete_result1 or delete_result2 or delete_result3 or delete_result4:
        print("JSON文件更新情况:")
        if delete_result1: print("- Sectors_All.json 已更新")
        if delete_result2: print("- Sectors_today.json 已更新")
        if delete_result3: print("- Sectors_500.json 已更新")
        if delete_result4: print("- Sectors_empty.json 已更新")
    else:
        print("- 在 sector 文件中未找到匹配项")
    
    print("Blacklist更新情况:")
    if add_result:
        print("- 已成功更新 blacklist的Screener分组")
    elif add_result_etf:
        print("- 已成功更新 blacklist的ETF分组")
    else:
        print("- blacklist 更新未执行或未发生变化")

    print("description.json更新情况:")
    if deleted_category:
        print(f"- 已从 {deleted_category} 列表中删除 {symbol}")
    else:
        print(f"- 在 etfs 和 stocks 列表中均未找到 {symbol}")

    # 新增：Compare_All.txt 的总结输出
    print("Compare_All.txt更新情况:")
    if delete_compare_result:
        print(f"- 已从文件中删除 {symbol} 相关的行")
    else:
        print(f"- 在文件中未找到 {symbol} 或文件未更新")


if __name__ == "__main__":
    main()