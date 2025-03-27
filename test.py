import os
import time

# 写入汇总日志文件
output_file = '/Users/yanzhang/Documents/News/screener_sectors.txt'

# 等待1秒
time.sleep(1)

# 打开文件
# 在 macOS 系统下使用 open 命令打开文件
os.system(f"open {output_file}")