# o1优化后代码
import re
import sqlite3
import subprocess
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
import matplotlib
import tkinter as tk
from tkinter import simpledialog, scrolledtext, font as tkFont
from functools import lru_cache
from scipy.interpolate import interp1d

@lru_cache(maxsize=None)
def fetch_data(db_path, table_name, name):
    """
    从数据库中获取指定名称的日期、价格、成交量数据。
    如果表中存在volume字段，则一起返回，否则只返回date和price。
    """
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
    """
    通过插值生成更多的点来让曲线更平滑。
    如果数据点少于四个，使用线性插值；否则使用三次插值。
    """
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
    """
    将数据库返回的数据处理为日期、价格、成交量三个列表。
    如果数据为空，则抛出异常。
    """
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
    """
    使用 AppleScript 在 macOS 上弹出提示对话框。
    """
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def draw_underline(text_obj, fig, ax1):
    """
    给可点击的标题下方画一条下划线视觉提示。
    """
    x, y = text_obj.get_position()
    text_renderer = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
    linewidth = text_renderer.width
    line = matplotlib.lines.Line2D([x, x + linewidth], [y - 2, y - 2], transform=ax1.transData, color='blue', linewidth=2)
    ax1.add_line(line)

def update_plot(line1, fill, line2, dates, prices, volumes, ax1, ax2, show_volume):
    """
    根据筛选后的数据更新图表。
    """
    line1.set_data(dates, prices)
    fill.remove()
    # 添加edgecolor='none'或linewidth=0参数来移除边缘线
    fill = ax1.fill_between(dates, prices, color='lightblue', alpha=0.3, edgecolor='none')
    if volumes:
        line2.set_data(dates, volumes)
    
    # 修改这一行，增加右侧余量
    date_min = np.min(dates)
    date_max = np.max(dates)
    date_range = date_max - date_min
    right_margin = date_range * 0.01  # 添加5%的右侧余量
    ax1.set_xlim(date_min, date_max + right_margin)
    
    ax1.set_ylim(np.min(prices), np.max(prices))
    if show_volume and volumes:
        ax2.set_ylim(0, np.max(volumes))
    line2.set_visible(show_volume)
    plt.draw()
    return fill

