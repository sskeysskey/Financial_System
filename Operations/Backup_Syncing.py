import json
import os
from datetime import datetime, timedelta
import shutil

# --- 配置部分 ---

USER_HOME = os.path.expanduser("~")

# 定义源文件和目标目录的路径
LOCAL_DOWNLOAD_BACKUP = os.path.join(USER_HOME, 'Downloads/backup/DB_backup')

# 新增的带时间戳备份的目标目录
LOCAL_SERVER_DIR = os.path.join(USER_HOME, 'Coding/LocalServer/Resources/Finance')

# version.json 文件路径
VERSION_JSON_PATH = os.path.join(LOCAL_SERVER_DIR, 'version.json')

# 定义需要进行简单覆盖备份的文件
# 格式为: { "源文件路径": ["目标文件路径1", "目标文件路径2", ...] }
SIMPLE_BACKUP_FILES = {
    os.path.join(USER_HOME, 'Coding/Database/Finance.db'): [
        os.path.join(LOCAL_DOWNLOAD_BACKUP, 'Finance.db'),
        os.path.join(LOCAL_SERVER_DIR,    'Finance.db')
    ],
}

# 定义需要进行时间戳备份的源文件列表
TIMESTAMP_BACKUP_SOURCES = [
    os.path.join(USER_HOME, 'Coding/News/backup/Compare_All.txt'),
    os.path.join(USER_HOME, 'Coding/News/Earnings_Release_new.txt'),
    os.path.join(USER_HOME, 'Coding/News/Earnings_Release_next.txt'),
    os.path.join(USER_HOME, 'Coding/News/Earnings_Release_third.txt'),
    os.path.join(USER_HOME, 'Coding/News/Earnings_Release_fourth.txt'),
    os.path.join(USER_HOME, 'Coding/News/Earnings_Release_fifth.txt'),
    os.path.join(USER_HOME, 'Coding/News/HighLow.txt'),
    os.path.join(USER_HOME, 'Coding/Financial_System/Modules/tags_weight.json'),
    os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_panel.json'), # 触发 Intro_Symbol
    os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_All.json'),
    os.path.join(USER_HOME, 'Coding/Financial_System/Modules/description.json'),
    os.path.join(USER_HOME, 'Coding/News/CompareStock.txt'),
    os.path.join(USER_HOME, 'Coding/News/CompareETFs.txt'),
    os.path.join(USER_HOME, 'Coding/News/10Y_newhigh_stock.txt'), # 触发 Intro_Symbol
    os.path.join(USER_HOME, 'Coding/Database/Options_Change.csv'),
    os.path.join(USER_HOME, 'Coding/Database/Options_History.csv'),
    os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Earning_History.json'),
    os.path.join(USER_HOME, 'Coding/News/0.5Y_volume_high.txt'),
]

# 定义触发 Intro_Symbol 更新的特定文件集合
INTRO_SYMBOL_TRIGGERS = {
    os.path.join(USER_HOME, 'Coding/Financial_System/Modules/Sectors_panel.json'),
    os.path.join(USER_HOME, 'Coding/News/10Y_newhigh_stock.txt'),
    os.path.join(USER_HOME, 'Coding/News/Options_History.csv')
}

def is_file_modified(source_path, destination_path):
    """
    模拟 rsync 逻辑：检查文件是否有变化。
    如果返回 True，说明需要复制；返回 False，说明文件一致，跳过。
    判断依据：
    1. 目标文件不存在 -> 需要复制
    2. 文件大小不同 -> 需要复制
    3. 修改时间 (mtime) 不同 -> 需要复制
    """
    if not os.path.exists(destination_path):
        return True

    try:
        s_stat = os.stat(source_path)
        d_stat = os.stat(destination_path)

        # 1. 检查大小 (Size)
        if s_stat.st_size != d_stat.st_size:
            return True

        # 2. 检查修改时间 (Mtime)
        # 注意：文件系统之间的时间戳精度可能不同，这里允许 1 秒以内的误差，或者你可以严格使用 !=
        # rsync 默认逻辑是: size 必须不同 或者 mtime 必须不同
        if int(s_stat.st_mtime) != int(d_stat.st_mtime):
            return True

        return False

    except OSError:
        # 如果获取属性失败，为了安全起见，认为需要复制
        return True

def smart_copy(source_path, destination_path):
    """
    智能复制：仅在源文件有变化时才覆盖。
    返回 True 表示进行了复制，False 表示跳过。
    """
    try:
        # 检查源文件是否存在
        if not os.path.exists(source_path):
            print(f"警告：源文件未找到 {source_path}")
            return False

        # 检查是否需要复制
        if is_file_modified(source_path, destination_path):
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            # copy2 会同时保留文件的元数据（包括 mtime），这对于下次比对至关重要
            shutil.copy2(source_path, destination_path)
            print(f"✅ [更新] 已复制: {os.path.basename(source_path)} -> {destination_path}")
            return True # 返回 True 表示文件发生了变化
        else:
            print(f"⏭️ [跳过] 无变化: {os.path.basename(source_path)}")
            return False # 返回 False 表示文件未变化
    except Exception as e:
        print(f"❌ 复制文件时发生错误: {e}")
        return False

