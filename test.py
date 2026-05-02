import sys
import sqlite3
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QLabel, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QBrush


class KLineChart(QWidget):
    """K线图和成交量图组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.ma_data = {}
        self.chart_type = 'day'
        self.display_count = 100
        self.setMinimumHeight(400)
        
        self.colors = {
            'up': QColor(239, 83, 80),
            'down': QColor(38, 166, 154),
            'ma28': QColor(255, 152, 0),
            'ma38': QColor(156, 39, 176),
            'ma48': QColor(33, 150, 243),
            'ma80': QColor(76, 175, 80),
            'ma132': QColor(244, 67, 54),
            'ma200': QColor(121, 85, 72),
            'grid': QColor(60, 60, 60),
            'text': QColor(200, 200, 200),
        }
        
        self.setStyleSheet("background-color: #1a1a2e;")
    
    def set_data(self, df):
        if df is None or df.empty:
            return
        self.data = df.copy()
        self.data = self.data.sort_values('date').reset_index(drop=True)
        
        for ma in [28, 38, 48, 80, 132, 200]:
            self.ma_data[f'MA{ma}'] = self.data['close'].rolling(window=ma, min_periods=1).mean()
        
        self.update()
    
    def set_chart_type(self, chart_type):
        self.chart_type = chart_type
        self.update()
    
    def resample_data(self):
        if self.data is None or self.data.empty:
            return None
            
        df = self.data.copy()
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        if self.chart_type == 'day':
            resampled = df.copy()
        elif self.chart_type == 'week':
            resampled = df.resample('W').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna()
        elif self.chart_type == 'month':
            resampled = df.resample('ME').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna()
        elif self.chart_type == 'year':
            resampled = df.resample('YE').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna()
        else:
            resampled = df.copy()
        
        resampled = resampled.tail(self.display_count).reset_index()
        return resampled
    
    def paintEvent(self, event):
        if self.data is None or self.data.empty:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        df = self.resample_data()
        if df is None or df.empty:
            return
        
        width = self.width()
        height = self.height()
        
        kline_height = int(height * 0.70)
        volume_height = int(height * 0.30)
        
        margin_left = 60
        margin_right = 10
        margin_top = 20
        margin_bottom = 30
        
        chart_width = width - margin_left - margin_right
        kline_chart_height = kline_height - margin_top - margin_bottom
        
        price_max = df[['high', 'open', 'close', 'low']].max().max()
        price_min = df[['high', 'open', 'close', 'low']].min().min()
        price_range = price_max - price_min
        price_max += price_range * 0.05
        price_min -= price_range * 0.05
        price_range = price_max - price_min
        
        volume_max = df['volume'].max() * 1.1
        
        n_bars = len(df)
        if n_bars == 0:
            return
            
        bar_width = chart_width / n_bars
        candle_width = max(bar_width * 0.7, 2)
        
        # 网格线
        painter.setPen(QPen(self.colors['grid'], 0.5, Qt.PenStyle.DotLine))
        for i in range(6):
            y = margin_top + kline_chart_height * i / 5
            painter.drawLine(int(margin_left), int(y), int(width - margin_right), int(y))
        
        for i in range(n_bars):
            if i % max(1, n_bars // 10) == 0:
                x = margin_left + i * bar_width + bar_width / 2
                painter.drawLine(int(x), margin_top, int(x), int(kline_height - margin_bottom))
        
        # K线
        for i, row in df.iterrows():
            x = margin_left + i * bar_width + bar_width / 2
            
            open_y = margin_top + kline_chart_height * (1 - (row['open'] - price_min) / price_range)
            close_y = margin_top + kline_chart_height * (1 - (row['close'] - price_min) / price_range)
            high_y = margin_top + kline_chart_height * (1 - (row['high'] - price_min) / price_range)
            low_y = margin_top + kline_chart_height * (1 - (row['low'] - price_min) / price_range)
            
            is_up = row['close'] >= row['open']
            color = self.colors['up'] if is_up else self.colors['down']
            
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            
            painter.drawLine(int(x), int(high_y), int(x), int(low_y))
            
            body_top = min(open_y, close_y)
            body_height = abs(close_y - open_y)
            body_height = max(body_height, 1)
            
            painter.drawRect(
                int(x - candle_width / 2), int(body_top),
                int(candle_width), int(body_height)
            )
        
        # 均线
        ma_names = ['MA28', 'MA38', 'MA48', 'MA80', 'MA132', 'MA200']
        
        for ma_name in ma_names:
            if ma_name not in self.ma_data:
                continue
                
            ma_values = self.ma_data[ma_name]
            ma_df = pd.DataFrame({'date': self.data['date'], 'value': ma_values})
            ma_df['date'] = pd.to_datetime(ma_df['date'])
            ma_df.set_index('date', inplace=True)
            
            if self.chart_type == 'week':
                ma_resampled = ma_df.resample('W').last().dropna()
            elif self.chart_type == 'month':
                ma_resampled = ma_df.resample('ME').last().dropna()
            elif self.chart_type == 'year':
                ma_resampled = ma_df.resample('YE').last().dropna()
            else:
                ma_resampled = ma_df.copy()
            
            ma_resampled = ma_resampled.tail(self.display_count).reset_index()
            
            if len(ma_resampled) == 0:
                continue
            
            color = self.colors.get(ma_name.lower(), QColor(255, 255, 255))
            painter.setPen(QPen(color, 1.5))
            
            points = []
            for j, ma_row in ma_resampled.iterrows():
                if j >= n_bars:
                    break
                if pd.isna(ma_row['value']):
                    continue
                mx = margin_left + j * bar_width + bar_width / 2
                my = margin_top + kline_chart_height * (1 - (ma_row['value'] - price_min) / price_range)
                points.append((mx, my))
            
            for k in range(len(points) - 1):
                painter.drawLine(int(points[k][0]), int(points[k][1]), 
                                int(points[k+1][0]), int(points[k+1][1]))
        
        # 成交量图
        volume_top = kline_height
        volume_chart_height = volume_height - margin_bottom
        
        painter.fillRect(margin_left, volume_top, chart_width, volume_chart_height, 
                        QColor(20, 20, 40))
        
        painter.setPen(QPen(self.colors['grid'], 0.5, Qt.PenStyle.DotLine))
        painter.drawLine(margin_left, volume_top, width - margin_right, volume_top)
        painter.drawLine(margin_left, volume_top + volume_chart_height // 2, 
                        width - margin_right, volume_top + volume_chart_height // 2)
        painter.drawLine(margin_left, volume_top + volume_chart_height - 1, 
                        width - margin_right, volume_top + volume_chart_height - 1)
        
        for i, row in df.iterrows():
            x = margin_left + i * bar_width + bar_width / 2
            
            is_up = row['close'] >= row['open']
            color = self.colors['up'] if is_up else self.colors['down']
            
            vol_height = (row['volume'] / volume_max) * volume_chart_height
            vol_y = volume_top + volume_chart_height - vol_height
            
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            painter.drawRect(
                int(x - candle_width / 2), int(vol_y),
                int(candle_width), int(vol_height)
            )
        
        # Y轴标签
        painter.setPen(QPen(self.colors['text'], 1))
        font = QFont("Arial", 8)
        painter.setFont(font)
        
        for i in range(6):
            price = price_min + price_range * (1 - i / 5)
            y = margin_top + kline_chart_height * i / 5
            painter.drawText(5, int(y - 6), 50, 12, 
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{price:.2f}")
        
        painter.drawText(5, int(volume_top + 2), 50, 12,
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        f"{volume_max/1e6:.1f}M")
        painter.drawText(5, int(volume_top + volume_chart_height - 14), 50, 12,
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        "0")
        
        # X轴日期
        date_count = min(n_bars, 10)
        for i in range(date_count):
            idx = int(i * (n_bars - 1) / max(date_count - 1, 1))
            if idx < len(df):
                x = margin_left + idx * bar_width + bar_width / 2
                date_str = str(df.iloc[idx]['date'])[:10]
                painter.drawText(int(x - 30), int(height - 5), 60, 12,
                               Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop,
                               date_str)
        
        # 图例
        legend_x = width - 400
        legend_y = 5
        legend_items = [
            ('MA28', self.colors['ma28']), ('MA38', self.colors['ma38']),
            ('MA48', self.colors['ma48']), ('MA80', self.colors['ma80']),
            ('MA132', self.colors['ma132']), ('MA200', self.colors['ma200']),
        ]
        
        for name, color in legend_items:
            painter.setPen(QPen(color, 2))
            painter.drawLine(legend_x, legend_y + 6, legend_x + 15, legend_y + 6)
            painter.setPen(QPen(self.colors['text'], 1))
            painter.drawText(legend_x + 18, legend_y, 40, 12,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           name)
            legend_x += 65
        
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NVDA 股票K线图")
        self.setStyleSheet("background-color: #0f0f23;")
        self.showFullScreen()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 顶部控制栏
        control_bar = QWidget()
        control_bar.setFixedHeight(50)
        control_bar.setStyleSheet("background-color: #1a1a3e;")
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(20, 5, 20, 5)
        
        title_label = QLabel("NVDA - NVIDIA Corporation")
        title_label.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        control_layout.addWidget(title_label)
        
        control_layout.addStretch()
        
        period_label = QLabel("周期选择:")
        period_label.setStyleSheet("color: #aaaaaa; font-size: 14px;")
        control_layout.addWidget(period_label)
        
        self.period_combo = QComboBox()
        self.period_combo.addItems(["日K", "周K", "月K", "年K"])
        self.period_combo.setFixedWidth(120)
        self.period_combo.setFixedHeight(35)
        self.period_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a5e; color: #ffffff;
                border: 1px solid #4444aa; border-radius: 5px;
                padding: 5px; font-size: 14px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #2a2a5e; color: #ffffff;
                selection-background-color: #4444aa;
            }
        """)
        self.period_combo.currentIndexChanged.connect(self.on_period_changed)
        control_layout.addWidget(self.period_combo)
        
        exit_btn = QPushButton("退出")
        exit_btn.setFixedWidth(80)
        exit_btn.setFixedHeight(35)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b; color: #ffffff;
                border: none; border-radius: 5px; font-size: 14px;
            }
            QPushButton:hover { background-color: #e74c3c; }
        """)
        exit_btn.clicked.connect(self.close)
        control_layout.addWidget(exit_btn)
        
        layout.addWidget(control_bar)
        
        self.chart = KLineChart()
        layout.addWidget(self.chart, stretch=1)
        
        self.load_data()
    
    def load_data(self):
        # db_path = '/Users/yanzhang/Downloads/Finance.db'
        db_path = '/Users/yanzhang/Coding/Database/Finance.db'
        
        try:
            conn = sqlite3.connect(db_path)
            query = "SELECT date, name, price as close, volume, open, high, low FROM Technology WHERE name = 'NVDA' ORDER BY date"
            df = pd.read_sql(query, conn)
            conn.close()
            
            numeric_cols = ['close', 'volume', 'open', 'high', 'low']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna()
            
            print(f"成功加载 {len(df)} 条NVDA数据")
            print(f"日期范围: {df['date'].min()} 至 {df['date'].max()}")
            
            self.chart.set_data(df)
            
        except Exception as e:
            print(f"数据库连接失败: {e}")
            print("使用示例数据...")
            self.create_sample_data()
    
    def create_sample_data(self):
        dates = pd.date_range(end='2024-12-31', periods=500, freq='B')
        np.random.seed(42)
        
        n = len(dates)
        returns = np.random.normal(0.001, 0.02, n)
        prices = 100 * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'date': dates.strftime('%Y-%m-%d'),
            'name': 'NVDA',
            'open': prices * (1 + np.random.normal(0, 0.005, n)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.01, n))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.01, n))),
            'close': prices,
            'volume': np.random.randint(10000000, 50000000, n)
        })
        
        df['high'] = df[['open', 'close', 'high']].max(axis=1)
        df['low'] = df[['open', 'close', 'low']].min(axis=1)
        
        self.chart.set_data(df)
    
    def on_period_changed(self, index):
        periods = {0: 'day', 1: 'week', 2: 'month', 3: 'year'}
        self.chart.set_chart_type(periods.get(index, 'day'))
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
