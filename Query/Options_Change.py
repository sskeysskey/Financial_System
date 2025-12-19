import pandas as pd
import os
import datetime
import glob
import subprocess

# ==========================================
# 配置区域 (Configuration)
# ==========================================

# 备份文件所在的文件夹路径 (自动模式用)
BACKUP_DIR = '/Users/yanzhang/Coding/News/backup'

# 输出文件的配置
OUTPUT_DIR = '/Users/yanzhang/Coding/News'
OUTPUT_FILENAME = 'Options_Change.csv'

# 每个 Symbol 的 Calls 和 Puts 各保留前多少名
TOP_N = 50 

# 开关：是否考虑新增的数据 (B有A无)
# True:  考虑新增数据 (计算 Change, 参与排序, 并标记 new)
# False: 不考虑新增数据 (只计算 A和B都有的行)
INCLUDE_NEW_ROWS = True

# ------------------------------------------
# 新增：模式切换配置
# ------------------------------------------

# 模式开关
# True:  手动模式 (使用下方指定的两个具体文件)
# False: 自动模式 (自动寻找 BACKUP_DIR 下最新的两个文件)
USE_MANUAL_MODE = False

# 手动模式下的文件路径 (仅当 USE_MANUAL_MODE = True 时生效)
MANUAL_FILE_OLD = '/Users/yanzhang/Coding/News/backup/Options_251215.csv'
MANUAL_FILE_NEW = '/Users/yanzhang/Coding/News/backup/Options_251216.csv'

# ==========================================
# 核心处理函数
# ==========================================

def process_options_change(file_old, file_new, top_n=50, include_new=True):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始处理...")
    print(f"旧文件 (Old): {os.path.basename(file_old)}")
    print(f"新文件 (New): {os.path.basename(file_new)}")
    print(f"配置: Top {top_n}, 包含新增: {include_new}")

    # 1. 读取文件
    if not os.path.exists(file_old) or not os.path.exists(file_new):
        print("错误: 找不到文件，请检查路径是否正确。")
        return

    try:
        # 关键列读为字符串，防止精度丢失
        dtype_dict = {'Symbol': str, 'Expiry Date': str, 'Type': str, 'Strike': str}
        df_old = pd.read_csv(file_old, dtype=dtype_dict)
        df_new = pd.read_csv(file_new, dtype=dtype_dict)
    except Exception as e:
        print(f"读取错误: {e}")
        return

    # 2. 数据预处理
    # 去除列名空格
    df_old.columns = df_old.columns.str.strip()
    df_new.columns = df_new.columns.str.strip()

    # 去除字符串内容的空格
    def clean_str_cols(df):
        for col in ['Symbol', 'Expiry Date', 'Type', 'Strike']:
            if col in df.columns:
                df[col] = df[col].str.strip()
        return df

    df_old = clean_str_cols(df_old)
    df_new = clean_str_cols(df_new)

    # 数值化 Open Interest (处理逗号, 比如 "1,000" -> 1000)
    # coerce 将无法转换的变为 NaN，fillna(0) 将 NaN 变为 0
    def clean_oi(val):
        if pd.isna(val): return 0
        if isinstance(val, (int, float)): return val
        try:
            return float(str(val).replace(',', ''))
        except:
            return 0.0

    if 'Open Interest' in df_old.columns:
        df_old['Open Interest'] = df_old['Open Interest'].apply(clean_oi)
    else:
        df_old['Open Interest'] = 0.0

    if 'Open Interest' in df_new.columns:
        df_new['Open Interest'] = df_new['Open Interest'].apply(clean_oi)
    else:
        df_new['Open Interest'] = 0.0

    # 3. 准备辅助数据：旧文件中存在的 (Symbol, Expiry) 组合
    # 用于判断是 "新日期" 还是 "新Strike"
    old_expiry_set = set(zip(df_old['Symbol'], df_old['Expiry Date']))

    # 4. 合并数据 (Merge)
    key_columns = ['Symbol', 'Expiry Date', 'Type', 'Strike']
    # how='outer' 保证全量，indicator=True 生成 _merge 列
    merged = pd.merge(df_old, df_new, on=key_columns, how='outer', suffixes=('_old', '_new'), indicator=True)

    # 5. 过滤与计算逻辑
    
    # 规则: "A(旧)有B(新)没有情况就都不考虑了" -> 剔除 left_only
    merged = merged[merged['_merge'] != 'left_only'].copy()

    # 如果开关关闭，剔除 right_only (新增的)
    if not include_new:
        merged = merged[merged['_merge'] == 'both'].copy()

    # 填充数值：
    # 如果是 right_only (新增)，old OI 为 NaN，需要填 0 方便计算
    merged['Open Interest_old'] = merged['Open Interest_old'].fillna(0)
    # new OI 理论上不应该有 NaN (因为剔除了 left_only)，但以防万一
    merged['Open Interest_new'] = merged['Open Interest_new'].fillna(0)

    # 计算 1-Day Chg
    merged['1-Day Chg'] = merged['Open Interest_new'] - merged['Open Interest_old']

    # 6. 标记 "new" (仅当 include_new=True 且行是 right_only 时)
    if include_new:
        # 定义一个函数来应用标记逻辑
        def mark_new_rows(row):
            if row['_merge'] == 'right_only':
                # 检查 (Symbol, Expiry) 是否在旧文件中存在
                if (row['Symbol'], row['Expiry Date']) not in old_expiry_set:
                    # 情况 A: Expiry 时间没有 -> 在时间后面加 new
                    row['Expiry Date'] = str(row['Expiry Date']) + " new"
                else:
                    # 情况 B: Expiry 有但 Strike 没有 -> 在 Strike 后面加 new
                    row['Strike'] = str(row['Strike']) + " new"
            return row

        # axis=1 表示逐行应用
        merged = merged.apply(mark_new_rows, axis=1)

    # 7. 排序逻辑
    # 规则: 按照绝对值从大到小排序
    merged['Abs_Chg'] = merged['1-Day Chg'].abs()

    # 为了实现 "先Calls后Puts"，我们需要一个辅助排序键
    # 假设 Type 只有 'Call'/'Calls' 和 'Put'/'Puts' (不区分大小写)
    merged['Type_Rank'] = merged['Type'].str.lower().apply(lambda x: 0 if 'call' in x else 1)

    # 分组取 Top N
    # 我们需要对每个 (Symbol, Type) 组取 Top N
    # 这里的 Type 是原始 Type，不是 rank
    
    final_rows = []
    
    # 获取所有 Symbol
    all_symbols = merged['Symbol'].unique()
    
    for symbol in all_symbols:
        symbol_df = merged[merged['Symbol'] == symbol]
        
        # 分别处理 Call 和 Put
        for type_val in symbol_df['Type'].unique():
            sub_df = symbol_df[symbol_df['Type'] == type_val]
            
            # 按绝对值降序排序
            sub_df_sorted = sub_df.sort_values(by='Abs_Chg', ascending=False)
            
            # 取前 N 名
            top_records = sub_df_sorted.head(top_n)
            final_rows.append(top_records)

    if not final_rows:
        print("没有符合条件的数据。")
        return

    result_df = pd.concat(final_rows)

    # 8. 最终整理输出格式
    # 排序：Symbol (A-Z) -> Type (Calls first) -> Abs Chg (Desc)
    result_df = result_df.sort_values(
        by=['Symbol', 'Type_Rank', 'Abs_Chg'], 
        ascending=[True, True, False]
    )

    # 选取需要的列
    output_cols = ['Symbol', 'Type', 'Expiry Date', 'Strike', 'Open Interest_new', '1-Day Chg']
    final_output = result_df[output_cols].rename(columns={'Open Interest_new': 'Open Interest'})

    # 9. 保存文件 (修改部分)
    # 确保输出目录存在，如果不存在则创建
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"创建目录: {OUTPUT_DIR}")
        except Exception as e:
            print(f"创建目录失败: {e}")
            return

    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)

    try:
        final_output.to_csv(output_path, index=False)
        print(f"\n✅ 成功生成文件: {output_path}")
        print(f"   共包含 {len(final_output)} 行数据。")
        # 打印前几行预览
        print("\n数据预览:")
        print(final_output.head(10).to_string(index=False))
    except Exception as e:
        print(f"保存文件失败: {e}")

