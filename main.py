import asyncio
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from dataclasses import dataclass
from typing import Dict, Any

# Token controller for Tushare Pro
class TsCtrl:
    def __init__(self, token: str):
        import tushare as ts
        ts.set_token(token)
        self.pro = ts.pro_api()

    async def __aenter__(self):
        # 无需异步连接
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # 无需清理
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

    @property
    def change_symbol(self) -> str:
        return '↑' if self.change > 0 else '↓' if self.change < 0 else '-'

@register("stock_price", "you_username", "股行情查询插件", "1.0.0")
class StockPricePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config  # AstrBotConfig inheriting dict

        token = config.get('tushare_token', '')
        if not token:
            logger.error("未配置 tushare_token，请在管理面板填写配置。")
        self.ctrl = TsCtrl(token)
        self.default_period = config.get('default_period', 'daily')
        self.default_limit = config.get('default_limit', 5)
        self._lock = asyncio.Lock()

    @filter.command("price")
    async def price(self, event: AstrMessageEvent, ts_code: str, start: str = None, end: str = None) -> MessageEventResult:
        """
        查询 A 股行情：
        /price 000001.SZ [start_date YYYYMMDD] [end_date YYYYMMDD]
        """
        try:
            if not ts_code or '.' not in ts_code:
                return event.plain_result("⚠️ 请输入正确的股票代码，如 000001.SZ")

            data = await self.ctrl.get_daily(
                ts_code,
                start or '',
                end or ''
            )
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
            return await self._render(event, card)
        except Exception as e:
            logger.error(f"行情查询异常: {e}")
            return event.plain_result("🔧 查询失败，请稍后重试。")

    async def _render(self, event: AstrMessageEvent, card: StockPriceCard) -> MessageEventResult:
        text = (
            f"📈 **{card.ts_code} 行情 ({card.trade_date})**\n"
            f"开盘: {card.open:.2f}  收盘: {card.close:.2f} {card.change_symbol}\n"
            f"最高: {card.high:.2f}  最低: {card.low:.2f}\n"
            f"昨收: {card.pre_close:.2f}  涨跌: {card.change:+.2f} ({card.pct_chg:+.2f}%)"
        )
        return event.plain_result(text)

    async def terminate(self):
        logger.info("A 股行情插件已停止")
