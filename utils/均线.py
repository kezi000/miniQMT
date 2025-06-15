# -*- coding: utf-8 -*-
"""
均线策略模块
基于miniQMT框架的智能均线交易系统

功能模块:
1. 行情数据获取与均线计算
2. 价格-均线关系动态分析
3. 交易决策辅助策略
4. 风险控制模块

作者: AI Assistant
创建时间: 2024
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# 导入项目模块
try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_manager import get_data_manager
    from logger import get_logger
    import config
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在miniQMT项目根目录下运行")

# 获取logger
logger = get_logger("moving_average_strategy")

class MovingAverageSystem:
    """
    均线交易系统核心类
    
    功能:
    - 多周期均线计算
    - 价格与均线关系分析
    - 交易信号生成
    - 风险控制
    """
    
    def __init__(self, stock_code: str = "000001.SZ"):
        """
        初始化均线系统
        
        参数:
        stock_code (str): 股票代码，默认为平安银行
        """
        self.stock_code = stock_code
        self.data = None  # 存储行情数据
        self.ma_periods = [5, 10, 20, 30, 60, 120, 250]  # 均线周期
        
        # 初始化数据管理器
        try:
            self.data_manager = get_data_manager()
            logger.info(f"均线系统初始化成功，股票代码: {stock_code}")
        except Exception as e:
            logger.error(f"初始化数据管理器失败: {e}")
            self.data_manager = None
    
    def fetch_data(self, period: str = '1d', count: int = 300) -> pd.DataFrame:
        """
        获取股票历史数据
        
        参数:
        period (str): K线周期，默认日线
        count (int): 获取数据条数
        
        返回:
        pd.DataFrame: 包含OHLCV数据的DataFrame
        """
        try:
            if self.data_manager is None:
                logger.error("数据管理器未初始化")
                return pd.DataFrame()
            
            # 使用项目的数据管理器获取数据
            df = self.data_manager.get_market_data(
                stock_code=self.stock_code,
                period=period,
                count=count
            )
            
            if df is None or df.empty:
                logger.warning(f"未获取到 {self.stock_code} 的数据")
                return pd.DataFrame()
            
            # 数据预处理
            df = self._process_data(df)
            self.data = df
            
            logger.info(f"成功获取 {self.stock_code} 数据，共 {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            return pd.DataFrame()
    
    def _process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据预处理
        
        参数:
        df (pd.DataFrame): 原始数据
        
        返回:
        pd.DataFrame: 处理后的数据
        """
        try:
            # 确保必要的列存在
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    logger.error(f"缺少必要列: {col}")
                    return pd.DataFrame()
            
            # 按时间排序
            if 'date' in df.columns:
                df = df.sort_values('date')
            elif df.index.name == 'date' or 'time' in str(df.index.name).lower():
                df = df.sort_index()
            
            # 计算收益率
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
            
            # 去除NaN值
            df = df.dropna()
            
            return df
            
        except Exception as e:
            logger.error(f"数据预处理失败: {e}")
            return pd.DataFrame()
    
    def calculate_moving_averages(self) -> pd.DataFrame:
        """
        计算多周期均线
        
        返回:
        pd.DataFrame: 包含均线数据的DataFrame
        """
        try:
            if self.data is None or self.data.empty:
                logger.warning("数据为空，先获取数据")
                self.fetch_data()
            
            if self.data is None or self.data.empty:
                logger.error("无法获取数据，均线计算失败")
                return pd.DataFrame()
            
            # 计算各周期均线
            for period in self.ma_periods:
                self.data[f'ma{period}'] = self.data['close'].rolling(window=period).mean()
            
            # 计算均线斜率（趋势强度）
            for period in [5, 10, 20, 30, 60]:
                if f'ma{period}' in self.data.columns:
                    self.data[f'ma{period}_slope'] = (
                        self.data[f'ma{period}'] - self.data[f'ma{period}'].shift(5)
                    ) / 5
            
            # 去除NaN值
            self.data = self.data.dropna()
            
            logger.info(f"成功计算 {len(self.ma_periods)} 个周期的均线")
            return self.data
            
        except Exception as e:
            logger.error(f"均线计算失败: {e}")
            return pd.DataFrame()
    
    def analyze_price_relations(self) -> Dict:
        """
        动态分析价格与均线关系
        
        功能:
        1. 当前价格相对各均线位置
        2. 突破/回踩关键均线信号
        3. 均线斜率方向分析
        
        返回:
        dict: 包含分析结果的字典
        """
        try:
            if self.data is None or self.data.empty:
                logger.warning("数据为空，先计算均线")
                self.calculate_moving_averages()
            
            if self.data is None or self.data.empty:
                logger.error("无法获取数据，分析失败")
                return {}
            
            current_price = self.data['close'].iloc[-1]
            analysis = {
                'current_price': current_price,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code
            }
            
            # 1. 位置分析 - 价格相对各均线位置
            analysis['position_analysis'] = {}
            for period in self.ma_periods:
                ma_col = f'ma{period}'
                if ma_col in self.data.columns:
                    ma_value = self.data[ma_col].iloc[-1]
                    deviation = (current_price - ma_value) / ma_value * 100
                    
                    analysis['position_analysis'][f'vs_ma{period}'] = {
                        'position': 'ABOVE' if current_price > ma_value else 'BELOW',
                        'ma_value': round(ma_value, 2),
                        'deviation_pct': round(deviation, 2)
                    }
            
            # 2. 突破/回踩信号检测
            analysis['signals'] = []
            
            # 金叉/死叉信号
            if len(self.data) >= 2:
                # MA5与MA10金叉/死叉
                if 'ma5' in self.data.columns and 'ma10' in self.data.columns:
                    ma5_curr = self.data['ma5'].iloc[-1]
                    ma5_prev = self.data['ma5'].iloc[-2]
                    ma10_curr = self.data['ma10'].iloc[-1]
                    ma10_prev = self.data['ma10'].iloc[-2]
                    
                    if ma5_curr > ma10_curr and ma5_prev <= ma10_prev:
                        analysis['signals'].append({
                            'type': 'GOLDEN_CROSS',
                            'description': 'MA5上穿MA10金叉',
                            'strength': 0.6
                        })
                    elif ma5_curr < ma10_curr and ma5_prev >= ma10_prev:
                        analysis['signals'].append({
                            'type': 'DEATH_CROSS',
                            'description': 'MA5下穿MA10死叉',
                            'strength': -0.6
                        })
                
                # MA20与MA60金叉/死叉
                if 'ma20' in self.data.columns and 'ma60' in self.data.columns:
                    ma20_curr = self.data['ma20'].iloc[-1]
                    ma20_prev = self.data['ma20'].iloc[-2]
                    ma60_curr = self.data['ma60'].iloc[-1]
                    ma60_prev = self.data['ma60'].iloc[-2]
                    
                    if ma20_curr > ma60_curr and ma20_prev <= ma60_prev:
                        analysis['signals'].append({
                            'type': 'MAJOR_GOLDEN_CROSS',
                            'description': 'MA20上穿MA60重要金叉',
                            'strength': 0.8
                        })
                    elif ma20_curr < ma60_curr and ma20_prev >= ma60_prev:
                        analysis['signals'].append({
                            'type': 'MAJOR_DEATH_CROSS',
                            'description': 'MA20下穿MA60重要死叉',
                            'strength': -0.8
                        })
            
            # 回踩支撑信号
            if 'ma5' in self.data.columns:
                ma5_value = self.data['ma5'].iloc[-1]
                price_to_ma5_ratio = abs(current_price - ma5_value) / current_price
                
                if price_to_ma5_ratio < 0.02:  # 价格接近MA5（2%以内）
                    # 检查是否为创新高后回踩
                    recent_high = self.data['high'].iloc[-20:].max()
                    if current_price >= recent_high * 0.98:  # 接近近期高点
                        analysis['signals'].append({
                            'type': 'PULLBACK_TO_MA5',
                            'description': '创新高后回踩MA5支撑',
                            'strength': 0.7
                        })
            
            # 3. 均线斜率分析（趋势强度）
            analysis['trend_analysis'] = {}
            for period in [5, 10, 20, 30, 60]:
                slope_col = f'ma{period}_slope'
                if slope_col in self.data.columns:
                    slope = self.data[slope_col].iloc[-1]
                    
                    if slope > 0.01:
                        trend = 'STRONG_UP'
                    elif slope > 0:
                        trend = 'WEAK_UP'
                    elif slope < -0.01:
                        trend = 'STRONG_DOWN'
                    elif slope < 0:
                        trend = 'WEAK_DOWN'
                    else:
                        trend = 'SIDEWAYS'
                    
                    analysis['trend_analysis'][f'ma{period}'] = {
                        'slope': round(slope, 4),
                        'trend': trend
                    }
            
            # 4. 多空排列分析
            ma_values = []
            for period in [5, 10, 20, 30, 60]:
                ma_col = f'ma{period}'
                if ma_col in self.data.columns:
                    ma_values.append(self.data[ma_col].iloc[-1])
            
            if len(ma_values) >= 3:
                is_bullish_alignment = all(ma_values[i] >= ma_values[i+1] for i in range(len(ma_values)-1))
                is_bearish_alignment = all(ma_values[i] <= ma_values[i+1] for i in range(len(ma_values)-1))
                
                if is_bullish_alignment:
                    analysis['signals'].append({
                        'type': 'BULLISH_ALIGNMENT',
                        'description': '均线多头排列',
                        'strength': 0.9
                    })
                elif is_bearish_alignment:
                    analysis['signals'].append({
                        'type': 'BEARISH_ALIGNMENT',
                        'description': '均线空头排列',
                        'strength': -0.9
                    })
            
            logger.info(f"价格关系分析完成，发现 {len(analysis['signals'])} 个信号")
            return analysis
            
        except Exception as e:
            logger.error(f"价格关系分析失败: {e}")
            return {}
    
    def generate_trading_signals(self, risk_level: int = 2) -> Dict:
        """
        生成交易策略信号（多因子加权决策）
        
        参数:
        risk_level (int): 风险偏好等级 1-5 (5为最高风险)
        
        返回:
        dict: 包含信号强度和仓位建议
        """
        try:
            # 获取价格关系分析结果
            analysis = self.analyze_price_relations()
            
            if not analysis:
                logger.error("无法获取分析结果")
                return {}
            
            # 因子权重系统（根据策略回测可调整权重）
            factor_weights = {
                'PULLBACK_TO_MA5': 0.25,
                'GOLDEN_CROSS': 0.20,
                'MAJOR_GOLDEN_CROSS': 0.30,
                'BULLISH_ALIGNMENT': 0.35,
                'DEATH_CROSS': -0.20,
                'MAJOR_DEATH_CROSS': -0.30,
                'BEARISH_ALIGNMENT': -0.35,
                'trend_strength': 0.15,
                'position_strength': 0.10
            }
            
            signal_strength = 0.0
            signal_details = []
            
            # 处理信号
            for signal in analysis.get('signals', []):
                signal_type = signal['type']
                signal_power = signal['strength']
                
                if signal_type in factor_weights:
                    weighted_score = factor_weights[signal_type] * signal_power
                    signal_strength += weighted_score
                    
                    signal_details.append({
                        'type': signal_type,
                        'description': signal['description'],
                        'raw_strength': signal_power,
                        'weighted_score': round(weighted_score, 3)
                    })
            
            # 趋势强度加分
            trend_score = 0
            trend_analysis = analysis.get('trend_analysis', {})
            for ma_period, trend_info in trend_analysis.items():
                trend = trend_info['trend']
                if trend == 'STRONG_UP':
                    trend_score += 0.1
                elif trend == 'WEAK_UP':
                    trend_score += 0.05
                elif trend == 'STRONG_DOWN':
                    trend_score -= 0.1
                elif trend == 'WEAK_DOWN':
                    trend_score -= 0.05
            
            signal_strength += trend_score * factor_weights['trend_strength']
            
            # 位置强度评估
            position_score = 0
            position_analysis = analysis.get('position_analysis', {})
            above_count = sum(1 for pos in position_analysis.values() if pos['position'] == 'ABOVE')
            total_count = len(position_analysis)
            
            if total_count > 0:
                position_ratio = above_count / total_count
                if position_ratio >= 0.8:
                    position_score = 0.5
                elif position_ratio >= 0.6:
                    position_score = 0.3
                elif position_ratio <= 0.2:
                    position_score = -0.5
                elif position_ratio <= 0.4:
                    position_score = -0.3
            
            signal_strength += position_score * factor_weights['position_strength']
            
            # 根据风险等级调整信号强度
            risk_multiplier = 0.5 + (risk_level - 1) * 0.125  # 0.5 到 1.0
            adjusted_signal = signal_strength * risk_multiplier
            
            # 生成交易决策
            position_suggestion = "HOLD"
            confidence = abs(adjusted_signal)
            
            if adjusted_signal > 0.4:
                position_pct = min(80, 30 + risk_level * 10)
                position_suggestion = f"BUY_{position_pct}%"
            elif adjusted_signal > 0.2:
                position_pct = min(50, 20 + risk_level * 6)
                position_suggestion = f"BUY_{position_pct}%"
            elif adjusted_signal < -0.4:
                position_pct = min(80, 30 + risk_level * 10)
                position_suggestion = f"SELL_{position_pct}%"
            elif adjusted_signal < -0.2:
                position_pct = min(50, 20 + risk_level * 6)
                position_suggestion = f"SELL_{position_pct}%"
            
            result = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code,
                'signal_score': round(signal_strength, 3),
                'adjusted_score': round(adjusted_signal, 3),
                'confidence': round(confidence, 3),
                'position_suggestion': position_suggestion,
                'risk_level': risk_level,
                'signal_details': signal_details,
                'trend_score': round(trend_score, 3),
                'position_score': round(position_score, 3),
                'analysis_summary': analysis
            }
            
            logger.info(f"交易信号生成完成: {position_suggestion}, 信号强度: {adjusted_signal:.3f}")
            return result
            
        except Exception as e:
            logger.error(f"交易信号生成失败: {e}")
            return {}
    
    def calculate_risk_metrics(self) -> Dict:
        """
        计算风险控制指标
        
        返回:
        dict: 风险指标
        """
        try:
            if self.data is None or self.data.empty:
                return {}
            
            # ATR计算（平均真实波幅）
            high = self.data['high']
            low = self.data['low']
            close = self.data['close']
            prev_close = close.shift(1)
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_14 = true_range.rolling(window=14).mean().iloc[-1]
            
            current_price = close.iloc[-1]
            
            # 动态止损位计算
            atr_stop_loss = {
                'conservative': current_price - (atr_14 * 1.5),
                'moderate': current_price - (atr_14 * 2.0),
                'aggressive': current_price - (atr_14 * 2.5)
            }
            
            # 波动率计算
            returns = self.data['returns'].dropna()
            volatility = returns.std() * np.sqrt(252)  # 年化波动率
            
            # 最大回撤计算
            cumulative_returns = (1 + returns).cumprod()
            rolling_max = cumulative_returns.expanding().max()
            drawdown = (cumulative_returns - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            risk_metrics = {
                'atr_14': round(atr_14, 2),
                'atr_stop_loss': {k: round(v, 2) for k, v in atr_stop_loss.items()},
                'volatility_annual': round(volatility, 4),
                'max_drawdown': round(max_drawdown, 4),
                'current_price': round(current_price, 2)
            }
            
            return risk_metrics
            
        except Exception as e:
            logger.error(f"风险指标计算失败: {e}")
            return {}
    
    def get_strategy_summary(self) -> Dict:
        """
        获取策略综合分析报告
        
        返回:
        dict: 完整的策略分析报告
        """
        try:
            # 确保数据已加载
            if self.data is None:
                self.calculate_moving_averages()
            
            # 获取各模块分析结果
            trading_signals = self.generate_trading_signals()
            risk_metrics = self.calculate_risk_metrics()
            
            summary = {
                'strategy_name': '智能均线交易系统',
                'version': '1.0',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code,
                'data_points': len(self.data) if self.data is not None else 0,
                'trading_signals': trading_signals,
                'risk_metrics': risk_metrics,
                'ma_periods': self.ma_periods
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"策略摘要生成失败: {e}")
            return {}

# ===== 工具函数 =====

def create_ma_system(stock_code: str) -> MovingAverageSystem:
    """
    创建均线系统实例的工厂函数
    
    参数:
    stock_code (str): 股票代码
    
    返回:
    MovingAverageSystem: 均线系统实例
    """
    return MovingAverageSystem(stock_code)

def quick_analysis(stock_code: str, risk_level: int = 2) -> Dict:
    """
    快速分析函数，一键获取交易建议
    
    参数:
    stock_code (str): 股票代码
    risk_level (int): 风险等级
    
    返回:
    dict: 交易建议
    """
    try:
        ma_system = create_ma_system(stock_code)
        ma_system.calculate_moving_averages()
        return ma_system.generate_trading_signals(risk_level)
    except Exception as e:
        logger.error(f"快速分析失败: {e}")
        return {}

# ===== 测试函数 =====

def test_ma_system():
    """
    测试均线系统功能
    """
    print("=== 均线策略系统测试 ===")
    
    # 测试股票代码
    test_stocks = ["000001.SZ", "000002.SZ", "600000.SH"]
    
    for stock_code in test_stocks:
        print(f"\n--- 测试股票: {stock_code} ---")
        
        try:
            # 创建系统实例
            ma_system = create_ma_system(stock_code)
            
            # 获取数据并计算均线
            ma_system.calculate_moving_averages()
            
            # 生成交易信号
            signals = ma_system.generate_trading_signals(risk_level=3)
            
            if signals:
                print(f"交易建议: {signals['position_suggestion']}")
                print(f"信号强度: {signals['adjusted_score']}")
                print(f"置信度: {signals['confidence']}")
            else:
                print("未能生成交易信号")
                
        except Exception as e:
            print(f"测试失败: {e}")

if __name__ == "__main__":
    # 运行测试
    test_ma_system()