import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def plot_financial_data(csv_file_path, start_date_str=None, end_date_str=None):
    try:
        # 1）删除 sep='\t'，让 pandas 用逗号分隔
        df = pd.read_csv(
            csv_file_path,
            encoding='utf-8-sig',    # 万一有 BOM
            parse_dates=['Date']    # 这时就能正常识别 date 列
        )
        
        # 2）后续保持不变
        df.set_index('Date', inplace=True)
        df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
        df.dropna(subset=['Value'], inplace=True)
        if df.empty:
            print("错误：没有可用数据。")
            return

        # 日期筛选
        if start_date_str:
            try: df = df[df.index >= pd.to_datetime(start_date_str)]
            except: print(f"警告：起始日期格式无效：{start_date_str}")
        if end_date_str:
            try: df = df[df.index <= pd.to_datetime(end_date_str)]
            except: print(f"警告：结束日期格式无效：{end_date_str}")
        if df.empty:
            print(f"错误：在范围 {start_date_str} – {end_date_str} 内没有数据。")
            return

        # 绘图
        plt.figure(figsize=(12,6))
        plt.plot(
    df.index,
    df['Value'],
    linestyle='-',
    marker='o',
    color='b',
    label='数值',
    markersize=2    # <- 把点的大小设为 4（默认大概是 6～8）
)
        title = '金融数据曲线图'
        if start_date_str or end_date_str:
            title += f" ({start_date_str or '开始'} → {end_date_str or '结束'})"
        plt.title(title)
        plt.xlabel('日期')
        plt.ylabel('数值')
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
        plt.gcf().autofmt_xdate()
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.legend()
        plt.tight_layout()
        plt.show()

    except FileNotFoundError:
        print(f"错误：文件 {csv_file_path} 未找到。")
    except pd.errors.EmptyDataError:
        print(f"错误：文件 {csv_file_path} 为空。")
    except Exception as e:
        print(f"处理文件时发生错误：{e}")

if __name__ == '__main__':
    # file_path = '/Users/yanzhang/Downloads/Firstrade/Deals.csv'
    file_path = '/Users/yanzhang/Downloads/Deal_simulated_trend.csv'
    plot_financial_data(file_path, start_date_str='2022-01-01', end_date_str='2023-01-01')