import subprocess
import time

def keep_awake_macos():
    """
    使用 macOS 原生的 caffeinate 命令。
    -i: 防止系统进入闲置休眠
    -d: 防止显示器进入休眠
    """
    print("正在启动 macOS 防休眠模式...")
    # 启动 caffeinate 进程
    # 只要这个进程存在，系统就不会休眠
    process = subprocess.Popen(['caffeinate', '-id'])
    return process

# 使用示例
if __name__ == "__main__":
    # 启动防休眠
    proc = keep_awake_macos()
    
    try:
        # 你的主逻辑代码...
        print("系统已设置为防休眠，按 Ctrl+C 停止。")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # 程序结束时，关闭 caffeinate 进程
        proc.terminate()
        print("防休眠模式已关闭。")