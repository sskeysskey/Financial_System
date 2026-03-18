import json
import os
import glob
import re
import shutil
from datetime import datetime

def process_market_data(old_file_path, new_file_path, output_file_path):
    """
    通用数据处理函数，对比新旧文件并计算 volume_trend
    """
    # 1. 读取旧文件并建立索引
    old_data_map = {}
    if os.path.exists(old_file_path):
        with open(old_file_path, 'r', encoding='utf-8') as f:
            try:
                old_data = json.load(f)
                for item in old_data:
                    old_data_map[item['name']] = item
            except json.JSONDecodeError:
                print(f"警告: {old_file_path} 格式错误，跳过旧数据读取。")

    # 2. 处理新文件并计算差值与标记
    result_data = []
    if os.path.exists(new_file_path):
        with open(new_file_path, 'r', encoding='utf-8') as f:
            try:
                new_data = json.load(f)
                for item in new_data:
                    name = item['name']
                    new_volume = int(item.get('volume', 0))
                    
                    # 判断是否为新出现的项目
                    if name in old_data_map:
                        # A类型：两者都有
                        old_volume = int(old_data_map[name].get('volume', 0))
                        trend = new_volume - old_volume
                        item['new'] = 0  # 标记为 0
                    else:
                        # B类型：只有新的有
                        trend = new_volume
                        item['new'] = 1  # 标记为 1
                    
                    # 将计算出的 trend 添加到当前对象中
                    item['volume_trend'] = trend
                    
                    # 将完整的对象存入列表
                    result_data.append(item)
            except json.JSONDecodeError:
                print(f"错误: {new_file_path} 格式错误，无法处理。")
                return

    # 3. 按 volume_trend 降序排序
    result_data.sort(key=lambda x: x['volume_trend'], reverse=True)

    # 4. 写入结果文件
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    print(f"处理完成，结果已保存至: {output_file_path}\n")

def get_latest_two_files(base_dir, prefix):
    """
    根据前缀查找目录下最近的两个数据文件
    假设文件名格式为 prefix_YYMMDD.json
    """
    # 使用 [0-9]* 确保只匹配带有数字日期后缀的文件，避开 _trend.json 文件
    search_pattern = os.path.join(base_dir, f"{prefix}_[0-9]*.json")
    files = glob.glob(search_pattern)
    
    # 因为日期格式是 YYMMDD，直接按字符串降序排列即可让最新的文件排在前面
    files.sort(reverse=True)
    
    if len(files) >= 2:
        new_file = files[0] # 最新的文件
        old_file = files[1] # 次新的文件
        return old_file, new_file
    else:
        return None, None

# ================= 配置区域 =================
db_dir = "/Users/yanzhang/Coding/Database/"
dl_dir = "/Users/yanzhang/Downloads/"
backup_dir = "/Users/yanzhang/Coding/News/backup/prediction/"
platforms = ["kalshi", "polymarket"]

# 获取今天日期的 YYMMDD 格式
today_str = datetime.now().strftime("%y%m%d")

# 确保目标文件夹存在
os.makedirs(db_dir, exist_ok=True)
os.makedirs(backup_dir, exist_ok=True)

# ================= 步骤 1: 检查并移动今天的文件 =================
print(f"今天的系统日期时间戳为: {today_str}\n")
for platform in platforms:
    target_filename = f"{platform}_{today_str}.json"
    db_file_path = os.path.join(db_dir, target_filename)
    dl_file_path = os.path.join(dl_dir, target_filename)
    
    # 如果 Database 目录下没有今天的文件
    if not os.path.exists(db_file_path):
        # 去 Downloads 目录下找
        if os.path.exists(dl_file_path):
            print(f"在 Downloads 找到今天的文件，正在移动到 Database: {target_filename}")
            shutil.move(dl_file_path, db_file_path)
        else:
            print(f"提示: 无论是在 Database 还是 Downloads 都没有找到今天的文件: {target_filename}")
    else:
        print(f"Database 目录中已存在今天的文件: {target_filename}")

print("-" * 40)

# ================= 步骤 2: 执行对比与输出 =================
for platform in platforms:
    print(f"开始检查 [{platform}] 的数据并计算趋势...")
    # 注意：现在基准目录改为了 db_dir
    old_file, new_file = get_latest_two_files(db_dir, platform)
    
    if old_file and new_file:
        # --- 新增逻辑：提取日期 ---
        # 假设文件名是 platform_YYMMDD.json
        # 使用正则提取最后的数字部分
        match = re.search(r'_(\d+)\.json$', os.path.basename(new_file))
        date_str = match.group(1) if match else "unknown_date"
        
        # 输出文件也保存到 db_dir
        output_filename = f"{platform}_trend_{date_str}.json"
        output_file = os.path.join(db_dir, output_filename)
        
        print(f"找到文件:\n - 旧文件: {os.path.basename(old_file)}\n - 新文件: {os.path.basename(new_file)}")
        print(f"输出文件将保存为: {output_filename}")
        
        process_market_data(old_file, new_file, output_file)
    else:
        print(f"警告: [{platform}] 在 Database 目录下的历史文件不足两个，无法进行趋势计算。\n")

print("-" * 40)

# ================= 步骤 3: 备份非今天的文件 =================
print("开始清理 Database 目录，备份旧文件...")
for platform in platforms:
    # 需要匹配原始文件和 trend 文件
    patterns = [
        f"{platform}_[0-9]*.json",
        f"{platform}_trend_[0-9]*.json"
    ]
    
    for pattern in patterns:
        search_pattern = os.path.join(db_dir, pattern)
        files = glob.glob(search_pattern)
        
        for file_path in files:
            filename = os.path.basename(file_path)
            # 提取文件名中的时间戳
            match = re.search(r'_(\d+)\.json$', filename)
            if match:
                file_date = match.group(1)
                # 如果时间戳不是今天的日期，则移动到 backup 目录
                if file_date != today_str:
                    backup_file_path = os.path.join(backup_dir, filename)
                    print(f"备份旧文件: {filename} -> {backup_dir}")
                    shutil.move(file_path, backup_file_path)

print("\n所有流程执行完毕！")