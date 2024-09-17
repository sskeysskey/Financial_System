import shutil  # 在文件最开始导入shutil模块

def copy_2_backup(source_path, destination_path):
    shutil.copy2(source_path, destination_path)  # 使用copy2来复制文件，并覆盖同名文件
    print(f"文件已从{source_path}复制到{destination_path}。")

# 备份数据库
copy_2_backup('/Users/yanzhang/Documents/Database/Finance.db', '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db')
copy_2_backup('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/sectors_panel.json')