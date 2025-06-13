#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VWAP分时均线测试模块

本模块实现了成交量加权平均价格(VWAP)的计算和测试功能，
用于量化交易策略中的分时均线判断。

VWAP计算公式：
VWAP = Σ(价格 × 成交量) / Σ(成交量)

作者: AI Assistant
创建时间: 2024
"""

import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from xtquant import xtdata
    from logger import get_logger
    from data_manager import get_data_manager
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)

# 获取logger
logger = get_logger("vwap_test")

class VWAPCalculator:
    """
    VWAP(成交量加权平均价格)计算器
    
    主要功能：
    1. 计算实时VWAP
    2. 计算分时VWAP均线
    3. 提供策略判断依据
    """
    
    def __init__(self):
        """初始化VWAP计算器"""
        self.data_manager = get_data_manager()
        self.vwap_cache = {}  # 缓存VWAP数据
        
    def calculate_vwap_from_tick(self, stock_code, start_time=None, end_time=None):
        """
        从tick数据计算VWAP
        
        参数:
        stock_code (str): 股票代码，如 '000001.SZ'
        start_time (str): 开始时间，格式 'YYYYMMDDHHMMSS'
        end_time (str): 结束时间，格式 'YYYYMMDDHHMMSS'
        
        返回:
        dict: 包含VWAP数据的字典
        """
        try:
            logger.info(f"开始计算 {stock_code} 的VWAP数据")
            
            # 如果没有指定时间，使用当日数据
            if not start_time:
                today = datetime.now().strftime('%Y%m%d')
                start_time = today + '093000'  # 开盘时间
            
            if not end_time:
                end_time = datetime.now().strftime('%Y%m%d%H%M%S')
            
            logger.info(f"尝试下载 {stock_code} 的tick历史数据")
            # 先下载历史数据到本地缓存
            try:
                xtdata.download_history_data(
                    stock_code=stock_code,
                    period='tick',
                    start_time=start_time,
                    end_time=end_time
                )
                logger.info(f"成功下载 {stock_code} 的tick历史数据")
            except Exception as download_error:
                logger.warning(f"下载tick数据失败: {str(download_error)}，尝试使用现有数据")
            
            # 获取tick数据
            tick_data = xtdata.get_market_data(
                field_list=['time', 'lastPrice', 'volume', 'amount'],
                stock_list=[stock_code],
                period='tick',
                start_time=start_time,
                end_time=end_time
            )
            
            if not tick_data or stock_code not in tick_data:
                logger.warning(f"未获取到 {stock_code} 的tick数据")
                return None
            
            # 处理tick数据
            stock_tick_data = tick_data[stock_code]
            if len(stock_tick_data) == 0:
                logger.warning(f"{stock_code} 的tick数据为空")
                return None
            
            # 转换为DataFrame
            df = pd.DataFrame(stock_tick_data)
            
            # 计算VWAP
            vwap_result = self._calculate_vwap_from_dataframe(df)
            
            logger.info(f"成功计算 {stock_code} 的VWAP，共 {len(df)} 条tick数据")
            return vwap_result
            
        except Exception as e:
            logger.error(f"计算 {stock_code} VWAP时出错: {str(e)}")
            return None
    
    def calculate_vwap_from_minute_data(self, stock_code, start_time=None, end_time=None, period='1m'):
        """
        从分钟数据计算VWAP
        
        参数:
        stock_code (str): 股票代码
        start_time (str): 开始时间
        end_time (str): 结束时间
        period (str): 数据周期，如 '1m', '5m'
        
        返回:
        dict: VWAP计算结果
        """
        try:
            logger.info(f"开始从{period}数据计算 {stock_code} 的VWAP")
            
            # 设置默认时间
            if not start_time:
                today = datetime.now().strftime('%Y%m%d')
                start_time = today + '093000'
            
            if not end_time:
                end_time = datetime.now().strftime('%Y%m%d%H%M%S')
            
            logger.info(f"尝试下载 {stock_code} 的{period}历史数据")
            # 先下载历史数据到本地缓存
            try:
                xtdata.download_history_data(
                    stock_code=stock_code,
                    period=period,
                    start_time=start_time,
                    end_time=end_time
                )
                logger.info(f"成功下载 {stock_code} 的{period}历史数据")
            except Exception as download_error:
                logger.warning(f"下载{period}数据失败: {str(download_error)}，尝试使用现有数据")
            
            # 获取分钟数据
            minute_data = xtdata.get_market_data(
                field_list=['time', 'open', 'high', 'low', 'close', 'volume', 'amount'],
                stock_list=[stock_code],
                period=period,
                start_time=start_time,
                end_time=end_time
            )
            
            if not minute_data or 'close' not in minute_data:
                logger.warning(f"未获取到 {stock_code} 的{period}数据")
                return None
            
            # 获取数据
            close_data = minute_data['close']
            volume_data = minute_data['volume']
            amount_data = minute_data['amount']
            time_data = minute_data['time'] if 'time' in minute_data else None
            
            if stock_code not in close_data.index:
                logger.warning(f"{stock_code} 不在数据索引中")
                return None
            
            # 构建DataFrame
            df_data = {
                'close': close_data.loc[stock_code],
                'volume': volume_data.loc[stock_code],
                'amount': amount_data.loc[stock_code]
            }
            
            if time_data is not None:
                df_data['time'] = time_data.columns
            
            df = pd.DataFrame(df_data)
            
            # 过滤无效数据
            df = df.dropna()
            df = df[df['volume'] > 0]
            
            if len(df) == 0:
                logger.warning(f"{stock_code} 没有有效的{period}数据")
                return None
            
            # 计算VWAP
            vwap_result = self._calculate_vwap_from_dataframe(df)
            
            logger.info(f"成功从{period}数据计算 {stock_code} 的VWAP，共 {len(df)} 条数据")
            return vwap_result
            
        except Exception as e:
            logger.error(f"从{period}数据计算 {stock_code} VWAP时出错: {str(e)}")
            return None
    
    def _calculate_vwap_from_dataframe(self, df):
        """
        从DataFrame计算VWAP
        
        参数:
        df (pandas.DataFrame): 包含价格和成交量数据的DataFrame
        
        返回:
        dict: VWAP计算结果
        """
        try:
            # 确定价格列
            price_col = None
            if 'lastPrice' in df.columns:
                price_col = 'lastPrice'
            elif 'close' in df.columns:
                price_col = 'close'
            else:
                logger.error("DataFrame中没有找到价格列")
                return None
            
            # 检查必要的列
            if 'volume' not in df.columns:
                logger.error("DataFrame中没有找到成交量列")
                return None
            
            # 过滤无效数据
            df = df.copy()
            df = df.dropna(subset=[price_col, 'volume'])
            df = df[df['volume'] > 0]
            df = df[df[price_col] > 0]
            
            if len(df) == 0:
                logger.warning("没有有效的价格和成交量数据")
                return None
            
            # 计算累积成交量和累积成交额
            df['cumulative_volume'] = df['volume'].cumsum()
            df['cumulative_amount'] = (df[price_col] * df['volume']).cumsum()
            
            # 计算VWAP
            df['vwap'] = df['cumulative_amount'] / df['cumulative_volume']
            
            # 计算当前VWAP
            current_vwap = df['vwap'].iloc[-1]
            
            # 计算VWAP相关统计信息
            total_volume = df['volume'].sum()
            total_amount = (df[price_col] * df['volume']).sum()
            avg_price = df[price_col].mean()
            current_price = df[price_col].iloc[-1]
            
            # 计算价格相对VWAP的偏离度
            price_deviation = (current_price - current_vwap) / current_vwap * 100
            
            result = {
                'current_vwap': round(current_vwap, 3),
                'current_price': round(current_price, 3),
                'price_deviation_pct': round(price_deviation, 2),
                'total_volume': int(total_volume),
                'total_amount': round(total_amount, 2),
                'avg_price': round(avg_price, 3),
                'data_points': len(df),
                'vwap_series': df['vwap'].round(3).tolist(),
                'time_series': df.get('time', df.index).tolist(),
                'price_series': df[price_col].round(3).tolist(),
                'volume_series': df['volume'].tolist()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"计算VWAP时出错: {str(e)}")
            return None
    
    def get_current_vwap(self, stock_code):
        """
        获取当前实时VWAP
        
        参数:
        stock_code (str): 股票代码
        
        返回:
        float: 当前VWAP值
        """
        try:
            # 先尝试从tick数据计算
            vwap_result = self.calculate_vwap_from_tick(stock_code)
            
            if vwap_result and 'current_vwap' in vwap_result:
                return vwap_result['current_vwap']
            
            # 如果tick数据不可用，尝试从1分钟数据计算
            vwap_result = self.calculate_vwap_from_minute_data(stock_code, period='1m')
            
            if vwap_result and 'current_vwap' in vwap_result:
                return vwap_result['current_vwap']
            
            logger.warning(f"无法获取 {stock_code} 的当前VWAP")
            return None
            
        except Exception as e:
            logger.error(f"获取 {stock_code} 当前VWAP时出错: {str(e)}")
            return None
    
    def analyze_vwap_strategy(self, stock_code, vwap_result=None):
        """
        基于VWAP进行策略分析
        
        参数:
        stock_code (str): 股票代码
        vwap_result (dict): VWAP计算结果，如果为None则重新计算
        
        返回:
        dict: 策略分析结果
        """
        try:
            if vwap_result is None:
                vwap_result = self.calculate_vwap_from_minute_data(stock_code)
            
            if not vwap_result:
                return None
            
            current_price = vwap_result['current_price']
            current_vwap = vwap_result['current_vwap']
            price_deviation = vwap_result['price_deviation_pct']
            
            # 策略判断逻辑
            strategy_signal = 'HOLD'  # 默认持有
            signal_strength = 0  # 信号强度 -100到100
            
            # 基于价格相对VWAP的位置判断（使用比例阈值）
            # 计算相对偏离度的绝对值
            abs_deviation = abs(price_deviation)
            
            # 动态阈值：基于股价波动性调整
            # 对于高价股，使用较小的比例阈值；对于低价股，使用较大的比例阈值
            base_threshold = 1.0  # 基础阈值1%
            strong_threshold = 2.5  # 强信号阈值2.5%
            
            # 根据当前价格调整阈值（价格越高，阈值越小）
            if current_price > 50:
                threshold_multiplier = 0.8
            elif current_price > 20:
                threshold_multiplier = 1.0
            elif current_price > 10:
                threshold_multiplier = 1.2
            else:
                threshold_multiplier = 1.5
            
            adjusted_base_threshold = base_threshold * threshold_multiplier
            adjusted_strong_threshold = strong_threshold * threshold_multiplier
            
            if price_deviation > adjusted_strong_threshold:  # 价格显著高于VWAP
                strategy_signal = 'STRONG_SELL'
                signal_strength = min(-60, -30 * (abs_deviation / adjusted_strong_threshold))
            elif price_deviation > adjusted_base_threshold:  # 价格适度高于VWAP
                strategy_signal = 'SELL'
                signal_strength = min(-30, -20 * (abs_deviation / adjusted_base_threshold))
            elif price_deviation < -adjusted_strong_threshold:  # 价格显著低于VWAP
                strategy_signal = 'STRONG_BUY'
                signal_strength = min(60, 30 * (abs_deviation / adjusted_strong_threshold))
            elif price_deviation < -adjusted_base_threshold:  # 价格适度低于VWAP
                strategy_signal = 'BUY'
                signal_strength = min(30, 20 * (abs_deviation / adjusted_base_threshold))
            else:  # 价格接近VWAP
                strategy_signal = 'HOLD'
                signal_strength = 0
            
            # 获取最新tick数据进行补充分析
            try:
                tick_data = xtdata.get_full_tick([stock_code])
                if tick_data and stock_code in tick_data:
                    tick = tick_data[stock_code]
                    bid_price = tick.get('bidPrice', [0])[0] if isinstance(tick, dict) else getattr(tick, 'bidPrice', [0])[0]
                    ask_price = tick.get('askPrice', [0])[0] if isinstance(tick, dict) else getattr(tick, 'askPrice', [0])[0]
                    
                    # 计算买卖价差
                    if bid_price > 0 and ask_price > 0:
                        spread = (ask_price - bid_price) / current_price * 100
                        spread_info = f"买卖价差: {spread:.2f}%"
                    else:
                        spread_info = "买卖价差: 无数据"
                else:
                    spread_info = "买卖价差: 无数据"
            except:
                spread_info = "买卖价差: 获取失败"
            
            analysis_result = {
                'stock_code': stock_code,
                'current_price': current_price,
                'current_vwap': current_vwap,
                'price_deviation_pct': price_deviation,
                'strategy_signal': strategy_signal,
                'signal_strength': signal_strength,
                'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'spread_info': spread_info,
                'recommendation': self._get_strategy_recommendation(strategy_signal, price_deviation),
                'thresholds': {
                    'base_threshold': adjusted_base_threshold,
                    'strong_threshold': adjusted_strong_threshold,
                    'threshold_multiplier': threshold_multiplier
                }
            }
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"分析 {stock_code} VWAP策略时出错: {str(e)}")
            return None
    
    def get_intraday_vwap_line(self, stock_code, start_time=None, end_time=None):
        """
        获取分时图中的分时均线（VWAP）
        这是主流股票软件（同花顺、通达信等）中黄线的计算方法
        
        参数:
        stock_code (str): 股票代码
        start_time (str): 开始时间，默认为当日开盘
        end_time (str): 结束时间，默认为当前时间
        
        返回:
        dict: 分时均线数据和分析结果
        """
        try:
            # 使用1分钟数据计算分时均线，这是最接近分时图的方法
            vwap_result = self.calculate_vwap_from_minute_data(
                stock_code=stock_code,
                start_time=start_time,
                end_time=end_time,
                period='1m'
            )
            
            if not vwap_result:
                return None
            
            # 获取当前价格（最新收盘价）
            current_price = vwap_result['price_series'][-1] if vwap_result['price_series'] else None
            current_vwap = vwap_result['current_vwap']
            
            # 分析价格与均线关系
            analysis = self.analyze_price_vs_vwap(current_price, current_vwap)
            
            result = {
                 'stock_code': stock_code,
                 'intraday_vwap_line': vwap_result['vwap_series'],
                 'price_line': vwap_result['price_series'],
                 'time_series': vwap_result['time_series'],
                 'current_price': current_price,
                 'current_vwap': current_vwap,
                 'price_analysis': analysis,
                 'data_count': vwap_result['data_points']
             }
            
            logger.info(f"成功获取 {stock_code} 的分时均线，当前价格: {current_price}, 分时均线: {current_vwap:.4f}")
            logger.info(f"价格位置: {analysis.get('position', 'unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"获取 {stock_code} 分时均线时出错: {str(e)}")
            return None
    
    def analyze_price_vs_vwap(self, current_price, vwap_value, threshold=0.01):
        """
        分析当前价格与VWAP的关系
        
        参数:
        current_price (float): 当前价格
        vwap_value (float): VWAP值
        threshold (float): 判断阈值，默认1%
        
        返回:
        dict: 分析结果
        """
        if not current_price or not vwap_value:
            return {'status': 'error', 'message': '价格或VWAP值无效'}
        
        # 计算偏离度
        deviation = (current_price - vwap_value) / vwap_value
        deviation_percent = deviation * 100
        
        # 判断位置关系
        if abs(deviation) <= threshold:
            position = '接近均线'
            signal = 'neutral'
        elif deviation > threshold:
            position = '均线之上'
            signal = 'bullish'
        else:
            position = '跌破均线'
            signal = 'bearish'
        
        return {
            'current_price': current_price,
            'vwap_value': vwap_value,
            'deviation': deviation,
            'deviation_percent': round(deviation_percent, 2),
            'position': position,
            'signal': signal,
            'threshold_percent': threshold * 100
        }
    
    def _get_strategy_recommendation(self, signal, deviation):
        """
        获取策略建议
        
        参数:
        signal (str): 策略信号
        deviation (float): 价格偏离度
        
        返回:
        str: 策略建议
        """
        recommendations = {
            'STRONG_BUY': f"强烈建议买入：当前价格比VWAP低{abs(deviation):.1f}%，可能存在超卖机会",
            'BUY': f"建议买入：当前价格比VWAP低{abs(deviation):.1f}%，价格相对便宜",
            'HOLD': f"建议持有：当前价格接近VWAP（偏离{deviation:.1f}%），价格相对合理",
            'SELL': f"建议卖出：当前价格比VWAP高{deviation:.1f}%，价格相对偏高",
            'STRONG_SELL': f"强烈建议卖出：当前价格比VWAP高{deviation:.1f}%，可能存在超买风险"
        }
        
        return recommendations.get(signal, "无明确建议")


def test_vwap_functionality():
    """
    测试VWAP功能
    """
    logger.info("=== 开始VWAP功能测试 ===")
    
    # 测试股票列表
    test_stocks = [
        '000001.SZ',  # 平安银行
        '000002.SZ',  # 万科A
        '600000.SH',  # 浦发银行
        '600036.SH',  # 招商银行
    ]
    
    # 创建VWAP计算器
    vwap_calc = VWAPCalculator()
    
    for stock_code in test_stocks:
        logger.info(f"\n--- 测试股票: {stock_code} ---")
        
        try:
            # 测试分时均线获取（主要功能）
            logger.info("1. 测试分时均线获取")
            intraday_result = vwap_calc.get_intraday_vwap_line(stock_code)
            
            if intraday_result:
                logger.info(f"✓ {stock_code} 分时均线获取成功")
                logger.info(f"  当前价格: {intraday_result['current_price']:.4f}")
                logger.info(f"  分时均线: {intraday_result['current_vwap']:.4f}")
                logger.info(f"  价格位置: {intraday_result['price_analysis']['position']}")
                logger.info(f"  偏离度: {intraday_result['price_analysis']['deviation_percent']:.2f}%")
                logger.info(f"  数据点数: {intraday_result['data_count']}")
            else:
                logger.warning(f"✗ {stock_code} 分时均线获取失败")
                continue
            
            # 测试从分钟数据计算VWAP
            logger.info("2. 测试从1分钟数据计算VWAP")
            vwap_result = vwap_calc.calculate_vwap_from_minute_data(stock_code, period='1m')
            
            if vwap_result:
                logger.info(f"✓ VWAP计算成功")
                logger.info(f"  当前VWAP: {vwap_result['current_vwap']}")
                logger.info(f"  当前价格: {vwap_result['current_price']}")
                logger.info(f"  价格偏离: {vwap_result['price_deviation_pct']}%")
                logger.info(f"  总成交量: {vwap_result['total_volume']}")
                logger.info(f"  数据点数: {vwap_result['data_points']}")
            else:
                logger.warning(f"✗ {stock_code} VWAP计算失败")
                continue
            
            # 测试策略分析
            logger.info("3. 测试VWAP策略分析")
            strategy_result = vwap_calc.analyze_vwap_strategy(stock_code, vwap_result)
            
            if strategy_result:
                logger.info(f"✓ 策略分析成功")
                logger.info(f"  策略信号: {strategy_result['strategy_signal']}")
                logger.info(f"  信号强度: {strategy_result['signal_strength']}")
                logger.info(f"  策略建议: {strategy_result['recommendation']}")
                logger.info(f"  {strategy_result['spread_info']}")
            else:
                logger.warning(f"✗ {stock_code} 策略分析失败")
            
            # 测试获取当前VWAP
            logger.info("4. 测试获取当前VWAP")
            current_vwap = vwap_calc.get_current_vwap(stock_code)
            
            if current_vwap:
                logger.info(f"✓ 当前VWAP获取成功: {current_vwap}")
            else:
                logger.warning(f"✗ {stock_code} 当前VWAP获取失败")
            
            # 短暂延迟，避免请求过于频繁
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"测试 {stock_code} 时出错: {str(e)}")
            continue
    
    logger.info("\n=== VWAP功能测试完成 ===")


def test_vwap_with_tick_data():
    """
    测试使用tick数据计算VWAP
    """
    logger.info("=== 开始tick数据VWAP测试 ===")
    
    test_stock = '000001.SZ'  # 平安银行
    vwap_calc = VWAPCalculator()
    
    try:
        # 测试从tick数据计算VWAP
        logger.info(f"测试从tick数据计算 {test_stock} 的VWAP")
        
        # 设置时间范围（最近30分钟）
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=30)
        
        start_time_str = start_time.strftime('%Y%m%d%H%M%S')
        end_time_str = end_time.strftime('%Y%m%d%H%M%S')
        
        vwap_result = vwap_calc.calculate_vwap_from_tick(
            test_stock, 
            start_time=start_time_str, 
            end_time=end_time_str
        )
        
        if vwap_result:
            logger.info(f"✓ tick数据VWAP计算成功")
            logger.info(f"  时间范围: {start_time_str} - {end_time_str}")
            logger.info(f"  当前VWAP: {vwap_result['current_vwap']}")
            logger.info(f"  当前价格: {vwap_result['current_price']}")
            logger.info(f"  价格偏离: {vwap_result['price_deviation_pct']}%")
            logger.info(f"  tick数据点: {vwap_result['data_points']}")
            
            # 显示VWAP趋势（最后10个点）
            if len(vwap_result['vwap_series']) >= 10:
                recent_vwap = vwap_result['vwap_series'][-10:]
                logger.info(f"  最近10个VWAP值: {recent_vwap}")
        else:
            logger.warning(f"✗ {test_stock} tick数据VWAP计算失败")
            
    except Exception as e:
        logger.error(f"tick数据VWAP测试时出错: {str(e)}")
    
    logger.info("=== tick数据VWAP测试完成 ===")


def test_intraday_vwap_line():
    """
    测试分时均线功能（主要功能）
    """
    logger.info("=== 开始分时均线测试 ===")
    
    vwap_calc = VWAPCalculator()
    test_stocks = ['000001.SZ', '600000.SH']
    
    for test_stock in test_stocks:
        logger.info(f"\n测试获取 {test_stock} 的分时均线")
        
        # 获取分时均线
        intraday_result = vwap_calc.get_intraday_vwap_line(test_stock)
        
        if intraday_result:
            logger.info(f"✓ {test_stock} 分时均线获取成功")
            logger.info(f"  股票代码: {intraday_result['stock_code']}")
            logger.info(f"  当前价格: {intraday_result['current_price']:.4f}")
            logger.info(f"  分时均线: {intraday_result['current_vwap']:.4f}")
            
            analysis = intraday_result['price_analysis']
            logger.info(f"  价格位置: {analysis['position']}")
            logger.info(f"  交易信号: {analysis['signal']}")
            logger.info(f"  偏离度: {analysis['deviation_percent']:.2f}%")
            logger.info(f"  数据点数: {intraday_result['data_count']}")
            
            # 显示最近几个VWAP值
            if len(intraday_result['intraday_vwap_line']) >= 5:
                recent_vwap = intraday_result['intraday_vwap_line'][-5:]
                logger.info(f"  最近5个VWAP值: {[f'{v:.4f}' for v in recent_vwap]}")
        else:
            logger.warning(f"✗ {test_stock} 分时均线获取失败")
    
    logger.info("=== 分时均线测试完成 ===")


def main():
    """
    主函数
    """
    logger.info("启动VWAP分时均线测试程序")
    
    try:
        # 初始化xtdata连接
        logger.info("初始化xtdata连接...")
        xtdata.connect()
        
        # 等待连接建立
        time.sleep(2)
        
        # 运行分时均线测试（主要功能）
        test_intraday_vwap_line()
        
        # 运行基本VWAP功能测试
        test_vwap_functionality()
        
        # 运行tick数据VWAP测试
        test_vwap_with_tick_data()
        
        logger.info("\n=== 所有测试完成 ===")
        
    except KeyboardInterrupt:
        logger.info("用户中断测试")
    except Exception as e:
        logger.error(f"测试过程中出错: {str(e)}")
    finally:
        logger.info("测试程序结束")


if __name__ == "__main__":
    main()