def backup_with_timestamp_and_cleanup():
    """
    执行带时间戳的备份，清理旧文件，并更新version.json。
    """
    print("\n--- 开始执行时间戳备份和清理任务 ---")
    
    # 确保目标目录存在
    os.makedirs(LOCAL_SERVER_DIR, exist_ok=True)
    
    # 1. 计算时间戳
    yesterday = datetime.now() - timedelta(days=1)
    timestamp = yesterday.strftime('%y%m%d')  # 格式化为 YYMMDD

    newly_created_files_info = []
    source_base_names = set()
    
    # 新增：用于记录本次实际更新了哪些源文件
    updated_source_paths = []

    # 2. 复制文件并添加时间戳
    for source_path in TIMESTAMP_BACKUP_SOURCES:
        if not os.path.exists(source_path):
            print(f"警告: 源文件不存在，跳过备份: {source_path}")
            continue

        # 分离文件名和扩展名
        base_name, extension = os.path.splitext(os.path.basename(source_path))
        source_base_names.add(base_name) # 记录基础文件名用于后续清理
        
        # 构建新的带时间戳的文件名和目标路径
        new_filename = f"{base_name}_{timestamp}{extension}"
        destination_path = os.path.join(LOCAL_SERVER_DIR, new_filename)
        
        # 执行智能复制，并捕获返回值
        is_updated = smart_copy(source_path, destination_path)
        
        # 如果文件发生了实质性更新（复制操作），记录下来
        if is_updated:
            updated_source_paths.append(source_path)
        
        file_type = 'text' if extension.lower() == '.txt' else extension.lstrip('.').lower()
        newly_created_files_info.append({
            "name": new_filename,
            "type": file_type
        })

    # 3. 清理旧文件
    print("\n--- 开始清理旧的备份文件 ---")
    for filename in os.listdir(LOCAL_SERVER_DIR):
        # 分离文件名，检查是否是我们管理的文件
        parts = filename.split('_')
        if len(parts) > 1:
            base_name = '_'.join(parts[:-1])
            file_timestamp_ext = parts[-1]
            
            # 检查文件是否属于本次备份的类型，并且时间戳不是最新的
            if base_name in source_base_names and not file_timestamp_ext.startswith(timestamp):
                file_to_delete = os.path.join(LOCAL_SERVER_DIR, filename)
                try:
                    os.remove(file_to_delete)
                    print(f"🗑️ 已删除旧文件: {file_to_delete}")
                except OSError as e:
                    print(f"删除文件时出错 {file_to_delete}: {e}")

    # 4. 更新 version.json
    print("\n--- 开始更新 version.json ---")
    # 将本次实际更新的文件列表传递给 update 函数
    update_version_json(newly_created_files_info, source_base_names, updated_source_paths)

def update_version_json(new_files_info, updated_base_names, updated_files_list):
    """
    更新version.json文件：增加版本号，处理 Eco_Data 和 Intro_Symbol 时间戳。
    """
    try:
        # 读取现有的version.json，如果不存在则创建一个新的结构
        if os.path.exists(VERSION_JSON_PATH):
            with open(VERSION_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            print(f"未找到 {VERSION_JSON_PATH}，将创建一个新的。")
            data = {"version": "1.0", "files": []}

        # --- 核心逻辑修改：更新 Eco_Data 和 Intro_Symbol ---
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # 1. 检查是否有 Intro_Symbol 触发文件发生了变更
        # 如果 updated_files_list 中包含 INTRO_SYMBOL_TRIGGERS 中的任意一个
        intro_updated = False
        for trigger_file in INTRO_SYMBOL_TRIGGERS:
            if trigger_file in updated_files_list:
                intro_updated = True
                break
        
        if intro_updated:
            data['Intro_Symbol'] = current_time_str
            print(f"⏰ 检测到关键文件变更，已更新 Intro_Symbol: {current_time_str}")

        # 2. 检查是否有“其他文件”发生了变更 (Eco_Data)
        # 逻辑：变更列表中存在 不属于 INTRO_SYMBOL_TRIGGERS 的文件
        eco_updated = False
        for updated_file in updated_files_list:
            if updated_file not in INTRO_SYMBOL_TRIGGERS:
                eco_updated = True
                break
        
        if eco_updated:
            data['Eco_Data'] = current_time_str
            print(f"⏰ 检测到常规文件变更，已更新 Eco_Data: {current_time_str}")
        
        # 确保这两个字段存在（即使没有更新，也保证json结构完整，如果是新文件）
        if 'Intro_Symbol' not in data:
            data['Intro_Symbol'] = current_time_str
        if 'Eco_Data' not in data:
            data['Eco_Data'] = current_time_str

        # -----------------------------------------------

        # 更新版本号
        try:
            major, minor = data.get('version', '1.0').split('.')
            data['version'] = f"{major}.{int(minor) + 1}"
            print(f"版本号已更新为: {data['version']}")
        except ValueError:
            print("警告: 版本号格式不正确，重置为 '1.1'")
            data['version'] = '1.1'

        # 过滤旧文件条目并添加新条目
        existing_files = data.get('files', [])
        filtered_files = []
        
        for entry in existing_files:
            name = entry.get('name', '')
            parts = name.split('_')
            if len(parts) > 1:
                base_name = '_'.join(parts[:-1])
                # 只有当这个基础名不在本次处理列表中时，才保留（因为新的会随后添加）
                if base_name not in updated_base_names:
                    filtered_files.append(entry)
            else:
                filtered_files.append(entry)

        data['files'] = filtered_files + new_files_info

        with open(VERSION_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"{VERSION_JSON_PATH} 已成功更新。")

    except json.JSONDecodeError:
        print(f"错误: {VERSION_JSON_PATH} 文件格式不正确，无法解析。")
    except Exception as e:
        print(f"更新 {VERSION_JSON_PATH} 时发生未知错误: {e}")

# --- 主程序执行 ---

if __name__ == "__main__":
    
    # 1. 执行简单的覆盖备份
    print("--- 开始执行简单覆盖备份 ---")
    for source, dest_list in SIMPLE_BACKUP_FILES.items():
        for dest in dest_list:
            smart_copy(source, dest)

    # 2. 执行带时间戳的备份、清理和version.json更新
    backup_with_timestamp_and_cleanup()
    
    print("\n所有任务已完成。")
