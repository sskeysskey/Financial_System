import json
import pyperclip
import subprocess

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

def add_to_blacklist(blacklist_file, symbol):
    try:
        # 读取blacklist文件
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查symbol是否已经在etf列表中
        if symbol in data['etf']:
            show_alert(f"{symbol} 已经在blacklist的etf列表中")
            return False
        
        # 添加symbol到etf列表
        data['etf'].append(symbol)
        
        # 写回文件
        with open(blacklist_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        show_alert(f"成功！")
        return True
    except Exception as e:
        show_alert(f"处理blacklist文件时出错: {e}")
        return False

def main():
    blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'

    # 获取股票代码
    Copy_Command_C()
    stock_name = pyperclip.paste().strip()
    
    # 验证股票代码不为空
    if not stock_name:
        show_alert("没有有效的股票代码")
        return
    
    # 更新黑名单
    add_to_blacklist(blacklist_file, stock_name)

if __name__ == "__main__":
    main()  # 没有传参时，执行默认行为