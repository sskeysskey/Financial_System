import json
import os
import random
from datetime import datetime
import shutil
import hashlib

# --- 配置部分 ---
USER_HOME = os.path.expanduser("~")

# --- Prediction 相关的路径配置 ---
PREDICTION_SOURCE_DIR = os.path.join(USER_HOME, 'Coding/Database')
PREDICTION_TARGET_DIR = os.path.join(USER_HOME, 'Coding/LocalServer/Resources/Prediction')
PREDICTION_VERSION_JSON_PATH = os.path.join(PREDICTION_TARGET_DIR, 'version.json')

# 需要随机遮蔽 hide 字段的文件前缀
RANDOM_HIDE_PREFIXES = {'kalshi', 'kalshi_trend'}

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


def randomize_hide_in_data(data):
    """
    按 subtype 分组，随机将每组中约 1/3 的项目 hide 设为 "0"，其余 2/3 设为 "1"。
    每次运行结果不同。
    """
    # 按 subtype 分组，记录每个 item 的引用
    groups = {}
    for item in data:
        subtype = item.get('subtype', 'unknown')
        if subtype not in groups:
            groups[subtype] = []
        groups[subtype].append(item)

    # 对每个 subtype 组随机设置 hide
    for subtype, items in groups.items():
        n = len(items)
        show_count = round(n / 3)  # 约 1/3 设为显示 ("0")
        # 随机选出要显示的项目索引
        show_indices = set(random.sample(range(n), show_count))
        for i, item in enumerate(items):
            # 如果在选出的 1/3 索引中，设为 "0" (显示)，否则设为 "1" (隐藏)
            item['hide'] = "0" if i in show_indices else "1"
        print(f"  🎲 subtype='{subtype}': 共 {n} 项，随机显示 {show_count} 项，隐藏 {n - show_count} 项")


def copy_with_random_hide(source_path, target_path):
    """
    读取源 JSON 文件，按 subtype 随机设置 hide 字段后写入目标路径。
    由于每次随机结果不同，此函数总是会写入文件。
    """
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            print(f"🎲 正在对 {os.path.basename(source_path)} 执行随机遮蔽...")
            randomize_hide_in_data(data)
        else:
            print(f"⚠️ 文件内容不是数组，跳过随机遮蔽: {os.path.basename(source_path)}")

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"✅ 已随机遮蔽并写入: {os.path.basename(source_path)} -> {target_path}")
        return True
    except Exception as e:
        print(f"❌ 随机遮蔽复制失败 {source_path}: {e}")
        return False


def cleanup_old_prediction_files(today_str, file_prefixes):
    """
    清理 Prediction 目录下的旧文件，保留今天的文件、version.json 和 translation_dict.json
    """
    print("\n--- 开始清理旧的 Prediction 文件 ---")

    if not os.path.exists(PREDICTION_TARGET_DIR):
        return

    # 今天应该保留的文件名集合
    today_files = {f"{prefix}_{today_str}.json" for prefix in file_prefixes}
    today_files.add('version.json')
    today_files.add('translation_dict.json')

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
    处理 Prediction 目录下的文件，确保所有目标文件都被记录到 version.json 中
    """
    print("\n--- 开始执行 Prediction 文件备份与更新 ---")

    os.makedirs(PREDICTION_TARGET_DIR, exist_ok=True)

    # 1. 定义所有需要处理的文件列表
    today_str = datetime.now().strftime('%y%m%d')

    # 定义必须存在的文件列表（动态 + 静态）
    dynamic_prefixes = ['kalshi', 'kalshi_trend', 'polymarket', 'polymarket_trend']
    static_files = ['translation_dict.json']

    # 2. 阶段一：同步/复制文件
    # 处理动态文件
    for prefix in dynamic_prefixes:
        filename = f"{prefix}_{today_str}.json"
        source_path = os.path.join(PREDICTION_SOURCE_DIR, filename)
        target_path = os.path.join(PREDICTION_TARGET_DIR, filename)
        if os.path.exists(source_path):
            if prefix in RANDOM_HIDE_PREFIXES:
                # 对 kalshi 和 kalshi_trend 执行随机遮蔽后写入
                copy_with_random_hide(source_path, target_path)
            else:
                # 其他文件仍使用智能复制
                smart_copy(source_path, target_path)
        else:
            print(f"⚠️ 找不到今天的 Prediction 文件: {source_path}")

    # 处理静态文件
    for filename in static_files:
        source_path = os.path.join(PREDICTION_SOURCE_DIR, filename)
        target_path = os.path.join(PREDICTION_TARGET_DIR, filename)
        if os.path.exists(source_path):
            smart_copy(source_path, target_path)
        else:
            print(f"⚠️ 警告: 静态文件不存在: {source_path}")

    # 3. 阶段二：扫描目标目录，构建 version.json 需要的清单 (只负责盘点)
    all_files_info = []

    # 这里的列表包含了所有我们关心且应该在目标目录里的文件
    files_to_check = [f"{p}_{today_str}.json" for p in dynamic_prefixes] + static_files

    for filename in files_to_check:
        target_path = os.path.join(PREDICTION_TARGET_DIR, filename)
        # 只要文件在目标目录里存在，就计算它的 MD5 并加入清单
        if os.path.exists(target_path):
            all_files_info.append({
                "name": filename,
                "type": "json",
                "md5": calculate_md5(target_path)  # 无论是否刚复制，都重新计算最新 MD5
            })
        else:
            print(f"⚠️ 目标目录中缺少文件，无法记录到 version.json: {filename}")

    # 4. 阶段三：更新 version.json
    if all_files_info:
        update_prediction_version(all_files_info)
        cleanup_old_prediction_files(today_str, dynamic_prefixes)
    else:
        print("⏭️ 没有找到任何文件，跳过更新 version.json。")


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
            return True  # 返回 True 表示文件发生了变化
        else:
            print(f"⏭️ [跳过] 无变化: {os.path.basename(source_path)}")
            return False  # 返回 False 表示文件未变化
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
    # 执行 Prediction 文件的备份、随机遮蔽、MD5计算和 version.json 更新
    backup_prediction_files()
    print("\n🎉 所有任务已完成。")