"""帮助命令模块"""
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api import logger


class HelpCommands:
    """帮助相关命令处理类"""
    
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance

    async def show_help(self, event: AstrMessageEvent, category: str = None) -> MessageEventResult:
        """显示插件帮助信息"""
        try:
            response = (
                "🚀 股票与数字货币行情插件\n\n"
                "📈 股票功能:\n"
                "  /price_now 000001.SZ    # 实时行情\n"
                "  /price 000001.SZ        # 历史数据\n"
                "  /price_chart 000001.SZ  # K线图\n"
                "  /index sh               # 指数查询\n\n"
                "🪙 数字货币功能:\n"
                "  /crypto BTC             # 实时价格\n"
                "  /crypto_list            # 热门榜单\n"
                "  /crypto_chart BTC       # K线图\n"
                "  /crypto_market          # 市场概览\n\n"
                "💡 支持: A股/港股/美股、主流数字货币\n"
                "📚 详细文档: https://github.com/anchorAnc/astrbot_plugin_stock\n"
                "⚠️ 免责声明: 仅供技术研究，不构成投资建议"
            )
            
            return event.plain_result(response)
            
        except Exception as e:
            logger.error(f"显示帮助信息异常: {e}")
            return event.plain_result("🔧 获取帮助信息失败，请稍后重试")
