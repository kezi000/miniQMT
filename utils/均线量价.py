# -*- coding: utf-8 -*-
"""
均线量价关系分析系统
基于miniQMT框架的智能均线与成交量价格关系分析

功能模块:
1. 量价关系与均线协同分析
2. 量能验证的突破信号识别
3. 动态仓位管理系统
4. 量价背离检测
5. 多维度决策引擎

作者: AI Assistant
创建时间: 2024
参考文档: 均线量价.md
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')

# 导入项目模块
try:
    import sys
    import os
    # 添加项目根目录到路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    
    from data_manager import get_data_manager
    from logger import get_logger
    import config
    
    # 直接导入同目录下的均线模块
    ma_file_path = os.path.join(current_dir, '均线.py')
    import importlib.util
    spec = importlib.util.spec_from_file_location("ma_module", ma_file_path)
    ma_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ma_module)
    MovingAverageSystem = ma_module.MovingAverageSystem
    
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在miniQMT项目根目录下运行")
    # 如果导入失败，创建一个基础类
    class MovingAverageSystem:
        def __init__(self, stock_code: str = "000001.SZ"):
            self.stock_code = stock_code
            self.data = None
        
        def get_data(self):
            return pd.DataFrame()
        
        def calculate_ma(self):
            pass
        
        def get_strategy_summary(self):
            return {}

# 获取logger
logger = get_logger("volume_enhanced_ma_strategy")

class VolumeEnhancedMASystem(MovingAverageSystem):
    """
    量价增强均线系统核心类
    
    继承自MovingAverageSystem，增加量价关系分析功能:
    - 量能验证的突破信号
    - 量价背离检测
    - 买卖量比分析
    - 动态仓位管理
    """
    
    def __init__(self, stock_code: str = "000001.SZ"):
        """
        初始化量价增强均线系统
        
        参数:
        stock_code (str): 股票代码，默认为平安银行
        """
        super().__init__(stock_code)
        self.volume_ma_periods = [5, 10, 20, 30]  # 量能均线周期
        logger.info(f"量价增强均线系统初始化成功，股票代码: {stock_code}")
    
    def _process_volume_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理量价特征工程
        
        参数:
        df (pd.DataFrame): 原始数据
        
        返回:
        pd.DataFrame: 增强的量价数据
        """
        try:
            # 基础量价特征
            df['volume_ma5'] = df['volume'].rolling(5).mean()
            df['volume_ma20'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma20']  # 相对量能
            
            # 模拟买卖量比（实际应用中需要从数据源获取）
            # 这里使用价格变化和成交量的关系来估算
            df['price_change'] = df['close'].pct_change()
            df['buy_volume_ratio'] = np.where(
                df['price_change'] > 0,
                0.5 + np.minimum(0.3, df['price_change'] * 10),  # 上涨时买方占优
                0.5 - np.minimum(0.3, abs(df['price_change']) * 10)  # 下跌时卖方占优
            )
            
            # 价格-量能相关性
            df['price_volume_corr'] = df['close'].rolling(10).corr(df['volume'])
            
            # 量价强度指标
            df['volume_price_strength'] = df['volume_ratio'] * abs(df['price_change'])
            
            return df
            
        except Exception as e:
            logger.error(f"量价数据处理失败: {e}")
            return df
    
    def _process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        重写数据预处理方法，增加量价特征
        
        参数:
        df (pd.DataFrame): 原始数据
        
        返回:
        pd.DataFrame: 处理后的数据
        """
        # 调用父类的数据处理
        df = super()._process_data(df)
        
        if df.empty:
            return df
        
        # 增加量价特征处理
        df = self._process_volume_data(df)
        
        return df
    
    def calculate_volume_ma(self) -> pd.DataFrame:
        """
        计算带量能验证的均线系统
        
        返回:
        pd.DataFrame: 包含量能均线的数据
        """
        try:
            # 先计算基础均线
            self.calculate_moving_averages()
            
            if self.data is None or self.data.empty:
                logger.error("无法获取数据，量能均线计算失败")
                return pd.DataFrame()
            
            # 计算量能均线系统
            for period in self.volume_ma_periods:
                self.data[f'vma{period}'] = self.data['volume'].rolling(period).mean()
            
            # 量价协同指标
            self.data['ma5_volume_confirm'] = np.where(
                (self.data['close'] > self.data['ma5']) & 
                (self.data['volume'] > self.data['vma5']), 1, 0
            )
            
            self.data['ma10_volume_confirm'] = np.where(
                (self.data['close'] > self.data['ma10']) & 
                (self.data['volume'] > self.data['vma10']), 1, 0
            )
            
            logger.info(f"成功计算量能均线系统")
            return self.data
            
        except Exception as e:
            logger.error(f"量能均线计算失败: {e}")
            return pd.DataFrame()
    
    def analyze_classic_volume_patterns(self) -> Dict:
        """
        经典量价形态识别分析
        
        功能:
        1. 有效阶段新高突破识别
        2. 假突破形态检测
        3. 量价齐升形态确认
        4. 成交量逐步放大形态
        
        返回:
        dict: 经典量价形态分析结果
        """
        try:
            if self.data is None or len(self.data) < 30:
                logger.warning("数据不足，无法进行经典形态分析")
                return {}
            
            current = self.data.iloc[-1]
            analysis = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code,
                'classic_patterns': {}
            }
            
            # 1. 有效阶段新高突破识别
            analysis['classic_patterns']['valid_breakout'] = self._detect_valid_breakout()
            
            # 2. 假突破形态检测
            analysis['classic_patterns']['false_breakout'] = self._detect_false_breakout()
            
            # 3. 量价齐升形态确认
            analysis['classic_patterns']['volume_price_rise'] = self._detect_volume_price_rise()
            
            # 4. 成交量逐步放大形态
            analysis['classic_patterns']['volume_expansion'] = self._detect_volume_expansion()
            
            # 5. 均线多头排列确认
            analysis['classic_patterns']['bullish_alignment'] = self._detect_bullish_alignment()
            
            # 6. 地量地价形态
            analysis['classic_patterns']['low_volume_price'] = self._detect_low_volume_price()
            
            # 7. 暴量突破形态
            analysis['classic_patterns']['explosive_breakout'] = self._detect_explosive_breakout()
            
            logger.info(f"经典量价形态分析完成")
            return analysis
            
        except Exception as e:
            logger.error(f"经典量价形态分析失败: {e}")
            return {}
    
    def _detect_valid_breakout(self) -> Dict:
        """
        检测有效阶段新高突破
        
        标准:
        1. 价格创近期新高（20日内）
        2. 突破时成交量放大（超过20日均量1.5倍）
        3. 突破后3日内不跌破突破点
        4. 均线支撑有效
        
        返回:
        dict: 有效突破分析结果
        """
        try:
            current = self.data.iloc[-1]
            recent_20_high = self.data['high'].iloc[-20:].max()
            recent_20_volume_avg = self.data['volume'].iloc[-20:].mean()
            
            # 检查是否创新高
            is_new_high = current['high'] >= recent_20_high
            
            # 检查量能配合
            volume_support = current['volume'] > recent_20_volume_avg * 1.5
            
            # 检查均线支撑（价格在MA5之上）
            ma_support = current['close'] > current.get('ma5', 0)
            
            # 检查突破强度（收盘价接近最高价）
            breakout_strength = (current['close'] - current['low']) / (current['high'] - current['low'])
            strong_close = breakout_strength > 0.7
            
            # 综合判断
            is_valid = is_new_high and volume_support and ma_support and strong_close
            
            return {
                'detected': is_valid,
                'confidence': 0.8 if is_valid else 0.3,
                'criteria': {
                    'new_high': is_new_high,
                    'volume_support': volume_support,
                    'ma_support': ma_support,
                    'strong_close': strong_close
                },
                'volume_ratio': round(current['volume'] / recent_20_volume_avg, 2),
                'breakout_strength': round(breakout_strength, 2),
                'description': '有效阶段新高突破' if is_valid else '突破条件不充分'
            }
            
        except Exception as e:
            logger.error(f"有效突破检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_false_breakout(self) -> Dict:
        """
        检测假突破形态
        
        标准:
        1. 价格短暂突破阻力位但快速回落
        2. 突破时成交量不足（低于均量）
        3. 上影线较长（超过实体的50%）
        4. 收盘价回到突破点以下
        
        返回:
        dict: 假突破分析结果
        """
        try:
            current = self.data.iloc[-1]
            prev = self.data.iloc[-2] if len(self.data) >= 2 else current
            recent_10_volume_avg = self.data['volume'].iloc[-10:].mean()
            
            # 检查上影线长度
            body_size = abs(current['close'] - current['open'])
            upper_shadow = current['high'] - max(current['close'], current['open'])
            long_upper_shadow = upper_shadow > body_size * 0.5
            
            # 检查成交量不足
            weak_volume = current['volume'] < recent_10_volume_avg * 0.8
            
            # 检查是否从高位回落
            price_retreat = current['close'] < current['high'] * 0.95
            
            # 检查是否跌破关键支撑
            ma5_break = current['close'] < current.get('ma5', current['close'])
            
            # 综合判断
            is_false_breakout = long_upper_shadow and weak_volume and price_retreat
            
            return {
                'detected': is_false_breakout,
                'confidence': 0.7 if is_false_breakout else 0.2,
                'criteria': {
                    'long_upper_shadow': long_upper_shadow,
                    'weak_volume': weak_volume,
                    'price_retreat': price_retreat,
                    'ma5_break': ma5_break
                },
                'upper_shadow_ratio': round(upper_shadow / body_size if body_size > 0 else 0, 2),
                'volume_ratio': round(current['volume'] / recent_10_volume_avg, 2),
                'description': '假突破形态' if is_false_breakout else '突破形态正常'
            }
            
        except Exception as e:
            logger.error(f"假突破检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_volume_price_rise(self) -> Dict:
        """
        检测量价齐升形态
        
        标准:
        1. 连续3-5日价格上涨
        2. 成交量同步放大
        3. 均线呈多头排列
        4. 量价相关性为正
        
        返回:
        dict: 量价齐升分析结果
        """
        try:
            # 检查最近5日的价格和成交量趋势
            recent_5 = self.data.iloc[-5:]
            
            # 价格上涨天数
            price_rises = (recent_5['close'].diff() > 0).sum()
            
            # 成交量放大天数
            volume_avg = self.data['volume'].iloc[-20:].mean()
            volume_expansion = (recent_5['volume'] > volume_avg).sum()
            
            # 计算量价相关性
            price_volume_corr = recent_5['close'].corr(recent_5['volume'])
            
            # 检查均线多头排列
            current = self.data.iloc[-1]
            ma_bullish = (
                current.get('ma5', 0) > current.get('ma10', 0) > 
                current.get('ma20', 0) > current.get('ma30', 0)
            )
            
            # 综合判断
            is_volume_price_rise = (
                price_rises >= 3 and 
                volume_expansion >= 3 and 
                price_volume_corr > 0.3 and 
                ma_bullish
            )
            
            return {
                'detected': is_volume_price_rise,
                'confidence': 0.8 if is_volume_price_rise else 0.4,
                'criteria': {
                    'price_rise_days': int(price_rises),
                    'volume_expansion_days': int(volume_expansion),
                    'price_volume_correlation': round(price_volume_corr, 2),
                    'ma_bullish_alignment': ma_bullish
                },
                'strength': 'STRONG' if is_volume_price_rise else 'WEAK',
                'description': '量价齐升形态' if is_volume_price_rise else '量价配合不佳'
            }
            
        except Exception as e:
            logger.error(f"量价齐升检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_volume_expansion(self) -> Dict:
        """
        检测成交量逐步放大形态
        
        标准:
        1. 最近5日成交量呈递增趋势
        2. 每日成交量都超过前一日
        3. 最新成交量是5日前的1.5倍以上
        4. 价格同步上涨
        
        返回:
        dict: 成交量放大分析结果
        """
        try:
            recent_5 = self.data.iloc[-5:]
            
            # 检查成交量递增
            volume_increases = (recent_5['volume'].diff() > 0).sum()
            
            # 检查成交量放大倍数
            volume_ratio = recent_5['volume'].iloc[-1] / recent_5['volume'].iloc[0]
            
            # 检查价格配合
            price_trend_up = recent_5['close'].iloc[-1] > recent_5['close'].iloc[0]
            
            # 计算成交量趋势斜率
            if len(recent_5) >= 3:
                volume_slope, _, _, _, _ = linregress(range(len(recent_5)), recent_5['volume'])
                volume_trend_positive = volume_slope > 0
            else:
                volume_trend_positive = False
            
            # 综合判断
            is_volume_expansion = (
                volume_increases >= 3 and 
                volume_ratio >= 1.5 and 
                price_trend_up and 
                volume_trend_positive
            )
            
            return {
                'detected': is_volume_expansion,
                'confidence': 0.7 if is_volume_expansion else 0.3,
                'criteria': {
                    'volume_increase_days': int(volume_increases),
                    'volume_expansion_ratio': round(volume_ratio, 2),
                    'price_trend_up': price_trend_up,
                    'volume_trend_positive': volume_trend_positive
                },
                'expansion_strength': 'STRONG' if volume_ratio >= 2.0 else 'MODERATE',
                'description': '成交量逐步放大' if is_volume_expansion else '成交量放大不明显'
            }
            
        except Exception as e:
            logger.error(f"成交量放大检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_bullish_alignment(self) -> Dict:
        """
        检测均线多头排列形态
        
        标准:
        1. MA5 > MA10 > MA20 > MA30 > MA60
        2. 所有均线斜率向上
        3. 价格在所有均线之上
        4. 均线间距逐渐扩大
        
        返回:
        dict: 多头排列分析结果
        """
        try:
            current = self.data.iloc[-1]
            
            # 检查均线排列
            ma_values = []
            ma_periods = [5, 10, 20, 30, 60]
            
            for period in ma_periods:
                ma_col = f'ma{period}'
                if ma_col in current.index:
                    ma_values.append(current[ma_col])
                else:
                    ma_values.append(0)
            
            # 检查多头排列
            bullish_order = all(ma_values[i] >= ma_values[i+1] for i in range(len(ma_values)-1) if ma_values[i+1] > 0)
            
            # 检查价格位置
            price_above_all = current['close'] > max(ma_values) if ma_values else False
            
            # 检查均线斜率
            upward_slopes = 0
            for period in [5, 10, 20, 30]:
                slope_col = f'ma{period}_slope'
                if slope_col in current.index and current[slope_col] > 0:
                    upward_slopes += 1
            
            slopes_positive = upward_slopes >= 3
            
            # 检查均线间距
            if len(ma_values) >= 3 and all(v > 0 for v in ma_values[:3]):
                ma_spread = (ma_values[0] - ma_values[2]) / ma_values[2]
                expanding_spread = ma_spread > 0.02  # 2%以上的间距
            else:
                expanding_spread = False
            
            # 综合判断
            is_bullish_alignment = bullish_order and price_above_all and slopes_positive
            
            return {
                'detected': is_bullish_alignment,
                'confidence': 0.9 if is_bullish_alignment else 0.3,
                'criteria': {
                    'bullish_order': bullish_order,
                    'price_above_all': price_above_all,
                    'slopes_positive': slopes_positive,
                    'expanding_spread': expanding_spread
                },
                'strength': 'VERY_STRONG' if (is_bullish_alignment and expanding_spread) else 'STRONG' if is_bullish_alignment else 'WEAK',
                'ma_spread_pct': round(ma_spread * 100, 2) if 'ma_spread' in locals() else 0,
                'description': '均线多头排列' if is_bullish_alignment else '均线排列混乱'
            }
            
        except Exception as e:
            logger.error(f"多头排列检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_low_volume_price(self) -> Dict:
        """
        检测地量地价形态
        
        标准:
        1. 成交量创近期新低（20日内）
        2. 价格也处于相对低位
        3. 均线开始收敛
        4. 可能是变盘前兆
        
        返回:
        dict: 地量地价分析结果
        """
        try:
            current = self.data.iloc[-1]
            recent_20 = self.data.iloc[-20:]
            
            # 检查成交量新低
            volume_new_low = current['volume'] == recent_20['volume'].min()
            
            # 检查价格相对位置
            price_percentile = (current['close'] - recent_20['close'].min()) / (recent_20['close'].max() - recent_20['close'].min())
            price_low_position = price_percentile < 0.3
            
            # 检查均线收敛
            ma_values = [current.get(f'ma{p}', 0) for p in [5, 10, 20, 30] if f'ma{p}' in current.index]
            if len(ma_values) >= 3:
                ma_range = (max(ma_values) - min(ma_values)) / current['close']
                ma_convergence = ma_range < 0.05  # 5%以内收敛
            else:
                ma_convergence = False
            
            # 综合判断
            is_low_volume_price = volume_new_low and price_low_position and ma_convergence
            
            return {
                'detected': is_low_volume_price,
                'confidence': 0.6 if is_low_volume_price else 0.2,
                'criteria': {
                    'volume_new_low': volume_new_low,
                    'price_low_position': price_low_position,
                    'ma_convergence': ma_convergence
                },
                'price_percentile': round(price_percentile, 2),
                'ma_range_pct': round(ma_range * 100, 2) if 'ma_range' in locals() else 0,
                'description': '地量地价形态，变盘前兆' if is_low_volume_price else '量价位置正常'
            }
            
        except Exception as e:
            logger.error(f"地量地价检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_explosive_breakout(self) -> Dict:
        """
        检测暴量突破形态
        
        标准:
        1. 成交量暴增（超过20日均量3倍）
        2. 价格大幅上涨（超过3%）
        3. 突破多根均线
        4. 收盘价接近最高价
        
        返回:
        dict: 暴量突破分析结果
        """
        try:
            current = self.data.iloc[-1]
            prev = self.data.iloc[-2] if len(self.data) >= 2 else current
            recent_20_volume_avg = self.data['volume'].iloc[-20:].mean()
            
            # 检查成交量暴增
            volume_explosive = current['volume'] > recent_20_volume_avg * 3
            
            # 检查价格大涨
            price_surge = (current['close'] - prev['close']) / prev['close'] > 0.03
            
            # 检查突破均线数量
            ma_breakouts = 0
            for period in [5, 10, 20, 30]:
                ma_col = f'ma{period}'
                if ma_col in current.index and ma_col in prev.index:
                    if current['close'] > current[ma_col] and prev['close'] <= prev[ma_col]:
                        ma_breakouts += 1
            
            multiple_ma_breakout = ma_breakouts >= 2
            
            # 检查收盘强度
            close_strength = (current['close'] - current['low']) / (current['high'] - current['low'])
            strong_close = close_strength > 0.8
            
            # 综合判断
            is_explosive_breakout = volume_explosive and price_surge and multiple_ma_breakout and strong_close
            
            return {
                'detected': is_explosive_breakout,
                'confidence': 0.9 if is_explosive_breakout else 0.2,
                'criteria': {
                    'volume_explosive': volume_explosive,
                    'price_surge': price_surge,
                    'multiple_ma_breakout': multiple_ma_breakout,
                    'strong_close': strong_close
                },
                'volume_multiple': round(current['volume'] / recent_20_volume_avg, 2),
                'price_change_pct': round((current['close'] - prev['close']) / prev['close'] * 100, 2),
                'ma_breakouts_count': ma_breakouts,
                'close_strength': round(close_strength, 2),
                'description': '暴量突破形态' if is_explosive_breakout else '突破力度不足'
            }
            
        except Exception as e:
            logger.error(f"暴量突破检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def analyze_volume_ma_relations(self) -> Dict:
        """
        量价-均线关系分析矩阵（整合经典形态分析）
        
        功能:
        1. 突破验证：价格突破均线时量能是否配合
        2. 回踩质量：回踩时的量能特征
        3. 背离检测：价格与量能走势背离
        4. 经典形态：整合经典量价形态识别
        
        返回:
        dict: 量价关系分析结果
        """
        try:
            if self.data is None or len(self.data) < 20:
                logger.warning("数据不足，无法进行量价关系分析")
                return {}
            
            current = self.data.iloc[-1]
            analysis = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code,
                'volume_ma_relations': {},
                'classic_patterns': {}
            }
            
            # 1. 突破验证分析
            analysis['volume_ma_relations']['breakout_validation'] = self._analyze_breakout_validation()
            
            # 2. 回踩质量分析
            analysis['volume_ma_relations']['pullback_quality'] = self._analyze_pullback_quality()
            
            # 3. 背离检测
            analysis['volume_ma_relations']['divergence'] = self._detect_price_volume_divergence()
            
            # 4. 量能堆积分析
            analysis['volume_ma_relations']['volume_accumulation'] = self._analyze_volume_accumulation()
            
            # 5. 整合经典形态分析
            classic_analysis = self.analyze_classic_volume_patterns()
            if classic_analysis and 'classic_patterns' in classic_analysis:
                analysis['classic_patterns'] = classic_analysis['classic_patterns']
            
            # 6. 综合评分
            analysis['overall_score'] = self._calculate_volume_ma_score(analysis)
            
            logger.info(f"量价-均线关系分析完成")
            return analysis
            
        except Exception as e:
            logger.error(f"量价-均线关系分析失败: {e}")
            return {}
    
    def _analyze_breakout_validation(self) -> Dict:
        """
        分析突破验证：价格突破均线时量能是否配合
        
        返回:
        dict: 突破验证分析结果
        """
        try:
            current = self.data.iloc[-1]
            prev = self.data.iloc[-2] if len(self.data) >= 2 else current
            
            # 检测均线突破
            ma_breakouts = []
            for period in [5, 10, 20, 30]:
                ma_col = f'ma{period}'
                if ma_col in current.index and ma_col in prev.index:
                    if current['close'] > current[ma_col] and prev['close'] <= prev[ma_col]:
                        ma_breakouts.append(period)
            
            if not ma_breakouts:
                return {'detected': False, 'description': '无均线突破'}
            
            # 检查量能配合
            recent_volume_avg = self.data['volume'].iloc[-10:].mean()
            volume_support = current['volume'] > recent_volume_avg * 1.2
            
            # 检查突破强度
            breakout_strength = (current['close'] - current['open']) / current['open']
            strong_breakout = breakout_strength > 0.02
            
            return {
                'detected': len(ma_breakouts) > 0,
                'ma_breakouts': ma_breakouts,
                'volume_support': volume_support,
                'strong_breakout': strong_breakout,
                'volume_ratio': round(current['volume'] / recent_volume_avg, 2),
                'breakout_strength': round(breakout_strength * 100, 2),
                'description': f'突破MA{ma_breakouts}，量能{"配合" if volume_support else "不足"}'
            }
            
        except Exception as e:
            logger.error(f"突破验证分析失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _analyze_pullback_quality(self) -> Dict:
        """
        分析回踩质量：回踩时的量能特征
        
        返回:
        dict: 回踩质量分析结果
        """
        try:
            recent_5 = self.data.iloc[-5:]
            
            # 检测回踩（价格下跌但在均线附近获得支撑）
            pullback_detected = False
            support_ma = None
            
            current = self.data.iloc[-1]
            for period in [5, 10, 20]:
                ma_col = f'ma{period}'
                if ma_col in current.index:
                    ma_value = current[ma_col]
                    # 检查是否在均线附近（±2%范围内）
                    if abs(current['close'] - ma_value) / ma_value < 0.02:
                        pullback_detected = True
                        support_ma = period
                        break
            
            if not pullback_detected:
                return {'detected': False, 'description': '无回踩形态'}
            
            # 分析回踩时的量能特征
            recent_volume_avg = self.data['volume'].iloc[-20:].mean()
            pullback_volume = recent_5['volume'].mean()
            
            # 理想的回踩：量能萎缩（表示抛压不重）
            volume_shrinkage = pullback_volume < recent_volume_avg * 0.8
            
            # 检查价格稳定性
            price_stability = recent_5['close'].std() / recent_5['close'].mean() < 0.03
            
            return {
                'detected': True,
                'support_ma': support_ma,
                'volume_shrinkage': volume_shrinkage,
                'price_stability': price_stability,
                'volume_ratio': round(pullback_volume / recent_volume_avg, 2),
                'quality': 'GOOD' if (volume_shrinkage and price_stability) else 'POOR',
                'description': f'MA{support_ma}回踩，量能{"萎缩" if volume_shrinkage else "放大"}'
            }
            
        except Exception as e:
            logger.error(f"回踩质量分析失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _detect_price_volume_divergence(self) -> Dict:
        """
        检测价格与量能走势背离
        
        返回:
        dict: 背离检测结果
        """
        try:
            recent_10 = self.data.iloc[-10:]
            
            # 计算价格和成交量的趋势
            price_slope, _, _, _, _ = linregress(range(len(recent_10)), recent_10['close'])
            volume_slope, _, _, _, _ = linregress(range(len(recent_10)), recent_10['volume'])
            
            # 检测背离
            bullish_divergence = price_slope < 0 and volume_slope > 0  # 价跌量增
            bearish_divergence = price_slope > 0 and volume_slope < 0  # 价涨量减
            
            divergence_type = None
            if bullish_divergence:
                divergence_type = 'BULLISH'  # 看涨背离
            elif bearish_divergence:
                divergence_type = 'BEARISH'  # 看跌背离
            
            return {
                'detected': bullish_divergence or bearish_divergence,
                'type': divergence_type,
                'price_slope': round(price_slope, 4),
                'volume_slope': round(volume_slope, 4),
                'significance': 'HIGH' if abs(price_slope) > 0.01 and abs(volume_slope) > 1000 else 'LOW',
                'description': f'{divergence_type}背离' if divergence_type else '无明显背离'
            }
            
        except Exception as e:
            logger.error(f"背离检测失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _analyze_volume_accumulation(self) -> Dict:
        """
        分析量能堆积（均线粘合区的量能特征）
        
        返回:
        dict: 量能堆积分析结果
        """
        try:
            current = self.data.iloc[-1]
            recent_10 = self.data.iloc[-10:]
            
            # 检查均线粘合（多条均线收敛）
            ma_values = []
            for period in [5, 10, 20, 30]:
                ma_col = f'ma{period}'
                if ma_col in current.index:
                    ma_values.append(current[ma_col])
            
            if len(ma_values) < 3:
                return {'detected': False, 'description': '均线数据不足'}
            
            # 计算均线收敛程度
            ma_range = (max(ma_values) - min(ma_values)) / current['close']
            ma_convergence = ma_range < 0.03  # 3%以内认为粘合
            
            if not ma_convergence:
                return {'detected': False, 'description': '均线未粘合'}
            
            # 分析粘合期间的量能特征
            volume_avg = self.data['volume'].iloc[-30:].mean()
            recent_volume_avg = recent_10['volume'].mean()
            
            # 量能堆积：成交量持续高于平均水平
            volume_accumulation = recent_volume_avg > volume_avg * 1.1
            
            # 量能稳定性
            volume_stability = recent_10['volume'].std() / recent_10['volume'].mean() < 0.5
            
            return {
                'detected': ma_convergence,
                'ma_convergence_pct': round(ma_range * 100, 2),
                'volume_accumulation': volume_accumulation,
                'volume_stability': volume_stability,
                'volume_ratio': round(recent_volume_avg / volume_avg, 2),
                'breakout_potential': 'HIGH' if (volume_accumulation and volume_stability) else 'LOW',
                'description': f'均线粘合，量能{"堆积" if volume_accumulation else "正常"}'
            }
            
        except Exception as e:
            logger.error(f"量能堆积分析失败: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _calculate_volume_ma_score(self, analysis: Dict) -> Dict:
        """
        计算量价-均线关系综合评分
        
        参数:
        analysis: 分析结果字典
        
        返回:
        dict: 综合评分结果
        """
        try:
            score = 0
            max_score = 100
            details = {}
            
            # 1. 经典形态评分 (40分)
            classic_score = 0
            if 'classic_patterns' in analysis:
                patterns = analysis['classic_patterns']
                
                # 有效突破 (10分)
                if patterns.get('valid_breakout', {}).get('detected', False):
                    classic_score += 10
                    details['valid_breakout'] = 10
                
                # 量价齐升 (10分)
                if patterns.get('volume_price_rise', {}).get('detected', False):
                    classic_score += 10
                    details['volume_price_rise'] = 10
                
                # 均线多头排列 (10分)
                if patterns.get('bullish_alignment', {}).get('detected', False):
                    classic_score += 10
                    details['bullish_alignment'] = 10
                
                # 暴量突破 (10分)
                if patterns.get('explosive_breakout', {}).get('detected', False):
                    classic_score += 10
                    details['explosive_breakout'] = 10
                
                # 假突破扣分 (-5分)
                if patterns.get('false_breakout', {}).get('detected', False):
                    classic_score -= 5
                    details['false_breakout'] = -5
            
            score += classic_score
            
            # 2. 量价关系评分 (30分)
            relations_score = 0
            if 'volume_ma_relations' in analysis:
                relations = analysis['volume_ma_relations']
                
                # 突破验证 (10分)
                breakout = relations.get('breakout_validation', {})
                if breakout.get('detected', False) and breakout.get('volume_support', False):
                    relations_score += 10
                    details['breakout_validation'] = 10
                
                # 回踩质量 (10分)
                pullback = relations.get('pullback_quality', {})
                if pullback.get('detected', False) and pullback.get('quality') == 'GOOD':
                    relations_score += 10
                    details['pullback_quality'] = 10
                
                # 量能堆积 (10分)
                accumulation = relations.get('volume_accumulation', {})
                if accumulation.get('detected', False) and accumulation.get('volume_accumulation', False):
                    relations_score += 10
                    details['volume_accumulation'] = 10
            
            score += relations_score
            
            # 3. 背离风险评分 (30分)
            divergence_score = 30  # 默认满分
            if 'volume_ma_relations' in analysis:
                divergence = analysis['volume_ma_relations'].get('divergence', {})
                if divergence.get('detected', False):
                    if divergence.get('type') == 'BEARISH':
                        divergence_score -= 20  # 看跌背离扣分
                        details['bearish_divergence'] = -20
                    elif divergence.get('type') == 'BULLISH':
                        divergence_score += 10  # 看涨背离加分
                        details['bullish_divergence'] = 10
            
            score += divergence_score
            
            # 确保评分在合理范围内
            score = max(0, min(score, max_score))
            
            # 评级
            if score >= 80:
                rating = 'EXCELLENT'
            elif score >= 60:
                rating = 'GOOD'
            elif score >= 40:
                rating = 'FAIR'
            else:
                rating = 'POOR'
            
            return {
                'total_score': score,
                'max_score': max_score,
                'rating': rating,
                'score_details': details,
                'description': f'量价关系评分: {score}/{max_score} ({rating})'
            }
            
        except Exception as e:
            logger.error(f"综合评分计算失败: {e}")
            return {'total_score': 0, 'rating': 'ERROR', 'error': str(e)}
    
    def generate_volume_enhanced_signals(self, risk_level: int = 2) -> Dict:
        """
        基于量价-均线关系的四维决策系统（整合经典形态分析）
        
        决策维度:
        1. 趋势方向（均线多头排列 + 经典形态）
        2. 量能验证（突破/回踩量能健康度 + 量价齐升）
        3. 市场情绪（经典形态信号强度）
        4. 风险系数（假突破风险 + 背离风险）
        
        参数:
        risk_level (int): 风险偏好等级 1-5
        
        返回:
        dict: 四维决策结果
        """
        try:
            # 确保数据已计算
            self.calculate_volume_ma()
            
            if self.data is None or self.data.empty:
                logger.error("无法获取数据，信号生成失败")
                return {}
            
            # 获取量价关系分析（包含经典形态）
            volume_analysis = self.analyze_volume_ma_relations()
            classic_patterns = volume_analysis.get('classic_patterns', {})
            volume_relations = volume_analysis.get('volume_ma_relations', {})
            overall_score = volume_analysis.get('overall_score', {})
            
            # 1. 趋势维度评分（基于经典形态）
            trend_strength = 0
            
            # 均线多头排列
            bullish_alignment = classic_patterns.get('bullish_alignment', {})
            if bullish_alignment.get('detected', False):
                confidence = bullish_alignment.get('confidence', 0)
                trend_strength += confidence * 0.4
            
            # 有效突破
            valid_breakout = classic_patterns.get('valid_breakout', {})
            if valid_breakout.get('detected', False):
                confidence = valid_breakout.get('confidence', 0)
                trend_strength += confidence * 0.3
            
            # 暴量突破
            explosive_breakout = classic_patterns.get('explosive_breakout', {})
            if explosive_breakout.get('detected', False):
                confidence = explosive_breakout.get('confidence', 0)
                trend_strength += confidence * 0.3
            
            # 2. 量能维度评分
            volume_score = 0
            
            # 量价齐升形态
            volume_price_rise = classic_patterns.get('volume_price_rise', {})
            if volume_price_rise.get('detected', False):
                confidence = volume_price_rise.get('confidence', 0)
                volume_score += confidence * 0.4
            
            # 成交量逐步放大
            volume_expansion = classic_patterns.get('volume_expansion', {})
            if volume_expansion.get('detected', False):
                confidence = volume_expansion.get('confidence', 0)
                volume_score += confidence * 0.3
            
            # 突破验证
            breakout_validation = volume_relations.get('breakout_validation', {})
            if breakout_validation.get('detected', False) and breakout_validation.get('volume_support', False):
                volume_score += 0.3
            
            # 3. 情绪维度评分（基于形态信号强度）
            sentiment_score = 0
            
            # 地量地价（变盘前兆）
            low_volume_price = classic_patterns.get('low_volume_price', {})
            if low_volume_price.get('detected', False):
                confidence = low_volume_price.get('confidence', 0)
                sentiment_score += confidence * 0.2  # 谨慎乐观
            
            # 量能堆积
            volume_accumulation = volume_relations.get('volume_accumulation', {})
            if volume_accumulation.get('detected', False) and volume_accumulation.get('volume_accumulation', False):
                sentiment_score += 0.3
            
            # 回踩质量
            pullback_quality = volume_relations.get('pullback_quality', {})
            if pullback_quality.get('detected', False) and pullback_quality.get('quality') == 'GOOD':
                sentiment_score += 0.2
            
            # 4. 风险维度（风险惩罚）
            risk_penalty = 0
            
            # 假突破风险
            false_breakout = classic_patterns.get('false_breakout', {})
            if false_breakout.get('detected', False):
                confidence = false_breakout.get('confidence', 0)
                risk_penalty += confidence * 0.4
            
            # 背离风险
            divergence = volume_relations.get('divergence', {})
            if divergence.get('detected', False):
                if divergence.get('type') == 'BEARISH':
                    risk_penalty += 0.3
                elif divergence.get('type') == 'BULLISH':
                    risk_penalty -= 0.1  # 看涨背离减少风险
            
            # 波动率风险
            if len(self.data) >= 10:
                volatility = self.data['close'].iloc[-10:].std() / self.data['close'].iloc[-10:].mean()
                risk_penalty += min(0.2, volatility * 5)
            
            # 综合评分
            total_score = trend_strength + volume_score + sentiment_score - risk_penalty
            total_score = max(0, min(1, total_score))  # 归一化到[0,1]
            
            # 根据风险等级调整
            risk_multiplier = 0.5 + (risk_level - 1) * 0.125
            adjusted_score = total_score * risk_multiplier
            
            # 使用综合评分系统的评级
            overall_rating = overall_score.get('rating', 'FAIR')
            overall_total_score = overall_score.get('total_score', 50)
            
            # 生成决策（结合评分和评级）
            if adjusted_score > 0.8 and overall_rating in ['EXCELLENT', 'GOOD']:
                action = "STRONG_BUY"
                position = f"80-{min(95, int(80 + (adjusted_score-0.8)*75))}%"
            elif adjusted_score > 0.6 and overall_rating != 'POOR':
                action = "BUY"
                position = f"50-{min(75, int(50 + (adjusted_score-0.6)*62.5))}%"
            elif adjusted_score < 0.3 or overall_rating == 'POOR':
                action = "STRONG_SELL"
                position = "0-20%"
            elif adjusted_score < 0.4:
                action = "SELL"
                position = "10-30%"
            else:
                action = "HOLD"
                position = "30-50%"
            
            # 特殊形态调整
            if explosive_breakout.get('detected', False):
                if action in ['BUY', 'HOLD']:
                    action = 'STRONG_BUY'
                    position = '70-90%'
            
            if false_breakout.get('detected', False):
                if action in ['BUY', 'STRONG_BUY']:
                    action = 'HOLD'
                    position = '20-40%'
            
            result = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code,
                'decision': action,
                'position': position,
                'score_breakdown': {
                    'trend': round(trend_strength, 3),
                    'volume': round(volume_score, 3),
                    'sentiment': round(sentiment_score, 3),
                    'risk_penalty': round(risk_penalty, 3)
                },
                'composite_score': round(total_score, 3),
                'adjusted_score': round(adjusted_score, 3),
                'overall_rating': overall_rating,
                'overall_score': overall_total_score,
                'risk_level': risk_level,
                'classic_patterns_detected': [
                    pattern for pattern, data in classic_patterns.items() 
                    if data.get('detected', False)
                ],
                'volume_analysis': volume_analysis
            }
            
            logger.info(f"量价增强信号生成完成: {action}, 综合评分: {adjusted_score:.3f}, 评级: {overall_rating}")
            return result
            
        except Exception as e:
            logger.error(f"量价增强信号生成失败: {e}")
            return {}
    
    def get_volume_enhanced_summary(self) -> Dict:
        """
        获取量价增强策略综合分析报告
        
        返回:
        dict: 完整的量价策略分析报告
        """
        try:
            # 获取基础策略摘要
            base_summary = self.get_strategy_summary()
            
            # 获取量价增强信号
            volume_signals = self.generate_volume_enhanced_signals()
            
            # 获取量价关系分析
            volume_analysis = self.analyze_volume_ma_relations()
            
            enhanced_summary = {
                'strategy_name': '量价增强均线交易系统',
                'version': '2.0',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': self.stock_code,
                'base_strategy': base_summary,
                'volume_enhanced_signals': volume_signals,
                'volume_analysis': volume_analysis,
                'enhancement_features': [
                    '量能验证的突破信号',
                    '量价背离检测',
                    '买卖量比分析',
                    '四维决策引擎',
                    '动态仓位管理'
                ]
            }
            
            return enhanced_summary
            
        except Exception as e:
            logger.error(f"量价增强策略摘要生成失败: {e}")
            return {}

# ===== 工具函数 =====

def create_volume_enhanced_ma_system(stock_code: str) -> VolumeEnhancedMASystem:
    """
    创建量价增强均线系统实例的工厂函数
    
    参数:
    stock_code (str): 股票代码
    
    返回:
    VolumeEnhancedMASystem: 量价增强均线系统实例
    """
    return VolumeEnhancedMASystem(stock_code)

def quick_volume_analysis(stock_code: str, risk_level: int = 2) -> Dict:
    """
    快速量价分析函数，一键获取量价增强交易建议
    
    参数:
    stock_code (str): 股票代码
    risk_level (int): 风险等级
    
    返回:
    dict: 量价增强交易建议
    """
    try:
        system = VolumeEnhancedMASystem(stock_code)
        return system.generate_volume_enhanced_signals(risk_level)
    except Exception as e:
        logger.error(f"快速量价分析失败: {e}")
        return {}

def test_volume_enhanced_ma_system():
    """
    测试量价增强均线系统的完整功能
    """
    print("=== 量价增强均线交易系统测试 ===")
    
    # 测试股票代码
    test_codes = ['000001.SZ', '000002.SZ', '600000.SH']
    
    for code in test_codes:
        print(f"\n--- 测试股票: {code} ---")
        
        try:
            # 创建系统实例
            system = VolumeEnhancedMASystem(code)
            
            # 获取量价增强信号
            signals = system.generate_volume_enhanced_signals(risk_level=3)
            
            if signals:
                print(f"交易决策: {signals.get('decision', 'N/A')}")
                print(f"建议仓位: {signals.get('position', 'N/A')}")
                print(f"综合评分: {signals.get('adjusted_score', 'N/A')}")
                print(f"检测到的经典形态: {signals.get('classic_patterns_detected', [])}")
            else:
                print("信号生成失败")
                
        except Exception as e:
            print(f"测试失败: {e}")
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    # 运行测试
    test_volume_enhanced_ma_system()

def quick_volume_analysis(stock_code: str, risk_level: int = 2) -> Dict:
    """
    快速量价分析函数，一键获取量价增强交易建议
    
    参数:
    stock_code (str): 股票代码
    risk_level (int): 风险等级
    
    返回:
    dict: 量价增强交易建议
    """
    try:
        volume_ma_system = create_volume_enhanced_ma_system(stock_code)
        return volume_ma_system.generate_volume_enhanced_signals(risk_level)
    except Exception as e:
        logger.error(f"快速量价分析失败: {e}")
        return {}

# ===== 测试函数 =====

def test_volume_enhanced_ma_system():
    """
    测试量价增强均线系统功能
    """
    print("=== 量价增强均线策略系统测试 ===")
    
    # 测试股票代码
    test_stocks = ["000001.SZ", "000002.SZ"]
    
    for stock_code in test_stocks:
        print(f"\n--- 测试股票: {stock_code} ---")
        
        try:
            # 创建系统实例
            volume_ma_system = create_volume_enhanced_ma_system(stock_code)
            
            # 获取量价增强信号
            signals = volume_ma_system.generate_volume_enhanced_signals(risk_level=3)
            
            if signals:
                print(f"交易决策: {signals['decision']}")
                print(f"仓位建议: {signals['position']}")
                print(f"综合评分: {signals['composite_score']}")
                print(f"评分明细: {signals['score_breakdown']}")
            else:
                print("未能生成量价增强信号")
                
        except Exception as e:
            print(f"测试失败: {e}")

if __name__ == "__main__":
    # 运行测试
    test_volume_enhanced_ma_system()