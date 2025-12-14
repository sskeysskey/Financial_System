import pandas as pd
import os

def compare_csv_files(file_path1, file_path2):
    # 检查文件是否存在
    if not os.path.exists(file_path1):
        print(f"错误: 找不到文件 {file_path1}")
        return
    if not os.path.exists(file_path2):
        print(f"错误: 找不到文件 {file_path2}")
        return

    print(f"正在比较:\n文件 A: {file_path1}\n文件 B: {file_path2}\n" + "-"*50)

    # 读取 CSV 文件
    # dtype=str 确保所有数据作为字符串读取，避免因为浮点数精度问题导致的误报
    try:
        df1 = pd.read_csv(file_path1, dtype=str)
        df2 = pd.read_csv(file_path2, dtype=str)
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
        return

    # 1. 比较基本形状 (行数和列数)
    if df1.shape != df2.shape:
        print(f"差异: 文件形状不同。")
        print(f"文件 A: {df1.shape[0]} 行, {df1.shape[1]} 列")
        print(f"文件 B: {df2.shape[0]} 行, {df2.shape[1]} 列")
    else:
        print("基本形状: 相同 (行数和列数一致)")

    # 2. 比较列名
    if list(df1.columns) != list(df2.columns):
        print("\n差异: 列名不同。")
        print(f"文件 A 列名: {list(df1.columns)}")
        print(f"文件 B 列名: {list(df2.columns)}")
        # 如果列名不同，后续内容比较可能会出错，建议停止或仅比较共有列
        common_cols = list(set(df1.columns) & set(df2.columns))
        print(f"将仅比较共有列: {common_cols}")
        df1 = df1[common_cols]
        df2 = df2[common_cols]
    else:
        print("列名: 相同")

    # 3. 比较内容
    # 填充 NaN 为空字符串以避免 NaN != NaN 的问题
    df1 = df1.fillna('')
    df2 = df2.fillna('')

    # 如果行数不同，无法直接进行逐单元格比较，先尝试找出仅仅存在于某一个文件中的行
    if df1.shape[0] != df2.shape[0]:
        print("\n由于行数不同，无法进行逐行对齐比较。正在查找完全独特的行...")
        # 这种方法适合找出哪些行是新增的或删除的
        # 注意：这对于大数据集可能会比较慢
        merged = df1.merge(df2, indicator=True, how='outer')
        unique_to_file1 = merged[merged['_merge'] == 'left_only']
        unique_to_file2 = merged[merged['_merge'] == 'right_only']
        
        if not unique_to_file1.empty:
            print(f"\n仅在文件 A 中存在的行数: {len(unique_to_file1)}")
            print(unique_to_file1.drop(columns=['_merge']).head().to_string())
        
        if not unique_to_file2.empty:
            print(f"\n仅在文件 B 中存在的行数: {len(unique_to_file2)}")
            print(unique_to_file2.drop(columns=['_merge']).head().to_string())
            
    else:
        # 如果行数相同，进行精确的逐单元格比较
        comparison_values = df1.values == df2.values
        
        if comparison_values.all():
            print("\n结论: 两个文件内容完全一致！")
        else:
            # 找出不匹配的位置
            rows, cols = np.where(comparison_values == False)
            
            print(f"\n结论: 发现内容差异！共有 {len(rows)} 处不同。")
            print("\n详细差异列表 (前 20 个):")
            print(f"{'行号':<10} | {'列名':<20} | {'文件 A 内容':<30} | {'文件 B 内容':<30}")
            print("-" * 100)
            
            count = 0
            for row, col in zip(rows, cols):
                col_name = df1.columns[col]
                val1 = df1.iloc[row, col]
                val2 = df2.iloc[row, col]
                print(f"{row:<10} | {col_name:<20} | {str(val1):<30} | {str(val2):<30}")
                
                count += 1
                if count >= 20:
                    print(f"... 还有 {len(rows) - 20} 处差异未显示")
                    break

# 引入 numpy 用于位置查找
import numpy as np

# 定义文件路径
file_a = '/Users/yanzhang/Coding/News/backup/Options_251214.csv'
file_b = '/Users/yanzhang/Coding/News/backup/Options_251214 copy.csv'

# 执行比较
if __name__ == "__main__":
    compare_csv_files(file_a, file_b)