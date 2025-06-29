"""
数字货币相关命令模块
"""
import asyncio
from datetime import datetime
import pandas as pd

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api import logger


class CryptoCommands:
    """数字货币相关命令处理类"""
    
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.data_source = plugin_instance.data_source
        self.config = plugin_instance.config
        self.default_limit = plugin_instance.default_limit

    async def crypto_price(self, event: AstrMessageEvent, symbol: str, vs_currency: str = None) -> MessageEventResult:
        """查询数字货币价格"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            symbol = symbol.upper().strip()
            result = await self.data_source.get_crypto_price(symbol, vs_currency)
            
            if "error" in result:
                return event.plain_result(f"⚠️ {result['error']}")
            
            # 格式化价格显示
            price = result['price']
            change = result['change']
            change_percent = result['change_percent']
            vs_cur = result['vs_currency']
            
            # 根据价格大小选择显示精度
            if price >= 1:
                price_str = f"{price:.6f}".rstrip('0').rstrip('.')
            else:
                price_str = f"{price:.8f}".rstrip('0').rstrip('.')
            
            # 变化方向指示
            trend_icon = "📈" if change >= 0 else "📉"
            change_sign = "+" if change >= 0 else ""
            
            response = (
                f"🪙 {result['name']} ({result['symbol']}) 实时行情\n\n"
                f"💰 当前价格: {price_str} {vs_cur}\n"
                f"{trend_icon} 24h变化: {change_sign}{change:.6f} ({change_percent:+.2f}%)\n"
                f"📊 24h最高: {result['high_24h']:.6f} {vs_cur}\n"
                f"📊 24h最低: {result['low_24h']:.6f} {vs_cur}\n"
                f"📈 24h成交量: {result['volume_24h']:.2f} {symbol}\n\n"
                f"🔄 数据来源: {result['source'].title()}\n"
                f"⏰ 更新时间: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            return event.plain_result(response)
            
        except Exception as e:
            logger.error(f"查询数字货币价格异常: {e}")
            return event.plain_result("🔧 查询数字货币价格失败，请稍后重试")

    async def crypto_list(self, event: AstrMessageEvent, limit: int = 10) -> MessageEventResult:
        """查询热门数字货币列表"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            if limit < 1 or limit > 50:
                limit = 10
            
            cryptos = await self.data_source.get_crypto_list(limit)
            
            if not cryptos:
                return event.plain_result("⚠️ 获取数字货币列表失败")
            
            response = f"🪙 热门数字货币行情 (Top {len(cryptos)})\n\n"
            
            for i, crypto in enumerate(cryptos, 1):
                name = crypto['name']
                price = crypto['price']
                change_percent = crypto['change_percent']
                
                # 价格格式化
                if price >= 1:
                    price_str = f"{price:.4f}".rstrip('0').rstrip('.')
                else:
                    price_str = f"{price:.6f}".rstrip('0').rstrip('.')
                
                # 变化方向
                trend = "📈" if change_percent >= 0 else "📉"
                sign = "+" if change_percent >= 0 else ""
                
                response += f"{i:2d}. {trend} {name:8s} {price_str:>12s} USDT ({sign}{change_percent:.2f}%)\n"
            
            response += f"\n🔄 数据来源: Binance\n⏰ 更新时间: {datetime.now().strftime('%H:%M:%S')}"
            
            return event.plain_result(response)
            
        except Exception as e:
            logger.error(f"查询数字货币列表异常: {e}")
            return event.plain_result("🔧 查询数字货币列表失败，请稍后重试")

    async def crypto_exchange_info(self, event: AstrMessageEvent) -> MessageEventResult:
        """查询币安交易所信息"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            info = await self.data_source.get_exchange_info()
            
            if not info:
                return event.plain_result("⚠️ 获取交易所信息失败")
            
            response = (
                f"🏦 {info['exchange']} 交易所信息\n\n"
                f"📊 总交易对数量: {info['total_symbols']}\n"
                f"💰 活跃USDT交易对: {info['active_usdt_pairs_count']}\n"
                f"⏰ 服务器时间: {datetime.fromtimestamp(info['server_time']/1000).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📈 支持的K线周期:\n"
            )
            
            intervals = info['supported_intervals']
            # 按行显示周期，每行4个
            for i in range(0, len(intervals), 4):
                line_intervals = intervals[i:i+4]
                response += "   " + "  ".join(f"{interval:>4s}" for interval in line_intervals) + "\n"
            
            response += f"\n💡 示例热门交易对:\n"
            for i, pair in enumerate(info['sample_pairs'][:10], 1):
                response += f"   {i:2d}. {pair['symbol']:12s} ({pair['base_asset']}/USDT)\n"
            
            response += f"\n🔄 更新时间: {datetime.now().strftime('%H:%M:%S')}"
            
            return event.plain_result(response)
            
        except Exception as e:
            logger.error(f"查询交易所信息异常: {e}")
            return event.plain_result("🔧 查询交易所信息失败，请稍后重试")

    async def crypto_history(self, event: AstrMessageEvent, symbol: str, vs_currency: str = None, limit: int = None) -> MessageEventResult:
        """查询数字货币历史行情"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            symbol = symbol.upper().strip()
            vs_currency = (vs_currency or 'USDT').upper()
            limit = limit or self.default_limit
            limit = max(5, min(100, limit))
            
            data = await self.data_source.get_crypto_daily(symbol, limit, vs_currency)
            
            if not data:
                return event.plain_result(f"⚠️ 未获取到 {symbol} 的历史数据，请检查交易对是否存在")
            
            trading_pair = self.data_source._normalize_crypto_symbol(symbol, vs_currency)
            lines = [f"📈 {trading_pair} 历史行情（最近 {len(data)} 条）：\n"]
            
            for item in data:
                change = item.get('change', 0)
                pct_chg = item.get('pct_chg', 0)
                symbol_icon = '📈' if change >= 0 else '📉'
                
                # 价格格式化
                close_price = item['close']
                if close_price >= 1:
                    price_str = f"{close_price:.6f}".rstrip('0').rstrip('.')
                else:
                    price_str = f"{close_price:.8f}".rstrip('0').rstrip('.')
                
                lines.append(
                    f"{item['trade_date']}: "
                    f"收 {price_str} {symbol_icon} ({pct_chg:+.2f}%)"
                )
            
            return event.plain_result("\n".join(lines))

        except Exception as e:
            logger.error(f"查询数字货币历史异常: {e}")
            return event.plain_result("🔧 查询数字货币历史失败，请稍后重试")

    async def crypto_chart(self, event: AstrMessageEvent, symbol: str, period: str = 'daily', limit: int = None, vs_currency: str = None) -> MessageEventResult:
        """绘制数字货币K线图"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            if not self.plugin.enable_chart_generation:
                return event.plain_result("⚠️ 图表生成功能未启用")
            
            symbol = symbol.upper().strip()
            vs_currency = (vs_currency or 'USDT').upper()
            
            # 获取历史数据
            if period == 'daily':
                data = await self.data_source.get_crypto_daily(symbol, limit or self.default_limit, vs_currency)
            elif period == 'hourly':
                data = await self.data_source.get_crypto_hourly(symbol, limit or 48, vs_currency)
            elif period in ['1min', '5min', '15min', '30min', '60min']:
                data = await self.data_source.get_crypto_minutely(symbol, period, limit or 96, vs_currency)
            else:
                return event.plain_result(f"⚠️ 不支持的时间周期: {period}\n支持: daily, hourly, 1min, 5min, 15min, 30min, 60min")

            if not data:
                return event.plain_result(f"⚠️ 未获取到 {symbol} 的K线数据，请检查交易对是否存在")

            df = pd.DataFrame(data)
            if df.empty:
                return event.plain_result(f"⚠️ {symbol} K线数据为空")

            # 数据预处理
            df = df.sort_values('trade_date')
            df.reset_index(drop=True, inplace=True)

            # 生成图表标题
            trading_pair = self.data_source._normalize_crypto_symbol(symbol, vs_currency)
            latest = df.iloc[-1]
            change = latest.get('change', 0)
            pct_chg = latest.get('pct_chg', 0)
            
            if 'trade_time' in df.columns and not df.empty:
                latest_time = df.iloc[-1].get('trade_time', '')
                title = (
                    f"{trading_pair} {latest['trade_date']} {latest_time} "
                    f"收: {latest['close']:.6f} {vs_currency}"
                )
            else:
                title = (
                    f"{trading_pair} {latest['trade_date']} "
                    f"收: {latest['close']:.6f} {vs_currency} "
                    f"涨跌: {change:+.6f} ({pct_chg:+.2f}%)"
                )

            async with self.plugin._lock:
                chart_file = self.plugin.plot_stock_chart(df, title)
                if not chart_file:
                    return event.plain_result("🔧 生成数字货币图表失败，请稍后重试")
                
                return event.image_result(chart_file)

        except Exception as e:
            logger.error(f"绘制数字货币图表异常: {e}")
            return event.plain_result("🔧 绘制数字货币图表失败，请稍后重试")

    async def crypto_compare(self, event: AstrMessageEvent, symbols: str, vs_currency: str = None, limit: int = 5) -> MessageEventResult:
        """比较多个数字货币价格"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            # 解析多个货币符号
            symbol_list = [s.strip().upper() for s in symbols.replace(',', ' ').split() if s.strip()]
            if not symbol_list:
                return event.plain_result("⚠️ 请提供至少一个数字货币符号\n例如: /crypto_compare BTC ETH BNB")
            
            if len(symbol_list) > 10:
                symbol_list = symbol_list[:10]  # 限制最多10个
            
            vs_currency = (vs_currency or 'USDT').upper()
            
            results = []
            for symbol in symbol_list:
                try:
                    result = await self.data_source.get_crypto_price(symbol, vs_currency)
                    if "error" not in result:
                        results.append(result)
                except Exception:
                    continue
            
            if not results:
                return event.plain_result("⚠️ 未获取到任何有效的数字货币价格数据")
            
            # 按价格变化排序
            results.sort(key=lambda x: x.get('change_percent', 0), reverse=True)
            
            response = f"🪙 数字货币价格对比 (vs {vs_currency})\n\n"
            
            for i, result in enumerate(results, 1):
                name = result['name']
                price = result['price']
                change_percent = result['change_percent']
                
                # 价格格式化
                if price >= 1:
                    price_str = f"{price:.6f}".rstrip('0').rstrip('.')
                else:
                    price_str = f"{price:.8f}".rstrip('0').rstrip('.')
                
                # 变化方向
                trend = "📈" if change_percent >= 0 else "📉"
                sign = "+" if change_percent >= 0 else ""
                
                response += f"{i:2d}. {trend} {name:8s} {price_str:>14s} ({sign}{change_percent:.2f}%)\n"
            
            response += f"\n🔄 数据来源: Binance\n⏰ 更新时间: {datetime.now().strftime('%H:%M:%S')}"
            
            return event.plain_result(response)
            
        except Exception as e:
            logger.error(f"比较数字货币价格异常: {e}")
            return event.plain_result("🔧 比较数字货币价格失败，请稍后重试")

    async def crypto_market_overview(self, event: AstrMessageEvent) -> MessageEventResult:
        """数字货币市场概览"""
        try:
            if not self.data_source._enable_crypto:
                return event.plain_result("⚠️ 数字货币功能未启用")
            
            # 获取顶级币种作为市场概览
            cryptos = await self.data_source.get_crypto_list(8)
            
            if not cryptos:
                return event.plain_result("⚠️ 获取市场数据失败")
            
            # 统计涨跌情况
            rising_count = sum(1 for crypto in cryptos if crypto['change_percent'] > 0)
            falling_count = len(cryptos) - rising_count
            
            # 找出涨跌幅最大的币种
            max_gainer = max(cryptos, key=lambda x: x['change_percent'])
            max_loser = min(cryptos, key=lambda x: x['change_percent'])
            
            # 计算平均涨跌幅
            avg_change = sum(crypto['change_percent'] for crypto in cryptos) / len(cryptos)
            
            response = f"🌍 数字货币市场概览 (Top {len(cryptos)})\n\n"
            
            # 市场情绪
            if avg_change > 2:
                sentiment = "🟢 强势上涨"
            elif avg_change > 0:
                sentiment = "📈 温和上涨"
            elif avg_change > -2:
                sentiment = "📉 轻微下跌"
            else:
                sentiment = "🔴 大幅下跌"
            
            response += f"📊 市场情绪: {sentiment} (平均涨跌 {avg_change:+.2f}%)\n"
            response += f"📈 上涨币种: {rising_count} 个 | 📉 下跌币种: {falling_count} 个\n\n"
            
            # 涨跌榜
            response += f"🏆 最大涨幅: {max_gainer['name']} {max_gainer['change_percent']:+.2f}%\n"
            response += f"💔 最大跌幅: {max_loser['name']} {max_loser['change_percent']:+.2f}%\n\n"
            
            # 主要币种行情
            response += "💰 主要币种行情:\n"
            for i, crypto in enumerate(cryptos, 1):
                name = crypto['name']
                price = crypto['price']
                change_percent = crypto['change_percent']
                
                # 价格格式化
                if price >= 1:
                    price_str = f"{price:.4f}".rstrip('0').rstrip('.')
                else:
                    price_str = f"{price:.6f}".rstrip('0').rstrip('.')
                
                # 变化方向
                trend = "📈" if change_percent >= 0 else "📉"
                sign = "+" if change_percent >= 0 else ""
                
                response += f"   {trend} {name:8s} ${price_str:>12s} ({sign}{change_percent:.2f}%)\n"
            
            response += f"\n🔄 数据来源: Binance\n⏰ 更新时间: {datetime.now().strftime('%H:%M:%S')}"
            
            return event.plain_result(response)
            
        except Exception as e:
            logger.error(f"查询市场概览异常: {e}")
            return event.plain_result("🔧 查询市场概览失败，请稍后重试")
