import json
import pyperclip
import re
import subprocess

def copy2clipboard():
    script = '''
    tell application "System Events"
	    keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

def is_uppercase_letters(text):
    return bool(re.match(r'^[A-Z]+$', text))

def update_json_file(filename, new_etf):
    with open(filename, 'r+') as file:
        data = json.load(file)
        if 'ETFs' not in data:
            data['ETFs'] = []
        if new_etf not in data['ETFs']:
            data['ETFs'].append(new_etf)
        file.seek(0)
        json.dump(data, file, indent=2)
        file.truncate()

def main():
    copy2clipboard()
    clipboard_content = pyperclip.paste().strip()
    
    if not clipboard_content:
        print("剪贴板为空")
        return
    
    if not is_uppercase_letters(clipboard_content):
        print("剪贴板内容不全为大写英文字母")
        return
    
    json_files = ['/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json',
                    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json',
                    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json']
    
    for file in json_files:
        try:
            update_json_file(file, clipboard_content)
            print(f"已更新 {file}")
        except Exception as e:
            print(f"更新 {file} 时出错: {str(e)}")

if __name__ == "__main__":
    main()