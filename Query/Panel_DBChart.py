import sqlite3
import matplotlib
import tkinter as tk
import tkinter.font as tkFont
import matplotlib.pyplot as plt
from tkinter import scrolledtext
from datetime import datetime, timedelta
from matplotlib.widgets import RadioButtons

class DatabaseApp:
    def __init__(self, root):
        self.root = root
        self.database_info = {
            'CommodityDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'},
            'IndexDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks'},
            'CryptoDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto'},
            'CurrencyDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies'},
            'Bonds': {'path': '/Users/yanzhang/Finance.db', 'table': 'Bonds'},
            'CommodityDB1': {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'}
        }
        self.database_mapping = {
            'CommodityDB': {'Uranium', 'Nickel', 'Soybeans', 'Wheat', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Corn', 'Crude Oil', 'Brent', 'Natural gas', 'Gold', 'Silver', 'Copper', 'Lithium'},
            'IndexDB': {'NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX'},
            'CommodityDB1': {'CRB Index', 'LME Index', 'Nuclear Energy Index', 'Solar Energy Index', 'EU Carbon Permits', 'Containerized Freight Index'},
            'CryptoDB': {"Bitcoin", "Ether", "Solana"},
            'CurrencyDB': {'DXY', 'CNYEUR', 'USDJPY', 'USDCNY', 'CNYJPY', 'CNYPHP'},
            'Bonds': {"United States", "Japan", "Russia", "India", "Turkey"},
        }
        self.reverse_mapping = {keyword: db for db, keywords in self.database_mapping.items() for keyword in keywords}
        self.create_selection_window()

    def create_selection_window(self):
        selection_window = tk.Toplevel(self.root)
        selection_window.title("选择查询关键字")
        selection_window.geometry("1280x800")
        selection_window.bind('<Escape>', lambda e: self.close_app(root))

        canvas = tk.Canvas(selection_window)
        scrollbar = tk.Scrollbar(selection_window, orient="horizontal", command=canvas.xview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set)

        # 创建一个新的Frame来纵向包含CurrencyDB1和CryptoDB1
        new_vertical_frame1 = tk.Frame(scrollable_frame)
        new_vertical_frame1.pack(side="left", padx=15, pady=10, fill="both", expand=True)

        new_vertical_frame2 = tk.Frame(scrollable_frame)
        new_vertical_frame2.pack(side="left", padx=15, pady=10, fill="both", expand=True)

        for db_key, keywords in self.database_mapping.items():
            if db_key in ['CurrencyDB', 'Bonds', 'CryptoDB']:
                # 将这两个数据库的框架放入新的纵向框架中
                frame = tk.LabelFrame(new_vertical_frame1, text=db_key, padx=10, pady=10)
                frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
            elif db_key in ['IndexDB', 'CommodityDB1']:
                frame = tk.LabelFrame(new_vertical_frame2, text=db_key, padx=10, pady=10)
                frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
            else:
                frame = tk.LabelFrame(scrollable_frame, text=db_key, padx=10, pady=10)
                frame.pack(side="left", padx=15, pady=10, fill="both", expand=True)

            for keyword in sorted(keywords):
                button_frame = tk.Frame(frame)  # 创建一个内部Frame来包裹两个按钮
                button_frame.pack(side="top", fill="x", padx=5, pady=2)

                button_data = tk.Button(button_frame, text=keyword, command=lambda k=keyword: self.on_keyword_selected(k))
                button_data.pack(side="left", fill="x", expand=True)  # 设置左侧填充

                button_chart = tk.Button(button_frame, text="图表", command=lambda k=keyword: self.on_keyword_selected_chart(k, selection_window))
                button_chart.pack(side="left", fill="x", expand=True)  # 设置右侧填充

        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")

    def on_keyword_selected(self, value):
        if value:
            db_key = self.reverse_mapping[value]
            db_info = self.database_info[db_key]
            condition = f"name = '{value}'"
            result = self.query_database(db_info['path'], db_info['table'], condition)
            self.create_window(result)

    def query_database(self, db_file, table_name, condition):
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        # 修改这里，添加 DESC 使结果按日期降序排列
        query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
        cursor.execute(query)
        rows = cursor.fetchall()
        if not rows:
            return "今天没有数据可显示。\n"

        columns = [description[0] for description in cursor.description]
        col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]
        output_text = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
        output_text += '-' * len(output_text) + '\n'
        for row in rows:
            output_text += ' | '.join([str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)]) + '\n'
        conn.close()
        return output_text

    def on_keyword_selected_chart(self, value, parent_window):
        db_key = self.reverse_mapping[value]
        db_info = self.database_info[db_key]
        condition = f"name = '{value}'"
        self.query_db2chart(db_info['path'], db_info['table'], condition, parent_window, value)

    def query_db2chart(self, path, table, condition, parent_window, value):
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        query = f"""
        SELECT date, price
        FROM {table}
        WHERE {condition}
        ORDER BY date;
        """
        cursor.execute(query)
        data = cursor.fetchall()
        cursor.close()
        conn.close()

        if not data:
            print("No data found.")
            return

        def update(val):
            current_option = val
            years = time_options[current_option]
            if years == 0:
                filtered_dates = dates
                filtered_prices = prices
            else:
                min_date = datetime.now() - timedelta(days=years * 365)
                filtered_dates = [date for date in dates if date >= min_date]
                filtered_prices = [price for date, price in zip(dates, prices) if date >= min_date]
            line.set_data(filtered_dates, filtered_prices)
            ax.relim()
            ax.autoscale_view()
            plt.draw()

        matplotlib.rcParams['font.family'] = 'sans-serif'
        matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS']
        matplotlib.rcParams['font.size'] = 14

        dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
        prices = [row[1] for row in data]

        fig, ax = plt.subplots(figsize=(10, 5))
        line, = ax.plot(dates, prices, marker='o', linestyle='-', color='b')
        ax.set_title(f'{value} Price Over Time')
        ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.grid(True)
        plt.xticks(rotation=45)

        time_options = {
            "全部时间": 0,
            "10年": 10,
            "5年": 5,
            "2年": 2,
            "1年": 1,
            "6个月": 0.5,
            "3个月": 0.25,
        }

        rax = plt.axes([0.15, 0.55, 0.1, 0.4])
        radio = RadioButtons(rax, list(time_options.keys()), activecolor='blue')

        for label in radio.labels:
            label.set_fontsize(14)

        update("3个月")  # 默认选择“3个月”
        radio.on_clicked(update)

        def on_key(event):
            if event.key == 'escape':
                plt.close()

        plt.gcf().canvas.mpl_connect('key_press_event', on_key)

        plt.show()

    def create_window(self, content):
        top = tk.Toplevel(self.root)
        top.title("数据库查询结果")
        window_width = 900
        window_height = 600
        screen_width = top.winfo_screenwidth()
        screen_height = top.winfo_screenheight()
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)
        top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        top.bind('<Escape>', lambda e: self.close_app(top))
        text_font = tkFont.Font(family="Courier", size=20)
        text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
        text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        text_area.insert(tk.INSERT, content)
        text_area.configure(state='disabled')

    def close_app(self, window):
        window.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    app = DatabaseApp(root)
    root.mainloop()