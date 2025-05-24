import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime # 用于将字符串转换为日期对象

def plot_financial_data(csv_file_path, start_date_str=None, end_date_str=None):
    """
    读取CSV文件中的金融数据并绘制曲线图，支持自定义时间范围。

    参数:
    csv_file_path (str): CSV文件的路径。
    start_date_str (str, optional): 起始日期字符串 (例如 'YYYY-MM-DD')。默认为 None。
    end_date_str (str, optional): 结束日期字符串 (例如 'YYYY-MM-DD')。默认为 None。
    """
    try:
        # 读取CSV文件
        df = pd.read_csv(csv_file_path, sep='\t', parse_dates=['date'])

        # 将 'date' 列设置为索引
        df.set_index('date', inplace=True)

        # 确保 'value' 列是数值类型
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df.dropna(subset=['value'], inplace=True)

        if df.empty:
            print("错误：读取或处理数据后，没有数据可供分析。")
            return

        # --- 新增：根据日期筛选数据 ---
        original_row_count = len(df)

        if start_date_str:
            try:
                start_date = pd.to_datetime(start_date_str)
                df = df[df.index >= start_date]
            except ValueError:
                print(f"警告：起始日期 '{start_date_str}' 格式无效，将忽略此筛选条件。请使用 YYYY-MM-DD 格式。")

        if end_date_str:
            try:
                end_date = pd.to_datetime(end_date_str)
                # 注意：为了包含结束日期当天的数据，通常筛选到该日期的结束（或下一天的开始）
                # 或者，如果日期时间不包含具体时间，可以直接比较
                df = df[df.index <= end_date]
            except ValueError:
                print(f"警告：结束日期 '{end_date_str}' 格式无效，将忽略此筛选条件。请使用 YYYY-MM-DD 格式。")

        if df.empty:
            if original_row_count > 0:
                print(f"错误：在指定的日期范围 '{start_date_str}' 到 '{end_date_str}' 内没有数据。")
            else:
                print("错误：没有可供绘制的数据。")
            return
        # --- 日期筛选结束 ---

        # 创建图表
        plt.figure(figsize=(12, 6))
        plt.plot(df.index, df['value'], linestyle='-', color='b', label='数值')

        # 设置图表标题和坐标轴标签
        title = '金融数据曲线图'
        if start_date_str and end_date_str:
            title += f' ({start_date_str} 到 {end_date_str})'
        elif start_date_str:
            title += f' (从 {start_date_str} 开始)'
        elif end_date_str:
            title += f' (截至 {end_date_str})'
        plt.title(title, fontsize=16)

        plt.xlabel('日期', fontsize=14)
        plt.ylabel('数值', fontsize=14)

        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=8, maxticks=15))
        plt.gcf().autofmt_xdate()

        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.show()

    except FileNotFoundError:
        print(f"错误：文件 '{csv_file_path}' 未找到。请检查文件路径是否正确。")
    except pd.errors.EmptyDataError:
        print(f"错误：文件 '{csv_file_path}' 为空。")
    except Exception as e:
        print(f"处理文件时发生错误：{e}")

# 主程序入口
if __name__ == '__main__':
    # file_path = '/Users/yanzhang/Downloads/generated_financial_data.csv'
    file_path = '/Users/yanzhang/Downloads/simulated_stock_data.csv'

    # --- 示例：如何使用自定义日期范围 ---

    # 1. 绘制所有数据 (不提供起始和结束日期)
    # print("绘制所有数据...")
    # plot_financial_data(file_path)

    # 2. 绘制指定日期之后的数据
    # print("\n绘制从2015-01-05开始的数据...")
    # plot_financial_data(file_path, start_date_str='2015-01-05')

    # 3. 绘制指定日期之前的数据
    # print("\n绘制截至2015-01-08的数据...")
    # plot_financial_data(file_path, end_date_str='2015-01-08')

    # 4. 绘制指定日期范围内的数据
    print("\n绘制从2015-01-06到2015-01-09的数据...")
    plot_financial_data(file_path, start_date_str='2022-01-01', end_date_str='2023-01-01')

    # 5. 示例：无效日期格式 (将显示警告)
    # print("\n尝试使用无效的起始日期...")
    # plot_financial_data(file_path, start_date_str='01/07/2015') # 格式不符合预期

    # --- 获取用户输入的日期 (可选) ---
    # print("\n--- 通过用户输入自定义日期范围 ---")
    # custom_start = input("请输入起始日期 (YYYY-MM-DD, 直接回车则不限制): ")
    # custom_end = input("请输入结束日期 (YYYY-MM-DD, 直接回车则不限制): ")
    #
    # # 如果用户没有输入，则将字符串设为 None
    # custom_start = custom_start if custom_start else None
    # custom_end = custom_end if custom_end else None
    #
    # plot_financial_data(file_path, start_date_str=custom_start, end_date_str=custom_end)