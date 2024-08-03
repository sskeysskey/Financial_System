import subprocess

applescript_code = 'display dialog "整个字幕文件翻译完毕。" buttons {"OK"} default button "OK"'
process = subprocess.run(['osascript', '-e', applescript_code], check=True)