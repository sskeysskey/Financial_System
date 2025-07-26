import json
import re
import os
import pyperclip
import subprocess
import sys
import time
from decimal import Decimal
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QInputDialog, QMessageBox)

def get_stock_symbol(default_symbol=""):
    """获取股票代码"""
    app = QApplication.instance() or QApplication(sys.argv)
    
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    
    # 设置窗口标志，确保窗口始终在最前面
    input_dialog.setWindowFlags(
        Qt.WindowTitleHint | 
        Qt.CustomizeWindowHint | 
        Qt.WindowCloseButtonHint
    )
    
    # 显示并激活窗口
    input_dialog.show()
    input_dialog.activateWindow()
    input_dialog.raise_()
    
    # 强制获取焦点
    input_dialog.setFocus(Qt.OtherFocusReason)
    
    if input_dialog.exec_() == QInputDialog.Accepted:
        # 直接将输入转换为大写
        return input_dialog.textValue().strip().upper()
    return None

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

# 读取权重配置文件
def load_weight_groups():
    weight_groups = {}
    try:
        with open('/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json', 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # 将字符串key转换为Decimal
            weight_groups = {Decimal(k): v for k, v in raw_data.items()}
        return weight_groups
    except Exception as e:
        print(f"加载权重配置文件时出错: {e}")
        return {}

# 加载权重组
weight_groups = load_weight_groups()

# 动态生成标签权重配置表
tags_weight_config = {tag: weight for weight, tags in weight_groups.items() for tag in tags}

# 默认权重
DEFAULT_WEIGHT = Decimal('1')

def find_tags_by_symbol(symbol, data):
    tags_with_weight = []
    # 遍历stocks和etfs，找到匹配的symbol并返回其tags
    for category in ['stocks', 'etfs']:
        for item in data[category]:
            if item['symbol'] == symbol:
                for tag in item['tag']:
                    # 从tags_weight_config中获取权重，找不到则使用默认权重
                    weight = tags_weight_config.get(tag, DEFAULT_WEIGHT)
                    tags_with_weight.append((tag, weight))
                return tags_with_weight
    return []

# 添加新的判断函数
def get_symbol_type(symbol, data):
    """判断symbol属于stock还是etf"""
    for item in data['stocks']:
        if item['symbol'] == symbol:
            return 'stock'
    for item in data['etfs']:
        if item['symbol'] == symbol:
            return 'etf'
    return None

def find_symbols_by_tags(target_tags_with_weight, data):
    related_symbols = {'stocks': [], 'etfs': []}
    
    # 创建一个目标标签字典，键为小写标签，值为权重
    target_tags_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}

    for category in ['stocks', 'etfs']:
        for item in data[category]:
            tags = item.get('tag', [])
            matched_tags = []
            used_tags = set()  # 用于记录已经匹配过的标签

            # 第一阶段：完全匹配，使用原始权重
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in target_tags_dict and tag_lower not in used_tags:
                    matched_tags.append((tag, target_tags_dict[tag_lower]))
                    used_tags.add(tag_lower)  # 标记该标签已被完全匹配

            # 第二阶段：部分匹配，根据原始权重大小决定使用哪个权重
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in used_tags:
                    continue  # 跳过已被完全匹配的标签
                for target_tag, target_weight in target_tags_dict.items():
                    # 检查是否为包含关系（任意一方包含另一方）
                    if (target_tag in tag_lower or tag_lower in target_tag) and tag_lower != target_tag:
                        if target_tag not in used_tags:
                            # 如果原始标签权重>1，使用1.0，否则使用原始标签权重
                            if target_weight > Decimal('1.0'):
                                weight_to_use = Decimal('1.0')
                            else:
                                weight_to_use = target_weight
                            matched_tags.append((tag, weight_to_use))
                            used_tags.add(target_tag)
                        break

            if matched_tags:
                related_symbols[category].append((item['symbol'], matched_tags, tags))

    # 按总权重降序排序
    for category in related_symbols:
        related_symbols[category].sort(
            key=lambda x: sum(weight for _, weight in x[1]),
            reverse=True
        )

    return related_symbols

