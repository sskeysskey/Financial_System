import re
import sys
import sqlite3
import subprocess
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
from functools import lru_cache
from scipy.interpolate import interp1d

from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

@lru_cache(maxsize=None)
def fetch_data(db_path, table_name, name):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
            # 为查询字段添加索引
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_name ON {table_name} (name);")
            query = f"SELECT date, price, volume FROM {table_name} WHERE name = ? ORDER BY date;"
            result = cursor.execute(query, (name,)).fetchall()
            if not result:
                raise ValueError("没有查询到可用数据")
            return result
        except sqlite3.OperationalError:
            query = f"SELECT date, price FROM {table_name} WHERE name = ? ORDER BY date;"
            result = cursor.execute(query, (name,)).fetchall()
            if not result:
                raise ValueError("没有查询到可用数据")
            return result

def smooth_curve(dates, prices, num_points=500):
    date_nums = matplotlib.dates.date2num(dates)
    if len(dates) < 4:
        interp_func = interp1d(date_nums, prices, kind='linear')
    else:
        interp_func = interp1d(date_nums, prices, kind='cubic')

    new_date_nums = np.linspace(min(date_nums), max(date_nums), num_points)
    new_prices = interp_func(new_date_nums)
    new_dates = matplotlib.dates.num2date(new_date_nums)

    return new_dates, new_prices

def process_data(data):
    if not data:
        raise ValueError("没有可供处理的数据")
        
    dates, prices, volumes = [], [], []
    for row in data:
        date = datetime.strptime(row[0], "%Y-%m-%d")
        price = float(row[1]) if row[1] is not None else None
        volume = int(row[2]) if len(row) > 2 and row[2] is not None else None
        if price is not None:
            dates.append(date)
            prices.append(price)
            volumes.append(volume)
    
    return dates, prices, volumes

def display_dialog(message):
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def update_plot(line1, fill, line2, dates, prices, volumes, ax1, ax2, show_volume):
    # 处理 prices 和 dates 可能为空的情况
    if not dates or not prices:
        line1.set_data([], [])
        if fill:
            fill.remove() # 确保移除旧的fill对象
            fill = None   # 将fill置为None，因为没有新的fill被创建
        if volumes: # 假设volumes与dates/prices长度一致或已处理
            line2.set_data([], [])
        
        # 设置默认的轴范围当没有数据时
        ax1.set_xlim(datetime.now() - timedelta(days=1), datetime.now())
        ax1.set_ylim(0, 1) # 或者其他合适的默认范围
        if show_volume:
            ax2.set_ylim(0, 1)
        line2.set_visible(show_volume and bool(volumes)) # 仅当有数据时显示
        plt.draw()
        return fill # 返回 None 因为 fill 被移除了

    # --- 数据存在，继续绘图 ---
    line1.set_data(dates, prices)
    if fill:
        fill.remove()
    
    # 添加edgecolor='none'或linewidth=0参数来移除边缘线
    fill = ax1.fill_between(dates, prices, color='lightblue', alpha=0.3, edgecolor='none')
    
    if volumes: # 确保 volumes 列表不为空
        line2.set_data(dates, volumes) # 假设 dates 和 volumes 长度匹配
    else: # 如果 volumes 为空或None
        line2.set_data([],[])

    # X轴范围设置
    date_min_val = np.min(dates)
    date_max_val = np.max(dates)
    if date_min_val == date_max_val:
        # 为单个日期点扩展X轴范围
        ax1.set_xlim(date_min_val - timedelta(days=1), date_max_val + timedelta(days=1))
    else:
        date_range = date_max_val - date_min_val
        right_margin = date_range * 0.01  # 添加1%的右侧余量
        ax1.set_xlim(date_min_val, date_max_val + right_margin)
    
    # Y轴价格范围设置
    min_p = np.min(prices)
    max_p = np.max(prices)
    if min_p == max_p:
        buffer = abs(min_p * 0.1) if min_p != 0 else 0.1
        buffer = max(buffer, 1e-6) # 确保buffer有一个最小正值
        min_p -= buffer
        max_p += buffer
        if min_p >= max_p: # 进一步安全检查
            max_p = min_p + buffer # 确保 max_p > min_p
    ax1.set_ylim(min_p, max_p)
    
    # Y轴成交量范围设置 (ax2)
    if show_volume:
        if volumes:
            valid_volumes = [v for v in volumes if v is not None]
            if valid_volumes:
                min_v = np.min(valid_volumes) # 通常成交量不为负，所以min_v可能是0
                max_v = np.max(valid_volumes)
                if max_v == min_v : # 所有成交量相同或只有一个点
                     ax2.set_ylim(0, max_v + 1 if max_v is not None else 1) # 从0开始，给最大值加一点buffer
                else:
                     ax2.set_ylim(0, max_v) # 成交量Y轴通常从0开始
            else: # valid_volumes 为空
                ax2.set_ylim(0, 1) # 默认范围
        else: # volumes 列表本身为空或None
            ax2.set_ylim(0, 1)
            
    line2.set_visible(show_volume and bool(volumes)) # bool(volumes) 检查volumes是否非空
    plt.draw()
    return fill

