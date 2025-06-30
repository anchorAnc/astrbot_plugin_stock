import asyncio
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .data_source import AkStockDataSource
from .commands.stock_commands import StockCommands
from .commands.crypto_commands import CryptoCommands
from .commands.help_commands import HelpCommands
from .utils.chart_utils import ChartGenerator

@register("astrbot_plugin_stock", "anchor", "股市行情查询插件", "1.2.1", "https://github.com/anchorAnc/astrbot_plugin_stock")
class StockPricePlugin(Star):
    """股票行情插件主类"""
    def __init__(self, context: Context):
        """初始化插件"""
        super().__init__(context)
        
        self._lock = asyncio.Lock()
        self.config = context.get_config()
        self.data_source = AkStockDataSource(self.config)
        
        # 配置参数
        self.default_limit = max(5, min(60, self.config.get('default_limit', 20)))
        self.enable_auto_correction = self.config.get('enable_auto_correction', True)
        
        features = self.config.get('features', {})
        self.enable_chart_generation = features.get('enable_chart_generation', True)
        self.enable_technical_analysis = features.get('enable_technical_analysis', True)
        
        self.chart_generator = ChartGenerator(self.config)
        
        self.stock_commands = StockCommands(self)
        self.crypto_commands = CryptoCommands(self)
        self.help_commands = HelpCommands(self)
        
        logger.info(f"股票插件初始化完成 - 超时设置: 美股{self.data_source._us_stock_timeout}s/通用{self.data_source._general_timeout}s")

    async def terminate(self):
        """插件停止清理"""
        logger.info("股市行情插件停止")
        if hasattr(self, '_lock'):
            del self._lock
    
    def plot_stock_chart(self, data, title: str) -> str:
        """绘制股票K线图 - 代理到图表生成器"""
        return self.chart_generator.plot_stock_chart(data, title)
    
    @filter.command("price")
    async def history_price(self, event: AstrMessageEvent, ts_code: str, start: str = None, end: str = None) -> MessageEventResult:
        """查询历史行情"""
        return await self.stock_commands.history_price(event, ts_code, start, end)
    
    @filter.command("price_now")
    async def realtime_price(self, event: AstrMessageEvent, ts_code: str) -> MessageEventResult:
        """查询股票实时行情"""
        return await self.stock_commands.realtime_price(event, ts_code)

    @filter.command("price_chart")
    async def plot_price(self, event: AstrMessageEvent, ts_code: str, period: str = 'daily', limit: int = None, start: str = None, end: str = None) -> MessageEventResult:
        """绘制K线图"""
        return await self.stock_commands.plot_price(event, ts_code, period, limit, start, end)

    @filter.command("index")
    async def index_price(self, event: AstrMessageEvent, index_code: str) -> MessageEventResult:
        """查询指数行情"""
        return await self.stock_commands.index_price(event, index_code)
    
    @filter.command("index_chart")
    async def plot_index(self, event: AstrMessageEvent, index_code: str, limit: int = None, start: str = None, end: str = None) -> MessageEventResult:
        """绘制指数K线图"""
        return await self.stock_commands.plot_index(event, index_code, limit, start, end)
    
    @filter.command("crypto")
    async def crypto_price(self, event: AstrMessageEvent, symbol: str, vs_currency: str = None) -> MessageEventResult:
        """查询数字货币价格"""
        return await self.crypto_commands.crypto_price(event, symbol, vs_currency)
    
    @filter.command("crypto_list")
    async def crypto_list(self, event: AstrMessageEvent, limit: int = 10) -> MessageEventResult:
        """查询热门数字货币列表"""
        return await self.crypto_commands.crypto_list(event, limit)
    
    @filter.command("crypto_info")
    async def crypto_exchange_info(self, event: AstrMessageEvent) -> MessageEventResult:
        """查询币安交易所信息"""
        return await self.crypto_commands.crypto_exchange_info(event)
    
    @filter.command("crypto_history")
    async def crypto_history(self, event: AstrMessageEvent, symbol: str, vs_currency: str = None, limit: int = None) -> MessageEventResult:
        """查询数字货币历史行情"""
        return await self.crypto_commands.crypto_history(event, symbol, vs_currency, limit)
    
    @filter.command("crypto_chart")
    async def crypto_chart(self, event: AstrMessageEvent, symbol: str, period: str = 'daily', limit: int = None, vs_currency: str = None) -> MessageEventResult:
        """绘制数字货币K线图"""
        return await self.crypto_commands.crypto_chart(event, symbol, period, limit, vs_currency)
    
    @filter.command("crypto_compare")
    async def crypto_compare(self, event: AstrMessageEvent, symbols: str, vs_currency: str = None, limit: int = 5) -> MessageEventResult:
        """比较多个数字货币价格"""
        return await self.crypto_commands.crypto_compare(event, symbols, vs_currency, limit)
    
    @filter.command("crypto_market")
    async def crypto_market_overview(self, event: AstrMessageEvent) -> MessageEventResult:
        """数字货币市场概览"""
        return await self.crypto_commands.crypto_market_overview(event)
    
    @filter.command("help_stock")
    async def show_help(self, event: AstrMessageEvent, category: str = None) -> MessageEventResult:
        """显示插件帮助信息"""
        return await self.help_commands.show_help(event, category)
