import asyncio
from datetime import datetime
import matplotlib
import matplotlib.pyplot as plt
import re
from matplotlib.font_manager import FontProperties
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import os
import tempfile
import pandas as pd
import numpy as np

matplotlib.use('Agg')

try:
    font = FontProperties(fname=r'C:\Windows\Fonts\msyh.ttc')
except:
    try:
        font = FontProperties(fname='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    except:
        font = FontProperties()

matplotlib.rcParams.update({
    'font.size': 12,
    'axes.titlesize': 14,
    'axes.unicode_minus': False,
    'figure.titlesize': 16,
    'figure.figsize': (12, 8),
})

import mplfinance as mpf

def calculate_macd(df: pd.DataFrame) -> tuple:
    """计算MACD指标"""
    try:
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        dif = exp12 - exp26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = (dif - dea) * 2
        return dif, dea, macd
    except Exception as e:
        logger.error(f"MACD计算异常: {e}")
        return None, None, None

def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> tuple:
    """计算KDJ指标"""
    try:
        low_list = df['low'].rolling(window=n, min_periods=1).min()
        high_list = df['high'].rolling(window=n, min_periods=1).max()
        rsv = (df['close'] - low_list) / (high_list - low_list) * 100
        rsv = rsv.fillna(50)
        k = rsv.ewm(alpha=1/m1, adjust=False).mean()
        d = k.ewm(alpha=1/m2, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j
    except Exception as e:
        logger.error(f"KDJ计算异常: {e}")
        return None, None, None

def calculate_rsi(df: pd.DataFrame, periods: list = [6, 12, 24]) -> dict:
    """计算RSI指标"""
    try:
        rsi_dict = {}
        for period in periods:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi_dict[period] = 100 - (100 / (1 + rs))
        return rsi_dict
    except Exception as e:
        logger.error(f"RSI计算异常: {e}")
        return {}

def calculate_volume_ma(df: pd.DataFrame, periods: list = [5, 10]) -> dict:
    """计算成交量移动平均线"""
    try:
        volume_ma_dict = {}
        for period in periods:
            volume_ma_dict[period] = df['volume'].rolling(window=period, min_periods=1).mean()
        return volume_ma_dict
    except Exception as e:
        logger.error(f"成交量MA计算异常: {e}")
        return {}

from .data_source import AkStockDataSource

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

@register("astrbot_plugin_stock", "anchor", "股市行情查询插件", "1.1.1", "https://github.com/anchorAnc/astrbot_plugin_stock")
class StockPricePlugin(Star):
    """股票行情插件主类"""
    
    def __init__(self, context: Context):
        """初始化插件"""
        super().__init__(context)
        
        self._lock = asyncio.Lock()
        self.config = context.get_config()
        self.data_source = AkStockDataSource(self.config)
        
        self.stock_code_pattern = r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$"
        
        self.index_map = {
            'sh': '000001.SH',
            'sz': '399001.SZ',
            'cyb': '399006.SZ',
            'zxb': '399005.SZ',
            'hs300': '000300.SH',
            'zz500': '000905.SH',
        }
        
        self.default_limit = max(5, min(60, self.config.get('default_limit', 20)))
        chart_style = self.config.get('chart_style', {})
        self.ma_periods = chart_style.get('ma_periods', [5, 10, 20])[:3]
        self.volume_ma_periods = chart_style.get('volume_ma_periods', [5, 10])[:2]
        self.color_style = chart_style.get('color_style', 'red_green')
        self.chart_width = chart_style.get('chart_width', 1200)
        self.chart_height = chart_style.get('chart_height', 800)
        self.show_volume = chart_style.get('show_volume', True)
        self.show_indicators = chart_style.get('show_indicators', True)
        self.enable_auto_correction = self.config.get('enable_auto_correction', True)
        
        features = self.config.get('features', {})
        self.enable_chart_generation = features.get('enable_chart_generation', True)
        self.enable_technical_analysis = features.get('enable_technical_analysis', True)
        
        self.up_color = 'green' if self.color_style == 'green_red' else 'red'
        self.down_color = 'red' if self.color_style == 'green_red' else 'green'
        
        logger.info(f"股票插件初始化完成 - 超时设置: 美股{self.data_source._us_stock_timeout}s/通用{self.data_source._general_timeout}s")

    async def terminate(self):
        """插件停止清理"""
        logger.info("股市行情插件停止")
        if hasattr(self, '_lock'):
            del self._lock
    
    def _validate_stock_code(self, ts_code: str) -> tuple:
        """验证股票代码格式"""
        if re.match(self.stock_code_pattern, ts_code) is not None:
            return True, ts_code
        
        if self.enable_auto_correction:
            corrected = self.data_source._validate_and_correct_stock_code(ts_code)
            if corrected != ts_code and re.match(self.stock_code_pattern, corrected):
                return True, corrected
            
        return False, ts_code

    def plot_stock_chart(self, data: pd.DataFrame, title: str) -> str:
        """绘制K线图"""
        try:
            if not self.enable_chart_generation:
                logger.warning("图表生成功能已禁用")
                return ""
            
            indicators_data = {}
            if self.enable_technical_analysis:
                (dif, dea, macd), (k, d, j) = self.calculate_indicators(data)
                indicators_data = {'dif': dif, 'dea': dea, 'macd': macd, 'k': k, 'd': d, 'j': j}
            
            plt.style.use('dark_background')
            figsize = (self.chart_width / 100, self.chart_height / 100)
            
            num_subplots = 1
            height_ratios = [3]
            
            if self.show_volume:
                num_subplots += 1
                height_ratios.append(1)
            
            if self.enable_technical_analysis and self.show_indicators:
                num_subplots += 2
                height_ratios.extend([1, 1])
            
            fig = plt.figure(figsize=figsize)
            gs = fig.add_gridspec(num_subplots, 1, height_ratios=height_ratios, hspace=0.2)
            axes = [fig.add_subplot(g) for g in gs]
            
            fig.patch.set_facecolor('#1C1C1C')
            fig.suptitle(title, fontproperties=font, fontsize=14, color='white', y=0.98)

            up = data['close'] > data['open']
            down = ~up
            width = 0.8
            
            for ax in axes:
                ax.set_facecolor('#1C1C1C')
                ax.grid(True, alpha=0.2)
                ax.tick_params(axis='y', labelright=True, labelleft=False)
                ax.yaxis.set_label_position('right')
                for spine in ax.spines.values():
                    spine.set_color('#404040')

            ax = axes[0]
            ax.bar(data.index[up], (data['close'] - data['open'])[up], width,
                  bottom=data['open'][up], color=self.up_color, zorder=3)
            ax.bar(data.index[down], (data['close'] - data['open'])[down], width,
                  bottom=data['open'][down], color=self.down_color, zorder=3)
            
            ax.vlines(data.index[up], data['low'][up], data['high'][up],
                     color=self.up_color, linewidth=1, zorder=2)
            ax.vlines(data.index[down], data['low'][down], data['high'][down],
                     color=self.down_color, linewidth=1, zorder=2)

            for period in self.ma_periods:
                ma = data['close'].rolling(window=period).mean()
                ax.plot(data.index, ma, lw=1, label=f'MA{period}')
            
            leg = ax.legend(loc='upper left', fontsize=9,
                          facecolor='#1C1C1C', edgecolor='#404040',
                          framealpha=0.8, bbox_to_anchor=(0.01, 0.99))
            for text in leg.get_texts():
                text.set_color('white')

            ax = axes[1]
            ax.set_title("Volume", fontproperties=font, fontsize=12, color='white', pad=12)
            ax.bar(data.index[up], data['volume'][up], width, color=self.up_color, zorder=3)
            ax.bar(data.index[down], data['volume'][down], width, color=self.down_color, zorder=3)
            
            for period in self.volume_ma_periods:
                vol_ma = data['volume'].rolling(window=period).mean()
                ax.plot(data.index, vol_ma, lw=1, label=f'VOL MA{period}')
            
            if self.volume_ma_periods:
                leg = ax.legend(loc='upper left', fontsize=9,
                            facecolor='#1C1C1C', edgecolor='#404040',
                            framealpha=0.8, bbox_to_anchor=(0.01, 0.99))
                for text in leg.get_texts():
                    text.set_color('white')

            ax = axes[2]
            ax.set_title("MACD(12,26,9)", fontproperties=font, fontsize=12, color='white', pad=12)
            if all(x is not None for x in [dif, dea, macd]):
                ax.bar(data.index, macd, width, color=np.where(macd >= 0, self.up_color, self.down_color))
                ax.plot(data.index, dif, 'white', lw=1, label='DIF')
                ax.plot(data.index, dea, 'yellow', lw=1, label='DEA')
                leg = ax.legend(loc='upper left', fontsize=9,
                            facecolor='#1C1C1C', edgecolor='#404040',
                            framealpha=0.8, bbox_to_anchor=(0.01, 0.99))
                for text in leg.get_texts():
                    text.set_color('white')

            ax = axes[3]
            ax.set_title("KDJ(9,3,3)", fontproperties=font, fontsize=12, color='white', pad=12)
            if all(x is not None for x in [k, d, j]):
                ax.plot(data.index, k, 'white', lw=1, label='K')
                ax.plot(data.index, d, 'yellow', lw=1, label='D')
                ax.plot(data.index, j, 'magenta', lw=1, label='J')
                leg = ax.legend(loc='upper left', fontsize=9,
                            facecolor='#1C1C1C', edgecolor='#404040',
                            framealpha=0.8, bbox_to_anchor=(0.01, 0.99))
                for text in leg.get_texts():
                    text.set_color('white')
            
            for ax in axes[:-1]:
                ax.set_xticks([])
            
            ax = axes[-1]
            x_ticks = range(0, len(data), max(1, len(data)//10))
            ax.set_xticks(x_ticks)
            
            if 'trade_time' in data.columns and not data.empty:
                labels = [data['trade_time'].iloc[x] for x in x_ticks]
            else:
                labels = [data['trade_date'].iloc[x] for x in x_ticks]
            
            ax.set_xticklabels(labels, rotation=30, ha='right')

            plt.subplots_adjust(
                left=0.08, 
                right=0.95, 
                bottom=0.1, 
                top=0.95, 
                hspace=0.2
            )
            
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight', facecolor='#1C1C1C')
            plt.close()

            return temp_file.name

        except Exception as e:
            logger.error(f"绘制K线图异常: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> tuple:
        """计算技术指标"""
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        dif = exp12 - exp26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = (dif - dea) * 2
        k, d, j = calculate_kdj(df)
        return (dif, dea, macd), (k, d, j)
    
    def _is_index_code(self, ts_code: str) -> bool:
        """判断是否为指数代码"""
        return ((ts_code.endswith('.SH') and ts_code.startswith('000')) or 
                (ts_code.endswith('.SZ') and ts_code.startswith('399')))
    
    @filter.command("price")
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
    
    @filter.command("price_now")
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

    @filter.command("price_chart")
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

            async with self._lock:
                chart_file = self.plot_stock_chart(df, title)
                if not chart_file:
                    return event.plain_result("🔧 生成图表失败，请稍后重试")
                
                return event.image_result(chart_file)

        except Exception as e:
            logger.error(f"绘制行情图异常: {e}")
            return event.plain_result("🔧 绘制图表失败，请稍后重试。")

    @filter.command("index")
    async def index_price(self, event: AstrMessageEvent, index_code: str) -> MessageEventResult:
        """查询指数行情"""
        try:
            if index_code.lower() in self.index_map:
                index_code = self.index_map[index_code.lower()]
            elif not self._is_index_code(index_code):
                if re.match(r'^\d{6}$', index_code):
                    if index_code.startswith(('000', '880')):
                        index_code = f"{index_code}.SH"
                    elif index_code.startswith('399'):
                        index_code = f"{index_code}.SZ"
                    else:
                        return event.plain_result(f"⚠️ {index_code} 不是有效的指数代码\n"
                                                "支持的指数：000001.SH(上证指数)、399001.SZ(深证成指)、399006.SZ(创业板指) 等")
                else:
                    return event.plain_result(f"⚠️ {index_code} 不是有效的指数代码\n"
                                            "支持的指数：000001.SH(上证指数)、399001.SZ(深证成指)、399006.SZ(创业板指) 等")
            
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
    
    @filter.command("index_chart")
    async def plot_index(self, event: AstrMessageEvent, index_code: str, limit: int = None, start: str = None, end: str = None) -> MessageEventResult:
        """绘制指数K线图"""
        try:
            if index_code.lower() in self.index_map:
                index_code = self.index_map[index_code.lower()]
            elif not self._is_index_code(index_code):
                if re.match(r'^\d{6}$', index_code):
                    if index_code.startswith(('000', '880')):
                        index_code = f"{index_code}.SH"
                    elif index_code.startswith('399'):
                        index_code = f"{index_code}.SZ"
                    else:
                        return event.plain_result(f"⚠️ {index_code} 不是有效的指数代码\n"
                                                "支持的指数：000001.SH(上证指数)、399001.SZ(深证成指)、399006.SZ(创业板指) 等")
                else:
                    return event.plain_result(f"⚠️ {index_code} 不是有效的指数代码\n"
                                            "支持的指数：000001.SH(上证指数)、399001.SZ(深证成指)、399006.SZ(创业板指) 等")
            
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
            
            async with self._lock:
                chart_file = self.plot_stock_chart(df, title)
                if not chart_file:
                    return event.plain_result("🔧 生成指数图表失败，请稍后重试")
                
                return event.image_result(chart_file)
                
        except Exception as e:
            logger.error(f"绘制指数图异常: {e}")
            return event.plain_result("🔧 绘制指数图表失败，请稍后重试。")
