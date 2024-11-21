import sqlite3
import json
from decimal import Decimal, ROUND_HALF_UP

def update_price_precision(db_path, json_path):
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 读取 JSON 文件获取所有表名
        with open(json_path, 'r') as f:
            sector_data = json.load(f)
        
        # 用于记录处理的记录数
        total_records = 0
        updated_records = 0
        
        # 遍历所有表
        for table_name in sector_data.keys():
            # 验证表是否存在
            cursor.execute(f"""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table_name,))
            
            if cursor.fetchone() is None:
                continue
            
            print(f"Processing table: {table_name}")
            
            # 获取所有价格记录
            cursor.execute(f"SELECT id, price FROM {table_name} WHERE price IS NOT NULL")
            records = cursor.fetchall()
            
            total_records += len(records)
            
            # 批量更新处理
            for id_val, price in records:
                if price is None:
                    continue
                    
                # 转换为 Decimal 以确保精确计算
                price_decimal = Decimal(str(price))
                
                # 根据价格大小决定精度
                if abs(price_decimal) < 1:
                    new_price = float(price_decimal.quantize(
                        Decimal('0.0001'), 
                        rounding=ROUND_HALF_UP
                    ))
                else:
                    new_price = float(price_decimal.quantize(
                        Decimal('0.01'), 
                        rounding=ROUND_HALF_UP
                    ))
                
                # 只在价格确实改变时更新数据库
                if abs(new_price - price) > 1e-10:
                    cursor.execute(f"""
                        UPDATE {table_name}
                        SET price = ?
                        WHERE id = ?
                    """, (new_price, id_val))
                    updated_records += 1
            
            # 定期提交以防止事务过大
            conn.commit()
        
        # 最终优化数据库
        print("Optimizing database...")
        cursor.execute("VACUUM")
        conn.commit()
        
        print(f"\nProcessing complete:")
        print(f"Total records processed: {total_records}")
        print(f"Records updated: {updated_records}")
        
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        conn.rollback()
    except Exception as e:
        print(f"发生错误: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'  # 替换为实际的数据库路径
    json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'  # JSON 文件路径
    
    print("Starting price precision update...")
    update_price_precision(db_path, json_path)
    print("Process completed!")

if __name__ == "__main__":
    main()