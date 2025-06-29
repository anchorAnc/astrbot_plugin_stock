"""AkShare 股票数据源模块"""

import akshare as ak
import pandas as pd
import logging
import re
import asyncio
import signal
import requests
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

class AkStockDataSource:
    """AkShare股票数据源"""
    
    def __init__(self, config: dict = None):
        """初始化数据源"""
        self.config = config or {}
        self._cache = {}
        self._cache_ttl = self.config.get('data_cache_ttl', 60)
        
        data_limits = self.config.get('data_limits', {})
        self._daily_max_records = data_limits.get('daily_max_records', 60)
        self._hourly_max_records = data_limits.get('hourly_max_records', 100)
        self._minutely_max_records = data_limits.get('minutely_max_records', 200)
        self._default_days_back = data_limits.get('default_days_back', 90)
        
        timeout_settings = self.config.get('timeout_settings', {})
        self._us_stock_timeout = timeout_settings.get('us_stock_timeout', 25)
        self._general_timeout = timeout_settings.get('general_timeout', 30)
        self._max_retries = timeout_settings.get('max_retries', 2)
        
        features = self.config.get('features', {})
        self._enable_us_stock = features.get('enable_us_stock', True)
        self._enable_hk_stock = features.get('enable_hk_stock', True)
        self._enable_chart_generation = features.get('enable_chart_generation', True)
        self._enable_technical_analysis = features.get('enable_technical_analysis', True)
        self._enable_crypto = features.get('enable_crypto', True)
        
        # 币安API配置
        crypto_config = self.config.get('crypto', {})
        self._binance_base_url = crypto_config.get('binance_base_url', 'https://api.binance.com')
        self._crypto_timeout = crypto_config.get('crypto_timeout', 15)
        self._default_vs_currency = crypto_config.get('default_vs_currency', 'USDT')
        self._supported_vs_currencies = crypto_config.get('supported_vs_currencies', ['USDT', 'BTC', 'ETH', 'BNB'])
        
        self._enable_auto_correction = self.config.get('enable_auto_correction', True)
        self._executor = ThreadPoolExecutor(max_workers=3)
        
        logger.info(f"数据源初始化完成 - 超时: 美股{self._us_stock_timeout}s/通用{self._general_timeout}s/数字货币{self._crypto_timeout}s")
    
    def _timeout_handler(self, signum, frame):
        """超时处理"""
        raise TimeoutError("操作超时")
        
    async def _fetch_with_timeout(self, func, timeout=10, *args, **kwargs):
        """异步执行函数"""
        loop = asyncio.get_event_loop()
        try:
            def wrapper():
                return func(*args, **kwargs)
            
            future = loop.run_in_executor(self._executor, wrapper)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"函数 {func.__name__} 执行超时 ({timeout}秒)")
            raise TimeoutError(f"操作超时: {timeout}秒")
        except Exception as e:
            logger.error(f"函数 {func.__name__} 执行异常: {e}")
            raise
    
    async def _retry_with_timeout(self, func, max_retries=2, timeout=10, *args, **kwargs):
        """重试机制执行"""
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    await asyncio.sleep(min(2 ** attempt, 5))
                
                result = await self._fetch_with_timeout(func, timeout, *args, **kwargs)
                return result
                
            except (TimeoutError, FutureTimeoutError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt == max_retries:
                    break
                    
            except Exception as e:
                last_exception = e
                if "network" in str(e).lower() or "connection" in str(e).lower():
                    if attempt == max_retries:
                        break
                    continue
                else:
                    raise
        
        logger.error(f"{func.__name__} 重试失败")
        raise last_exception
    
    def _validate_stock_code(self, ts_code: str) -> bool:
        """验证股票代码格式"""
        pattern = r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$"
        if re.match(pattern, ts_code) is not None:
            return True
            
        corrected_code = self._validate_and_correct_stock_code(ts_code)
        return corrected_code != ts_code
    
    def _validate_and_correct_stock_code(self, ts_code: str) -> str:
        """验证并纠正股票代码格式"""
        standard_pattern = r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$"
        if re.match(standard_pattern, ts_code):
            return ts_code
        
        ts_code = ts_code.strip().upper()
        
        if re.match(r"^\d{6}$", ts_code):
            code = ts_code
            if code.startswith(('6', '9', '5')):
                return f"{code}.SH"
            elif code.startswith(('0', '1', '2', '3')):
                return f"{code}.SZ"
                
        sh_sz_pattern = r"^(sh|sz)(\d{6})$"
        match = re.match(sh_sz_pattern, ts_code.lower())
        if match:
            market, code = match.groups()
            return f"{code}.{market.upper()}"
            
        if re.match(r"^\d{6}\.[A-Za-z]{2,3}$", ts_code):
            code, suffix = ts_code.split('.')
            suffix = suffix.upper()
            
            if suffix in ['SHA', 'SHH', 'SS'] or suffix.startswith('SH'):
                return f"{code}.SH"
            elif suffix in ['SZE', 'SZA', 'SZ0'] or suffix.startswith('SZ'):
                return f"{code}.SZ"
                
        if re.match(r"^(sh|sz)\.\d{6}$", ts_code.lower()):
            market, code = ts_code.lower().split('.')
            return f"{code}.{market.upper()}"
            
        hk_pattern1 = r"^hk(\d{1,5})$"
        hk_pattern2 = r"^(\d{1,5})\.hk$"
        
        match1 = re.match(hk_pattern1, ts_code.lower())
        match2 = re.match(hk_pattern2, ts_code.lower())
        
        if match1:
            code = match1.group(1).zfill(5)
            return f"{code}.HK"
        elif match2:
            code = match2.group(1).zfill(5)
            return f"{code}.HK"
            
        us_pattern = r"^us\.([a-zA-Z]{1,5})$"
        match = re.match(us_pattern, ts_code.lower())
        
        if match:
            code = match.group(1).upper()
            return f"{code}.US"
        elif re.match(r"^[a-zA-Z]{1,5}$", ts_code):
            return f"{ts_code}.US"
            
        return ts_code

    async def get_daily(self, ts_code: str, start_date: str = None, end_date: str = None) -> list:
        """获取日K线数据"""
        try:
            corrected_ts_code = self._validate_and_correct_stock_code(ts_code)
            if corrected_ts_code != ts_code:
                logger.warning(f"自动纠正股票代码: {ts_code} -> {corrected_ts_code}")
                ts_code = corrected_ts_code
            elif not re.match(r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$", ts_code):
                logger.error(f"无效的股票代码格式: {ts_code}")
                return []
                
            market_type = "A股"
            if ts_code.endswith('.HK'):
                market_type = "港股"
            elif ts_code.endswith('.US'):
                market_type = "美股"
            elif ts_code.startswith(('1', '5')) and ts_code.endswith('.SH'):
                market_type = "ETF"
            elif ts_code.startswith(('1', '5')) and ts_code.endswith('.SZ'):
                market_type = "ETF"
            elif (ts_code.startswith('000') or ts_code.startswith('399')) and (ts_code.endswith('.SH') or ts_code.endswith('.SZ')):
                market_type = "指数"
            
            stock_code = ts_code.split('.')[0]
            
            if not start_date:
                from datetime import datetime, timedelta
                default_start = (datetime.now() - timedelta(days=self._default_days_back)).strftime('%Y%m%d')
                start_date = default_start
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            
            if market_type == "A股" or market_type == "ETF" or market_type == "指数":
                df = await self._retry_with_timeout(
                    ak.stock_zh_a_hist,
                    max_retries=1,
                    timeout=self._general_timeout,
                    symbol=stock_code, 
                    period="daily", 
                    start_date=start_date, 
                    end_date=end_date,
                    adjust="qfq"
                )
            elif market_type == "港股":
                if not self._enable_hk_stock:
                    logger.warning("港股查询功能已禁用")
                    return []
                df = await self._retry_with_timeout(
                    ak.stock_hk_hist,
                    max_retries=1,
                    timeout=self._general_timeout,
                    symbol=stock_code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
            elif market_type == "美股":
                if not self._enable_us_stock:
                    logger.warning("美股查询功能已禁用")
                    return []
                
                logger.info(f"开始获取美股{stock_code}历史数据")
                
                try:
                    df = None
                    
                    try:
                        logger.info("尝试获取美股代码映射...")
                        realtime_data = await self._retry_with_timeout(
                            ak.stock_us_spot_em,
                            max_retries=1,
                            timeout=12
                        )
                        
                        if realtime_data is not None and not realtime_data.empty and '代码' in realtime_data.columns:
                            us_symbol = stock_code.upper()
                            exact_match = realtime_data[realtime_data['代码'].str.contains(f'{us_symbol}$', na=False, regex=True)]
                            
                            if not exact_match.empty:
                                us_hist_symbol = exact_match.iloc[0]['代码']
                                logger.info(f"找到美股代码映射: {us_symbol} -> {us_hist_symbol}")
                                
                                df = await self._retry_with_timeout(
                                    ak.stock_us_hist,
                                    max_retries=1,
                                    timeout=self._us_stock_timeout,
                                    symbol=us_hist_symbol,
                                    period="daily",
                                    start_date=start_date,
                                    end_date=end_date,
                                    adjust="qfq"
                                )
                                
                                if df is not None and not df.empty:
                                    logger.info(f"通过东财接口成功获取美股{stock_code}历史数据")
                            else:
                                logger.warning(f"未找到美股代码{us_symbol}的映射")
                        
                    except (TimeoutError, FutureTimeoutError, asyncio.TimeoutError):
                        logger.warning(f"美股东财接口超时")
                    except Exception as e:
                        logger.warning(f"美股东财接口失败: {e}")
                    
                    if df is None or df.empty:
                        try:
                            logger.info("尝试新浪美股历史数据接口...")
                            df = await self._retry_with_timeout(
                                ak.stock_us_daily,
                                max_retries=1,
                                timeout=self._us_stock_timeout,
                                symbol=stock_code.upper(),
                                adjust="qfq"
                            )
                            
                            if df is not None and not df.empty:
                                logger.info(f"通过新浪接口成功获取美股{stock_code}历史数据")
                                df = df.rename(columns={
                                    'date': '日期',
                                    'open': '开盘',
                                    'high': '最高', 
                                    'low': '最低',
                                    'close': '收盘',
                                    'volume': '成交量'
                                })
                        except Exception as e:
                            logger.warning(f"新浪美股接口失败: {e}")
                    
                    if df is None or df.empty:
                        logger.warning(f"美股{stock_code}历史数据获取失败")
                        return []
                        
                except Exception as e:
                    logger.error(f"美股历史数据获取异常: {e}")
                    return []
            else:
                logger.error(f"不支持的市场类型: {market_type}")
                return []
                
            if df is None or df.empty:
                logger.warning(f"未获取到{ts_code}的日K线数据")
                return []
                
            result = []
            max_records = self._daily_max_records
            
            df = df.sort_values(df.columns[0], ascending=False)  # 使用第一列作为日期列排序
            df = df.head(max_records)
            df = df.sort_values(df.columns[0], ascending=True)
            
            # 动态识别列名
            date_col = self._find_column(df, ['日期', 'date', 'Date', 'trade_date'])
            open_col = self._find_column(df, ['开盘', 'open', 'Open'])
            high_col = self._find_column(df, ['最高', 'high', 'High'])
            low_col = self._find_column(df, ['最低', 'low', 'Low'])
            close_col = self._find_column(df, ['收盘', 'close', 'Close'])
            volume_col = self._find_column(df, ['成交量', 'volume', 'Volume', 'vol'])
            
            # 如果找不到标准列名，使用索引
            if not date_col and len(df.columns) > 0:
                date_col = df.columns[0]
            if not open_col and len(df.columns) > 1:
                open_col = df.columns[1]
            if not high_col and len(df.columns) > 2:
                high_col = df.columns[2]
            if not low_col and len(df.columns) > 3:
                low_col = df.columns[3]
            if not close_col and len(df.columns) > 4:
                close_col = df.columns[4]
            if not volume_col and len(df.columns) > 5:
                volume_col = df.columns[5]
            
            for _, row in df.iterrows():
                try:
                    # 处理日期
                    if date_col and pd.notna(row[date_col]):
                        if isinstance(row[date_col], str):
                            trade_date = row[date_col].replace('-', '')
                        else:
                            trade_date = row[date_col].strftime('%Y%m%d')
                    else:
                        trade_date = datetime.now().strftime('%Y%m%d')
                    
                    item = {
                        'ts_code': ts_code,
                        'trade_date': trade_date,
                        'open': float(row[open_col]) if open_col and pd.notna(row[open_col]) else 0,
                        'high': float(row[high_col]) if high_col and pd.notna(row[high_col]) else 0,
                        'low': float(row[low_col]) if low_col and pd.notna(row[low_col]) else 0,
                        'close': float(row[close_col]) if close_col and pd.notna(row[close_col]) else 0,
                        'volume': float(row[volume_col]) if volume_col and pd.notna(row[volume_col]) else 0
                    }
                    if len(result) > 0:
                        pre_close = result[-1]['close']
                        item['pre_close'] = pre_close
                        item['change'] = item['close'] - pre_close
                        if pre_close != 0:
                            item['pct_chg'] = (item['change'] / pre_close) * 100
                        else:
                            item['pct_chg'] = 0
                    else:
                        item['pre_close'] = item['close']
                        item['change'] = 0
                        item['pct_chg'] = 0
                        
                    result.append(item)
                except Exception as e:
                    logger.warning(f"处理行数据异常: {e}")
                    continue
                    
            logger.info(f"成功获取{ts_code}的{len(result)}条日K线数据")
            return result
            
        except Exception as e:
            logger.error(f"获取日K线数据异常: {e}")
            return []
    
    async def get_realtime(self, ts_code: str) -> dict:
        """获取实时行情数据"""
        try:
            # 验证并自动纠正股票代码格式
            corrected_ts_code = self._validate_and_correct_stock_code(ts_code)
            if corrected_ts_code != ts_code:
                logger.warning(f"自动纠正股票代码: {ts_code} -> {corrected_ts_code}")
                ts_code = corrected_ts_code
            elif not re.match(r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$", ts_code):
                logger.error(f"无效的股票代码格式: {ts_code}")
                return {}
                
            stock_code = ts_code.split('.')[0]
            
            # 根据市场选择接口
            if ts_code.endswith('.SH') or ts_code.endswith('.SZ'):
                # A股实时行情
                df = ak.stock_zh_a_spot_em()
                match = df[df['代码'] == stock_code]
                
                if match.empty:
                    logger.warning(f"未找到股票代码: {stock_code}")
                    return {}
                
                row = match.iloc[0]
                result = {
                    'ts_code': ts_code,
                    'price': float(row['最新价']),
                    'open': float(row['今开']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'pre_close': float(row['昨收']),
                    'volume': float(row['成交量']),
                    'amount': float(row['成交额']),
                    'time': datetime.now().strftime('%H:%M:%S')
                }
                
            elif ts_code.endswith('.HK'):
                # 港股实时行情
                df = ak.stock_hk_spot_em()
                match = df[df['代码'] == stock_code]
                
                if match.empty:
                    logger.warning(f"未找到港股代码: {stock_code}")
                    return {}
                
                row = match.iloc[0]
                result = {
                    'ts_code': ts_code,
                    'price': float(row['最新价']),
                    'open': float(row['今开']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'pre_close': float(row['昨收']),
                    'volume': float(row['成交量']),
                    'time': datetime.now().strftime('%H:%M:%S')
                }
                
            elif ts_code.endswith('.US'):
                # 美股实时行情 - 使用优化的超时和错误处理
                if not self._enable_us_stock:
                    logger.warning("美股查询功能已禁用")
                    return {'error': '美股查询功能已禁用', 'ts_code': ts_code}
                
                try:
                    df = await self._retry_with_timeout(
                        ak.stock_us_spot_em,
                        max_retries=1,
                        timeout=12
                    )
                    
                    if df is None or df.empty:
                        return {
                            'error': f'美股{stock_code}数据暂时不可用，请稍后重试',
                            'ts_code': ts_code,
                            'suggestion': '美股数据可能因网络问题暂时不可用'
                        }
                    
                    match = None
                    search_code = stock_code.upper()
                    
                    # 尝试精确匹配代码
                    if '代码' in df.columns:
                        match = df[df['代码'].str.contains(f'{search_code}$', na=False, regex=True)]
                    
                    # 如果没找到，尝试名称匹配
                    if (match is None or match.empty) and '名称' in df.columns:
                        match = df[df['名称'].str.contains(search_code, case=False, na=False)]
                    
                    if match is None or match.empty:
                        return {
                            'error': f'未找到美股{stock_code}',
                            'ts_code': ts_code,
                            'suggestion': '请检查代码是否正确，如AAPL、TSLA、MSFT等'
                        }
                    
                    row = match.iloc[0]
                    
                    # 安全地提取数据，处理可能的字段缺失
                    result = {
                        'ts_code': ts_code,
                        'time': datetime.now().strftime('%H:%M:%S')
                    }
                    
                    # 动态映射字段
                    field_mappings = {
                        'price': ['最新价', 'Price', 'price', 'last'],
                        'open': ['开盘价', 'Open', 'open', '今开'],
                        'high': ['最高价', 'High', 'high', '最高'],
                        'low': ['最低价', 'Low', 'low', '最低'], 
                        'pre_close': ['昨收价', 'PreClose', 'pre_close', '昨收'],
                        'volume': ['成交量', 'Volume', 'volume'],
                        'market_cap': ['总市值', 'MarketCap', 'market_cap']
                    }
                    
                    for field, possible_cols in field_mappings.items():
                        found_col = None
                        for col in possible_cols:
                            if col in df.columns:
                                found_col = col
                                break
                        
                        if found_col and pd.notna(row[found_col]):
                            try:
                                value = float(row[found_col])
                                result[field] = value
                            except (ValueError, TypeError):
                                result[field] = 0
                        else:
                            result[field] = 0
                    
                    if '名称' in df.columns and pd.notna(row['名称']):
                        result['name'] = str(row['名称'])
                    
                    logger.info(f"成功获取美股{stock_code}实时数据: ${result.get('price', 0)}")
                    return result
                    
                except (TimeoutError, FutureTimeoutError, asyncio.TimeoutError):
                    logger.warning(f"美股{stock_code}数据获取超时")
                    return {
                        'error': f'美股{stock_code}查询超时，请稍后重试',
                        'ts_code': ts_code,
                        'suggestion': '美股数据接口可能繁忙，请稍后重试'
                    }
                except Exception as us_error:
                    logger.error(f"美股{stock_code}数据获取异常: {us_error}")
                    return {
                        'error': f'美股{stock_code}数据获取失败',
                        'ts_code': ts_code,
                        'suggestion': '请检查代码格式或稍后重试'
                    }
            else:
                return {}
                
            return result
            
        except Exception as e:
            logger.error(f"获取实时行情异常: {e}")
            return {}
    
    async def get_hourly(self, ts_code: str) -> list:
        """获取小时K线数据"""
        try:
            # 验证并自动纠正股票代码格式
            corrected_ts_code = self._validate_and_correct_stock_code(ts_code)
            if corrected_ts_code != ts_code:
                logger.warning(f"自动纠正股票代码: {ts_code} -> {corrected_ts_code}")
                ts_code = corrected_ts_code
            elif not re.match(r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$", ts_code):
                logger.error(f"无效的股票代码格式: {ts_code}")
                return []
                
            stock_code = ts_code.split('.')[0]
            
            if ts_code.endswith('.SH') or ts_code.endswith('.SZ'):
                df = ak.stock_zh_a_hist_min_em(symbol=stock_code, period="60")
            else:
                return []
                
            if df is None or df.empty:
                logger.warning(f"未获取到{ts_code}的小时K线数据")
                return []
                
            result = []
            max_records = self._hourly_max_records
            
            df = df.sort_values('时间', ascending=False)
            df = df.head(max_records)
            df = df.sort_values('时间', ascending=True)
            for _, row in df.iterrows():
                try:
                    # 处理时间格式
                    if isinstance(row['时间'], str):
                        # 如果是字符串，尝试解析
                        try:
                            import pandas as pd
                            time_obj = pd.to_datetime(row['时间'])
                        except:
                            # 如果解析失败，使用当前时间
                            time_obj = datetime.now()
                    else:
                        time_obj = row['时间']
                    
                    item = {
                        'ts_code': ts_code,
                        'trade_date': time_obj.strftime('%Y%m%d'),
                        'trade_time': time_obj.strftime('%Y-%m-%d %H:%M:%S'),
                        'open': float(row['开盘']),
                        'high': float(row['最高']),
                        'low': float(row['最低']),
                        'close': float(row['收盘']),
                        'volume': float(row['成交量'])
                    }
                    result.append(item)
                except Exception as e:
                    logger.warning(f"处理小时K线数据异常: {e}")
                    continue
                    
            return result
            
        except Exception as e:
            logger.error(f"获取小时K线数据异常: {e}")
            return []
    
    async def get_minutely(self, ts_code: str, freq: str = "5min") -> list:
        """获取分钟K线数据"""
        try:
            # 验证并自动纠正股票代码格式
            corrected_ts_code = self._validate_and_correct_stock_code(ts_code)
            if corrected_ts_code != ts_code:
                logger.warning(f"自动纠正股票代码: {ts_code} -> {corrected_ts_code}")
                ts_code = corrected_ts_code
            elif not re.match(r"^(\d{6}\.(SZ|SH)|\d{5}\.HK|[A-Za-z]{1,5}\.US)$", ts_code):
                logger.error(f"无效的股票代码格式: {ts_code}")
                return []
                
            stock_code = ts_code.split('.')[0]
            
            # 频率映射
            freq_map = {
                '5min': '5',
                '15min': '15',
                '30min': '30',
                '60min': '60'
            }
            
            period = freq_map.get(freq, '5')
            
            if ts_code.endswith('.SH') or ts_code.endswith('.SZ'):
                df = ak.stock_zh_a_hist_min_em(symbol=stock_code, period=period)
            else:
                return []
                
            if df is None or df.empty:
                logger.warning(f"未获取到{ts_code}的{freq}分钟K线数据")
                return []
                
            result = []
            max_records = self._minutely_max_records
            
            df = df.sort_values('时间', ascending=False)
            df = df.head(max_records)
            df = df.sort_values('时间', ascending=True)
            for _, row in df.iterrows():
                try:
                    # 处理时间格式
                    if isinstance(row['时间'], str):
                        # 如果是字符串，尝试解析
                        try:
                            import pandas as pd
                            time_obj = pd.to_datetime(row['时间'])
                        except:
                            # 如果解析失败，使用当前时间
                            time_obj = datetime.now()
                    else:
                        time_obj = row['时间']
                    
                    item = {
                        'ts_code': ts_code,
                        'trade_date': time_obj.strftime('%Y%m%d'),
                        'trade_time': time_obj.strftime('%Y-%m-%d %H:%M:%S'),
                        'open': float(row['开盘']),
                        'high': float(row['最高']),
                        'low': float(row['最低']),
                        'close': float(row['收盘']),
                        'volume': float(row['成交量'])
                    }
                    result.append(item)
                except Exception as e:
                    logger.warning(f"处理分钟K线数据异常: {e}")
                    continue
                    
            return result
            
        except Exception as e:
            logger.error(f"获取分钟K线数据异常: {e}")
            return []
    
    async def get_index_realtime(self, index_code: str) -> dict:
        """获取指数实时行情"""
        try:
            try:
                df = ak.stock_zh_index_spot_em()
                
                if index_code.startswith('sh'):
                    query_code = index_code[2:]
                elif index_code.startswith('sz'):
                    query_code = index_code[2:]
                else:
                    query_code = index_code
                
                match = df[df['代码'] == query_code]
                
                if match.empty:
                    return {}
                
                row = match.iloc[0]
                result = {
                    'code': index_code,
                    'name': row['名称'],
                    'price': float(row['最新价']),
                    'open': float(row['今开']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'pre_close': float(row['昨收']),
                    'volume': float(row['成交量']),
                    'amount': float(row['成交额']),
                    'time': datetime.now().strftime('%H:%M:%S')
                }
                
                return result
                
            except Exception as e:
                logger.error(f"获取指数实时行情异常: {e}")
                return {}
                
        except Exception as e:
            logger.error(f"获取指数实时行情异常: {e}")
            return {}
    
    # ======================== 币安API数字货币行情方法 ========================
    
    def _normalize_crypto_symbol(self, symbol: str, vs_currency: str = None) -> str:
        """标准化数字货币交易对符号"""
        if not symbol:
            return ""
            
        symbol = symbol.upper().strip()
        vs_currency = (vs_currency or self._default_vs_currency).upper()
        
        # 如果已包含交易对后缀且不等于单一货币符号，直接返回
        # 避免BTC被误认为是已包含后缀的XXXBTC
        for vs in self._supported_vs_currencies:
            if symbol.endswith(vs) and len(symbol) > len(vs):
                return symbol
        
        # 如果symbol本身就是一个支持的计价货币且不想要自引用，返回原始形式
        if symbol in self._supported_vs_currencies and symbol == vs_currency:
            return symbol  # 比如用户查询USDT价格
            
        # 组合交易对
        return f"{symbol}{vs_currency}"
    
    async def _binance_api_request(self, endpoint: str, params: dict = None) -> dict:
        """发送币安API请求"""
        url = f"{self._binance_base_url}{endpoint}"
        
        def make_request():
            response = requests.get(url, params=params, timeout=self._crypto_timeout)
            response.raise_for_status()
            return response.json()
        
        try:
            result = await self._retry_with_timeout(
                make_request, 
                max_retries=self._max_retries, 
                timeout=self._crypto_timeout
            )
            return result
        except Exception as e:
            logger.error(f"币安API请求失败 {endpoint}: {e}")
            return {}
    
    async def get_crypto_price(self, symbol: str, vs_currency: str = None) -> dict:
        """获取数字货币当前价格"""
        if not self._enable_crypto:
            return {"error": "数字货币功能未启用"}
            
        try:
            trading_pair = self._normalize_crypto_symbol(symbol, vs_currency)
            
            # 获取24小时价格统计
            ticker_data = await self._binance_api_request(
                "/api/v3/ticker/24hr", 
                {"symbol": trading_pair}
            )
            
            if not ticker_data:
                return {"error": f"未找到交易对 {trading_pair}"}
            
            # 格式化返回数据
            current_price = float(ticker_data.get('lastPrice', 0))
            price_change = float(ticker_data.get('priceChange', 0))
            price_change_percent = float(ticker_data.get('priceChangePercent', 0))
            high_24h = float(ticker_data.get('highPrice', 0))
            low_24h = float(ticker_data.get('lowPrice', 0))
            volume_24h = float(ticker_data.get('volume', 0))
            
            result = {
                'symbol': trading_pair,
                'name': symbol.upper(),
                'price': current_price,
                'change': price_change,
                'change_percent': price_change_percent,
                'high_24h': high_24h,
                'low_24h': low_24h,
                'volume_24h': volume_24h,
                'vs_currency': vs_currency or self._default_vs_currency,
                'market_cap': None,  # 币安API不直接提供市值
                'timestamp': datetime.now().isoformat(),
                'source': 'binance'
            }
            
            logger.info(f"获取数字货币价格成功: {trading_pair}")
            return result
            
        except Exception as e:
            logger.error(f"获取数字货币价格异常 {symbol}: {e}")
            return {"error": f"获取{symbol}价格失败: {str(e)}"}
    
    async def get_crypto_list(self, limit: int = 10) -> list:
        """获取热门数字货币列表"""
        if not self._enable_crypto:
            return []
            
        try:
            # 获取24小时行情统计，按交易量排序
            tickers_data = await self._binance_api_request("/api/v3/ticker/24hr")
            
            if not tickers_data:
                return []
            
            # 过滤USDT交易对并按交易量排序
            usdt_pairs = [
                ticker for ticker in tickers_data 
                if ticker['symbol'].endswith('USDT') and float(ticker['quoteVolume']) > 0
            ]
            
            # 按交易量排序
            usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
            
            result = []
            for ticker in usdt_pairs[:limit]:
                symbol = ticker['symbol']
                base_asset = symbol.replace('USDT', '')
                
                crypto_info = {
                    'symbol': symbol,
                    'name': base_asset,
                    'price': float(ticker['lastPrice']),
                    'change_percent': float(ticker['priceChangePercent']),
                    'volume_24h': float(ticker['volume']),
                    'quote_volume_24h': float(ticker['quoteVolume']),
                    'vs_currency': 'USDT'
                }
                result.append(crypto_info)
            
            logger.info(f"获取热门数字货币列表成功: {len(result)}个")
            return result
            
        except Exception as e:
            logger.error(f"获取数字货币列表异常: {e}")
            return []
    
    async def get_exchange_info(self) -> dict:
        """获取币安交易所信息和支持的交易对"""
        if not self._enable_crypto:
            return {}
            
        try:
            exchange_info = await self._binance_api_request("/api/v3/exchangeInfo")
            
            if not exchange_info:
                return {}
            
            # 提取活跃的USDT交易对
            active_usdt_pairs = []
            for symbol_info in exchange_info.get('symbols', []):
                if (symbol_info.get('status') == 'TRADING' and 
                    symbol_info.get('symbol', '').endswith('USDT')):
                    active_usdt_pairs.append({
                        'symbol': symbol_info['symbol'],
                        'base_asset': symbol_info['baseAsset'],
                        'quote_asset': symbol_info['quoteAsset'],
                        'status': symbol_info['status']
                    })
            
            result = {
                'exchange': 'Binance',
                'server_time': exchange_info.get('serverTime'),
                'active_usdt_pairs_count': len(active_usdt_pairs),
                'total_symbols': len(exchange_info.get('symbols', [])),
                'supported_intervals': ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'],
                'sample_pairs': active_usdt_pairs[:20]  # 返回前20个作为示例
            }
            
            logger.info(f"获取交易所信息成功: {len(active_usdt_pairs)}个USDT交易对")
            return result
            
        except Exception as e:
            logger.error(f"获取交易所信息异常: {e}")
            return {}
    
    async def get_crypto_klines(self, symbol: str, interval: str = "1d", limit: int = 100, vs_currency: str = None) -> list:
        """获取数字货币K线历史数据"""
        if not self._enable_crypto:
            return []
            
        try:
            trading_pair = self._normalize_crypto_symbol(symbol, vs_currency)
            
            # 币安支持的K线周期映射
            interval_map = {
                '1min': '1m', '5min': '5m', '15min': '15m', '30min': '30m', 
                '60min': '1h', 'hourly': '1h', '4hour': '4h', 
                'daily': '1d', '1day': '1d', 'weekly': '1w', 'monthly': '1M'
            }
            
            binance_interval = interval_map.get(interval, interval)
            if binance_interval not in ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']:
                logger.warning(f"不支持的K线周期: {interval}, 使用默认1d")
                binance_interval = '1d'
            
            # 限制数据量
            limit = max(5, min(500, limit))
            
            params = {
                'symbol': trading_pair,
                'interval': binance_interval,
                'limit': limit
            }
            
            klines_data = await self._binance_api_request("/api/v3/klines", params)
            
            if not klines_data:
                return []
            
            # 转换为标准格式
            result = []
            for kline in klines_data:
                try:
                    # 币安K线数据格式: [timestamp, open, high, low, close, volume, close_time, quote_volume, ...]
                    timestamp = int(kline[0])
                    date_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y%m%d')
                    time_str = datetime.fromtimestamp(timestamp / 1000).strftime('%H:%M:%S')
                    
                    kline_data = {
                        'trade_date': date_str,
                        'trade_time': time_str,
                        'open': float(kline[1]),
                        'high': float(kline[2]),
                        'low': float(kline[3]),
                        'close': float(kline[4]),
                        'volume': float(kline[5]),
                        'amount': float(kline[7]),  # quote_volume
                        'timestamp': timestamp
                    }
                    
                    # 计算涨跌
                    if len(result) > 0:
                        prev_close = result[-1]['close']
                        kline_data['change'] = kline_data['close'] - prev_close
                        kline_data['pct_chg'] = (kline_data['change'] / prev_close) * 100 if prev_close else 0
                    else:
                        kline_data['change'] = 0
                        kline_data['pct_chg'] = 0
                    
                    result.append(kline_data)
                    
                except (IndexError, ValueError, TypeError) as e:
                    logger.warning(f"解析K线数据异常: {e}")
                    continue
            
            # 按时间排序 (最新的在前)
            result.reverse()
            
            logger.info(f"获取数字货币K线数据成功: {trading_pair} {binance_interval} {len(result)}条")
            return result
            
        except Exception as e:
            logger.error(f"获取数字货币K线数据异常 {symbol}: {e}")
            return []
    
    async def get_crypto_daily(self, symbol: str, limit: int = 100, vs_currency: str = None) -> list:
        """获取数字货币日K线数据"""
        return await self.get_crypto_klines(symbol, 'daily', limit, vs_currency)
    
    async def get_crypto_hourly(self, symbol: str, limit: int = 48, vs_currency: str = None) -> list:
        """获取数字货币小时K线数据"""
        return await self.get_crypto_klines(symbol, 'hourly', limit, vs_currency)
    
    async def get_crypto_minutely(self, symbol: str, interval: str = '15min', limit: int = 96, vs_currency: str = None) -> list:
        """获取数字货币分钟K线数据"""
        valid_intervals = ['1min', '5min', '15min', '30min', '60min']
        if interval not in valid_intervals:
            interval = '15min'
        return await self.get_crypto_klines(symbol, interval, limit, vs_currency)
    
    def _find_column(self, df: pd.DataFrame, possible_names: list) -> str:
        """在DataFrame中查找可能的列名"""
        for name in possible_names:
            if name in df.columns:
                return name
        return None
