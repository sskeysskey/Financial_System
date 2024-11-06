import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import pyperclip
import matplotlib
import subprocess

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def get_db_connection(db_path):
    """创建数据库连接"""
    return sqlite3.connect(db_path)

def query_database(conn, query, params):
    """查询数据库并返回DataFrame"""
    return pd.read_sql_query(query, conn, params=params)

def on_key_press(event):
    """当按下ESC键时关闭图表并退出程序"""
    if event.key == 'escape':
        plt.close('all')

def plot_price_trend(df, title):
    """绘制价格趋势图"""
    plt.figure(figsize=(12, 6))
    
    # 修改背景颜色
    ax = plt.gca()  # 获取当前的坐标轴对象
    ax.set_facecolor('#2e2e2e')  # 深色背景
    plt.gcf().set_facecolor('#2e2e2e')  # 整个图表的背景

    # 绘制价格趋势线
    plt.plot(df['date'], df['price'], marker='o', color='#00ff7f')  # 绿色线条

    # 设置标题和标签的颜色
    plt.title(title, color='white')

    # 设置坐标轴刻度标签颜色
    plt.xticks(color='white', rotation=45)
    plt.yticks(color='white')

    # 设置网格线颜色
    plt.grid(True, color='#444444')  # 深灰色网格线
    
    plt.tight_layout()
    
    # 连接键盘事件处理函数
    plt.gcf().canvas.mpl_connect('key_press_event', on_key_press)
    
    plt.show()

def display_dialog(message):
    """使用AppleScript显示弹窗提示"""
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def main():
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    query = """
    SELECT date, price
    FROM Earning
    WHERE name = ?
    ORDER BY date
    """
    
    Copy_Command_C()
    clipboard_content = pyperclip.paste().strip()
    
    try:
        with get_db_connection(db_path) as conn:
            df = query_database(conn, query, (clipboard_content,))
            
            if df.empty:
                display_dialog(f"没有找到与 '{clipboard_content}' 相关的数据。")
            else:
                df['date'] = pd.to_datetime(df['date'])
                plot_price_trend(df, f"{clipboard_content} 财报历史记录")
    
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")

if __name__ == "__main__":
    main()