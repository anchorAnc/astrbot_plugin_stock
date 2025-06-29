"""
股票相关命令模块
"""
import asyncio
import re
import tempfile
from datetime import datetime
import pandas as pd

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api import logger
from dataclasses import dataclass
from typing import Optional


@dataclass
class StockPriceCard:
    """股票价格数据结构"""
    ts_code: str
    trade_date: str
    open: Optional[float] = None
    close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    pre_close: Optional[float] = None
    change: Optional[float] = None
    pct_chg: Optional[float] = None
    time: str = ''

    @property
    def change_symbol(self) -> str:
        return '↑' if self.change > 0 else '↓' if self.change < 0 else '-'


class StockCommands:
    """股票相关命令处理类"""
    
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.data_source = plugin_instance.data_source
        self.config = plugin_instance.config
        self.default_limit = plugin_instance.default_limit
        self.enable_auto_correction = plugin_instance.enable_auto_correction
        
        self.stock_code_pattern = r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$"
        
        self.index_map = {
            'sh': '000001.SH',
            'sz': '399001.SZ',
            'cyb': '399006.SZ',
            'zxb': '399005.SZ',
            'hs300': '000300.SH',
            'zz500': '000905.SH',
        }
    
    def _validate_stock_code(self, ts_code: str) -> tuple:
        """验证股票代码格式"""
        if re.match(self.stock_code_pattern, ts_code) is not None:
            return True, ts_code
        
        if self.enable_auto_correction:
            corrected = self.data_source._validate_and_correct_stock_code(ts_code)
            if corrected != ts_code and re.match(self.stock_code_pattern, corrected):
                return True, corrected
            
        return False, ts_code
    
    def _normalize_index_code(self, index_code: str) -> str:
        """规范化指数代码"""
        # 处理简化代码映射
        if index_code.lower() in self.index_map:
            return self.index_map[index_code.lower()]
        
        # 处理纯数字代码
        if re.match(r'^\d{6}$', index_code):
            if index_code.startswith(('000', '880')):
                return f"{index_code}.SH"
            elif index_code.startswith('399'):
                return f"{index_code}.SZ"
        
        return index_code

    def _is_index_code(self, ts_code: str) -> bool:
        """判断是否为指数代码"""
        return ((ts_code.endswith('.SH') and ts_code.startswith('000')) or 
                (ts_code.endswith('.SZ') and ts_code.startswith('399')))

    async def history_price(self, event: AstrMessageEvent, ts_code: str, start: str = None, end: str = None) -> MessageEventResult:
        """查询历史行情"""
        try:
            is_valid, corrected_code = self._validate_stock_code(ts_code)
            if not is_valid:
                return event.plain_result(
                    f"⚠️ 无效的股票代码格式: {ts_code}\n"
                    "支持格式:\n"
                    "• A股: 000001.SZ/SH\n"
                    "• 港股: 00700.HK\n"
                    "• 美股: AAPL.US"
                )
            
            if corrected_code != ts_code:
                ts_code = corrected_code
                
            if self._is_index_code(ts_code):
                return event.plain_result(f"⚠️ {ts_code} 是指数，请使用 /index {ts_code} 命令查询")

            all_data = await self.data_source.get_daily(ts_code, start or '', end or '')
            if not all_data:
                if ts_code.endswith('.US'):
                    return event.plain_result(
                        f"⚠️ 美股历史数据获取失败: {ts_code}\n"
                        f"💡 可能原因：\n"
                        f"1. 股票代码不存在或格式不正确\n"
                        f"2. 美股历史数据接口暂时不可用\n"
                        f"🔄 建议使用实时行情命令: /price_now {ts_code}\n"
                        "📋 或查询A股/港股历史数据"
                    )
                else:
                    return event.plain_result(f"⚠️ 未获取到 {ts_code} 的历史行情数据，请检查代码是否正确")
                
            slice_data = all_data[:self.default_limit]
            lines = [f"📈 {ts_code} 历史行情（最近 {len(slice_data)} 条）："]
            
            for item in slice_data:
                change = item.get('change', 0)
                pct_chg = item.get('pct_chg', 0)
                symbol = '↑' if change > 0 else '↓' if change < 0 else '-'
                lines.append(
                    f"{item['trade_date']}: "
                    f"开{item['open']:.2f} 收{item['close']:.2f} {symbol} "
                    f"({pct_chg:+.2f}%)"
                )
            
            return event.plain_result("\n".join(lines))

        except Exception as e:
            logger.error(f"历史行情查询异常: {e}", exc_info=True)
            return event.plain_result("🔧 查询失败，请稍后重试")

    async def realtime_price(self, event: AstrMessageEvent, ts_code: str) -> MessageEventResult:
        """查询股票实时行情"""
        try:
            is_valid, corrected_code = self._validate_stock_code(ts_code)
            if not is_valid:
                return event.plain_result(
                    f"⚠️ 无效的股票代码格式: {ts_code}\n"
                    "支持格式:\n"
                    "• A股: 000001.SZ/SH\n"
                    "• 港股: 00700.HK\n"
                    "• 美股: AAPL.US"
                )
            
            if corrected_code != ts_code:
                ts_code = corrected_code
                
            if self._is_index_code(ts_code):
                return event.plain_result(f"⚠️ {ts_code} 是指数，请使用 /index {ts_code} 命令查询")

            data = await self.data_source.get_realtime(ts_code)
            if not data:
                return event.plain_result(f"⚠️ 未获取到 {ts_code} 的实时行情数据，请检查代码是否正确")
                
            change = data.get('price', 0) - data.get('pre_close', 0)
            pct = change / data['pre_close'] * 100 if data['pre_close'] else 0
            
            card = StockPriceCard(
                ts_code=ts_code,
                trade_date=datetime.now().strftime('%Y%m%d'),
                open=data.get('open', 0),
                close=data.get('price', 0),
                high=data.get('high', 0),
                low=data.get('low', 0),
                pre_close=data.get('pre_close', 0),
                change=change,
                pct_chg=pct,
                time=data.get('time', '')
            )
            
            symbol = card.change_symbol
            color_emoji = "🔴" if change > 0 else "🟢" if change < 0 else "⚪"
            
            text = (
                f"📈 {card.ts_code} 实时行情 ({card.time})\n"
                f"{color_emoji} 当前: {card.close:.2f} {symbol} {card.change:+.2f} ({card.pct_chg:+.2f}%)\n"
                f"📊 开盘: {card.open:.2f}  昨收: {card.pre_close:.2f}\n"
                f"📈 最高: {card.high:.2f}  📉 最低: {card.low:.2f}"
            )
            return event.plain_result(text)

        except Exception as e:
            logger.error(f"实时行情查询异常: {e}", exc_info=True)
            return event.plain_result("🔧 实时查询失败，请稍后重试")

    async def plot_price(self, event: AstrMessageEvent, ts_code: str, period: str = 'daily', limit: int = None, start: str = None, end: str = None) -> MessageEventResult:
        """绘制K线图"""
        try:
            is_valid, corrected_code = self._validate_stock_code(ts_code)
            if not is_valid:
                return event.plain_result(f"⚠️ 无效的股票代码格式: {ts_code}\n"
                                          "支持格式: A股(000001.SZ/SH), 港股(00700.HK), 美股(AAPL.US)")
            
            if corrected_code != ts_code:
                ts_code = corrected_code
                
            if self._is_index_code(ts_code):
                return event.plain_result(f"⚠️ {ts_code} 是指数，请使用 /index {ts_code} 命令查询")

            if period == 'daily':
                data = await self.data_source.get_daily(ts_code, start or '', end or '')
            elif period == 'hourly':
                data = await self.data_source.get_hourly(ts_code)
            elif period in ['5min', '15min', '30min', '60min']:
                data = await self.data_source.get_minutely(ts_code, freq=period)
            else:
                return event.plain_result(f"⚠️ 不支持的粒度类型: {period}")

            if not data:
                if ts_code.endswith('.US'):
                    return event.plain_result(
                        f"⚠️ 美股历史数据获取失败: {ts_code}\n"
                        f"💡 可能原因：\n"
                        f"1. 股票代码不存在或格式不正确\n"
                        f"2. 美股历史数据接口暂时不可用\n"
                        f"🔄 建议使用实时行情命令: /price_now {ts_code}\n"
                        "📋 或查询A股/港股K线图"
                    )
                else:
                    return event.plain_result(f"⚠️ 未获取到{ts_code}的行情数据，请检查代码是否正确")

            df = pd.DataFrame(data)
            if df.empty:
                return event.plain_result(f"⚠️ 未获取到{ts_code}的行情数据，请检查代码是否正确")

            limit_num = self.default_limit
            if limit is not None:
                try:
                    limit_num = max(5, min(120, int(limit)))  # 分钟数据上限提高到120
                except Exception:
                    limit_num = self.default_limit

            if not start and not end:
                df = df.head(limit_num)

            df = df.sort_values('trade_date')
            df.reset_index(drop=True, inplace=True)

            if 'trade_time' in df.columns and not df.empty:
                latest_time = df.iloc[-1].get('trade_time', '')
                title = (
                    f"{ts_code} {latest_time} "
                    f"收: {df.iloc[-1]['close']:.2f}"
                )
            else:
                latest = df.iloc[-1]
                change = latest.get('change', 0)
                pct_chg = latest.get('pct_chg', 0)
                title = (
                    f"{ts_code} {latest['trade_date']} "
                    f"收: {latest['close']:.2f} "
                    f"涨跌: {change:+.2f} ({pct_chg:+.2f}%)"
                )

            async with self.plugin._lock:
                chart_file = self.plugin.plot_stock_chart(df, title)
                if not chart_file:
                    return event.plain_result("🔧 生成图表失败，请稍后重试")
                
                return event.image_result(chart_file)

        except Exception as e:
            logger.error(f"绘制行情图异常: {e}")
            return event.plain_result("🔧 绘制图表失败，请稍后重试。")

    async def index_price(self, event: AstrMessageEvent, index_code: str) -> MessageEventResult:
        """查询指数行情"""
        try:
            index_code = self._normalize_index_code(index_code)
            
            # 最终验证
            if not self._is_index_code(index_code):
                return event.plain_result(f"⚠️ {index_code} 不是有效的指数代码\n"
                                        "支持的指数：000001.SH(上证指数)、399001.SZ(深证成指)、399006.SZ(创业板指) 等")
            
            if index_code.endswith('.SH'):
                query_code = 'sh' + index_code.split('.')[0]
            elif index_code.endswith('.SZ'):
                query_code = 'sz' + index_code.split('.')[0]
            else:
                query_code = index_code
                
            data = await self.data_source.get_index_realtime(query_code)
            if not data:
                return event.plain_result(f"⚠️ 未获取到 {index_code} 的指数行情数据")
            
            change = data.get('price', 0) - data.get('pre_close', 0) 
            pct = change / data['pre_close'] * 100 if data['pre_close'] else 0
            
            up_symbol = '↑' if change > 0 else '↓' if change < 0 else '-'
            color_text = '红' if change > 0 else '绿' if change < 0 else '平'
            
            index_names = {
                '000001.SH': '上证指数',
                '399001.SZ': '深证成指',
                '000300.SH': '沪深300',
                '000905.SH': '中证500',
                '399006.SZ': '创业板指',
                '399005.SZ': '中小板指'
            }
            index_name = index_names.get(index_code, index_code)
            
            text = (
                f"📊 {index_name} ({index_code}) {color_text} {data.get('time', '')}\n"
                f"当前: {data['price']:.2f} {up_symbol} {change:+.2f} ({pct:+.2f}%)\n"
                f"今开: {data['open']:.2f}  昨收: {data['pre_close']:.2f}\n"
                f"最高: {data['high']:.2f}  最低: {data['low']:.2f}"
            )
            
            return event.plain_result(text)
            
        except Exception as e:
            logger.error(f"指数查询异常: {e}")
            return event.plain_result("🔧 指数查询失败，请稍后重试。")

    async def plot_index(self, event: AstrMessageEvent, index_code: str, limit: int = None, start: str = None, end: str = None) -> MessageEventResult:
        """绘制指数K线图"""
        try:
            index_code = self._normalize_index_code(index_code)
            
            # 最终验证
            if not self._is_index_code(index_code):
                return event.plain_result(f"⚠️ {index_code} 不是有效的指数代码\n"
                                        "支持的指数：000001.SH(上证指数)、399001.SZ(深证成指)、399006.SZ(创业板指) 等")
            
            all_data = await self.data_source.get_daily(index_code, start or '', end or '')
            if not all_data:
                return event.plain_result(f"⚠️ 未获取到 {index_code} 的指数历史数据")
                
            df = pd.DataFrame(all_data)
            if df.empty:
                return event.plain_result(f"⚠️ {index_code} 指数数据为空")
            
            limit_num = self.default_limit
            if limit is not None:
                try:
                    limit_num = max(5, min(120, int(limit)))
                except Exception:
                    limit_num = self.default_limit
            
            if not start and not end:
                df = df.head(limit_num)
            
            df = df.sort_values('trade_date')
            df.reset_index(drop=True, inplace=True)
            
            latest = df.iloc[-1]
            change = latest.get('change', 0) 
            pct_chg = latest.get('pct_chg', 0)
            
            index_names = {
                '000001.SH': '上证指数',
                '399001.SZ': '深证成指',
                '000300.SH': '沪深300',
                '000905.SH': '中证500',
                '399006.SZ': '创业板指',
                '399005.SZ': '中小板指'
            }
            index_name = index_names.get(index_code, index_code)
            
            title = (
                f"{index_name} ({index_code}) {latest['trade_date']} "
                f"收: {latest['close']:.2f} "
                f"涨跌: {change:+.2f} ({pct_chg:+.2f}%)"
            )
            
            async with self.plugin._lock:
                chart_file = self.plugin.plot_stock_chart(df, title)
                if not chart_file:
                    return event.plain_result("🔧 生成指数图表失败，请稍后重试")
                
                return event.image_result(chart_file)
                
        except Exception as e:
            logger.error(f"绘制指数图异常: {e}")
            return event.plain_result("🔧 绘制指数图表失败，请稍后重试。")
