import pyperclip
import json
import subprocess
import sys

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
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def update_blacklist(symbol):
    """更新黑名单JSON文件"""
    json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Blacklist.json'
    
    try:
        # 读取现有的JSON文件
        with open(json_path, 'r') as file:
            blacklist = json.load(file)
        
        # 检查symbol是否已经存在于newlow列表中
        if symbol not in blacklist['newlow']:
            # 添加新的symbol到newlow列表
            blacklist['newlow'].append(symbol)
            
            # 将更新后的数据写回文件
            with open(json_path, 'w') as file:
                json.dump(blacklist, file, indent=4)
            
            show_alert(f"成功将 {symbol} 添加到黑名单")
        else:
            show_alert(f"{symbol} 已经在黑名单中")
            
    except Exception as e:
        show_alert(f"更新黑名单时发生错误: {str(e)}")

def main(symbol=None):
    # 获取股票代码
    if symbol is None:
        Copy_Command_C()
        stock_name = pyperclip.paste().strip()
    else:
        stock_name = symbol.strip()
    
    # 验证股票代码不为空
    if not stock_name:
        show_alert("没有有效的股票代码")
        return
    
    # 更新黑名单
    update_blacklist(stock_name)

if __name__ == "__main__":
    # 如果有传参，则使用传递的参数；如果没有传参，则 symbol = None
    if len(sys.argv) > 1:
        main(sys.argv[1])  # 使用传递的第一个参数作为 symbol
    else:
        main()  # 没有传参时，执行默认行为