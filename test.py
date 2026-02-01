import os
import json
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ================= 配置区域 =================

# --- 核心配置：在这里修改时间跨度 ---
LOOKBACK_YEARS = 0.5  # 1 代表一年, 2 代表两年, 3 代表三年...

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# 输入文件路径
DB_PATH = os.path.join(BASE_CODING_DIR, 'Database/Finance.db')
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/Sectors_All.json')
COMPARE_ALL_PATH = os.path.join(BASE_CODING_DIR, 'News/backup/Compare_All.txt')
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/description.json')
BLACKLIST_PATH = os.path.join(BASE_CODING_DIR, 'Financial_System/Modules/blacklist.json')

# 输出文件路径 (文件名会自动包含年份信息，例如 1Y_volume_high.txt)
OUTPUT_FILENAME = f'{LOOKBACK_YEARS}Y_volume_high.txt'
OUTPUT_FILE = os.path.join(BASE_CODING_DIR, f'News/{OUTPUT_FILENAME}')

# 需要扫描的板块 (只扫描股票板块)
TARGET_SECTORS = [
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities"
]

# ================= 辅助函数 =================

def format_volume(vol):
    """将成交量数值转换为 K, M, B 格式"""
    if not vol:
        return "0"
    try:
        vol = float(vol)
    except ValueError:
        return str(vol)
        
    if vol >= 1_000_000_000:
        return f"{vol / 1_000_000_000:.2f}B"
    elif vol >= 1_000_000:
        return f"{vol / 1_000_000:.2f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.2f}K"
    else:
        return f"{int(vol)}"

def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取 JSON 失败 {filepath}: {e}")
        return {}

def load_compare_info(filepath):
    """读取 Compare_All.txt 获取涨跌幅和财报信息"""
    info_map = {}
    if not os.path.exists(filepath):
        return info_map
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':', 1)
                if len(parts) == 2:
                    info_map[parts[0].strip()] = parts[1].strip()
    except Exception as e:
        print(f"读取 Compare_All 失败: {e}")
    return info_map

def load_tags(filepath):
    """读取 description.json 获取中文标签"""
    tag_map = {}
    data = load_json(filepath)
    # 遍历 stocks 和 etfs (虽然主要针对 stocks)
    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            symbol = item.get('symbol')
            tags = item.get('tag', [])
            if symbol and tags:
                tag_map[symbol] = ','.join(tags)
    return tag_map

def get_blacklist(filepath):
    data = load_json(filepath)
    return set(data.get("newlow", []))

def load_latest_earnings(db_path):
    """
    从 Earning 表中获取每只股票最新的财报日期。
    返回字典: {'PDD': '2024-08-26', 'AAPL': '2024-08-01', ...}
    """
    earnings_map = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 使用 GROUP BY 和 MAX(date) 直接获取每个 symbol 最新的日期
        query = "SELECT name, MAX(date) FROM Earning GROUP BY name"
        cursor.execute(query)
        rows = cursor.fetchall()
        for name, date_str in rows:
            if name and date_str:
                earnings_map[name] = date_str
        conn.close()
        print(f"已加载 {len(earnings_map)} 条最新财报日期信息。")
    except Exception as e:
        print(f"读取 Earning 表失败 (可能表不存在): {e}")
    return earnings_map

# ================= 主逻辑 =================

