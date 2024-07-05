import json
import sqlite3
import tkinter as tk
from tkinter import ttk, scrolledtext
import tkinter.font as tkFont
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import asyncio
import os
import sys

sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from Chart_input import plot_financial_data

class FinancialApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.root.bind('<Escape>', lambda e: self.close_app(self.root))
        self.load_data()
        self.create_selection_window()

    def load_data(self):
        base_path = '/Users/yanzhang/Documents/Financial_System/Modules/'
        news_path = '/Users/yanzhang/Documents/News/backup/'
        
        with ThreadPoolExecutor() as executor:
            self.keyword_colors = executor.submit(self.load_json, f'{base_path}Colors.json')
            self.config = executor.submit(self.load_json, f'{base_path}Sectors_panel.json')
            self.json_data = executor.submit(self.load_json, f'{base_path}Description.json')
            self.sector_data = executor.submit(self.load_json, f'{base_path}Sectors_All.json')
            self.compare_data = executor.submit(pd.read_csv, f'{news_path}Compare_All.txt', sep=':', header=None, names=['key', 'value'])
            self.shares = executor.submit(pd.read_csv, f'{news_path}Shares.txt', sep=':', header=None, names=['key', 'value'])
            self.marketcap_pe_data = executor.submit(pd.read_csv, f'{news_path}marketcap_pe.txt', sep='[,:]', engine='python', header=None, names=['key', 'marketcap', 'pe'])

        self.keyword_colors = self.keyword_colors.result()
        self.config = self.config.result()
        self.json_data = self.json_data.result()
        self.sector_data = self.sector_data.result()
        self.compare_data = self.compare_data.result().set_index('key')['value'].to_dict()
        self.shares = self.shares.result().set_index('key')['value'].to_dict()
        self.marketcap_pe_data = self.marketcap_pe_data.result().set_index('key')[['marketcap', 'pe']].to_dict('index')

    @staticmethod
    def load_json(path):
        with open(path, 'r', encoding='utf-8') as file:
            return json.loads(file.read())

    def create_selection_window(self):
        self.selection_window = tk.Toplevel(self.root)
        self.selection_window.title("选择查询关键字")
        self.selection_window.geometry("1480x900")
        self.selection_window.bind('<Escape>', lambda e: self.close_app(self.selection_window))

        self.create_custom_style()
        self.create_notebook()

    def create_custom_style(self):
        style = ttk.Style()
        style.theme_use('alt')
        button_styles = {
            "Green": ("green", "white"),
            "White": ("white", "black"),
            "Purple": ("purple", "white"),
            "Yellow": ("yellow", "black"),
            "Orange": ("orange", "black"),
            "Blue": ("blue", "white"),
            "Red": ("red", "black"),
            "Black": ("black", "white"),
            "Default": ("gray", "black")
        }
        for name, (bg, fg) in button_styles.items():
            style.configure(f"{name}.TButton", background=bg, foreground=fg, font=('Helvetica', 16))
            style.map("TButton", background=[('active', '!disabled', 'pressed', 'focus', 'hover', 'alternate', 'selected', 'background')])

    def create_notebook(self):
        notebook = ttk.Notebook(self.selection_window)
        notebook.pack(fill=tk.BOTH, expand=True)

        categories = [
            ['Basic_Materials', 'Communication_Services', 'Consumer_Cyclical'],
            ['Technology', 'Energy', 'Real_Estate'],
            ['Industrials', 'Consumer_Defensive', 'Utilities'],
            ['Healthcare', 'Financial_Services'],
            ['Bonds', 'Crypto', 'Indices'],
            ['Commodities'],
            ['Currencies', 'ETFs_Oversea', "ETFs_Commodity"],
            ['Economics', 'ETFs_US']
        ]

        for category_group in categories:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=', '.join(category_group))
            for category in category_group:
                self.create_category_buttons(frame, category)

    def create_category_buttons(self, frame, category):
        if category not in self.config:
            return

        category_frame = ttk.LabelFrame(frame, text=category)
        category_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas = tk.Canvas(category_frame)
        scrollbar = ttk.Scrollbar(category_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        keywords = self.config[category]
        if isinstance(keywords, dict):
            items = keywords.items()
        else:
            items = [(kw, kw) for kw in keywords]

        for keyword, translation in items:
            button_frame = ttk.Frame(scrollable_frame)
            button_frame.pack(side="top", fill="x", padx=2, pady=3)

            button_style = self.get_button_style(keyword)
            button_text = f"{translation} {self.compare_data.get(keyword, '')}"

            ttk.Button(button_frame, text=button_text, style=button_style,
                       command=lambda k=keyword: self.on_keyword_selected_chart(k)).pack(side="left", fill="x", expand=True)

            link_label = tk.Label(button_frame, text="🔢", fg="gray", cursor="hand2")
            link_label.pack(side="right", fill="x", expand=False)
            link_label.bind("<Button-1>", lambda event, k=keyword: self.on_keyword_selected(k))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def get_button_style(self, keyword):
        color_styles = {
            "purple": "Purple.TButton",
            "yellow": "Yellow.TButton",
            "orange": "Orange.TButton",
            "blue": "Blue.TButton",
            "red": "Red.TButton",
            "black": "Black.TButton",
            "white": "White.TButton",
            "green": "Green.TButton"
        }
        for color, style in color_styles.items():
            if keyword in self.keyword_colors[f"{color}_keywords"]:
                return style
        return "Default.TButton"

    def on_keyword_selected(self, value):
        sector = next((s for s, names in self.sector_data.items() if value in names), None)
        if sector:
            db_path = "/Users/yanzhang/Documents/Database/Finance.db"
            condition = f"name = ?"
            result = self.query_database(db_path, sector, condition, (value,))
            self.create_window(result)

    @staticmethod
    def query_database(db_path, table_name, condition, params):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            if not rows:
                return "今天没有数据可显示。\n"
            columns = [description[0] for description in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            return df.to_string(index=False)

    def on_keyword_selected_chart(self, value):
        stock_sectors = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                         "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", "Industrials",
                         "Real_Estate", "Technology", "Utilities"]
        economics_sectors = ["Economics", "ETFs", "Indices"]

        db_path = "/Users/yanzhang/Documents/Database/Finance.db"
        sector = next((s for s, names in self.sector_data.items() if value in names), None)

        if sector:
            compare_value = self.compare_data.get(value, "N/A")
            shares_value = self.shares.get(value, "N/A")
            marketcap, pe = self.marketcap_pe_data.get(value, (None, 'N/A'))

            if sector in stock_sectors:
                period = '1Y'
            elif sector in economics_sectors:
                period = '10Y'
            else:
                period = '1Y'

            plot_financial_data(db_path, sector, value, compare_value, shares_value, marketcap, pe, self.json_data, period, False)

    def create_window(self, content):
        top = tk.Toplevel(self.selection_window)
        top.title("数据库查询结果")
        window_width, window_height = 900, 600
        center_x = (top.winfo_screenwidth() - window_width) // 2
        center_y = (top.winfo_screenheight() - window_height) // 2
        top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        top.bind('<Escape>', lambda e: self.close_app(top))

        text_font = tkFont.Font(family="Courier", size=20)
        text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
        text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        text_area.insert(tk.INSERT, content)
        text_area.configure(state='disabled')

    @staticmethod
    def close_app(window):
        window.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    root = tk.Tk()
    app = FinancialApp(root)
    app.run()