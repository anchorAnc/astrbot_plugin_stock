"""
图表绘制工具模块
"""
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tempfile
from matplotlib.font_manager import FontProperties
from astrbot.api import logger

matplotlib.use('Agg')

def load_font(font_file="msyh.ttf"):
    """加载指定字体文件"""
    import os
    
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_dir = os.path.dirname(current_dir)
        font_path = os.path.join(plugin_dir, "fonts", font_file)
        
        if os.path.isfile(font_path):
            return FontProperties(fname=font_path)
    except Exception:
        pass
    
    return get_builtin_font()

def get_builtin_font():
    """获取内置字体"""
    import os
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(current_dir)
    fonts_dir = os.path.join(plugin_dir, "fonts")
    
    font_files = ["msyh.ttf", "simsun.ttc", "simkai.ttf"]
    
    for font_file in font_files:
        font_path = os.path.join(fonts_dir, font_file)
        if os.path.isfile(font_path):
            try:
                logger.info(f"使用内置字体: {font_file}")
                return FontProperties(fname=font_path)
            except Exception as e:
                logger.warning(f"加载字体失败 {font_file}: {e}")
                continue
    
    logger.warning("未找到内置字体，使用默认字体")
    return FontProperties()

font = get_builtin_font()

matplotlib.rcParams.update({
    'font.size': 12,
    'axes.titlesize': 14,
    'axes.unicode_minus': False,
    'figure.titlesize': 16,
    'figure.figsize': (12, 8),
})


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


class ChartGenerator:
    """图表生成器"""
    
    def __init__(self, config):
        self.config = config
        chart_style = config.get('chart_style', {})
        self.ma_periods = chart_style.get('ma_periods', [5, 10, 20])[:3]
        self.volume_ma_periods = chart_style.get('volume_ma_periods', [5, 10])[:2]
        self.color_style = chart_style.get('color_style', 'red_green')
        self.chart_width = chart_style.get('chart_width', 1200)
        self.chart_height = chart_style.get('chart_height', 800)
        self.show_volume = chart_style.get('show_volume', True)
        self.show_indicators = chart_style.get('show_indicators', True)
        
        # 从配置读取字体文件
        font_file = chart_style.get('font_file', 'msyh.ttf')
        self.font = load_font(font_file)
        
        features = config.get('features', {})
        self.enable_chart_generation = features.get('enable_chart_generation', True)
        self.enable_technical_analysis = features.get('enable_technical_analysis', True)
        
        self.up_color = 'green' if self.color_style == 'green_red' else 'red'
        self.down_color = 'red' if self.color_style == 'green_red' else 'green'

    def calculate_indicators(self, df: pd.DataFrame) -> tuple:
        """计算技术指标"""
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        dif = exp12 - exp26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = (dif - dea) * 2
        k, d, j = calculate_kdj(df)
        return (dif, dea, macd), (k, d, j)

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
            fig.suptitle(title, fontproperties=self.font, fontsize=14, color='white', y=0.98)

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

            if self.show_volume and len(axes) > 1:
                ax = axes[1]
                ax.set_title("Volume", fontproperties=self.font, fontsize=12, color='white', pad=12)
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

            if self.enable_technical_analysis and self.show_indicators and len(axes) > 2:
                ax = axes[-2]
                ax.set_title("MACD(12,26,9)", fontproperties=self.font, fontsize=12, color='white', pad=12)
                if all(x is not None for x in [dif, dea, macd]):
                    ax.bar(data.index, macd, width, color=np.where(macd >= 0, self.up_color, self.down_color))
                    ax.plot(data.index, dif, 'white', lw=1, label='DIF')
                    ax.plot(data.index, dea, 'yellow', lw=1, label='DEA')
                    leg = ax.legend(loc='upper left', fontsize=9,
                                facecolor='#1C1C1C', edgecolor='#404040',
                                framealpha=0.8, bbox_to_anchor=(0.01, 0.99))
                    for text in leg.get_texts():
                        text.set_color('white')

                ax = axes[-1]
                ax.set_title("KDJ(9,3,3)", fontproperties=self.font, fontsize=12, color='white', pad=12)
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