def main():
    print(f"--- 开始筛选 {LOOKBACK_YEARS} 年内成交量创新高的股票 ---")
    print(f"--- 过滤条件: 若今日为财报发布日，则跳过 ---")
    
    # 1. 加载基础数据
    sectors_data = load_json(SECTORS_ALL_PATH)
    compare_map = load_compare_info(COMPARE_ALL_PATH)
    tags_map = load_tags(DESCRIPTION_PATH)
    blacklist = get_blacklist(BLACKLIST_PATH)
    
    # 新增：加载最新财报日期
    latest_earnings_map = load_latest_earnings(DB_PATH)
    
    results = []
    skipped_count = 0
    
    # 2. 连接数据库
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        print(f"无法连接数据库: {e}")
        return

    # 3. 遍历板块和股票
    for table_name in TARGET_SECTORS:
        if table_name not in sectors_data:
            continue
            
        symbols = sectors_data[table_name]
        print(f"正在扫描板块: {table_name} ({len(symbols)} 个代码)...")
        
        for name in symbols:
            if name in blacklist:
                continue
                
            try:
                # A. 获取最新一天的成交量和日期
                query_latest = f"SELECT date, volume FROM {table_name} WHERE name = ? ORDER BY date DESC LIMIT 1"
                cursor.execute(query_latest, (name,))
                latest_row = cursor.fetchone()
                
                if not latest_row or not latest_row[1]:
                    continue
                    
                latest_date_str, latest_volume = latest_row
                latest_volume = float(latest_volume)
                
                # 如果成交量太小（例如停牌或极不活跃），可以过滤，这里设为0
                if latest_volume <= 0:
                    continue

                # --- 新增过滤逻辑：检查是否撞上财报日 ---
                # 如果该股票有财报记录，且最新行情日期 == 最新财报日期
                if name in latest_earnings_map:
                    if latest_date_str == latest_earnings_map[name]:
                        # print(f"跳过 {name}: 今日({latest_date_str})是财报日") # 调试用
                        skipped_count += 1
                        continue
                # ---------------------------------------

                # B. 计算 N 年前的日期
                try:
                    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")
                    # 核心改动：支持小数年份 (例如 0.5 年) 或 整数年份
                    start_date = latest_date - relativedelta(years=int(LOOKBACK_YEARS), months=int((LOOKBACK_YEARS % 1) * 12))
                    start_date_str = start_date.strftime("%Y-%m-%d")
                except ValueError:
                    # 如果日期格式不对，跳过
                    continue
                
                # C. 查询过去 N 年内的最大成交量 (包含最新这一天)
                # 逻辑：如果 MAX(volume) 等于 latest_volume，说明今天就是最大
                query_max = f"SELECT MAX(volume) FROM {table_name} WHERE name = ? AND date >= ? AND date <= ?"
                cursor.execute(query_max, (name, start_date_str, latest_date_str))
                max_vol_row = cursor.fetchone()
                
                if max_vol_row and max_vol_row[0] is not None:
                    max_volume_period = float(max_vol_row[0])
                    
                    # D. 判断是否新高
                    # 使用 >= 确保如果是今天刚创的新高也能被捕获
                    if latest_volume >= max_volume_period:
                        # 组装数据
                        vol_str = format_volume(latest_volume)
                        info_str = compare_map.get(name, "")
                        tags_str = tags_map.get(name, "")
                        
                        # 格式: Sector Symbol [Info] Volume [Tags]
                        # 示例: Financial_Services SNEX 0204后0.02%+ 15.4M 金融服务,清算...
                        
                        line_parts = [table_name, name]
                        if info_str:
                            line_parts.append(info_str)
                        
                        line_parts.append(vol_str)
                        
                        if tags_str:
                            line_parts.append(tags_str)
                            
                        results.append(" ".join(line_parts))
                        
            except Exception as e:
                # 某些表可能缺少字段或数据异常，跳过
                continue

    conn.close()

    # 4. 写入文件
    if results:
        try:
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(results))
            print("\n" + "="*50)
            print(f"成功！已生成文件: {OUTPUT_FILE}")
            print(f"筛选条件: 过去 {LOOKBACK_YEARS} 年内成交量新高 (已剔除财报日)")
            print(f"因财报日剔除数量: {skipped_count}")
            print(f"最终筛选出: {len(results)} 只股票")
            print("="*50)
        except Exception as e:
            print(f"写入文件失败: {e}")
    else:
        print(f"未找到符合条件的股票 (因财报日剔除: {skipped_count})。")

if __name__ == "__main__":
    main()