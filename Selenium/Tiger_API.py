#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
老虎证券 API 数据获取核心代码提炼
包含：
1. 客户端初始化
2. 获取实时行情（含盘前盘后）
3. 获取历史K线数据
4. 获取账户资产（可用资金、购买力）
5. 获取当前持仓
"""

import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import logging
from datetime import datetime, timedelta
from pytz import timezone as pytz_timezone
import pandas as pd

# 导入老虎 API 核心组件
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.common.util.signature_utils import read_private_key
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.trade.trade_client import TradeClient
from tigeropen.common.consts import Language, BarPeriod, QuoteRight

# ==================== 配置区 ====================
PRIVATE_KEY_PATH = '/Users/yanzhang/Downloads/backup/tiger.pem'
TIGER_ID = '20150215'
ACCOUNT = '21638488022016545'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# --- 新增：符号映射表 ---
# 如果未来还有其他股票需要转换，直接在这个字典里添加即可
SYMBOL_MAPPING = {
    "BRK-B": "BRK.B",
    # 例如：如果以后有其他需要转换的，可以继续加
    "BF-B": "BF.B", 
}

def _normalize_symbol(symbol):
    """内部辅助函数：将本地符号转换为 API 识别的符号"""
    return SYMBOL_MAPPING.get(symbol, symbol)

class TigerDataFetcher:
    def __init__(self, private_key_path: str, tiger_id: str, account: str):
        """初始化老虎 API 客户端"""
        self.private_key_path = private_key_path
        self.tiger_id = tiger_id
        self.account = account
        
        self.quote_client = None
        self.trade_client = None
        
        self._init_clients()

    def _init_clients(self):
        """配置并初始化 QuoteClient 和 TradeClient"""
        try:
            client_config = TigerOpenClientConfig()
            client_config.private_key = read_private_key(self.private_key_path)
            client_config.tiger_id = self.tiger_id
            client_config.account = self.account
            client_config.language = Language.zh_CN
            client_config.timezone = 'US/Eastern'

            self.quote_client = QuoteClient(client_config)
            self.trade_client = TradeClient(client_config)
            logger.info("Tiger 客户端初始化成功")
        except Exception as e:
            logger.error(f"客户端初始化失败: {e}")
            raise

    # ==================== 行情数据获取 ====================

    def get_realtime_prices(self, symbols):
        """
        批量获取实时价格(盘前/盘后期间优先返回 hour_trading_latest_price)
        返回: {symbol: price, ...}
        """
        if not symbols:
            return {}
            
        # 将列表中的每个 symbol 都进行标准化
        symbols = [_normalize_symbol(s) for s in symbols] 

        result = {}
        symbols_list = list(symbols)
        batch_size = 50  # 老虎 API 限制单次最多查询 50 只股票
        
        try:
            # 将 symbols 列表按 batch_size 分批
            for i in range(0, len(symbols_list), batch_size):
                batch_symbols = symbols_list[i:i + batch_size]
                
                briefs = self.quote_client.get_stock_briefs(
                    symbols=batch_symbols,
                    include_hour_trading=True,
                    lang=Language.zh_CN
                )
                
                if briefs is None or briefs.empty:
                    continue
                    
                for _, row in briefs.iterrows():
                    sym = row.get('symbol')
                    if not sym:
                        continue
                    # 优先盘前/盘后
                    hour_price = row.get('hour_trading_latest_price')
                    price = None
                    if hour_price is not None and hour_price != '' and not pd.isna(hour_price):
                        try:
                            price = float(hour_price)
                        except Exception:
                            price = None
                            
                    # 如果没有盘前/盘后价格，或者价格为0，则使用常规最新价
                    if price is None or price == 0:
                        try:
                            price = float(row.get('latest_price', 0))
                        except Exception:
                            continue
                    if price and price > 0:
                        result[sym] = price
                        
            return result
        except Exception as e:
            logger.error(f"批量获取实时价格失败: {e}")
            return result  # 发生异常时，返回已经成功获取到的部分数据
        
    def get_realtime_quote(self, symbol: str) -> dict:
        """
        获取单只股票的实时行情（包含盘前盘后数据）
        """
        try:
            symbol = _normalize_symbol(symbol)
            
            df = self.quote_client.get_stock_briefs(
                symbols=[symbol],
                include_hour_trading=True,
                lang=Language.zh_CN
            )
            
            if df is None or df.empty:
                logger.warning(f"获取 {symbol} 价格数据为空")
                return {}

            row = df.iloc[0]
            
            # 判断是否有盘前/盘后价格
            hour_price = row.get('hour_trading_latest_price')
            if hour_price is not None and hour_price != '':
                price = float(hour_price)
                tag = row.get('hour_trading_tag', '常规')
                is_extended = True
            else:
                price = float(row.get('latest_price', 0))
                tag = '常规'
                is_extended = False

            return {
                'symbol': symbol,
                'price': price,
                'volume': int(row.get('volume', 0)),
                'pre_close': float(row.get('pre_close', 0)),
                'tag': tag,
                'is_extended': is_extended
            }
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return {}

    def get_historical_bars(self, symbol: str, days: int = 100) -> pd.DataFrame:
        """
        修正后的获取历史日K线数据
        """
        us_eastern = pytz_timezone('US/Eastern')
        
        # 1. 明确结束时间：使用昨天或今天，确保覆盖最新交易日
        end_dt = datetime.now(us_eastern)
        # 2. 明确开始时间：往前推 N 天
        begin_dt = end_dt - timedelta(days=days + 15) 

        end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        begin_time = begin_dt.strftime('%Y-%m-%d %H:%M:%S')
        symbol = _normalize_symbol(symbol)

        try:
            # 修改点：将 total 设置为一个足够大的数，确保能把这段时间的数据全拿回来
            # 然后在本地进行排序和截取
            df = self.quote_client.get_bars_by_page(
                symbol=symbol,
                period=BarPeriod.DAY,
                begin_time=begin_time,
                end_time=end_time,
                total=5000, # 增大这个值，防止被截断
                page_size=1000,
                right=QuoteRight.BR, 
                time_interval=0.5
            )

            if df is None or df.empty:
                logger.warning(f"获取 {symbol} 历史日K数据为空")
                return pd.DataFrame()

            # 数据清洗与转换
            df['time'] = pd.to_numeric(df['time'], errors='coerce')
            df['date'] = pd.to_datetime(df['time'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('US/Eastern').dt.strftime('%Y-%m-%d')
            
            # 核心修改：按时间倒序排序，取最后 N 条
            df = df.sort_values('time', ascending=False).head(days)
            
            # 为了符合你原本的习惯（从旧到新），再反转回来
            df = df.sort_values('time', ascending=True).reset_index(drop=True)

            return df
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return pd.DataFrame()

    # ==================== 账户与交易数据获取 ====================

    def get_account_assets(self) -> dict:
        """
        获取账户资产信息（重点提取可用资金和购买力）
        """
        try:
            assets = self.trade_client.get_assets()
            available_funds = 0.0
            buying_power = 0.0

            # 老虎 API 返回的 assets 格式可能是 DataFrame, list 或 dict
            if isinstance(assets, pd.DataFrame) and not assets.empty:
                available_funds = float(assets.iloc[0].get('available_funds', 0))
                buying_power = float(assets.iloc[0].get('buying_power', 0))
            
            elif isinstance(assets, list) and len(assets) > 0:
                first_asset = assets[0]
                summary = getattr(first_asset, 'summary', None)
                if summary:
                    available_funds = float(getattr(summary, 'available_funds', 0))
                    buying_power = float(getattr(summary, 'buying_power', 0))
                    
                    # 备用字段降级处理
                    if available_funds == 0:
                        available_funds = float(getattr(summary, 'cash', 0))
            
            elif isinstance(assets, dict):
                available_funds = float(assets.get('available_funds', 0))
                buying_power = float(assets.get('buying_power', 0))

            return {
                'available_funds': available_funds,
                'buying_power': buying_power
            }
        except Exception as e:
            logger.error(f"获取账户资产失败: {e}")
            return {}

    def get_positions(self, target_symbol: str = None) -> list:
        """
        获取账户当前持仓
        :param target_symbol: 如果指定了标的，则只返回该标的的持仓；否则返回所有持仓
        """
        target_symbol = _normalize_symbol(target_symbol)

        try:
            positions = self.trade_client.get_positions()
            parsed_positions = []

            if isinstance(positions, pd.DataFrame) and not positions.empty:
                for _, pos in positions.iterrows():
                    parsed_positions.append({
                        'symbol': pos.get('symbol'),
                        'quantity': int(pos.get('quantity', 0)),
                        'average_cost': float(pos.get('average_cost', 0)),
                        'market_value': float(pos.get('market_value', 0))
                    })
            elif isinstance(positions, list):
                for pos in positions:
                    parsed_positions.append({
                        'symbol': getattr(pos, 'symbol', ''),
                        'quantity': int(getattr(pos, 'quantity', 0)),
                        'average_cost': float(getattr(pos, 'average_cost', 0)),
                        'market_value': float(getattr(pos, 'market_value', 0))
                    })

            # 如果指定了 symbol，进行过滤
            if target_symbol:
                return [p for p in parsed_positions if p['symbol'] == target_symbol]
            
            return parsed_positions
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return []

    def get_estimate_tradable_qty(self, symbol: str, action: str = 'BUY', price: float = None) -> int:
        """
        获取预估可交易数量（常用于做空时查询最大可融券数量）
        action: 'BUY' 或 'SELL_SHORT'
        """
        symbol = _normalize_symbol(symbol)
        
        try:
            estimate = self.trade_client.get_estimate_tradable_quantity(
                symbol=symbol, 
                sec_type='STK', 
                action=action,
                order_type='LMT', 
                limit_price=price,
                total_quantity=999999 # 传入极大值以获取上限
            )
            
            if isinstance(estimate, pd.DataFrame) and not estimate.empty:
                return int(estimate.iloc[0].get('max_quantity', 0))
            elif isinstance(estimate, list) and len(estimate) > 0:
                return int(getattr(estimate[0], 'max_quantity', 0))
                
            return 0
        except Exception as e:
            logger.error(f"获取预估可交易数量失败: {e}")
            return 0

_global_fetcher = None

def _get_global_fetcher():
    """单例：避免每次调用都重新加载私钥与建立连接"""
    global _global_fetcher
    if _global_fetcher is None:
        _global_fetcher = TigerDataFetcher(
            private_key_path=PRIVATE_KEY_PATH,
            tiger_id=TIGER_ID,
            account=ACCOUNT
        )
    return _global_fetcher
    
if __name__ == "__main__":
    # 实例化数据获取器
    fetcher = TigerDataFetcher(
        private_key_path=PRIVATE_KEY_PATH,
        tiger_id=TIGER_ID,
        account=ACCOUNT
    )
    
    symbol_to_check = "NVDA"

    # 1. 获取实时行情
    logger.info("--- 获取实时行情 ---")
    quote = fetcher.get_realtime_quote(symbol_to_check)
    logger.info(f"实时行情: {quote}")

    # 2. 获取历史K线数据
    logger.info("\n--- 获取历史K线 ---")
    bars_df = fetcher.get_historical_bars(symbol_to_check, days=5)
    if not bars_df.empty:
        logger.info(f"最近5天K线数据:\n{bars_df[['date', 'open', 'high', 'low', 'close', 'volume']].tail()}")

    # 3. 获取账户资金
    logger.info("\n--- 获取账户资金 ---")
    assets = fetcher.get_account_assets()
    logger.info(f"账户资金: {assets}")

    # 4. 获取持仓
    logger.info("\n--- 获取当前持仓 ---")
    nvda_position = fetcher.get_positions(target_symbol=symbol_to_check)
    logger.info(f"{symbol_to_check} 持仓情况: {nvda_position}")

    # 5. 获取预估可做空数量
    logger.info("\n--- 获取预估可做空数量 ---")
    short_qty = fetcher.get_estimate_tradable_qty(symbol_to_check, action='SELL_SHORT')
    logger.info(f"{symbol_to_check} 预估最大可做空数量: {short_qty}")