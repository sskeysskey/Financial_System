import subprocess

# --- 8. 调用 Check_yesterday.py 脚本 ---
print("\n--------------------------------------------------")
print("--- 开始执行 Check_yesterday.py 脚本 ---")
check_yesterday_script_path = '/Users/yanzhang/Documents/Financial_System/Query/Check_yesterday.py'

try:
    # 使用 subprocess.run 来执行另一个 Python 脚本。
    # - ['python', check_yesterday_script_path]: 这是要执行的命令，第一个元素是解释器，第二个是脚本路径。
    # - check=True: 如果被调用的脚本返回非零退出码（通常表示错误），则会抛出一个 CalledProcessError 异常。
    # - capture_output=True: 捕获子进程的标准输出和标准错误。
    # - text=True: 将标准输出和标准错误解码为文本（使用指定的 encoding）。
    # - encoding='utf-8': 指定用于解码的编码，确保中文等字符正确显示。
    result = subprocess.run(
        ['/Library/Frameworks/Python.framework/Versions/Current/bin/python3', check_yesterday_script_path],
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    print("Check_yesterday.py 脚本成功执行。")
    # 打印被调用脚本的输出，方便调试和查看结果
    print("--- Check_yesterday.py 输出开始 ---")
    print(result.stdout)
    print("--- Check_yesterday.py 输出结束 ---")

except FileNotFoundError:
    print(f"错误: 'python' 命令未找到。请确保 Python 已安装并正确配置在系统的 PATH 环境变量中。")
except subprocess.CalledProcessError as e:
    # 如果 check=True 并且脚本执行失败，则会进入这里
    print(f"错误: Check_yesterday.py 脚本执行失败。")
    print(f"返回码: {e.returncode}")
    print("\n--- 标准输出 (stdout) ---")
    print(e.stdout)
    print("\n--- 标准错误 (stderr) ---")
    print(e.stderr)
except Exception as e:
    print(f"调用 Check_yesterday.py 脚本时发生未知错误: {e}")

print("\n所有任务已完成。")