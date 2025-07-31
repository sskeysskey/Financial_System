import json
import sqlite3
import logging
import os

# --- 配置日志记录 ---
# 设置日志级别为INFO，这样INFO, WARNING, ERROR级别的日志都会被记录
# 日志格式包含时间、日志级别和消息内容
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 文件路径配置 ---
# 请确保这些路径是正确的
blacklist_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/Blacklist.json"
screener_file_path = "/Users/yanzhang/Downloads/screener_below_250520.txt"
db_file_path = "/Users/yanzhang/Coding/Database/Finance.db"

def process_stock_data_deletion():
    """
    主函数，用于处理从数据库中删除黑名单股票数据的逻辑。
    """
    # --- 1. 加载黑名单中的 'screener' 股票代码 ---
    try:
        with open(blacklist_file_path, 'r', encoding='utf-8') as f:
            blacklist_data = json.load(f)
        # 获取 "screener"键下的股票列表，如果键不存在或列表为空，则默认为空列表
        symbols_to_delete_from_blacklist = blacklist_data.get("screener", [])
        if not symbols_to_delete_from_blacklist:
            logging.warning(f"在黑名单文件 '{blacklist_file_path}' 的 'screener' 分组下没有找到任何股票代码，或者 'screener' 键不存在。")
            return
        logging.info(f"从黑名单 'screener' 分组中加载的待处理股票代码: {symbols_to_delete_from_blacklist}")
    except FileNotFoundError:
        logging.error(f"黑名单文件未找到: {blacklist_file_path}")
        return
    except json.JSONDecodeError:
        logging.error(f"解析黑名单JSON文件失败: {blacklist_file_path}")
        return
    except Exception as e:
        logging.error(f"加载黑名单时发生未知错误: {e}")
        return

    # --- 2. 处理筛选器文件，建立 股票代码 -> 表名 的映射 ---
    # screener_map 用于存储从 screener_*.txt 文件中解析出来的 股票代码: 表名 对
    screener_map = {}
    try:
        with open(screener_file_path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line: # 跳过空行
                    continue
                
                parts = line.split(":", 1) # 按第一个冒号分割
                if len(parts) < 2:
                    logging.warning(f"筛选器文件第 {line_number} 行格式不正确 (缺少冒号): '{line}' - 跳过此行")
                    continue
                
                symbol = parts[0].strip() # 冒号前的股票代码
                
                data_parts = parts[1].split(",") # 冒号后的数据部分按逗号分割
                if len(data_parts) < 2:
                    logging.warning(f"筛选器文件第 {line_number} 行数据部分格式不正确 (缺少逗号分隔的字段): '{parts[1]}' - 跳过股票代码 '{symbol}'")
                    continue
                
                table_name = data_parts[1].strip() # 第二个字段是表名
                
                if not symbol:
                    logging.warning(f"筛选器文件第 {line_number} 行解析得到空的股票代码 - 跳过此行")
                    continue
                if not table_name:
                    logging.warning(f"筛选器文件第 {line_number} 行解析得到空的表名 (股票代码: '{symbol}') - 跳过此股票代码")
                    continue
                    
                screener_map[symbol] = table_name
        
        if not screener_map:
            logging.warning(f"未能从筛选器文件 '{screener_file_path}' 中解析出任何 股票代码-表名 映射。")
            # 如果screener_map为空，后续操作没有意义，可以提前返回
            # 但为了逻辑完整性，让它继续，这样如果黑名单中有股票，会提示在screener中找不到
        else:
            logging.info(f"从筛选器文件成功解析 {len(screener_map)} 个 股票代码-表名 映射。")

    except FileNotFoundError:
        logging.error(f"筛选器文件未找到: {screener_file_path}")
        return
    except Exception as e:
        logging.error(f"处理筛选器文件时发生未知错误: {e}")
        return

    # --- 3. 连接数据库并执行删除操作 ---
    conn = None # 初始化数据库连接对象
    deleted_something_overall = False # 标记是否实际执行了任何删除操作
    try:
        if not os.path.exists(db_file_path):
            logging.error(f"数据库文件未找到: {db_file_path}")
            return
            
        conn = sqlite3.connect(db_file_path)
        cursor = conn.cursor()
        logging.info(f"成功连接到数据库: {db_file_path}")

        for symbol_to_delete in symbols_to_delete_from_blacklist:
            if symbol_to_delete in screener_map:
                target_table = screener_map[symbol_to_delete]
                try:
                    # 构造SQL语句，注意表名不能直接用占位符?，需要格式化字符串插入
                    # 但要确保 target_table 的来源是可信的（这里它来自我们解析的文件）
                    # 为了安全，表名和列名最好使用双引号括起来，以防它们是SQL关键字或包含特殊字符
                    sql_delete_query = f'DELETE FROM "{target_table}" WHERE "name" = ?'
                    
                    # 执行删除前，可以先查询一下是否存在，以提供更详细的日志
                    cursor.execute(f'SELECT COUNT(*) FROM "{target_table}" WHERE "name" = ?', (symbol_to_delete,))
                    count_before_delete = cursor.fetchone()[0]

                    if count_before_delete > 0:
                        cursor.execute(sql_delete_query, (symbol_to_delete,))
                        # cursor.rowcount 会返回受影响的行数
                        rows_deleted = cursor.rowcount 
                        conn.commit() # 提交事务使更改生效
                        if rows_deleted > 0:
                            logging.info(f"成功: 从表 '{target_table}' 中删除了 {rows_deleted} 条关于股票代码 '{symbol_to_delete}' 的记录。")
                            deleted_something_overall = True
                        else:
                            # 这种情况理论上不应该发生，因为我们先检查了count_before_delete
                            logging.warning(f"警告: 尝试从表 '{target_table}' 删除股票代码 '{symbol_to_delete}'，但没有行被实际删除 (rowcount=0)，尽管查询显示有 {count_before_delete} 条记录。")
                    else:
                        logging.info(f"信息: 在表 '{target_table}' 中未找到股票代码 '{symbol_to_delete}' 的数据，无需删除。")

                except sqlite3.Error as db_err:
                    # 如果发生数据库错误（例如表不存在），记录错误并回滚（尽管单个操作的回滚意义不大，除非有更复杂的事务）
                    conn.rollback() 
                    logging.error(f"数据库错误: 尝试从表 '{target_table}' 删除股票代码 '{symbol_to_delete}' 时失败: {db_err}")
                except Exception as e:
                    logging.error(f"处理股票代码 '{symbol_to_delete}' (表: '{target_table}') 时发生未知错误: {e}")
            else:
                logging.warning(f"跳过: 黑名单中的股票代码 '{symbol_to_delete}' 在筛选器文件数据中未找到对应的表名。")
        
        if not deleted_something_overall and symbols_to_delete_from_blacklist:
            logging.info("所有处理已完成，但没有实际从数据库中删除任何数据行。")
        elif not symbols_to_delete_from_blacklist:
            logging.info("黑名单的 'screener' 列表为空，没有需要处理的股票代码。")


    except sqlite3.Error as e:
        logging.error(f"连接数据库或执行操作时发生SQLite错误: {e}")
    except Exception as e:
        logging.error(f"在数据库操作过程中发生未知错误: {e}")
    finally:
        if conn:
            conn.close() # 确保数据库连接被关闭
            logging.info("数据库连接已关闭。")

if __name__ == "__main__":
    logging.info("--- 开始执行股票数据删除脚本 ---")
    process_stock_data_deletion()
    logging.info("--- 股票数据删除脚本执行完毕 ---")