# --- PyQt5 替换实现 ---
class InfoDialog(QDialog):
    """一个自定义的对话框，用于显示信息，并支持按ESC键关闭"""
    def __init__(self, title, content, font_family, font_size, width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(0, 0, width, height)
        self.center_on_screen()

        layout = QVBoxLayout(self)
        
        text_box = QTextEdit(self)
        text_box.setReadOnly(True)
        text_box.setFont(QFont(font_family, font_size))
        text_box.setText(content)
        
        layout.addWidget(text_box)
        self.setLayout(layout)

    def keyPressEvent(self, event):
        """重写按键事件，当按下ESC时关闭窗口"""
        if event.key() == Qt.Key_Escape:
            self.close()

    def center_on_screen(self):
        """将窗口居中显示"""
        screen_geometry = QApplication.desktop().screenGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

# ### 新增：统一的外部脚本执行函数 ###
def execute_external_script(script_type, keyword):
    # 集中管理所有外部脚本的路径
    base_path = '/Users/yanzhang/Coding/Financial_System'
    script_configs = {
        'earning_input': f'{base_path}/Operations/Insert_Earning_Manual.py',
        'earning_edit': f'{base_path}/Operations/Editor_Earning_DB.py',
        'tags_edit': f'{base_path}/Operations/Editor_Tags.py',
        'event_input': f'{base_path}/Operations/Insert_Events.py',
        'event_edit': f'{base_path}/Operations/Editor_Events.py',
        'symbol_compare': f'{base_path}/Query/Compare_Chart.py',
        'similar_tags': f'{base_path}/Query/Search_Similar_Tag.py',
        'check_kimi': '/Users/yanzhang/Coding/ScriptEditor/CheckKimi_Earning.scpt',
        'check_futu': '/Users/yanzhang/Coding/ScriptEditor/Stock_CheckFutu.scpt'
    }

    script_path = script_configs.get(script_type)
    if not script_path:
        display_dialog(f"未知的脚本类型: {script_type}")
        return

    try:
        # 根据文件扩展名判断是AppleScript还是Python脚本
        if script_path.endswith('.scpt'):
            subprocess.Popen(['osascript', script_path, keyword])
        else:
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.Popen([python_path, script_path, keyword])
    except Exception as e:
        display_dialog(f"启动程序失败: {e}")

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel="False"):
    """
    主函数，绘制股票或ETF的时间序列图表。支持成交量、标签说明、信息弹窗、区间切换等功能。
    按键说明：
    - v：显示或隐藏成交量
    - 1~9：快速切换不同时间区间
    - `：弹出信息对话框
    - d：查询数据库并弹窗显示
    - c：切换显示或隐藏标记点（红色全局点)
    - a：切换显示或隐藏收益公告日期点（白色点）
    - x：切换显示或隐藏标记点（橙色特定点)
    - e：启动财报数据编辑程序
    - n：启动财报数据输入程序
    - t：启动标签Tags编辑程序
    - w：启动新增Event程序
    - q：启动修改Event程序
    - 方向键上下：在不同时间区间间移动
    - ESC：关闭所有图表，并在panel为True时退出系统
    """
    # 确保PyQt5应用实例存在
    app = QApplication.instance() or QApplication(sys.argv)
    plt.close('all')  # 关闭所有图表
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    matplotlib.rcParams['toolbar'] = 'none'  # <-- 添加这一行来隐藏工具栏

    # --- 修改开始: 处理 pb_text ---
    # 如果传入的 share 是一个元组，则拆分为 share_val 与 pb
    if isinstance(share, tuple):
        share_val, pb = share
        # 如果 pb 是 None 或空字符串，则显示 '--'，否则显示其值
        pb_text = f"{pb}" if pb not in [None, ""] else "--"
    else:
        share_val = share
        pb_text = "--"  # 如果没提供元组，pb默认为'--'
    # --- 修改结束 ---

    show_volume = False
    mouse_pressed = False
    initial_price = None
    initial_date = None
    fill = None
    show_global_markers = False  # 红色点默认不显示
    show_specific_markers = True  # 橙色点默认显示
    show_earning_markers = True  # 默认不显示收益点
    show_all_annotations = False  # 新增：浮窗默认显示

    try:
        data = fetch_data(db_path, table_name, name)
    except ValueError as e:
        display_dialog(f"{e}")
        return

    try:
        dates, prices, volumes = process_data(data)
    except ValueError as e:
        display_dialog(f"{e}")
        return

    if not dates or not prices:
        display_dialog("没有有效的数据来绘制图表。")
        return

    # 使用插值函数生成更多的平滑数据点
    smooth_dates, smooth_prices = smooth_curve(dates, prices)

    #这里可以修改整个表格的大小
    fig, ax1 = plt.subplots(figsize=(15, 8))
    
    # 这里调整图表居上边沿的距离
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.83, top=0.8)
    ax2 = ax1.twinx()

    # 隐藏ax2的轴线和刻度
    ax2.axis('off')

    fig.patch.set_facecolor('black')
    ax1.set_facecolor('black')
    ax1.tick_params(axis='x', colors='white')
    ax1.tick_params(axis='y', colors='white')
    ax2.tick_params(axis='y', colors='white')

    highlight_point = ax1.scatter([], [], s=100, color='cyan', zorder=5)
    
    # 绘制插值后的平滑曲线
    line1, = ax1.plot(
        smooth_dates,
        smooth_prices,
        marker='',
        linestyle='-',
        linewidth=2,
        color='cyan',
        alpha=0.7,
        label='Price'
    )
    # 在每个原始价格点处添加一个小小的白色散点，并保存散点对象引用
    small_dot_scatter = ax1.scatter(dates, prices, s=5, color='white', zorder=1)
    
    line2, = ax2.plot(
        dates,
        volumes,
        marker='o',
        markersize=2,
        linestyle='-',
        linewidth=2,
        color='magenta',
        alpha=0.7,
        label='Volume'
    )
    fill = ax1.fill_between(dates, prices, color='cyan', alpha=0.2)
    line2.set_visible(show_volume)

    # 处理全局标记点和特定股票标记点
    global_markers = {}
    specific_markers = {}
    earning_markers = {}  # 新增：收益公告标记点
    # 保存所有注释的引用
    all_annotations = []
    
    # 获取全局标记点
    if 'global' in json_data:
        for date_str, text in json_data['global'].items():
            try:
                marker_date = datetime.strptime(date_str, "%Y-%m-%d")
                global_markers[marker_date] = text
            except ValueError:
                print(f"无法解析全局标记日期: {date_str}")
    
    # 获取特定股票的标记点
    found_item = None
    for source in ['stocks', 'etfs']:
        for item in json_data.get(source, []):
            if item['symbol'] == name and 'description3' in item:
                found_item = item
                for date_obj in item.get('description3', []):
                    for date_str, text in date_obj.items():
                        try:
                            marker_date = datetime.strptime(date_str, "%Y-%m-%d")
                            specific_markers[marker_date] = text
                        except ValueError:
                            print(f"无法解析特定标记日期: {date_str}")
                break
        if found_item:
            break
    
    # 修改获取收益公告日期的部分
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date", (name,))
            for date_str, price_change in cursor.fetchall():
                try:
                    marker_date = datetime.strptime(date_str, "%Y-%m-%d")
                    # 查找与 marker_date 最接近的日期（假设主数据的 dates 列表已经生成）
                    closest_date = min(dates, key=lambda d: abs(d - marker_date))
                    index = dates.index(closest_date)
                    marker_price = prices[index]  # 获取该日期对应的价格
                    latest_price = prices[-1]     # 最新一天的价格

                    # 计算当天价格与最新价格之间的百分比差值，注意防止除以0
                    if marker_price and marker_price != 0:
                        diff_percent = ((latest_price - marker_price) / marker_price) * 100
                    else:
                        diff_percent = 0

                    # 拼接提示文本，先显示最新价差，再显示昨日财报数据
                    earning_markers[marker_date] = f"昨日财报: {price_change}%\n最新价差: {diff_percent:.2f}%\n{date_str}"
                except ValueError:
                    print(f"无法解析收益公告日期: {date_str}")
    except sqlite3.OperationalError as e:
        print(f"获取收益数据失败: {e}")
    
    # 标记点
    global_scatter_points = []
    specific_scatter_points = []
    earning_scatter_points = []  # 新增：收益公告标记点列表
    
    # 绘制全局标记点（红色）
    for marker_date, text in global_markers.items():
        if min(dates) <= marker_date <= max(dates):
            closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
            closest_date = dates[closest_date_idx]
            price_at_date = prices[closest_date_idx]
            scatter = ax1.scatter([closest_date], [price_at_date], s=100, color='red', 
                                #  alpha=0.7, zorder=4, picker=5) # 初始设为可见
                                 alpha=0.7, zorder=4, picker=5, visible=show_global_markers)  # 初始设为不可见
            global_scatter_points.append((scatter, closest_date, price_at_date, text))
    
    # 绘制特定股票标记点（橙色）
    for marker_date, text in specific_markers.items():
        if min(dates) <= marker_date <= max(dates):
            closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
            closest_date = dates[closest_date_idx]
            price_at_date = prices[closest_date_idx]
            scatter = ax1.scatter([closest_date], [price_at_date], s=100, color='white', 
                                #  alpha=0.7, zorder=4, picker=5) # 初始设为可见
                                 alpha=0.7, zorder=4, picker=5, visible=show_specific_markers)  # 初始设为不可见
            specific_scatter_points.append((scatter, closest_date, price_at_date, text))
    
    # 新增：绘制财报收益公告标记点（白色）
    for marker_date, text in earning_markers.items():
        if min(dates) <= marker_date <= max(dates):
            closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
            closest_date = dates[closest_date_idx]
            price_at_date = prices[closest_date_idx]
            scatter = ax1.scatter([closest_date], [price_at_date], s=100, color='orange', 
                                 alpha=0.7, zorder=4, picker=5, visible=show_earning_markers)
            earning_scatter_points.append((scatter, closest_date, price_at_date, text))

    # 为每个全局标记点(红色点)创建固定注释，交替设置左上与左下偏移
    red_offsets = [(-60, 50),(50, -60), (-70, 45), (-50, -45)]  # 第一个为左上、第二个为右下、第三个还是为左上、第四个为右上
    for i, (scatter, date, price, text) in enumerate(global_scatter_points):
        offset = red_offsets[i % 4]
        annotation = ax1.annotate(
            text,
            xy=(date, price),  # 箭头指向的位置
            xytext=offset,     # 使用交替的偏移
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="black", alpha=0.8),
            arrowprops=dict(arrowstyle="->", color='red'),
            color='red',
            fontsize=12,
            visible=False  # 默认隐藏(因为红色点初始设定为不可见)
        )
        all_annotations.append((annotation, 'global', date, price))

    specific_offsets = [
        (-150, 50),    # 偶数（i=0,2,4…）向右下
        (20, -50)   # 奇数（i=1,3,5…）向左下
    ]
    # 为每个特定股票标记点(橙色点)创建固定注释，左右交替偏移
    for i, (scatter, date, price, text) in enumerate(specific_scatter_points):
        offset = specific_offsets[i % 2]
        annotation = ax1.annotate(
            text,
            xy=(date, price),
            xytext=offset,
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="black", alpha=0.8),
            arrowprops=dict(arrowstyle="->", color='white'),
            color='white',
            fontsize=12,
            visible=show_specific_markers and show_all_annotations
        )
        all_annotations.append((annotation, 'specific', date, price))

    # 为每个收益公告标记点(白色点)创建固定注释，将偏移修改为右上（例如 (50,50)）
    for scatter, date, price, text in earning_scatter_points:
        annotation = ax1.annotate(
            text,
            xy=(date, price),
            xytext=(50, 50),  # 修改为右上偏移
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="black", alpha=0.8),
            arrowprops=dict(arrowstyle="->", color='cyan'),
            color='orange',
            fontsize=12,
            visible=show_earning_markers and show_all_annotations
        )
        all_annotations.append((annotation, 'earning', date, price))

    # 添加一个新的函数来控制所有浮窗的显示或隐藏
    def toggle_all_annotations():
        """切换所有注释的显示状态"""
        nonlocal show_all_annotations
        show_all_annotations = not show_all_annotations
        
        # 更新所有注释的可见性
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'global':
                annotation.set_visible(show_global_markers and show_all_annotations)
            elif anno_type == 'specific':
                annotation.set_visible(show_specific_markers and show_all_annotations)
            elif anno_type == 'earning':
                annotation.set_visible(show_earning_markers and show_all_annotations)
        
        fig.canvas.draw_idle()
    
    def clean_percentage_string(percentage_str):
        """
        将可能包含 % 符号的字符串转换为浮点数。
        """
        try:
            return float(percentage_str.strip('%'))
        except ValueError:
            return None

    turnover = (
        (volumes[-1] * prices[-1]) / 1e6
        if volumes and volumes[-1] is not None and prices[-1] is not None
        else None
    )

    if turnover is not None:
        if turnover >= 1000:  # 大于等于1000M时转换为B
            turnover = turnover / 1000  # 转换为B
            turnover_str = f"{turnover:.1f}B"
        else:  # 小于1000M时保持M
            turnover_str = f"{turnover:.1f}M"
    else:
        turnover_str = ""

    # 从compare中去除中文和加号
    filtered_compare = re.sub(r'[\u4e00-\u9fff+]', '', compare)
    compare_value = clean_percentage_string(filtered_compare)

    # 根据compare和换手额做"可疑"标记
    if turnover is not None and turnover < 100 and compare_value is not None and compare_value > 0:
        turnover_str = f"可疑{turnover_str}"

    # 注意：这里用 share_val（而不是原来的 share）来计算换手率
    try:
        # 尝试将 share_val 转换为整数
        # 如果 share_val 是 'N/A' 或其他非数字字符串，会进入 except 块
        share_int = int(share_val)
        if volumes and volumes[-1] is not None and share_int > 0:
            turnover_rate = f"{(volumes[-1] / share_int) * 100:.2f}"
        else:
            # 如果成交量数据缺失或股本为0，则显示'--'
            turnover_rate = "--"
    except (ValueError, TypeError):
        # 如果 share_val 无法转换为整数 (例如 'N/A')
        turnover_rate = "--"
    # --- 修改结束 ---
        
    # --- 修改开始: 格式化 marketcap ---
    marketcap_in_billion = ""
    if marketcap not in [None, "N/A"]:
        mc_val = float(marketcap) / 1e9
        # 检查除以10亿后的值是否为整数
        if mc_val == int(mc_val):
            # 如果是整数，则不显示小数点
            marketcap_in_billion = f"{int(mc_val)}B"
        else:
            # 如果有小数，则保留一位小数
            marketcap_in_billion = f"{mc_val:.1f}B"
    # --- 修改结束 ---

    # --- 修改开始: 处理 pe_text ---
    pe_text = f"{pe}" if pe not in [None, "N/A"] else "--"
    # --- 修改结束 ---

    # clickable = False
    tag_str = ""
    fullname = ""
    data_sources = ['stocks', 'etfs']
    found = False

    # 在JSON中查找对应的name信息以展示完整名称、标签、描述等
    for source in data_sources:
        for item in json_data.get(source, []):
            if item['symbol'] == name:
                tags = item.get('tag', [])
                fullname = item.get('name', '')
                tag_str = ','.join(tags)
                if len(tag_str) > 45:
                    tag_str = tag_str[:45] + '...'
                clickable = True
                found = True
                break
        if found:
            break

    # 根据 table_name 动态组合标题
    if table_name == 'ETFs':
        # 如果是ETF，则不显示市值、PE和PB
        title_text = (
            f'{name}  {compare}  {turnover_str} '
            f'"{table_name}" {fullname} {tag_str}'
        )
    else:
        # 对于其他类型（如股票），正常显示所有指标
        title_text = (
            f'{name}  {compare}  {turnover_str} {turnover_rate} '
            f'{marketcap_in_billion} {pe_text} {pb_text} "{table_name}" {fullname} {tag_str}'
        )

    # 移除原来的标题设置，改用可选择的文本
    # 不再使用 ax1.set_title()，而是使用 text() 创建可选择文本
    title_text_obj = fig.text(
        0.5, 0.95,  # 位置坐标 (x=0.5居中, y=0.95在顶部)
        title_text,
        ha='center',  # 水平居中
        va='top',     # 垂直顶部对齐
        color='orange',  # 保持金黄色
        fontsize=16,
        fontweight='bold',
        transform=fig.transFigure,  # 使用figure坐标系
        picker=False  # 关闭picker功能，使其不可点击跳转
    )

    def show_stock_etf_info(event=None):
        """
        使用 PyQt5 展示当前name在JSON数据中的信息。
        """
        for source in data_sources:
            for item in json_data.get(source, []):
                if item['symbol'] == name:
                    descriptions = item
                    info = (
                        f"{name}\n"
                        f"{descriptions['name']}\n\n"
                        f"{descriptions['tag']}\n\n"
                        f"{descriptions['description1']}\n\n"
                        f"{descriptions['description2']}"
                    )
                    # 创建并显示对话框
                    dialog = InfoDialog("Information", info, 'Arial', 22, 600, 750)
                    dialog.exec_()
                    return
        display_dialog(f"未找到 {name} 的信息")

    # 修改toggle_global_markers函数
    def toggle_global_markers():
        """切换全局标记点（红色）的显示状态"""
        nonlocal show_global_markers
        show_global_markers = not show_global_markers
        
        # 更新所有全局标记点的可见性
        for scatter, _, _, _ in global_scatter_points:
            scatter.set_visible(show_global_markers)
        
        # 更新对应注释的可见性
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'global':
                annotation.set_visible(show_global_markers and show_all_annotations)
        
        fig.canvas.draw_idle()

    # 修改toggle_specific_markers函数
    def toggle_specific_markers():
        """切换特定股票标记点（橙色）的显示状态"""
        nonlocal show_specific_markers
        show_specific_markers = not show_specific_markers
        
        # 更新所有特定股票标记点的可见性
        for scatter, _, _, _ in specific_scatter_points:
            scatter.set_visible(show_specific_markers)
        
        # 更新对应注释的可见性
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'specific':
                annotation.set_visible(show_specific_markers and show_all_annotations)
        
        fig.canvas.draw_idle()

    # 修改toggle_earning_markers函数
    def toggle_earning_markers():
        """切换收益公告标记点的显示状态"""
        nonlocal show_earning_markers
        show_earning_markers = not show_earning_markers
        
        # 更新所有收益公告标记点的可见性
        for scatter, _, _, _ in earning_scatter_points:
            scatter.set_visible(show_earning_markers)
        
        # 更新对应注释的可见性
        for annotation, anno_type, _, _ in all_annotations:
            if anno_type == 'earning':
                annotation.set_visible(show_earning_markers and show_all_annotations)
        
        fig.canvas.draw_idle()

    # 修改update_marker_visibility函数来同时更新注释
    def update_marker_visibility():
        """根据当前时间区间和各开关状态，更新标记点和注释的可见性。"""
        # 提取当前时间区间内显示的最早日期
        current_val = radio.value_selected
        if current_val in time_options:
            years = time_options[current_val]
            if years == 0:
                min_date = min(dates)
            else:
                min_date = datetime.now() - timedelta(days=years * 365)
        else:
            min_date = min(dates)

        # 更新标记点可见性
        for scatter, date, _, _ in global_scatter_points:
            scatter.set_visible((min_date <= date) and show_global_markers)
        for scatter, date, _, _ in specific_scatter_points:
            scatter.set_visible((min_date <= date) and show_specific_markers)
        for scatter, date, _, _ in earning_scatter_points:
            scatter.set_visible((min_date <= date) and show_earning_markers)
        
        # 更新注释可见性
        for annotation, anno_type, date, _ in all_annotations:
            if min_date <= date:
                if anno_type == 'global':
                    annotation.set_visible(show_global_markers and show_all_annotations)
                elif anno_type == 'specific':
                    annotation.set_visible(show_specific_markers and show_all_annotations)
                elif anno_type == 'earning':
                    annotation.set_visible(show_earning_markers and show_all_annotations)
            else:
                annotation.set_visible(False)
        
        fig.canvas.draw_idle()
    
    def on_pick(event):
        """
        当点击标记点时，展示对应信息窗口。
        移除了标题点击功能。
        """
        # 移除标题点击处理
        if event.artist in [point[0] for point in global_scatter_points + specific_scatter_points + earning_scatter_points]:
            # 查找被点击的标记点
            for scatter, date, price, text in global_scatter_points + specific_scatter_points + earning_scatter_points:
                if event.artist == scatter:
                    # 更新注释内容和显示位置
                    annot.xy = (date, price)
                    annot.set_text(f"{datetime.strftime(date, '%Y-%m-%d')}\n{price}\n{text}")
                    annot.get_bbox_patch().set_alpha(0.8)
                    annot.set_fontsize(16)
                    # 调整注释显示位置
                    midpoint = max(dates) - (max(dates) - min(dates)) / 2
                    if date < midpoint:
                        annot.set_position((50, -20))
                    else:
                        annot.set_position((-150, -20))
                    annot.set_visible(True)
                    highlight_point.set_offsets([date, price])
                    highlight_point.set_visible(True)
                    fig.canvas.draw_idle()
                    break

    # --- PyQt5 替换实现 ---
    def create_window_qt(content):
        """
        使用 PyQt5 创建新窗口显示查询数据库的结果。
        """
        dialog = InfoDialog("数据库查询结果", content, "Courier", 20, 900, 600)
        dialog.exec_()

    def query_database(db_path, table_name, condition):
        """
        根据条件查询数据库并返回结果的字符串形式。
        """
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
            cursor.execute(query)
            rows = cursor.fetchall()
            if not rows:
                return "今天没有数据可显示。\n"
            columns = [description[0] for description in cursor.description]
            col_widths = [
                max(len(str(row[i])) for row in rows + [columns])
                for i in range(len(columns))
            ]
            output_text = ' | '.join(
                [col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]
            ) + '\n'
            output_text += '-' * len(output_text) + '\n'
            for row in rows:
                output_text += ' | '.join(
                    [str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)]
                ) + '\n'
            return output_text

    def on_keyword_selected(db_path, table_name, name):
        """
        按关键字查询数据库并弹框显示结果。
        """
        condition = f"name = '{name}'"
        result = query_database(db_path, table_name, condition)
        create_window_qt(result) # 调用 PyQt5 版本的窗口

    if clickable:
        fig.canvas.mpl_connect('pick_event', on_pick)

    ax1.grid(True, color='gray', alpha=0.1, linestyle='--')
    plt.xticks(rotation=45)

    annot = ax1.annotate(
        "",
        xy=(0, 0),
        xytext=(20, 20),
        textcoords="offset points",
        bbox=dict(boxstyle="round", fc="black"),
        arrowprops=dict(arrowstyle="->"),
        color='white'
    )
    annot.set_visible(False)

    # 定义可选时间范围
    time_options = {
        "1m": 0.08,
        "3m": 0.25,
        "6m": 0.5,
        "1Y": 1,
        "2Y": 2,
        "3Y": 3,
        "5Y": 5,
        "10Y": 10,
        "All": 0
    }
    default_index = list(time_options.keys()).index(default_time_range)

    # 配置单选按钮
    rax = plt.axes([0.95, 0.005, 0.05, 0.8], facecolor='black')
    radio = RadioButtons(rax, list(time_options.keys()), active=default_index)
    for label in radio.labels:
        label.set_color('white')
        label.set_fontsize(14)
    radio.circles[default_index].set_facecolor('red')

    # ------ 添加快捷键说明 ------
    instructions = (
        "N： 新财报\n"
        "E： 改财报\n"
        "T： 新标签\n"
        "W： 新事件\n"
        "Q： 改事件\n"
        "K： 查kimi\n"
        "U： 查富途\n"
        "P： 做比较\n"
        "L： 查相似"
    )

    # 在 radio 按钮的 axes 上方绘制说明文字
    rax.text(
        0.5, 1.02,             # 相对坐标：(x=0.5 居中, y=1.02 在 axes 之上)
        instructions,
        transform=rax.transAxes,
        ha="center",           # 水平居中
        va="bottom",           # 从 bottom 开始向上排
        color="white",
        fontsize=10,
        fontfamily="Arial Unicode MS"
    )
    
    # ### 删除：所有独立的 open_* 和 check_* 函数已被移除 ###

    def update_annot(ind):
        """
        更新工具提示位置和文本内容。
        """
        x_data, y_data = line1.get_data()
        xval, yval = x_data[ind["ind"][0]], y_data[ind["ind"][0]]
        annot.xy = (xval, yval)
        
        # 查找当前日期是否有标记信息
        current_date = xval.replace(tzinfo=None)
        global_marker_text = None
        specific_marker_text = None
        earning_marker_text = None  # 新增：收益公告文本
        
        # 只有当标记点可见时才显示对应的事件文本
        # 查找全局标记
        if show_global_markers:
            for marker_date, text in global_markers.items():
                if abs((marker_date - current_date).total_seconds()) < 86400:  # 两天内
                    global_marker_text = text
                    break
                
        if show_specific_markers:
            for marker_date, text in specific_markers.items():
                if abs((marker_date - current_date).total_seconds()) < 86400:  # 两天内
                    specific_marker_text = text
                    break
    
        # 只有当收益标记点可见时才显示收益事件文本
        if show_earning_markers:
            # 查找收益公告标记
            for marker_date, text in earning_markers.items():
                if abs((marker_date - current_date).total_seconds()) < 86400:  # 两天内
                    earning_marker_text = text
                    break
                
        # 如果鼠标按下，则显示与初始点的百分比变化，否则显示日期和数值
        if mouse_pressed and initial_price is not None:
            percent_change = ((yval - initial_price) / initial_price) * 100
            text = f"{percent_change:.1f}%"
            annot.set_color('white')  # 百分比变化使用白色
        else:
            # --- 这是修改的核心逻辑 ---
            text_parts = []
            latest_price = prices[-1]
            current_price = yval
            percent_diff = ((latest_price - current_price) / current_price) * 100

            # 1. 添加日期和当前价格
            text_parts.append(f"{datetime.strftime(xval, '%Y-%m-%d')}")
            text_parts.append(f"{current_price:.2f}")
            text_parts.append("") # 添加一个空行

            # 2. 添加标记文本（全局和特定）
            marker_texts = []
            if global_marker_text:
                marker_texts.append(global_marker_text)
            if specific_marker_text:
                marker_texts.append(specific_marker_text + "\n")

            # 3. 特殊处理财报标记文本，只提取需要的部分
            has_earning_marker = False
            if earning_marker_text:
                # 从预存的财报信息中，只提取包含“昨日财报”的那一行
                for line in earning_marker_text.split('\n'):
                    if "昨日财报" in line:
                        marker_texts.append(line)
                        break
                has_earning_marker = True
            
            if marker_texts:
                text_parts.extend(marker_texts)

            # 4. 在最下方添加与最新价的百分比差值
            text_parts.append(f"最新价差: {percent_diff:.2f}%")
            
            # 组合所有部分
            text = "\n".join(text_parts)
            
            # 设置颜色
            if has_earning_marker and not (global_marker_text or specific_marker_text):
                annot.set_color('orange')  # 收益公告标记使用黄色文字
            elif global_marker_text and not (specific_marker_text or has_earning_marker):
                annot.set_color('red')    # 全局标记使用红色文字
            elif specific_marker_text and not (global_marker_text or has_earning_marker):
                annot.set_color('white')    # 特殊标记使用橘色文字
            elif global_marker_text and (specific_marker_text or has_earning_marker):
                annot.set_color('purple')    # 全局标记使用红色文字
            else:
                annot.set_color('cyan')  # 其他标记使用白色文字
        
        annot.set_text(text)
        annot.get_bbox_patch().set_alpha(0.4)
        annot.set_fontsize(16)
        
        # 检查点的垂直位置
        y_range = ax1.get_ylim()
        y_position_ratio = (yval - y_range[0]) / (y_range[1] - y_range[0])
        
        # 更智能地调整注释位置
        x_range = ax1.get_xlim()
        position_ratio = (matplotlib.dates.date2num(xval) - x_range[0]) / (x_range[1] - x_range[0])
        
        # 根据点在图表中的水平和垂直位置调整注释
        if y_position_ratio < 0.2:  # 如果点在底部区域（靠近X轴）
            # 将注释向上方移动
            y_offset = 60  # 设置一个较大的向上偏移
        elif y_position_ratio > 0.8:    # 如果点在顶部区域
            y_offset = -120  # 默认向下偏移
        else:
            y_offset = -70  # 默认向下偏移
        
        # 根据水平位置调整
        if position_ratio > 0.7:  # 如果点在右侧30%区域
            # 估计文本长度，越长偏移越大
            text_length = len(text)
            x_offset = -20 - min(text_length * 6, 300)  # 根据文本长度动态调整左偏移
            annot.set_position((x_offset, y_offset))
        elif position_ratio < 0.3:  # 如果点在左侧30%区域
            annot.set_position((50, y_offset))
        else:  # 中间区域
            # 如果在底部区域，仍然向上偏移
            if y_position_ratio < 0.2:
                annot.set_position((-200, y_offset))
            else:
                annot.set_position((-200, -70))  # 放到下方

    def hover(event):
        """
        鼠标在图表上滑动时，更新垂直参考线、注释、以及高亮最近的数据点。
        """
        if event.inaxes in [ax1, ax2]:
            if event.xdata:
                current_date = matplotlib.dates.num2date(event.xdata).replace(tzinfo=None)
                vline.set_xdata(current_date)
                vline.set_visible(True)

                x_data, y_data = line1.get_data()
                # 找到最近的点
                nearest_index = (np.abs(np.array(x_data) - current_date)).argmin()
                selected_date = x_data[nearest_index]
                selected_price = y_data[nearest_index]

                # --- 新增：根据是否命中标记点来切换高亮点颜色 ---
                highlight_color = 'cyan'  # 默认
                # 红色全局标记
                for _, date, _, _ in global_scatter_points:
                    if date == selected_date:
                        highlight_color = 'red'
                        break
                else:
                    # 白色特定标记
                    for _, date, _, _ in specific_scatter_points:
                        if date == selected_date:
                            highlight_color = 'white'
                            break
                    else:
                        # 橙色收益公告标记
                        for _, date, _, _ in earning_scatter_points:
                            if date == selected_date:
                                highlight_color = 'orange'
                                break
                # 应用到 highlight_point
                highlight_point.set_color(highlight_color)
                # --------------------------------------------------------

                # 只有非常靠近数据点时才显示高亮和注释
                date_distance = 0.2 * ((ax1.get_xlim()[1] - ax1.get_xlim()[0]) / 365)
                if np.isclose(
                    matplotlib.dates.date2num(selected_date),
                    matplotlib.dates.date2num(current_date),
                    atol=date_distance
                ):
                    update_annot({"ind": [nearest_index]})
                    annot.set_visible(True)
                    highlight_point.set_offsets([[selected_date, selected_price]])
                    highlight_point.set_visible(True)
                else:
                    annot.set_visible(False)
                    highlight_point.set_visible(False)

                fig.canvas.draw_idle()
            else:
                # 鼠标移出绘图区
                vline.set_visible(False)
                annot.set_visible(False)
                highlight_point.set_visible(False)
                fig.canvas.draw_idle()
        elif event.inaxes == rax:
            vline.set_visible(False)
            annot.set_visible(False)
            highlight_point.set_visible(False)
            fig.canvas.draw_idle()

    def update(val):
        """
        根据单选按钮选项更新图表显示的时间范围。
        """
        years = time_options[val]
        if years == 0:
            filtered_dates, filtered_prices, filtered_volumes = dates, prices, volumes
            min_date = min(dates)
        else:
            min_date = datetime.now() - timedelta(days=years * 365)
            filtered_dates = [d for d in dates  if d >= min_date]
            filtered_prices = [p for d,p in zip(dates, prices)  if d >= min_date]
            filtered_volumes= [v for d,v in zip(dates, volumes) if d >= min_date] if volumes else None

        # ---------- 如果某个区间竟然把所有点都筛没了，但我们确实有老数据，就默认显示最后一条 ----------
        if not filtered_dates and dates:
            filtered_dates  = [dates[-1]]
            filtered_prices = [prices[-1]]
            filtered_volumes= [volumes[-1]] if volumes else None

        nonlocal fill
        fill = update_plot(line1, fill, line2, filtered_dates, filtered_prices, filtered_volumes, ax1, ax2, show_volume)
        radio.circles[list(time_options.keys()).index(val)].set_facecolor('red')
        
        # 根据所选时间区间控制原始价格点散点的显示
        if val in ["1m", "3m", "6m"]:
            small_dot_scatter.set_visible(True)
        else:
            small_dot_scatter.set_visible(False)

        # 更新红色标记点显示，考虑时间范围和红色标记点可见性设置
        for scatter, date, _, _ in global_scatter_points:
            scatter.set_visible((min_date <= date) and show_global_markers)
            
        # 更新橙色标记点显示，考虑时间范围和橙色标记点可见性设置
        for scatter, date, _, _ in specific_scatter_points:
            scatter.set_visible((min_date <= date) and show_specific_markers)
            
        # 更新绿色收益公告标记点显示，考虑时间范围和总体可见性设置
        for scatter, date, _, _ in earning_scatter_points:
            scatter.set_visible((min_date <= date) and show_earning_markers)
            
        # 更新标记点显示后，同时更新注释显示
        update_marker_visibility()

        fig.canvas.draw_idle()

    def toggle_volume():
        """
        显示或隐藏成交量曲线。
        """
        nonlocal show_volume
        show_volume = not show_volume
        update(radio.value_selected)

    def on_key(event):
        """
        处理键盘事件，用于快捷操作图表。
        """
        actions = {
            'v': toggle_volume,
            'r': toggle_global_markers,  # 'r'键切换红色全局标记点显示
            'x': toggle_all_annotations,  # 'x'键切换橙色特定股票标记点显示
            'a': toggle_earning_markers,  # 'a'键切换白色收益公告标记点显示（保持不变）
            'c': toggle_specific_markers,  # 'c'键切换所有浮窗的显示/隐藏
            'n': lambda: execute_external_script('earning_input', name),
            'e': lambda: execute_external_script('earning_edit', name),
            't': lambda: execute_external_script('tags_edit', name),
            'w': lambda: execute_external_script('event_input', name),
            'q': lambda: execute_external_script('event_edit', name),
            'k': lambda: execute_external_script('check_kimi', name),
            'u': lambda: execute_external_script('check_futu', name),
            'p': lambda: execute_external_script('symbol_compare', name),
            'l': lambda: execute_external_script('similar_tags', name),
            '1': lambda: radio.set_active(7),
            '2': lambda: radio.set_active(1),
            '3': lambda: radio.set_active(3),
            '4': lambda: radio.set_active(4),
            '5': lambda: radio.set_active(5),
            '6': lambda: radio.set_active(6),
            '7': lambda: radio.set_active(8),
            '8': lambda: radio.set_active(2),
            '9': lambda: radio.set_active(0),
            '`': show_stock_etf_info,
            'd': lambda: on_keyword_selected(db_path, table_name, name)
        }
        if event.key in actions:
            actions[event.key]()

        # 处理方向键在不同时间区间间移动
        current_index = list(time_options.keys()).index(radio.value_selected)
        if event.key == 'up' and current_index > 0:
            radio.set_active(current_index - 1)
        elif event.key == 'down' and current_index < len(time_options) - 1:
            radio.set_active(current_index + 1)

    def close_everything(event, panel_flag):
        """
        按下ESC时关闭图表，并在panel为真时退出系统。
        """
        if event.key == 'escape':
            plt.close('all')
            if panel_flag:
                import sys
                sys.exit(0)

    def on_mouse_press(event):
        """
        记录鼠标左键按下时的价格和日期，用于计算百分比变化。
        """
        nonlocal mouse_pressed, initial_price, initial_date
        if event.button == 1:
            mouse_pressed = True
            nearest_index = (np.abs(np.array(dates) -
                            matplotlib.dates.num2date(event.xdata).replace(tzinfo=None))).argmin()
            initial_price = prices[nearest_index]
            initial_date = dates[nearest_index]

    def on_mouse_release(event):
        """
        鼠标左键释放时，停止显示百分比变化。
        """
        nonlocal mouse_pressed
        if event.button == 1:
            mouse_pressed = False

    # 参考线
    vline = ax1.axvline(x=dates[0], color='cyan', linestyle='--', linewidth=1, visible=False)

    # 连接事件
    plt.gcf().canvas.mpl_connect("motion_notify_event", hover)
    plt.gcf().canvas.mpl_connect('key_press_event', on_key)
    plt.gcf().canvas.mpl_connect('key_press_event', lambda e: close_everything(e, panel))
    plt.gcf().canvas.mpl_connect('button_press_event', on_mouse_press)
    plt.gcf().canvas.mpl_connect('button_release_event', on_mouse_release)
    radio.on_clicked(update)

    def hide_annot_on_leave(event):
        """
        当鼠标离开图表区域时，隐藏注释和高亮点。
        """
        annot.set_visible(False)
        highlight_point.set_visible(False)
        vline.set_visible(False)
        fig.canvas.draw_idle()

    plt.gcf().canvas.mpl_connect('figure_leave_event', hide_annot_on_leave)

    # 初始化图表
    update(default_time_range)
    print("图表绘制完成，等待用户操作...")
    plt.show()