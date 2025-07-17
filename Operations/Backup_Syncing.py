import sqlite3
import json
from datetime import datetime, timedelta
import shutil
import os

# --- 配置部分 ---
# 定义源文件和目标目录的路径，方便管理
LOCAL_DOWNLOAD_BACKUP = '/Users/yanzhang/Downloads/backup/DB_backup'
# 原始备份目标目录
GITHUB_IO_DIR = '/Users/yanzhang/Documents/sskeysskey.github.io/economics'
# 新增的带时间戳备份的目标目录
LOCAL_SERVER_DIR = '/Users/yanzhang/LocalServer/Resources/Finance'
# version.json 文件路径
VERSION_JSON_PATH = os.path.join(LOCAL_SERVER_DIR, 'version.json')

# 定义需要进行简单覆盖备份的文件
# 格式为: { "源文件路径": ["目标文件路径1", "目标文件路径2", ...] }
SIMPLE_BACKUP_FILES = {
    '/Users/yanzhang/Documents/Database/Finance.db': [
        os.path.join(LOCAL_DOWNLOAD_BACKUP, 'Finance.db'),
        os.path.join(LOCAL_SERVER_DIR,    'Finance.db')
    ],
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json': [
        os.path.join(GITHUB_IO_DIR, 'sectors_panel.json')
    ],
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json': [
        os.path.join(GITHUB_IO_DIR, 'sectors_all.json')
    ],
    '/Users/yanzhang/Documents/Financial_System/Modules/description.json': [
        os.path.join(GITHUB_IO_DIR, 'description.json')
    ],
    '/Users/yanzhang/Documents/News/CompareStock.txt': [
        os.path.join(GITHUB_IO_DIR, 'comparestock.txt')
    ],
    '/Users/yanzhang/Documents/News/CompareETFs.txt': [
        os.path.join(GITHUB_IO_DIR, 'Compareetfs.txt')
    ],
    '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt': [
        os.path.join(GITHUB_IO_DIR, 'marketcap_pe.txt')
    ],
}

# 定义需要进行时间戳备份的源文件列表
TIMESTAMP_BACKUP_SOURCES = [
    '/Users/yanzhang/Documents/News/backup/Compare_All.txt',
    '/Users/yanzhang/Documents/News/Earnings_Release_new.txt',
    '/Users/yanzhang/Documents/News/HighLow.txt',
    '/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json',
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json',
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json',
    '/Users/yanzhang/Documents/Financial_System/Modules/description.json',
    '/Users/yanzhang/Documents/News/CompareStock.txt',
]

def copy_and_overwrite(source_path, destination_path):
    """简单的文件复制和覆盖功能"""
    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy2(source_path, destination_path)
        print(f"文件已从 {source_path} 复制到 {destination_path}。")
    except FileNotFoundError:
        print(f"错误：源文件未找到 {source_path}")
    except Exception as e:
        print(f"复制文件时发生错误: {e}")

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
        
        # 复制文件
        copy_and_overwrite(source_path, destination_path)
        
        # 收集新文件的信息用于更新version.json
        # 新增一行：将 .txt 映射为 "text"，其他按扩展名小写
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
                    print(f"已删除旧文件: {file_to_delete}")
                except OSError as e:
                    print(f"删除文件时出错 {file_to_delete}: {e}")

    # 4. 更新 version.json
    print("\n--- 开始更新 version.json ---")
    update_version_json(newly_created_files_info, source_base_names)


def update_version_json(new_files_info, updated_base_names):
    """
    更新version.json文件：增加版本号，移除旧文件条目，添加新文件条目。
    """
    try:
        # 读取现有的version.json，如果不存在则创建一个新的结构
        if os.path.exists(VERSION_JSON_PATH):
            with open(VERSION_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            print(f"未找到 {VERSION_JSON_PATH}，将创建一个新的。")
            data = {"version": "1.0", "files": []}

        # 更新版本号
        try:
            major, minor = data.get('version', '1.0').split('.')
            data['version'] = f"{major}.{int(minor) + 1}"
            print(f"版本号已更新为: {data['version']}")
        except ValueError:
            print("警告: 版本号格式不正确，重置为 '1.1'")
            data['version'] = '1.1'


        # 过滤掉本次更新所涉及的文件的旧条目
        # 逻辑：保留那些基础文件名不在 updated_base_names 集合中的文件条目
        existing_files = data.get('files', [])
        filtered_files = []
        for entry in existing_files:
            name = entry.get('name', '')
            parts = name.split('_')
            if len(parts) > 1:
                base_name = '_'.join(parts[:-1])
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

def export_db_to_json():
    """
    将数据库中最近一年的数据导出为 finance.json。
    """
    print("\n--- 开始将数据库导出为 JSON ---")
    db_file = '/Users/yanzhang/Documents/Database/Finance.db'
    json_output_file = os.path.join(GITHUB_IO_DIR, 'finance.json')
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        database_dict = {}
        one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        for (table_name,) in tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            cols = cursor.fetchall()
            col_names = [c[1] for c in cols]
            
            if 'date' in col_names:
                cursor.execute(
                    f"SELECT * FROM {table_name} WHERE date >= ? ORDER BY date DESC",
                    (one_year_ago,)
                )
            else:
                cursor.execute(f"SELECT * FROM {table_name}")

            rows = cursor.fetchall()
            database_dict[table_name] = [
                dict(zip(col_names, row)) for row in rows
            ]

        with open(json_output_file, 'w', encoding='utf-8') as f:
            json.dump(database_dict, f, indent=4, default=str)

        conn.close()
        print(f"数据库 {db_file} 中最近一年的数据已成功导出为 {os.path.basename(json_output_file)}。")
    except sqlite3.Error as e:
        print(f"数据库操作失败: {e}")
    except Exception as e:
        print(f"导出JSON时发生错误: {e}")

# --- 主程序执行 ---
if __name__ == "__main__":
    # 1. 执行简单的覆盖备份
    print("--- 开始执行简单覆盖备份 ---")
    for source, dest_list in SIMPLE_BACKUP_FILES.items():
        for dest in dest_list:
            copy_and_overwrite(source, dest)

    # 2. 执行带时间戳的备份、清理和version.json更新
    backup_with_timestamp_and_cleanup()

    # 3. 执行数据库到JSON的导出
    export_db_to_json()
    
    print("\n所有任务已完成。")