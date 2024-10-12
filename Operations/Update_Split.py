import sqlite3
import json
import pyperclip
import sys
import subprocess
from PyQt5.QtWidgets import QApplication, QInputDialog, QLineEdit, QWidget
from PyQt5.QtCore import Qt

def copy2clipboard():
    script = '''
    tell application "System Events"
        keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

copy2clipboard()

# 从剪贴板获取内容
name = pyperclip.paste().strip()

# 加载 JSON 文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as f:
    sectors_data = json.load(f)

# 从 JSON 数据中查找表名
def find_table_name(stock_name, sectors_data):
    for table_name, stock_list in sectors_data.items():
        if stock_name in stock_list:
            return table_name
    return None

# 找到表名
table_name = find_table_name(name, sectors_data)

# 如果表名不存在，抛出错误
if table_name is None:
    raise ValueError(f"股票代码 {name} 不在 JSON 文件中找到对应的表名。")

# 使用 PyQt5 实现弹出界面获取 price_divisor
def get_price_divisor():
    app = QApplication(sys.argv)

    # 创建一个 QInputDialog 对象
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入价格除数")
    input_dialog.setLabelText("请输入拆股比例:")

    # 设置输入框为 "Double" 类型，并设置默认值为 0（但隐藏显示0）
    input_dialog.setDoubleDecimals(2)
    input_dialog.setDoubleValue(0.0)  # 默认值为 0.0
    input_dialog.setDoubleRange(0.0, 100.0)  # 设置数值范围

    # 获取 QLineEdit 对象并设置 placeholder text
    line_edit = input_dialog.findChild(QLineEdit)
    line_edit.setPlaceholderText("请输入有效的拆股比例")  # 设置提示文本
    line_edit.clear()  # 将输入框初始化为空

    # 设置窗口为 "始终在最前" 的模式
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)

    input_dialog.setFocus()  # 强制将焦点设定在弹窗上

    # 显示对话框并获取用户输入
    if input_dialog.exec_() == QInputDialog.Accepted:
        return input_dialog.doubleValue()
    else:
        raise ValueError("用户未输入有效的价格除数")

# 获取用户输入的 price_divisor
price_divisor = get_price_divisor()

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 获取该股票的最新日期
cursor.execute(f"""
    SELECT MAX(date) 
    FROM {table_name} 
    WHERE name = ?
""", (name,))
latest_date = cursor.fetchone()[0]  # 获取最新日期

# 执行拆股操作，排除最新日期的数据
cursor.execute(f"""
    UPDATE {table_name} 
    SET price = ROUND(price / ?, 2) 
    WHERE name = ? AND date < ?
""", (price_divisor, name, latest_date))

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()