import sys
import json
import sqlite3
from datetime import date, timedelta
from functools import partial

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Earnings 百分比处理")

        # 1. 计算日期
        today = date.today()
        self.date1 = (today - timedelta(days=1)).strftime("%Y-%m-%d")   # 昨天
        self.date2 = (today - timedelta(days=2)).strftime("%Y-%m-%d")   # 前天

        # 2. 解析 txt 文件，按日期分类 symbol
        self.symbols_by_date = {self.date1: [], self.date2: []}
        txt_path = "/Users/yanzhang/Documents/News/Earnings_Release_new.txt"
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # symbol 在第一冒号前，date 在最后冒号后
                symbol = line.split(":", 1)[0].strip()
                dt = line.rsplit(":", 1)[1].strip()
                if dt in self.symbols_by_date:
                    self.symbols_by_date[dt].append(symbol)

        # 3. 载入 sector 配置，并反向索引 symbol->sector
        self.symbol_to_sector = {}
        json_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
        with open(json_path, "r", encoding="utf-8") as f:
            sectors = json.load(f)
        for sector_name, syms in sectors.items():
            for s in syms:
                self.symbol_to_sector[s] = sector_name

        # 4. 连接数据库
        db_path = "/Users/yanzhang/Documents/Database/Finance.db"
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        # 5. 构建界面
        self._init_ui()

        # 6. 分两部分处理
        self.process_date1()
        self.process_date2()

    def _init_ui(self):
        cw = QWidget()
        vlay = QVBoxLayout()

        # 第一部分：昨天的 symbols，延迟写入，带“替换”按钮
        gb1 = QGroupBox(f"日期 {self.date1} 符合条件的 Symbols（点击“替换”写入/覆盖）")
        lay1 = QVBoxLayout()
        # 3 列：Symbol, 百分比, 操作
        self.table1 = QTableWidget(0, 3)
        self.table1.setHorizontalHeaderLabels(["Symbol", "百分比(%)", "操作"])
        self.table1.horizontalHeader().setStretchLastSection(True)
        lay1.addWidget(self.table1)
        gb1.setLayout(lay1)
        vlay.addWidget(gb1)

        # 第二部分：前天的 symbols，可“替换”
        gb2 = QGroupBox(f"日期 {self.date2} 符合条件的 Symbols （可替换旧百分比）")
        lay2 = QVBoxLayout()
        self.table2 = QTableWidget(0, 4)
        self.table2.setHorizontalHeaderLabels(["Symbol", "新百分比(%)", "旧百分比(%)", "操作"])
        self.table2.horizontalHeader().setStretchLastSection(True)
        lay2.addWidget(self.table2)
        gb2.setLayout(lay2)
        vlay.addWidget(gb2)

        cw.setLayout(vlay)
        self.setCentralWidget(cw)
        self.resize(1024, 900) # 你已经设置了窗口大小

        # 新增：将窗口移动到屏幕中央
        self.center_window()

    def center_window(self):
        """将窗口移动到屏幕中央"""
        try:
            # 获取主屏幕
            screen = QApplication.primaryScreen()
            if not screen:
                # 如果没有主屏幕（不太可能，但作为备用），尝试获取第一个屏幕
                screens = QApplication.screens()
                if not screens:
                    return # 没有可用屏幕
                screen = screens[0]

            screen_geometry = screen.availableGeometry() # 获取可用屏幕区域几何信息
            window_geometry = self.frameGeometry()    # 获取窗口框架几何信息（包括标题栏）

            # 计算中心点并移动窗口
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())

        except Exception as e:
            print(f"Error centering window: {e}")
            # 如果出现异常，可以尝试旧方法或不进行居中
            # 对于非常旧的 PyQt5 版本，可能需要 QDesktopWidget
            try:
                from PyQt5.QtWidgets import QDesktopWidget
                qr = self.frameGeometry()
                cp = QDesktopWidget().availableGeometry().center()
                qr.moveCenter(cp)
                self.move(qr.topLeft())
            except ImportError:
                pass # QDesktopWidget 不可用
            except Exception as e_old:
                print(f"Error centering window with QDesktopWidget: {e_old}")
                
    def _get_prev_price(self, table: str, dt: str, symbol: str):
        """
        从指定表里找 name=symbol 且 date<dt 的最近一条 price
        """
        sql = f"""
            SELECT price
              FROM `{table}`
             WHERE name=? AND date<? 
          ORDER BY date DESC
             LIMIT 1
        """
        self.cur.execute(sql, (symbol, dt))
        r = self.cur.fetchone()
        return r["price"] if r else None
    
    def process_date1(self):
        """
        扫描“昨天”的 symbols，计算百分比，
        但不写库，只在界面添加“替换”按钮，点击后再写入/覆盖。
        """
        for symbol in self.symbols_by_date[self.date1]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector:
                continue
            # 从 sector 表中取 price
            # 1) 当日收盘
            p1 = self._get_price_from_table(sector, self.date1, symbol)
            if p1 is None:
                continue

            # 2) 上一交易日收盘（动态查找）
            p2 = self._get_prev_price(sector, self.date1, symbol)
            if p2 is None or p2 == 0:
                continue

            # 计算涨跌 %
            pct = round((p1 - p2) / p2 * 100, 2)

            row = self.table1.rowCount()
            self.table1.insertRow(row)
            self.table1.setItem(row, 0, QTableWidgetItem(symbol))
            self.table1.setItem(row, 1, QTableWidgetItem(str(pct)))

            btn = QPushButton("替换")
            btn.clicked.connect(partial(self.on_replace_date1, symbol, pct, row))
            self.table1.setCellWidget(row, 2, btn)

    def on_replace_date1(self, symbol, pct, row):
        """
        第一部分“替换”按钮回调：检查是否已存在同一天同symbol记录，
        如果存在询问覆盖，否则直接写入。
        """
        # 检查是否已有记录
        self.cur.execute(
            "SELECT id FROM Earning WHERE date=? AND name=?",
            (self.date1, symbol)
        )
        exists = self.cur.fetchone() is not None

        if exists:
            reply = QMessageBox.question(
                self, "确认覆盖",
                f"Earning 表中已存在 {symbol} 在 {self.date1} 的记录，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            # 执行更新
            self.cur.execute(
                "UPDATE Earning SET price=? WHERE date=? AND name=?",
                (pct, self.date1, symbol)
            )
            action = "已覆盖"
        else:
            # 执行插入
            self.cur.execute(
                "INSERT INTO Earning (date, name, price) VALUES (?, ?, ?)",
                (self.date1, symbol, pct)
            )
            action = "已写入"

        self.conn.commit()
        # 禁用按钮并提示
        btn = self.table1.cellWidget(row, 2)
        btn.setEnabled(False)
        # QMessageBox.information(self, action, f"{symbol} @ {self.date1} → {pct}%  {action}")

    def process_date2(self):
        """
        对前天的 symbols：
         - 查表算百分比
         - 读 Earning 表取旧百分比
         - 显示在 table2，并加“替换”按钮
        """
        for symbol in self.symbols_by_date[self.date2]:
            sector = self.symbol_to_sector.get(symbol)
            if not sector:
                continue
            p1 = self._get_price_from_table(sector, self.date1, symbol)
            p2 = self._get_price_from_table(sector, self.date2, symbol)
            if p1 is None or p2 is None or p2 == 0:
                continue
            pct_new = round((p1 - p2) / p2 * 100, 2)

            # 从 Earning 表里取该 symbol 最新一条记录的 price
            self.cur.execute(
                "SELECT price FROM Earning WHERE name=? ORDER BY date DESC LIMIT 1",
                (symbol,)
            )
            rowr = self.cur.fetchone()
            pct_old = rowr["price"] if rowr else None

            # 在界面上显示
            row = self.table2.rowCount()
            self.table2.insertRow(row)
            self.table2.setItem(row, 0, QTableWidgetItem(symbol))
            self.table2.setItem(row, 1, QTableWidgetItem(str(pct_new)))
            self.table2.setItem(row, 2, QTableWidgetItem(str(pct_old) if pct_old is not None else ""))

            btn = QPushButton("替换")
            btn.clicked.connect(partial(self.on_replace_date2, symbol, pct_new, row, btn))
            self.table2.setCellWidget(row, 3, btn)

    def on_replace_date2(self, symbol, new_pct, row, btn):
        """
        点击“替换”后，将 new_pct 写回 Earning 表中，覆盖该 symbol 最新一行，
        并在界面上更新旧百分比列，同时禁用按钮。
        """
        # 首先确认覆盖
        reply = QMessageBox.question(
            self, "确认替换",
            f"真的要把 {symbol} 的旧百分比替换成 {new_pct}% 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes   # 这里把 YES 设为默认
        )
        if reply != QMessageBox.Yes:
            return

        # 用子查询定位最新那一行，同时更新 price 和 date
        self.cur.execute("""
            UPDATE Earning
               SET price=?, date=?
             WHERE name=?
               AND id = (
                   SELECT id FROM Earning WHERE name=? ORDER BY date DESC LIMIT 1
               )
        """, (new_pct, self.date1, symbol, symbol))
        self.conn.commit()

        # 更新界面上的“旧百分比”列
        self.table2.setItem(row, 2, QTableWidgetItem(str(new_pct)))

        btn.setText("已替换")
        btn.setEnabled(False)

        # QMessageBox.information(self, "已替换", f"{symbol} 的百分比已更新为 {new_pct}%")

    def _get_price_from_table(self, table: str, dt: str, symbol: str):
        """
        从指定表里取单个价格
        """
        try:
            self.cur.execute(
                f"SELECT price FROM `{table}` WHERE date=? AND name=?",
                (dt, symbol)
            )
            r = self.cur.fetchone()
            return r["price"] if r else None
        except sqlite3.OperationalError:
            return None

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()