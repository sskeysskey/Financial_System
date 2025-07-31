import sqlite3
import os

def create_and_populate_db():
    """
    读取文本文件中的股票数据，并将其存入SQLite数据库。
    能够处理"--"这样的无效数据。
    """
    # --- 1. 定义文件和数据库路径 ---
    # 请确保这些路径是正确的
    db_path = '/Users/yanzhang/Coding/Database/Finance.db'
    marketcap_pe_file = '/Users/yanzhang/Coding/News/backup/marketcap_pe.txt'
    shares_file = '/Users/yanzhang/Coding/News/backup/Shares.txt'
    names_file = '/Users/yanzhang/Coding/News/backup/symbol_names.txt'
    
    # --- 2. 解析数据文件 ---
    # 使用字典来存储解析后的数据，以股票代码为键
    
    names_data = {}
    try:
        with open(names_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(':', 1)
                names_data[parts[0].strip()] = parts[1].strip()
    except FileNotFoundError:
        print(f"错误：找不到文件 {names_file}")
        return

    shares_data = {}
    try:
        with open(shares_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(':', 1)
                share_value = parts[1].split(',')[0].strip()
                shares_data[parts[0].strip()] = float(share_value)
    except FileNotFoundError:
        print(f"错误：找不到文件 {shares_file}")
        return

    market_data = {}
    try:
        with open(marketcap_pe_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(':', 1)
                symbol = parts[0].strip()
                # 按逗号分割数值
                values = [v.strip() for v in parts[1].split(',')]
                
                # --- 这里是修改的核心 ---
                # 安全地处理每个值，如果值为'--'或无法转换，则设为None
                try:
                    # 市值通常是必须的，如果它无效，我们可以跳过这一行
                    marketcap = int(float(values[0]))
                except (ValueError, IndexError):
                    print(f"警告：跳过 Symbol '{symbol}'，因为其市值数据无效。")
                    continue

                # 对于PE和PB，检查是否为'--'，如果是，则设为None
                pe_ratio_str = values[1] if len(values) > 1 else '--'
                pb_ratio_str = values[2] if len(values) > 2 else '--'
                
                pe_ratio = float(pe_ratio_str) if pe_ratio_str != '--' else None
                pb_ratio = float(pb_ratio_str) if pb_ratio_str != '--' else None
                
                market_data[symbol] = (marketcap, pe_ratio, pb_ratio)
    except FileNotFoundError:
        print(f"错误：找不到文件 {marketcap_pe_file}")
        return

    # --- 3. 整合数据 ---
    # 将来自不同文件的数据合并到一个列表中，每个元素是一个准备插入的元组
    combined_data = []
    # 以 names_data 的键（所有 symbol）为基础进行整合
    for symbol, name in names_data.items():
        # 使用 .get() 方法可以避免因某个文件缺少某个symbol而导致程序出错
        shares = shares_data.get(symbol)
        market_info = market_data.get(symbol)
        
        # 确保所有数据都存在
        if shares is not None and market_info is not None:
            marketcap, pe_ratio, pb_ratio = market_info
            # 按照数据库表的顺序组织数据
            combined_data.append((
                symbol,
                name,
                shares,
                marketcap,
                pe_ratio,
                pb_ratio
            ))

    # --- 4. 数据库操作 ---
    conn = None # 初始化连接变量
    try:
        # 确保数据库所在的目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        # 连接到SQLite数据库（如果不存在，则会创建）
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 创建表的SQL语句 (修正了您提供的语句末尾多余的逗号)
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS MNSPP (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE,
            name TEXT,
            shares REAL,
            marketcap REAL,
            pe_ratio REAL,
            pb REAL
        );
        """
        cursor.execute(create_table_sql)
        
        # 为了防止重复插入，可以先清空表（可选）
        # print("清空旧数据...")
        # cursor.execute("DELETE FROM MNSPP;")

        # 使用 executemany 插入数据
        # 使用 INSERT OR IGNORE 来避免因为 UNIQUE 约束（symbol）而插入失败
        insert_sql = """
        INSERT OR IGNORE INTO MNSPP (symbol, name, shares, marketcap, pe_ratio, pb) 
        VALUES (?, ?, ?, ?, ?, ?);
        """
        cursor.executemany(insert_sql, combined_data)
        
        # 提交事务
        conn.commit()
        
        print(f"操作完成。向 'MNSPP' 表中插入或更新了 {cursor.rowcount} 条记录。")
        
    except sqlite3.Error as e:
        print(f"数据库操作失败: {e}")
        
    finally:
        # 确保数据库连接被关闭
        if conn:
            conn.close()
            print("数据库连接已关闭。")

# --- 运行主函数 ---
if __name__ == '__main__':
    create_and_populate_db()