# ==========================================
# 自动查找文件并执行
# ==========================================

def get_latest_two_files(directory, pattern='Options_*.csv'):
    """
    在指定目录下查找符合 pattern 的文件，
    按修改时间倒序排列，返回 (最新文件, 次新文件)
    """
    # 拼接搜索路径
    search_path = os.path.join(directory, pattern)
    # 获取所有匹配的文件列表
    files = glob.glob(search_path)
    
    # 按最后修改时间排序 (reverse=True 表示最新的在前面)
    # os.path.getmtime 获取文件的时间戳
    files.sort(key=os.path.getmtime, reverse=True)
    
    if len(files) < 2:
        return None, None
    
    # files[0] 是最新的 (New)
    # files[1] 是次新的 (Old)
    return files[0], files[1]

def show_alert(message):
    try:
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except Exception as e:
        print(f"弹窗提示失败 (可能是非macOS环境): {e}")

if __name__ == "__main__":
    file_new = None
    file_old = None

    # ----------------------------------------------------
    # 根据配置决定使用 手动模式 还是 自动模式
    # ----------------------------------------------------
    if USE_MANUAL_MODE:
        print(">>> 当前模式: 手动指定文件 (Manual Mode)")
        file_old = MANUAL_FILE_OLD
        file_new = MANUAL_FILE_NEW
        
        # 简单检查文件是否存在
        if not os.path.exists(file_old):
            print(f"❌ 错误: 找不到旧文件: {file_old}")
            file_old = None # 标记为无效
        if not os.path.exists(file_new):
            print(f"❌ 错误: 找不到新文件: {file_new}")
            file_new = None # 标记为无效

    else:
        print(">>> 当前模式: 自动扫描最新文件 (Auto Mode)")
        print(f"正在扫描目录: {BACKUP_DIR} ...")
        file_new, file_old = get_latest_two_files(BACKUP_DIR)
        
        if not file_new or not file_old:
             print("❌ 错误: 在备份目录下未找到至少两个以 'Options_' 开头的 CSV 文件。")

    # ----------------------------------------------------
    # 如果文件都准备好了，开始执行处理
    # ----------------------------------------------------
    if file_new and file_old:
        print("-" * 40)
        print(f"检测到最新文件 (New): {os.path.basename(file_new)}")
        print(f"检测到次新文件 (Old): {os.path.basename(file_old)}")
        print("-" * 40)
        
        # 调用处理函数
        process_options_change(file_old, file_new, TOP_N, INCLUDE_NEW_ROWS)
        show_alert("已生成比对结果")
    else:
        print("\n程序终止: 未能获取有效的对比文件。")