import asyncio
from datetime import datetime, time
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from dataclasses import dataclass
from typing import Dict, Any

class TsCtrl:
    def __init__(self, token: str):
        import tushare as ts
        ts.set_token(token)
        self.pro = ts.pro_api()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get_daily(self, ts_code: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        row = df.sort_values('trade_date', ascending=False).iloc[0]
        return {
            'trade_date': row.trade_date,
            'open': row.open,
            'close': row.close,
            'high': row.high,
            'low': row.low,
            'pre_close': row.pre_close,
            'change': row.change,
            'pct_chg': row.pct_chg
        }

    async def get_realtime(self, ts_code: str) -> Dict[str, Any]:
        import tushare as ts
        code = ts_code.split('.')[0]
        df = ts.get_realtime_quotes(code)
        row = df.iloc[0]
        return {
            'price': float(row.price),
            'open': float(row.open),
            'pre_close': float(row.pre_close),
            'high': float(row.high),
            'low': float(row.low),
            'time': row.time
        }

@dataclass
class StockPriceCard:
    ts_code: str
    trade_date: str
    open: float
    close: float
    high: float
    low: float
    pre_close: float
    change: float
    pct_chg: float
    time: str = ''

    @property
    def change_symbol(self) -> str:
        return '↑' if self.change > 0 else '↓' if self.change < 0 else '-'

@register("stock_price", "you_username", "股市行情查询插件", "1.1.0")
class StockPricePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        token = config.get('tushare_token', '')
        if not token:
            logger.error("未配置 tushare_token，请在管理面板填写配置。")
        self.ctrl = TsCtrl(token)
        self.default_period = config.get('default_period', 'daily')
        self.default_limit = config.get('default_limit', 5)
        self._lock = asyncio.Lock()

    def is_market_open(self) -> bool:
        now = datetime.now().time()
        return time(9, 30) <= now <= time(11, 30) or time(13, 0) <= now <= time(15, 0)

    @filter.command("price")
    async def price(self, event: AstrMessageEvent, ts_code: str, start: str = None, end: str = None) -> MessageEventResult:
        """
        查询股市行情：
        /price ts_code [start_date YYYYMMDD] [end_date YYYYMMDD]
        当在交易时段会返回实时行情，否则返回日线数据。
        """
        try:
            if not ts_code or '.' not in ts_code:
                return event.plain_result("⚠️ 请输入正确的股票代码，如 000001.SZ")

            # 根据时间选择接口
            if self.is_market_open() and not start and not end:
                data = await self.ctrl.get_realtime(ts_code)
                card = StockPriceCard(
                    ts_code=ts_code,
                    trade_date=datetime.now().strftime('%Y%m%d'),
                    open=data['open'],
                    close=data['price'],
                    high=data['high'],
                    low=data['low'],
                    pre_close=data['pre_close'],
                    change=data['price'] - data['pre_close'],
                    pct_chg=(data['price'] - data['pre_close']) / data['pre_close'] * 100,
                    time=data['time']
                )
                text = (
                    f"📈 {card.ts_code} 实时行情 ({card.time})\n"
                    f"开盘: {card.open:.2f}  当前: {card.close:.2f} {card.change_symbol}\n"
                    f"最高: {card.high:.2f}  最低: {card.low:.2f}\n"
                    f"昨收: {card.pre_close:.2f}  涨跌: {card.change:+.2f} ({card.pct_chg:+.2f}%)"
                )
                return event.plain_result(text)

            # 历史/非交易时段日线数据
            data = await self.ctrl.get_daily(ts_code, start or '', end or '')
            card = StockPriceCard(
                ts_code=ts_code,
                trade_date=data['trade_date'],
                open=data['open'],
                close=data['close'],
                high=data['high'],
                low=data['low'],
                pre_close=data['pre_close'],
                change=data['change'],
                pct_chg=data['pct_chg']
            )
            text = (
                f"📈 {card.ts_code} 行情 ({card.trade_date})\n"
                f"开盘: {card.open:.2f}  收盘: {card.close:.2f} {card.change_symbol}\n"
                f"最高: {card.high:.2f}  最低: {card.low:.2f}\n"
                f"昨收: {card.pre_close:.2f}  涨跌: {card.change:+.2f} ({card.pct_chg:+.2f}%)"
            )
            return event.plain_result(text)

        except Exception as e:
            logger.error(f"行情查询异常: {e}")
            return event.plain_result("🔧 查询失败，请稍后重试。")

    async def terminate(self):
        logger.info("股市行情插件已停止")