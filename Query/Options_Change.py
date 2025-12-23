import pandas as pd
import os
import datetime
import glob
import subprocess
import json
import sqlite3

# ==========================================
# 配置区域 (Configuration)
# ==========================================

# 备份文件所在的文件夹路径 (自动模式用)
BACKUP_DIR = '/Users/yanzhang/Coding/News/backup'

# 输出文件的配置
OUTPUT_DIR = '/Users/yanzhang/Coding/News'
OUTPUT_FILENAME = 'Options_Change.csv'

# JSON 映射文件路径
SECTORS_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'

# SQLite 数据库路径
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

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
# 辅助函数：获取 Symbol 对应的最新价格
# ==========================================

def load_symbol_sector_map(json_path):
    """加载 JSON 并反转为 Symbol -> Sector 的字典"""
    if not os.path.exists(json_path):
        print(f"⚠️ 警告: 找不到 JSON 映射文件: {json_path}")
        return {}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        symbol_map = {}
        for sector, symbols in data.items():
            for sym in symbols:
                # 统一转大写，防止大小写不一致
                symbol_map[sym.upper()] = sector
        return symbol_map
    except Exception as e:
        print(f"⚠️ 读取 JSON 失败: {e}")
        return {}

def get_latest_prices(symbols, symbol_sector_map, db_path):
    """
    批量获取 Symbol 的最新价格。
    返回字典: { 'AAPL': 150.23, 'TSLA': 200.50, ... }
    """
    if not os.path.exists(db_path):
        print(f"⚠️ 警告: 找不到数据库文件: {db_path}")
        return {}

    price_dict = {}
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 为了减少查询次数，我们按 Sector 分组查询
        # 结构: { 'Technology': ['AAPL', 'MSFT'], 'Bonds': ['US2Y'] }
        sector_groups = {}
        
        for sym in symbols:
            sym_upper = sym.upper()
            
            # ======================================================
            # [修改点 1] 特例处理：如果是 ^VIX，映射为 VIX 去找 Sector
            # ======================================================
            lookup_sym = 'VIX' if sym_upper == '^VIX' else sym_upper
            
            sector = symbol_sector_map.get(lookup_sym)
            if sector:
                if sector not in sector_groups:
                    sector_groups[sector] = []
                # 注意：这里我们把 lookup_sym (例如 VIX) 加入列表去查库
                # 假设数据库里存的也是 VIX
                sector_groups[sector].append(lookup_sym)
            else:
                # 如果 JSON 里没找到这个 Symbol，就没法查表，跳过或记录
                pass

        print(f"正在从数据库获取 {len(symbols)} 个 Symbol 的最新价格...")

        for sector, sym_list in sector_groups.items():
            if not sym_list:
                continue
            
            # 构造 SQL: 
            # SELECT name, price FROM SectorTable 
            # WHERE name IN (...) AND date = (SELECT MAX(date) FROM SectorTable WHERE name = T.name)
            # 这种逐行子查询可能较慢，改为直接取每个 name 的最新一条
            
            # 优化策略：由于 SQLite 对窗口函数支持较好，或者简单的 group by
            # 这里假设数据量较大，使用 Group By 获取最新日期可能比较快
            
            placeholders = ','.join(['?'] * len(sym_list))
            
            # 方法：先找到每个 Symbol 的最大日期，再 Join 取价格
            # 注意：表名不能参数化，必须字符串拼接，要注意安全性(这里来源是内部JSON，相对安全)
            query = f"""
                SELECT t1.name, t1.price
                FROM "{sector}" t1
                JOIN (
                    SELECT name, MAX(date) as max_date
                    FROM "{sector}"
                    WHERE name IN ({placeholders})
                    GROUP BY name
                ) t2 ON t1.name = t2.name AND t1.date = t2.max_date
            """
            
            try:
                cursor.execute(query, sym_list)
                rows = cursor.fetchall()
                for name, price in rows:
                    name_upper = name.upper()
                    price_dict[name_upper] = price
                    
                    # ======================================================
                    # [修改点 2] 结果回填：如果查到的是 VIX，也要赋值给 ^VIX
                    # ======================================================
                    # 这样主程序里用 ^VIX 也能查到价格
                    if name_upper == 'VIX':
                        price_dict['^VIX'] = price

            except sqlite3.OperationalError as e:
                print(f"   ⚠️ 查询表 '{sector}' 失败 (可能表不存在): {e}")
            except Exception as e:
                print(f"   ⚠️ 查询出错: {e}")

    except Exception as e:
        print(f"数据库连接或查询总错误: {e}")
    finally:
        if conn:
            conn.close()
            
    return price_dict

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

    # ============================================================
    # [新增逻辑 START] 过滤掉新文件中出现的“全新日期”
    # ============================================================
    print("正在过滤全新出现的 Expiry Date ...")
    
    # 1. 获取旧文件中存在的 (Symbol, Expiry Date) 组合
    # 使用 zip 将两列组合成 tuple，放入 set 中以提高查找速度
    valid_old_dates = set(zip(df_old['Symbol'], df_old['Expiry Date']))

    # 2. 给新文件创建一个临时列，用于存放 (Symbol, Expiry Date) 组合
    # 注意：这里假设 Symbol 和 Expiry Date 列一定存在，因为前面已经读取并 clean 过了
    df_new['_date_key'] = list(zip(df_new['Symbol'], df_new['Expiry Date']))

    # 3. 记录过滤前的行数
    rows_before = len(df_new)

    # 4. 执行过滤：只保留那些 key 存在于 valid_old_dates 中的行
    df_new = df_new[df_new['_date_key'].isin(valid_old_dates)].copy()

    # 5. 记录过滤后的行数并打印
    rows_after = len(df_new)
    dropped_count = rows_before - rows_after
    if dropped_count > 0:
        print(f"已剔除 {dropped_count} 行数据 (因为这些 Expiry Date 在旧文件中不存在)。")
    else:
        print("未发现全新的 Expiry Date，无需剔除。")

    # 6. 删除临时列，保持 DataFrame 干净
    df_new.drop(columns=['_date_key'], inplace=True)
    # ============================================================
    # [新增逻辑 END]
    # ============================================================

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
    # (注意：虽然上面过滤了全新的日期，但这里依然需要这个 set 来判断逻辑，
    #  不过理论上经过上面的过滤，情况 A "Expiry 时间没有" 应该不会再发生了，
    #  只会剩下情况 B "Expiry 有但 Strike 没有")
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

    # ============================================================
    # [新增逻辑] 剔除负值
    # ============================================================
    # 过滤掉 1-Day Chg 小于 0 的行 (即只保留增加或持平的)
    merged = merged[merged['1-Day Chg'] >= 0].copy()

    # 6. 标记 "new" (仅当 include_new=True 且行是 right_only 时)
    if include_new:
        # 定义一个函数来应用标记逻辑
        def mark_new_rows(row):
            if row['_merge'] == 'right_only':
                # 检查 (Symbol, Expiry) 是否在旧文件中存在
                if (row['Symbol'], row['Expiry Date']) not in old_expiry_set:
                    # 情况 A: Expiry 时间没有 -> 在时间后面加 new
                    # (由于我们在前面已经过滤了全新的日期，这行代码理论上很少触发，除非逻辑有漏网之鱼，保留无害)
                    row['Expiry Date'] = str(row['Expiry Date']) + " new"
                else:
                    # 情况 B: Expiry 有但 Strike 没有 -> 在 Strike 后面加 new
                    row['Strike'] = str(row['Strike']) + " new"
            return row

        # axis=1 表示逐行应用
        # 注意：如果过滤后 merged 为空，apply 可能会报错或不做任何事，加个判断更稳健
        if not merged.empty:
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
    
    if not merged.empty:
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
        print("没有符合条件的数据 (可能所有变动均为负值或无数据)。")
        return

    result_df = pd.concat(final_rows)

    # ============================================================
    # [新增逻辑] 计算 Distance
    # ============================================================
    print("正在计算 Distance ...")
    
    # 1. 准备 Symbol 列表
    unique_symbols = result_df['Symbol'].unique().tolist()
    
    # 2. 加载映射并获取价格
    symbol_map = load_symbol_sector_map(SECTORS_JSON_PATH)
    price_map = get_latest_prices(unique_symbols, symbol_map, DB_PATH)
    
    # 3. 定义计算函数
    def calculate_distance(row):
        sym = row['Symbol'].upper()
        strike_str = str(row['Strike']).replace(' new', '').strip() # 去掉可能存在的 " new" 标记
        
        # 获取 Strike 数值
        try:
            strike_val = float(strike_str.replace(',', ''))
        except:
            return "N/A" # Strike 无法转为数字
            
        # 获取 Price 数值
        price_val = price_map.get(sym)
        
        if price_val is None:
            return "N/A" # 数据库没查到价格
            
        if price_val == 0:
            return "Err" # 价格为0无法做除数
            
        # 计算公式: (Strike - Price) / Price
        dist = (strike_val - price_val) / price_val
        
        # 格式化为百分比字符串，保留2位小数，例如 "5.23%" 或 "-10.05%"
        return f"{dist * 100:.2f}%"

    # 4. 应用计算
    result_df['Distance'] = result_df.apply(calculate_distance, axis=1)

    # ============================================================
    # 最终整理输出
    # ============================================================

    # 8. 最终整理输出格式
    # 排序：Symbol (A-Z) -> Type (Calls first) -> Abs Chg (Desc)
    result_df = result_df.sort_values(
        by=['Symbol', 'Type_Rank', 'Abs_Chg'], 
        ascending=[True, True, False]
    )

    # 选取需要的列，把 Distance 放在 Strike 后面
    output_cols = ['Symbol', 'Type', 'Expiry Date', 'Strike', 'Distance', 'Open Interest_new', '1-Day Chg']
    final_output = result_df[output_cols].rename(columns={'Open Interest_new': 'Open Interest'})

    # ============================================================
    # [新增修改] 特殊处理：将 ^VIX 显示为 VIX
    # ============================================================
    # 将 Symbol 列中完全等于 '^VIX' 的值替换为 'VIX'
    final_output['Symbol'] = final_output['Symbol'].replace('^VIX', 'VIX')

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

    if file_new and file_old:
        print("-" * 40)
        print(f"检测到最新文件 (New): {os.path.basename(file_new)}")
        print(f"检测到次新文件 (Old): {os.path.basename(file_old)}")
        print("-" * 40)
        
        # 调用处理函数
        process_options_change(file_old, file_new, TOP_N, INCLUDE_NEW_ROWS)
        show_alert("已生成Option_Change期权的比对结果")
    else:
        print("\n程序终止: 未能获取有效的对比文件。")