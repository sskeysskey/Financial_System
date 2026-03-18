import sqlite3

# 数据库路径
db_path = '/Users/yanzhang/Coding/Database/Finance.db'
# 输出文件路径
output_path = '/Users/yanzhang/Downloads/a.txt'

# 需要处理的表名列表
tables = [
    "ETFs", "Basic_Materials", "Communication_Services", 
    "Consumer_Cyclical", "Consumer_Defensive", "Energy", 
    "Financial_Services", "Healthcare", "Industrials", 
    "Real_Estate", "Technology", "Utilities"
]

def process_finance_data():
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        all_results = []

        # 1. 获取所有数据
        for table in tables:
            # 1. 获取该表中的最新日期
            cursor.execute(f"SELECT MAX(date) FROM {table}")
            latest_date_tuple = cursor.fetchone()
            if not latest_date_tuple or latest_date_tuple[0] is None:
                continue
            
            latest_date = latest_date_tuple[0]
            
            query = f"""
            SELECT name, price, volume, (price * volume) as total_value 
            FROM {table} 
            WHERE date = ?
            """
            cursor.execute(query, (latest_date,))
            rows = cursor.fetchall()

            for row in rows:
                # row结构: (name, price, volume, total_value)
                all_results.append({
                    "table": table,
                    "name": row[0],
                    "total_value": row[3],
                    "date": latest_date
                })
        conn.close()

        # 2. 排序：先按表名，再按金额升序
        sorted_results = sorted(all_results, key=lambda x: (x['table'], x['total_value']))

        # 3. 写入文件并限制每组 50 个
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"{'表名':<25} | {'名称':<10} | {'最新日期':<12} | {'成交总额 (Price*Vol)':<20}\n")
            f.write("-" * 80 + "\n")
            
            current_table = None
            count = 0
            
            for item in sorted_results:
                # 如果切换到新表，重置计数器
                if item['table'] != current_table:
                    current_table = item['table']
                    count = 0
                
                # 如果还没满 50 个，则写入
                if count < 50:
                    f.write(f"{item['table']:<25} | {item['name']:<10} | {item['date']:<12} | {item['total_value']:,.2f}\n")
                    count += 1
                # 如果 count >= 50，循环会直接跳过该条数据，直到遇到下一个表

        print(f"处理完成！结果已保存至: {output_path}")

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    process_finance_data()