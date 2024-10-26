import sqlite3
import json
import pyperclip
import sys
import subprocess
import time
from PyQt5.QtWidgets import QApplication, QInputDialog, QLineEdit, QWidget, QMessageBox
from PyQt5.QtCore import Qt

def get_clipboard_content():
    """获取剪贴板内容，包含错误处理"""
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception:
        return ""

def copy2clipboard():
    """执行复制操作并等待复制完成"""
    try:
        script = '''
        tell application "System Events"
            keystroke "c" using {command down}
        end tell
        '''
        subprocess.run(['osascript', '-e', script], check=True)
        # 给系统一点时间来完成复制操作
        time.sleep(0.5)
        return True
    except subprocess.CalledProcessError:
        return False

def get_stock_symbol(default_symbol=""):
    """获取股票代码"""
    app = QApplication.instance() or QApplication(sys.argv)
    
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
    
    if input_dialog.exec_() == QInputDialog.Accepted:
        # 直接将输入转换为大写
        return input_dialog.textValue().strip().upper()
    return None

# 使用 PyQt5 实现弹出界面获取 price_divisor
def get_price_divisor():
    """获取拆股比例"""
    app = QApplication.instance() or QApplication(sys.argv)

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
    return None

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    
    # 保存初始剪贴板内容
    initial_content = get_clipboard_content()
    
    # 执行复制操作
    if not copy2clipboard():
        QMessageBox.warning(None, "警告", "复制操作失败")
        return
    
    # 获取复制后的剪贴板内容
    new_content = get_clipboard_content()
    
    # 根据剪贴板内容变化确定股票代码
    if initial_content == new_content:
        name = get_stock_symbol()
        if name is None:  # 用户点击取消
            return
    else:
        name = get_stock_symbol(new_content)
        if name is None:  # 用户点击取消
            return
            
    if not name:  # 检查股票代码是否为空
        QMessageBox.warning(None, "警告", "股票代码不能为空")
        return

    # 加载 JSON 文件
    try:
        with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as f:
            sectors_data = json.load(f)
    except Exception as e:
        QMessageBox.critical(None, "错误", f"无法加载JSON文件: {str(e)}")
        return

    # 查找表名
    table_name = None
    for t_name, stock_list in sectors_data.items():
        if name in stock_list:
            table_name = t_name
            break

    if table_name is None:
        QMessageBox.warning(None, "警告", f"股票代码 {name} 不在JSON文件中找到对应的表名。")
        return

    # 获取拆股比例
    price_divisor = get_price_divisor()
    if price_divisor is None:  # 用户点击取消
        return
        
    if price_divisor <= 0:  # 验证拆股比例
        QMessageBox.warning(None, "警告", "拆股比例必须大于0")
        return
    
    try:
        # 连接数据库并执行更新
        conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
        cursor = conn.cursor()

        # 获取最新日期
        cursor.execute(f"SELECT MAX(date) FROM {table_name} WHERE name = ?", (name,))
        latest_date = cursor.fetchone()[0]

        if not latest_date:
            QMessageBox.warning(None, "警告", f"未找到股票 {name} 的数据")
            conn.close()
            return

        # 执行拆股操作
        cursor.execute(f"""
            UPDATE {table_name} 
            SET price = ROUND(price / ?, 2) 
            WHERE name = ? AND date < ?
        """, (price_divisor, name, latest_date))

        conn.commit()
        conn.close()

        QMessageBox.information(None, "成功", "拆股操作已完成")
    except Exception as e:
        QMessageBox.critical(None, "错误", f"数据库操作失败: {str(e)}")

if __name__ == "__main__":
    main()