def plot_financial_data(db_path, table_name, name, compare, share, marketcap, pe, json_data,
                        default_time_range="1Y", panel="False"):
    """
    主函数，绘制股票或ETF的时间序列图表。支持成交量、标签说明、信息弹窗、区间切换等功能。
    按键说明：
    - v：显示或隐藏成交量
    - 1~9：快速切换不同时间区间
    - `：弹出信息对话框
    - d：查询数据库并弹窗显示
    - c：切换显示或隐藏标记点（黄色全局点和橙色特定点）
    - x：切换显示或隐藏收益公告日期点（绿色点）
    - 方向键上下：在不同时间区间间移动
    - ESC：关闭所有图表，并在panel为True时退出系统
    """
    plt.close('all')  # 关闭所有图表
    matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']

    show_volume = False
    mouse_pressed = False
    initial_price = None
    initial_date = None
    fill = None
    show_markers = False  # 修改为默认不显示标记点
    show_earning_markers = True  # 默认不显示收益点

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

    fig, ax1 = plt.subplots(figsize=(13, 6))
    fig.subplots_adjust(left=0.05, bottom=0.1, right=0.91, top=0.9)
    ax2 = ax1.twinx()

    fig.patch.set_facecolor('black')
    ax1.set_facecolor('black')
    ax1.tick_params(axis='x', colors='white')
    ax1.tick_params(axis='y', colors='white')
    ax2.tick_params(axis='y', colors='white')

    highlight_point = ax1.scatter([], [], s=100, color='blue', zorder=5)
    
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
    
    # 修改获取收益公告日期和价格变动的部分
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date", (name,))
            for date_str, price_change in cursor.fetchall():
                try:
                    marker_date = datetime.strptime(date_str, "%Y-%m-%d")
                    # 查找该日期在价格数据中的索引
                    closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
                    closest_date = dates[closest_date_idx]
                    price_at_date = prices[closest_date_idx]
                    
                    # 获取最新价格
                    latest_price = prices[-1]
                    
                    # 计算从财报日期到最新日期的价格变化百分比
                    price_change_to_present = ((latest_price - price_at_date) / price_at_date) * 100
                    
                    # 存储价格变动作为标记文本，包含财报收益和至今变化
                    earning_markers[marker_date] = f"昨日财报收益: {price_change}%\n至今变化: {price_change_to_present:.2f}%"
                except ValueError:
                    print(f"无法解析收益公告日期: {date_str}")
    except sqlite3.OperationalError as e:
        print(f"获取收益数据失败: {e}")
    
    # 标记点
    global_scatter_points = []
    specific_scatter_points = []
    earning_scatter_points = []  # 新增：收益公告标记点列表
    
    # 绘制全局标记点（黄色）
    for marker_date, text in global_markers.items():
        if min(dates) <= marker_date <= max(dates):
            closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
            closest_date = dates[closest_date_idx]
            price_at_date = prices[closest_date_idx]
            scatter = ax1.scatter([closest_date], [price_at_date], s=100, color='red', 
                                #  alpha=0.7, zorder=4, picker=5) # 初始设为可见
                                 alpha=0.7, zorder=4, picker=5, visible=show_markers)  # 初始设为不可见
            global_scatter_points.append((scatter, closest_date, price_at_date, text))
    
    # 绘制特定股票标记点（橙色）
    for marker_date, text in specific_markers.items():
        if min(dates) <= marker_date <= max(dates):
            closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
            closest_date = dates[closest_date_idx]
            price_at_date = prices[closest_date_idx]
            scatter = ax1.scatter([closest_date], [price_at_date], s=100, color='orange', 
                                #  alpha=0.7, zorder=4, picker=5) # 初始设为可见
                                 alpha=0.7, zorder=4, picker=5, visible=show_markers)  # 初始设为不可见
            specific_scatter_points.append((scatter, closest_date, price_at_date, text))
    
    # 新增：绘制财报收益公告标记点（绿色）
    for marker_date, text in earning_markers.items():
        if min(dates) <= marker_date <= max(dates):
            closest_date_idx = (np.abs(np.array(dates) - marker_date)).argmin()
            closest_date = dates[closest_date_idx]
            price_at_date = prices[closest_date_idx]
            scatter = ax1.scatter([closest_date], [price_at_date], s=100, color='white', 
                                 alpha=0.7, zorder=4, picker=5, visible=show_earning_markers)
            earning_scatter_points.append((scatter, closest_date, price_at_date, text))

    def clean_percentage_string(percentage_str):
        """
        将可能包含 % 符号的字符串转换为浮点数。
        """
        try:
            return float(percentage_str.strip('%'))
        except ValueError:
            return None

    # 计算换手额（单位：百万）
    turnover = (
        (volumes[-1] * prices[-1]) / 1e6
        if volumes and volumes[-1] is not None and prices[-1] is not None
        else None
    )
    turnover_str = f"{turnover:.1f}" if turnover is not None else ""

    # 从compare中去除中文和加号
    filtered_compare = re.sub(r'[\u4e00-\u9fff+]', '', compare)
    compare_value = clean_percentage_string(filtered_compare)

    # 根据compare和换手额做"可疑"标记
    if turnover is not None and turnover < 100 and compare_value is not None and compare_value > 0:
        turnover_str = f"可疑{turnover_str}"

    turnover_rate = (
        f"{(volumes[-1] / int(share)) * 100:.2f}"
        if volumes and volumes[-1] is not None and share not in [None, "N/A"]
        else ""
    )
    marketcap_in_billion = (
        f"{float(marketcap) / 1e9:.1f}B"
        if marketcap not in [None, "N/A"]
        else ""
    )
    pe_text = f"{pe}" if pe not in [None, "N/A"] else ""

    clickable = False
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
                if len(tag_str) > 25:
                    tag_str = tag_str[:25] + '...'
                clickable = True
                found = True
                break
        if found:
            break

    # 组合标题
    title_text = (
        f'{name}  {compare}  {turnover_str}M/{turnover_rate} '
        f'{marketcap_in_billion} {pe_text}"{table_name}" {fullname} {tag_str}'
    )
    title_style = {
        'color': 'orange' if clickable else 'lightgray',
        'fontsize': 16 if clickable else 15,
        'fontweight': 'bold',
        'picker': clickable,
    }
    title = ax1.set_title(title_text, **title_style)

    def show_stock_etf_info(event=None):
        """
        展示当前name在JSON数据中的信息（如全名、标签、描述等）。
        如果未找到则弹框提示。
        """
        for source in data_sources:
            for item in json_data.get(source, []):
                if item['symbol'] == name:
                    descriptions = item
                    root = tk.Tk()
                    root.withdraw()  # 隐藏主窗口
                    top = tk.Toplevel(root)
                    top.title("Information")
                    top.geometry("600x750")
                    font_size = ('Arial', 22)
                    text_box = scrolledtext.ScrolledText(top, wrap=tk.WORD, font=font_size)
                    text_box.pack(expand=True, fill='both')
                    info = (
                        f"{name}\n"
                        f"{descriptions['name']}\n\n"
                        f"{descriptions['tag']}\n\n"
                        f"{descriptions['description1']}\n\n"
                        f"{descriptions['description2']}"
                    )
                    text_box.insert(tk.END, info)
                    text_box.config(state=tk.DISABLED)
                    top.bind('<Escape>', lambda event: root.destroy())
                    root.mainloop()
                    return
        display_dialog(f"未找到 {name} 的信息")

    def toggle_markers():
        """
        切换标记点的显示状态，不弹出提示框
        """
        nonlocal show_markers
        show_markers = not show_markers
        
        # 更新所有标记点的可见性
        for scatter, _, _, _ in global_scatter_points + specific_scatter_points:
            scatter.set_visible(show_markers)
        
        # 如果当前有高亮的标记点且标记点被隐藏，则也隐藏高亮和注释
        if not show_markers and highlight_point.get_visible():
            highlight_point.set_visible(False)
            annot.set_visible(False)
            
        fig.canvas.draw_idle()
    
    def toggle_earning_markers():
        """
        切换收益公告标记点的显示状态
        """
        nonlocal show_earning_markers
        show_earning_markers = not show_earning_markers
        
        # 更新所有收益公告标记点的可见性
        for scatter, _, _, _ in earning_scatter_points:
            scatter.set_visible(show_earning_markers)
        
        # 如果当前有高亮的标记点且标记点被隐藏，则也隐藏高亮和注释
        if not show_earning_markers and highlight_point.get_visible():
            highlight_point.set_visible(False)
            annot.set_visible(False)
            
        fig.canvas.draw_idle()

    def on_pick(event):
        """
        当点击标题（可点击）或标记点时，展示对应信息窗口。
        如果标记点不可见，则不会触发点击事件。
        """
        if event.artist == title:
            show_stock_etf_info()
        elif event.artist in [point[0] for point in global_scatter_points + specific_scatter_points + earning_scatter_points]:
            # 查找被点击的标记点
            for scatter, date, price, text in global_scatter_points + specific_scatter_points + earning_scatter_points:
                if event.artist == scatter:
                    # 更新注释并显示
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

    def on_keyword_selected(db_path, table_name, name):
        """
        按关键字查询数据库并弹框显示结果。
        """
        condition = f"name = '{name}'"
        result = query_database(db_path, table_name, condition)
        create_window(result)

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

    def create_window(content):
        """
        创建新窗口显示查询数据库的结果。
        """
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        top = tk.Toplevel(root)
        top.title("数据库查询结果")
        window_width, window_height = 900, 600
        center_x = (top.winfo_screenwidth() - window_width) // 2
        center_y = (top.winfo_screenheight() - window_height) // 2
        top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        top.bind('<Escape>', lambda event: root.destroy())

        text_font = tkFont.Font(family="Courier", size=20)
        text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
        text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        text_area.insert(tk.INSERT, content)
        text_area.configure(state='disabled')
        root.mainloop()

    # 给标题添加可点击下划线
    if clickable:
        draw_underline(title, fig, ax1)
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
        if show_markers:
            for marker_date, text in global_markers.items():
                if abs((marker_date - current_date).total_seconds()) < 86400:  # 两天内
                    global_marker_text = text
                    break
                
            # 查找特定股票标记
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
        else:
            # 显示日期和价格
            text = f"{datetime.strftime(xval, '%Y-%m-%d')}\n{yval}"
            
            # 添加标记文本信息（如果有）
            marker_texts = []
            if global_marker_text:
                marker_texts.append(global_marker_text)
            if specific_marker_text:
                marker_texts.append(specific_marker_text)
            if earning_marker_text:
                marker_texts.append(earning_marker_text)
                
            if marker_texts:
                text += "\n" + "\n".join(marker_texts)
        
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
        else:
            y_offset = -20  # 默认向下偏移
        
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
                annot.set_position((0, y_offset))
            else:
                annot.set_position((0, -60))  # 放到下方

    def hover(event):
        """
        鼠标在图表上滑动时，更新垂直参考线、注释、以及高亮最近的数据点。
        """
        if event.inaxes in [ax1, ax2]:
            if event.xdata:
                current_date = matplotlib.dates.num2date(event.xdata).replace(tzinfo=None)
                vline.set_xdata(current_date)
                vline.set_visible(True)
                fig.canvas.draw_idle()
                x_data, y_data = line1.get_data()
                nearest_index = (np.abs(np.array(x_data) - current_date)).argmin()

                # 判断鼠标位置是否接近数据点的容差（tolerance）值来提高敏感度，根据差值判断是否接近某个数据点
                # 如果你将它调大，比如改为 0.1 或 0.2，那么即便鼠标离数据点稍远一些，仍然可以触发高亮蓝色价格点
                date_distance = 0.1 * ((ax1.get_xlim()[1] - ax1.get_xlim()[0]) / 365)
                if np.isclose(
                    matplotlib.dates.date2num(x_data[nearest_index]),
                    matplotlib.dates.date2num(current_date),
                    atol=date_distance
                ):
                    update_annot({"ind": [nearest_index]})
                    annot.set_visible(True)
                    highlight_point.set_offsets([x_data[nearest_index], y_data[nearest_index]])
                    highlight_point.set_visible(True)
                else:
                    annot.set_visible(False)
                    highlight_point.set_visible(False)
                fig.canvas.draw_idle()
            else:
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
            filtered_dates = [d for d in dates if d >= min_date]
            filtered_prices = [p for d, p in zip(dates, prices) if d >= min_date]
            filtered_volumes = [v for d, v in zip(dates, volumes) if d >= min_date] if volumes else None

        nonlocal fill
        fill = update_plot(line1, fill, line2, filtered_dates, filtered_prices, filtered_volumes, ax1, ax2, show_volume)
        radio.circles[list(time_options.keys()).index(val)].set_facecolor('red')
        
        # 更新黄色和橙色标记点显示，考虑时间范围和总体可见性设置
        for scatter, date, _, _ in global_scatter_points + specific_scatter_points:
            # scatter.set_visible((min_date <= date if years != 0 else True) and show_markers)
            scatter.set_visible((min_date <= date) and show_markers)
            
        # 更新绿色收益公告标记点显示，考虑时间范围和总体可见性设置
        for scatter, date, _, _ in earning_scatter_points:
            scatter.set_visible((min_date <= date) and show_earning_markers)
            
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
            'c': toggle_markers,  # 'c'键切换黄色和橙色标记点显示
            'a': toggle_earning_markers,  # 新增：'x'键切换绿色收益公告标记点显示
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
    vline = ax1.axvline(x=dates[0], color='blue', linestyle='--', linewidth=1, visible=False)

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