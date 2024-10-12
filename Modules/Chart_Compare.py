import sys
import sqlite3
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.dates import DateFormatter, num2date
from PyQt5.QtWidgets import (QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QLabel, QDateEdit, QHBoxLayout)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QDate
from datetime import datetime

class StockComparisonApp(QWidget):
    def __init__(self):
        super().__init__()
        self.max_symbols = 10  # 限制最多10个symbol
        self.symbol_inputs = []  # 存储所有symbol输入框
        self.initUI()

    def initUI(self):
        # 设置窗口标题和大小
        self.setWindowTitle('股票比较工具')
        self.setGeometry(100, 100, 400, 400)  # 增加窗口高度以容纳新组件

        # 创建布局
        self.layout = QVBoxLayout()

        # 创建日期选择器
        self.start_date_edit = QDateEdit(self)
        self.start_date_edit.setFont(QFont('Arial', 12))
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate(2024, 1, 1))  # 默认开始日期
        # self.layout.addWidget(QLabel('选择开始日期:', self))
        self.layout.addWidget(self.start_date_edit)

        self.end_date_edit = QDateEdit(self)
        self.end_date_edit.setFont(QFont('Arial', 12))
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())  # 默认结束日期为当前日期
        # self.layout.addWidget(QLabel('选择结束日期:', self))
        self.layout.addWidget(self.end_date_edit)

        # 创建标签
        self.label = QLabel('请输入股票代码进行比较')
        self.label.setFont(QFont('Arial', 12))
        self.layout.addWidget(self.label)

        # 默认创建两个输入框
        self.add_symbol_input()
        self.add_symbol_input()

        # 添加按钮用于动态添加更多symbol输入框
        self.add_symbol_button = QPushButton('添加股票代码', self)
        self.add_symbol_button.setFont(QFont('Arial', 12))
        self.add_symbol_button.clicked.connect(self.add_symbol_input)
        self.layout.addWidget(self.add_symbol_button)

        # 创建按钮用于开始比较
        self.compare_button = QPushButton('开始比较', self)
        self.compare_button.setFont(QFont('Arial', 12))
        self.compare_button.clicked.connect(self.compare_stocks)
        self.layout.addWidget(self.compare_button)

        # 设置布局
        self.setLayout(self.layout)
        self.show()

    def add_symbol_input(self):
        """动态添加股票代码输入框"""
        if len(self.symbol_inputs) < self.max_symbols:
            symbol_input = QLineEdit(self)
            symbol_input.setFont(QFont('Arial', 14))
            symbol_input.setPlaceholderText(f'股票代码 {len(self.symbol_inputs) + 1}')
            symbol_input.returnPressed.connect(self.compare_stocks)
            self.layout.addWidget(symbol_input, len(self.symbol_inputs) + 1)
            self.symbol_inputs.append(symbol_input)
        else:
            self.label.setText(f'最多只能添加 {self.max_symbols} 个股票代码')
            self.label.setStyleSheet('color: red')

    def compare_stocks(self):
        # 获取所有输入框中输入的股票代码
        symbols = [input.text().upper() for input in self.symbol_inputs if input.text().strip()]

        if len(symbols) == 0:
            self.label.setText('请至少输入一个股票代码')
            self.label.setStyleSheet('color: red')
            return

        # 获取用户选择的开始日期和结束日期
        start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
        end_date = self.end_date_edit.date().toString('yyyy-MM-dd')

        # 调用后续的股票比较逻辑
        if len(symbols) == 1:
            self.label.setText(f'正在显示 {symbols[0]} 的价格曲线')
        else:
            self.label.setText(f'正在比较 {", ".join(symbols)}')
            
        self.label.setStyleSheet('color: gold')

        # 在这里进行后续的查询和图表展示操作
        self.compare_and_plot(symbols, start_date, end_date)

    def compare_and_plot(self, symbols, custom_start_date, custom_end_date):
        # 自动分配颜色
        colors = ['tab:blue', 'tab:red', 'tab:green', 'tab:purple', 'tab:pink', 'tab:brown', 'tab:gray', 'tab:olive', 'tab:cyan', 'tab:orange']

        # 查询数据库
        db_path = '/Users/yanzhang/Documents/Database/Finance.db'
        conn = sqlite3.connect(db_path)

        # 创建字典来存储每个symbol的数据
        dfs = {}

        for i, symbol in enumerate(symbols):
            table = self.find_table_by_symbol(symbol)
            if not table:
                self.label.setText(f'找不到股票代码 {symbol} 的表名')
                self.label.setStyleSheet('color: red')
                return

            query = f"SELECT date, price FROM {table} WHERE name='{symbol}'"
            df = pd.read_sql_query(query, conn)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            dfs[symbol] = (df, colors[i % len(colors)])

        # 找出共同的日期范围
        start_date = max(df[0].index.min() for df in dfs.values())
        end_date = min(df[0].index.max() for df in dfs.values())

        # 确定最终的日期范围
        final_start_date = max(pd.to_datetime(custom_start_date), start_date)
        final_end_date = min(pd.to_datetime(custom_end_date), end_date) if pd.to_datetime(custom_end_date) <= end_date else pd.to_datetime(custom_end_date)

        # 筛选共同日期范围内的数据
        for name in dfs:
            dfs[name] = (dfs[name][0].reindex(pd.date_range(final_start_date, final_end_date)).ffill(), dfs[name][1])

        # 创建图表
        fig, ax1 = plt.subplots(figsize=(16, 6))

        # 设置中文字体
        zh_font = fm.FontProperties(fname='/Users/yanzhang/Library/Fonts/FangZhengHeiTiJianTi-1.ttf')

        # 如果只有一个股票，绘制单一曲线
        if len(symbols) == 1:
            symbol = symbols[0]
            df, color = dfs[symbol]
            ax1.plot(df.index, df['price'], label=symbol, color=color, linewidth=2)
            ax1.legend([symbol], loc='upper left', prop=zh_font)
            ax1.set_title(f'{symbol} 价格曲线', fontproperties=zh_font)
        else:
            # 绘制第一个股票价格曲线
            first_name, (first_df, first_color) = next(iter(dfs.items()))

            line1, = ax1.plot(first_df.index, first_df['price'], label=first_name, color=first_color, linewidth=2)
            ax1.tick_params(axis='y', labelcolor=first_color)

            # 绘制其他股票价格曲线
            second_axes = [ax1]
            lines = [line1]
            for i, (name, (df, color)) in enumerate(list(dfs.items())[1:], 1):
                ax = ax1.twinx()
                if i > 1:
                    ax.spines['right'].set_position(('outward', 60 * (i - 1)))
                
                line, = ax.plot(df.index, df['price'], label=name, color=color, linewidth=2)
                ax.tick_params(axis='y', labelcolor=color)
                second_axes.append(ax)
                lines.append(line)

            # 设置图例
            lines_labels = [ax.get_legend_handles_labels() for ax in second_axes]
            lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
            ax1.legend(lines, labels, loc='upper left', prop=zh_font)

        # 设置图表标题
        plt.grid(True)

        # 添加竖直虚线
        vline = ax1.axvline(x=final_start_date, color='gray', linestyle='--', linewidth=1)

        # 添加显示日期的文本注释，并初始化位置
        date_text = fig.text(0.5, 0.005, '', ha='center', va='bottom', fontproperties=zh_font)

        # 定义鼠标移动事件处理函数
        def on_mouse_move(event):
            if event.inaxes:
                vline.set_xdata([event.xdata, event.xdata])  # 使用列表
                current_date = num2date(event.xdata).strftime('%m-%d')
                date_text.set_text(current_date)
                # 更新文本位置
                date_text.set_position((event.x / fig.dpi / fig.get_size_inches()[0], 0.005))
                fig.canvas.draw_idle()

        # 定义按键事件处理函数
        def on_key(event):
            if event.key == 'escape':
                plt.close(fig)

        # 连接事件处理函数
        fig.canvas.mpl_connect('motion_notify_event', on_mouse_move)
        fig.canvas.mpl_connect('key_press_event', on_key)

        # 显示图表
        plt.tight_layout()
        plt.show()

    def find_table_by_symbol(self, symbol):
        with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as f:
            sector_data = json.load(f)

        for table, symbols in sector_data.items():
            if symbol in symbols:
                return table
        return None  # 没有找到则返回 None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = StockComparisonApp()
    sys.exit(app.exec_())