import pandas as pd
import os

def compare_all_symbols(file_path1, file_path2):
    # ---------------------------------------------------------
    # 1. 读取与预处理
    # ---------------------------------------------------------
    if not os.path.exists(file_path1) or not os.path.exists(file_path2):
        print("错误: 找不到文件。")
        return

    print(f"正在读取文件...\n文件 A (旧): {file_path1}\n文件 B (新): {file_path2}")
    
    try:
        # dtype=str 保证所有数据按字符串处理，避免精度问题
        df1 = pd.read_csv(file_path1, dtype=str)
        df2 = pd.read_csv(file_path2, dtype=str)
    except Exception as e:
        print(f"读取错误: {e}")
        return

    # 数据清洗：去除列名和内容的空格
    df1.columns = df1.columns.str.strip()
    df2.columns = df2.columns.str.strip()
    
    # 这是一个辅助函数，用于快速清洗整个DataFrame的字符串空格
    def clean_df(df):
        return df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    
    df1 = clean_df(df1)
    df2 = clean_df(df2)

    print(f"读取完成。文件 A: {len(df1)} 行, 文件 B: {len(df2)} 行")
    print("-" * 60)

    # ---------------------------------------------------------
    # 2. 全局对比 (一次性 Merge)
    # ---------------------------------------------------------
    # 定义主键
    key_columns = ['Symbol', 'Expiry Date', 'Type', 'Strike']
    
    # 检查列是否存在
    if not set(key_columns).issubset(df1.columns) or not set(key_columns).issubset(df2.columns):
        print(f"错误: 缺少关键列 {key_columns}")
        return

    print("正在进行全量数据比对，请稍候...")
    
    # 填充 Open Interest 的 NaN 为 '0'，方便后续比较
    if 'Open Interest' in df1.columns: df1['Open Interest'] = df1['Open Interest'].fillna('0')
    if 'Open Interest' in df2.columns: df2['Open Interest'] = df2['Open Interest'].fillna('0')

    # 执行全量 Merge
    # indicator=True 会生成 _merge 列: 'left_only', 'right_only', 'both'
    merged = pd.merge(df1, df2, on=key_columns, how='outer', indicator=True, suffixes=('_A', '_B'))

    # ---------------------------------------------------------
    # 3. 按 Symbol 分组处理并输出
    # ---------------------------------------------------------
    
    # 获取所有涉及的 Symbol 列表并排序
    all_symbols = merged['Symbol'].dropna().unique()
    all_symbols.sort()
    
    diff_symbol_count = 0
    
    for symbol in all_symbols:
        # 提取当前 Symbol 的所有数据
        sub_df = merged[merged['Symbol'] == symbol]
        
        # 1. 找出新增和减少的行
        removed = sub_df[sub_df['_merge'] == 'left_only'] # A有B无
        added = sub_df[sub_df['_merge'] == 'right_only']   # B有A无
        
        # 2. 找出存在的行中，Open Interest 发生变化的
        both = sub_df[sub_df['_merge'] == 'both'].copy()
        changed = pd.DataFrame()
        
        if not both.empty and 'Open Interest_A' in both.columns:
            # 比较数值 (字符串比较)
            changed = both[both['Open Interest_A'] != both['Open Interest_B']]

        # ---------------------------------------------------------
        # 4. 判断该 Symbol 是否有差异，如果有则输出
        # ---------------------------------------------------------
        if removed.empty and added.empty and changed.empty:
            # 如果完全一致，直接跳过，不打印任何东西
            continue
            
        diff_symbol_count += 1
        print(f"\n{'='*20} 🔴 差异发现: {symbol} {'='*20}")
        
        # 输出减少的
        if not removed.empty:
            print(f"📉 [减少] (A有B无): {len(removed)} 行")
            cols = key_columns + ['Open Interest_A']
            # 只打印前10行，防止刷屏
            print(removed[cols].head(10).to_string(index=False))
            if len(removed) > 10: print(f"... 等共 {len(removed)} 行")
            print("-" * 30)

        # 输出新增的
        if not added.empty:
            print(f"📈 [新增] (B有A无): {len(added)} 行")
            cols = key_columns + ['Open Interest_B']
            print(added[cols].head(10).to_string(index=False))
            if len(added) > 10: print(f"... 等共 {len(added)} 行")
            print("-" * 30)

        # 输出数值变化的
        if not changed.empty:
            print(f"🔄 [数值变化] (Open Interest 变动): {len(changed)} 行")
            cols = key_columns + ['Open Interest_A', 'Open Interest_B']
            print(changed[cols].head(10).to_string(index=False))
            if len(changed) > 10: print(f"... 等共 {len(changed)} 行")
            print("-" * 30)

    # ---------------------------------------------------------
    # 5. 总结
    # ---------------------------------------------------------
    print("\n" + "="*60)
    print(f"比对结束。")
    print(f"总共检查 Symbol 数: {len(all_symbols)}")
    if diff_symbol_count == 0:
        print("✅ 结论: 两个文件内容完全一致！")
    else:
        print(f"⚠️ 结论: 发现 {diff_symbol_count} 个 Symbol 存在差异 (详情见上文)。")
        print(f"   (未显示的 Symbol 表示完全一致)")
    print("="*60)

# 定义文件路径
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
file_a = os.path.join(BASE_CODING_DIR, "News", "Options_Change copy.csv")
file_b = os.path.join(BASE_CODING_DIR, "News", "Options_Change.csv")

if __name__ == "__main__":
    compare_all_symbols(file_a, file_b)