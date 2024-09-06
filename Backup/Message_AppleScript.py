import subprocess

def display_dialog(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)