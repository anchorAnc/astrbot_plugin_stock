import asyncio
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from dataclasses import dataclass
from typing import Dict, Any, List

# ---------------------- TsCtrl 控制器 ----------------------
class TsCtrl:
    def __init__(self, token: str):
        import tushare as ts
        ts.set_token(token)
        self.pro = ts.pro_api()

    async def get_daily(self, ts_code: str, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """
        返回指定区间内的日线行情列表，按 trade_date 倒序。
        """
        df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        df = df.sort_values('trade_date', ascending=False)
        result = []
        for _, row in df.iterrows():
            result.append({
                'trade_date': row.trade_date,
                'open': row.open,
                'close': row.close,
                'high': row.high,
                'low': row.low,
                'pre_close': row.pre_close,
                'change': row.change,
                'pct_chg': row.pct_chg
            })
        return result

    async def get_realtime(self, ts_code: str) -> Dict[str, Any]:
        """获取当日实时行情"""
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

# ---------------------- 数据结构 ----------------------
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

# ---------------------- 插件主类 ----------------------
@register("stock_price", "you_username", "股市行情查询插件", "1.2.0")
class StockPricePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        token = config.get('tushare_token', '')
        if not token:
            logger.error("未配置 tushare_token，请在管理面板填写配置。")
        self.ctrl = TsCtrl(token)
        self.default_limit = config.get('default_limit', 5)
        self._lock = asyncio.Lock()

    @filter.command("price")
    async def history_price(self,
                            event: AstrMessageEvent,
                            ts_code: str,
                            start: str = None,
                            end: str = None) -> MessageEventResult:
        """
        历史行情查询（默认最新 default_limit 条）：
        /price TS_CODE [START_YYYYMMDD] [END_YYYYMMDD]
        """
        try:
            if not ts_code or '.' not in ts_code:
                return event.plain_result("⚠️ 请输入正确的股票代码，如 000001.SZ")

            all_data = await self.ctrl.get_daily(ts_code, start or '', end or '')
            slice_data = all_data[:self.default_limit]
            lines = [f"📈 {ts_code} 历史行情（最近 {len(slice_data)} 条）：" ]
            for item in slice_data:
                sym = '↑' if item['change'] > 0 else '↓' if item['change'] < 0 else '-'
                lines.append(
                    f"{item['trade_date']}: 开{item['open']:.2f} 收{item['close']:.2f} {sym} ({item['pct_chg']:+.2f}%)"
                )
            return event.plain_result("\n".join(lines))

        except Exception as e:
            logger.error(f"历史行情查询异常: {e}")
            return event.plain_result("🔧 查询失败，请稍后重试。")

    @filter.command("price_now")
    async def realtime_price(self,
                             event: AstrMessageEvent,
                             ts_code: str) -> MessageEventResult:
        """
        实时行情查询（强制实时快照，不受交易时段限制）：
        /price_now TS_CODE
        """
        try:
            if not ts_code or '.' not in ts_code:
                return event.plain_result("⚠️ 请输入正确的股票代码，如 000001.SZ")

            data = await self.ctrl.get_realtime(ts_code)
            change = data['price'] - data['pre_close']
            pct = change / data['pre_close'] * 100
            card = StockPriceCard(
                ts_code=ts_code,
                trade_date=datetime.now().strftime('%Y%m%d'),
                open=data['open'],
                close=data['price'],
                high=data['high'],
                low=data['low'],
                pre_close=data['pre_close'],
                change=change,
                pct_chg=pct,
                time=data['time']
            )
            text = (
                f"📈 {card.ts_code} 实时行情 ({card.time})\n"
                f"开盘: {card.open:.2f}  当前: {card.close:.2f} {card.change_symbol}\n"
                f"最高: {card.high:.2f}  最低: {card.low:.2f}\n"
                f"昨收: {card.pre_close:.2f}  涨跌: {card.change:+.2f} ({card.pct_chg:+.2f}%)"
            )
            return event.plain_result(text)

        except Exception as e:
            logger.error(f"实时行情查询异常: {e}")
            return event.plain_result("🔧 实时查询失败，请稍后重试。")

    async def terminate(self):
        logger.info("股市行情插件已停止")