def load_compare_data(file_path):
    compare_data = {}
    with open(file_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if ':' in line:
                sym, value = line.split(':', 1)
                compare_data[sym.strip()] = value.strip()
    return compare_data

def main(symbol):
    # 加载 compare_all 文件中的数据
    compare_data = load_compare_data('/Users/yanzhang/Documents/News/backup/Compare_All.txt')
    
    # 找到给定 symbol 的 tags 及其权重
    target_tags_with_weight = find_tags_by_symbol(symbol, data)
    
    # 从 compare_data 里取出源 symbol 的百分比（如果没有则为空字符串）
    compare_value = compare_data.get(symbol, '')
    
    # 将 Decimal 转换为浮点数并生成输出
    # 在第一行里加上 compare_value
    output_lines = [
        f"Tags with weight for {symbol} ({compare_value}): "
        f"{[(tag, float(weight)) for tag, weight in target_tags_with_weight]}"
    ]

    if not target_tags_with_weight:
        output_lines.append("No tags found for the given symbol.\n")
    else:
        # 找到所有与这些tags模糊匹配的symbols和tags
        related_symbols = find_symbols_by_tags(target_tags_with_weight, data)
    
        # 移除原始symbol以避免自引用
        related_symbols['stocks'] = [item for item in related_symbols['stocks'] if item[0] != symbol]
        related_symbols['etfs'] = [item for item in related_symbols['etfs'] if item[0] != symbol]
        
        output_lines.append(f"\n")
        
        # 获取symbol类型
        symbol_type = get_symbol_type(symbol, data)
        
        # 根据symbol类型决定显示顺序
        categories_order = ['etfs', 'stocks'] if symbol_type == 'etf' else ['stocks', 'etfs']
        
        # 按确定的顺序输出结果
        for category in categories_order:
            title = "【ETFs】" if category == 'etfs' else "【Stocks】"
            if related_symbols[category]:  # 只在有结果时显示类别标题
                output_lines.append(f"\n{title}\n")
                for sym, matched_tags, all_tags in related_symbols[category]:
                    compare_value = compare_data.get(sym, '')
                    total_weight = round(sum(float(weight) for _, weight in matched_tags), 2)
                    output_lines.append(f"{sym:<7}{total_weight:<3} {compare_value:<12}{all_tags}\n")
    
    output_path = '/Users/yanzhang/Documents/News/similar.txt'
    with open(output_path, 'w') as file:
        file.writelines(output_lines)

    # 自动打开文件
    os.system(f'open "{output_path}"')

if __name__ == '__main__':
    try:
        # 检查是否有命令行参数
        if len(sys.argv) > 1:
            # 使用命令行参数作为输入
            symbol = sys.argv[1]
        else:
            pyperclip.copy('')
            # 执行复制操作
            copy2clipboard()
            
            # 获取复制后的剪贴板内容
            new_content = get_clipboard_content()
            
            # 根据剪贴板内容变化确定股票代码
            if not new_content:
                symbol = get_stock_symbol()
                if symbol is None:  # 用户点击取消
                    sys.exit()  # 使用sys.exit()替代return
            else:
                if re.match('^[A-Z-]+$', new_content):
                    # symbol = get_stock_symbol(new_content)
                    symbol = new_content
                else:
                    symbol = get_stock_symbol(new_content)
                if symbol is None:  # 用户点击取消
                    sys.exit()  # 使用sys.exit()替代return
                    
            if not symbol:  # 检查股票代码是否为空
                QMessageBox.warning(None, "警告", "股票代码不能为空")
                sys.exit()  # 使用sys.exit()替代return

        # 读取JSON文件
        with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'r') as file:
            data = json.load(file)

        # 执行主程序
        main(symbol)
        time.sleep(2)

        try:
            os.remove('/Users/yanzhang/Documents/News/similar.txt')
            print("文件已删除")
        except OSError as e:
            print(f"删除文件时出错: {e}")
            
    except Exception as e:
        print(f"程序执行出错: {e}")
        sys.exit(1)