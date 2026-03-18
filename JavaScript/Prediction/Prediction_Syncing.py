import json
import os
from datetime import datetime
import shutil
import hashlib  # 新增：用于计算MD5

# --- 配置部分 ---
USER_HOME = os.path.expanduser("~")

# --- 新增：Prediction 相关的路径配置 ---
PREDICTION_SOURCE_DIR = os.path.join(USER_HOME, 'Coding/Database')
PREDICTION_TARGET_DIR = os.path.join(USER_HOME, 'Coding/LocalServer/Resources/Prediction')
PREDICTION_VERSION_JSON_PATH = os.path.join(PREDICTION_TARGET_DIR, 'version.json')

def calculate_md5(file_path):
    """
    计算并返回文件的MD5哈希值
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"❌ 计算MD5时出错 {file_path}: {e}")
        return ""

def cleanup_old_prediction_files(today_str, file_prefixes):
    """
    清理 Prediction 目录下的旧文件，只保留今天的文件和 version.json
    """
    print("\n--- 开始清理旧的 Prediction 文件 ---")
    
    if not os.path.exists(PREDICTION_TARGET_DIR):
        return
    
    # 今天应该保留的文件名集合
    today_files = {f"{prefix}_{today_str}.json" for prefix in file_prefixes}
    today_files.add('version.json')  # 也保留 version.json
    
    try:
        for filename in os.listdir(PREDICTION_TARGET_DIR):
            file_path = os.path.join(PREDICTION_TARGET_DIR, filename)
            
            # 跳过目录
            if os.path.isdir(file_path):
                continue
            
            # 如果不在今天的文件列表中，则删除
            if filename not in today_files:
                try:
                    os.remove(file_path)
                    print(f"🗑️ 已删除旧文件: {filename}")
                except Exception as e:
                    print(f"❌ 删除文件失败 {filename}: {e}")
    
    except Exception as e:
        print(f"❌ 清理旧文件时发生错误: {e}")
    
def backup_prediction_files():
    """
    处理 Prediction 目录下的四个当天 JSON 文件，计算 MD5 并更新对应的 version.json
    """
    print("\n--- 开始执行 Prediction 文件备份与更新 ---")
    
    os.makedirs(PREDICTION_TARGET_DIR, exist_ok=True)
    
    # 获取今天的日期 YYMMDD 格式
    today_str = datetime.now().strftime('%y%m%d')
    
    # 需要处理的四个文件前缀
    file_prefixes = ['kalshi', 'kalshi_trend', 'polymarket', 'polymarket_trend']
    new_files_info = []
    
    files_updated = False

    for prefix in file_prefixes:
        filename = f"{prefix}_{today_str}.json"
        source_path = os.path.join(PREDICTION_SOURCE_DIR, filename)
        target_path = os.path.join(PREDICTION_TARGET_DIR, filename)
        
        if os.path.exists(source_path):
            # 复制文件
            is_copied = smart_copy(source_path, target_path)
            if is_copied:
                files_updated = True
            
            # 计算目标文件的 MD5
            file_md5 = calculate_md5(target_path)
            
            new_files_info.append({
                "name": filename,
                "type": "json",
                "md5": file_md5
            })
        else:
            print(f"⚠️ 找不到今天的 Prediction 文件: {source_path}")

    # 如果找到了文件，更新 Prediction 的 version.json
    if new_files_info:
        update_prediction_version(new_files_info)
        # 🆕 添加清理旧文件的步骤
        cleanup_old_prediction_files(today_str, file_prefixes)
    else:
        print("⏭️ 没有找到任何今天的 Prediction 文件，跳过更新 version.json。")

def update_prediction_version(new_files_info):
    """
    专门用于更新 Prediction 目录下的 version.json
    """
    print("\n--- 开始更新 Prediction version.json ---")
    current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    try:
        if os.path.exists(PREDICTION_VERSION_JSON_PATH):
            with open(PREDICTION_VERSION_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            print(f"未找到 {PREDICTION_VERSION_JSON_PATH}，将创建一个新的。")
            data = {
                "version": "1.0",
                "min_app_version": "1.0",
                "store_url": "",
                "notification": "",
                "welcome_topics": []
            }

        # 更新 update_time
        data['update_time'] = current_time_str
        print(f"⏰ 已更新 update_time: {current_time_str}")

        # 替换旧的 files 列表为今天最新的四个文件
        data['files'] = new_files_info

        with open(PREDICTION_VERSION_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"✅ {PREDICTION_VERSION_JSON_PATH} 已成功更新。")

    except json.JSONDecodeError:
        print(f"❌ 错误: {PREDICTION_VERSION_JSON_PATH} 文件格式不正确，无法解析。")
    except Exception as e:
        print(f"❌ 更新 {PREDICTION_VERSION_JSON_PATH} 时发生未知错误: {e}")

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

# --- 主程序执行 ---

if __name__ == "__main__":
    # 3. 新增：执行 Prediction 文件的备份、MD5计算和 version.json 更新
    backup_prediction_files()
    print("\n🎉 所有任务已完成。")