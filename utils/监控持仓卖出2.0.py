#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓监控卖出2.0测试模块

基于超短线情绪接力的交易特点，结合分时均线协同卖出策略体系。

9大核心卖出规则：
1. 高开冲高回落 - 高开+最高价高于开盘价N%+跌破分时均线
2. 低开冲高回落 - 低开+最高价高于开盘价N%+跌破分时均线  
3. 涨幅达标回落 - 涨幅>6%+回落2.5%+股价-均线乖离率>4%
4. 巨幅冲高回落 - 涨幅>8%+回落3%+股价-均线乖离率>6%
5. 分时均线压制 - 上攻均线失败3次+量能递减+均线向下
6. 炸板防御 - 封单<500万+封单衰减30%+炸板量能3倍+距均线<0.5%
7. 最大回撤止损 - 从当日高点回撤3%+跌破分时均线+持续180秒
8. 尾盘卖出 - 尾盘时段+股价低于均线0.5%+未涨停+量能不足
9. 板块联动卖出 - 板块指数跌3%+板块龙头炸板+跌破分时均线

作者: AI Assistant
创建时间: 2024
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import config
from logger import get_logger
from data_manager import get_data_manager
from position_manager import get_position_manager
from trading_executor import get_trading_executor
from vwap_intraday import VWAPCalculator
import xtquant.xtdata as xtdata

# 颜色定义（ANSI颜色代码）
class Colors:
    RED = '\033[91m'      # 红色（亏损）
    GREEN = '\033[92m'    # 绿色（盈利）
    YELLOW = '\033[93m'   # 黄色（持平）
    BLUE = '\033[94m'     # 蓝色（标题）
    MAGENTA = '\033[95m'  # 紫色（重要信息）
    CYAN = '\033[96m'     # 青色（股票代码）
    WHITE = '\033[97m'    # 白色（普通文本）
    BOLD = '\033[1m'      # 粗体
    UNDERLINE = '\033[4m' # 下划线
    END = '\033[0m'       # 结束颜色

# 获取logger
logger = get_logger("test_监控持仓卖出2.0")

# ===== 卖出策略配置 =====

# 基础定义
HIGH_OPEN_THRESHOLD = 0.015  # 高开阈值：开盘价 >= 昨收*1.015
LOW_OPEN_THRESHOLD = 0.005   # 低开阈值：开盘价 <= 昨收*0.995

# 规则1: 高开冲高回落
SELL_RULE1 = {
    'enable': True,
    'conditions': {
        'is_high_open': True,                 # 高开
        'rise_above_open': 0.03,              # 最高价高于开盘价3%
        'drawdown_from_high': 0.015,          # 从最高点回落1.5%
        'ma_relation': 'below',               # 当前价低于分时均线
        'ma_recovery_time': 60,               # 60秒内未站回均线
        'volume_ratio': 0.7                   # 量能不足均量70%
    }
}

# 规则2: 低开冲高回落
SELL_RULE2 = {
    'enable': True,
    'conditions': {
        'is_low_open': True,                  # 低开
        'rise_above_open': 0.05,              # 最高价高于开盘价5%
        'drawdown_from_high': 0.02,           # 从最高点回落2%
        'ma_relation': 'below',               # 当前价低于分时均线
        'ma_recovery_time': 90,               # 90秒内未站回均线
        'volume_ratio': 0.6                   # 量能不足均量60%
    }
}

# 规则3: 涨幅达标回落
SELL_RULE3 = {
    'enable': True,
    'conditions': {
        'gain_from_yclose': 0.06,            # 最高价涨幅大于6%(相对昨收)
        'drawdown_from_high': 0.025,          # 从最高点回落2.5%
        'ma_divergence': 0.04,                # 股价-均线乖离率>4%
        'volume_ratio': 0.8                   # 量能不足均量80%
    }
}

# 规则4: 巨幅冲高回落
SELL_RULE4 = {
    'enable': True,
    'conditions': {
        'gain_from_yclose': 0.08,            # 最高价涨幅大于8%
        'drawdown_from_high': 0.03,           # 从最高点回落3%
        'ma_divergence': 0.06,                # 股价-均线乖离率>6%
        'volume_ratio': 1.2                   # 量能超过均量120%(出货量)
    }
}

# 规则5: 分时均线压制
SELL_RULE5 = {
    'enable': True,
    'conditions': {
        'ma_pressure_attempts': 3,           # 上攻均线失败次数
        'ma_distance': 0.003,                 # 距离均线0.3%内失败
        'volume_decrease': True,              # 量能逐次递减
        'ma_direction': 'down'                # 均线方向向下
    }
}

# 规则6: 炸板防御
SELL_RULE6 = {
    'enable': True,
    'conditions': {
        'seal_amount': 5000000,               # 封单<500万元
        'seal_decline_rate': 0.3,             # 封单30秒内衰减30%
        'volume_ratio': 3.0,                  # 炸板量能3倍于均量
        'ma_support': 0.005,                  # 股价距均线<0.5%
        'time_since_open': (9, 30)            # 早盘时段更敏感
    }
}

# 规则7: 最大回撤止损
SELL_RULE7 = {
    'enable': True,
    'conditions': {
        'max_drawdown': 0.03,                 # 从当日高点回撤3%
        'ma_relation': 'below',               # 当前价低于分时均线
        'time_elapsed': 180                   # 持续180秒
    }
}

# 规则8: 尾盘卖出
SELL_RULE8 = {
    'enable': True,
    'conditions': {
        'time_window': ('14:55', '15:00'),    # 尾盘时段
        'price_below_ma': 0.005,              # 股价低于均线0.5%
        'not_limit_up': True,                 # 未涨停
        'volume_ratio': 0.9                   # 量能不足均量90%
    }
}

# 规则9: 板块联动卖出
SELL_RULE9 = {
    'enable': True,
    'conditions': {
        'sector_decline': 0.03,               # 板块指数3分钟跌3%
        'sector_leader_down': True,           # 板块龙头炸板
        'ma_relation': 'below',               # 当前价低于分时均线
        'time_since_signal': 60               # 信号出现60秒内
    }
}

# 委托管理
ORDER_PARAMS = {
    'cancel_timeout': 2,                      # 2秒未成交撤单
    'resend_price_offset': -0.002,            # 重挂单价格偏移-0.2%
    'max_resend_times': 3                     # 最大重挂次数
}

# 特殊场景处理
SPECIAL_CASES = {
    'market_leader': {                        # 市场龙头特殊处理
        'drawdown_threshold_adjust': 0.3,     # 回撤阈值放宽30%
        'ma_tolerance': 0.01,                 # 均线容忍度1%
        'tail_sell_exempt': True              # 尾盘卖出豁免
    },
    'limit_up_streak': {                      # 连续涨停股
        'seal_threshold_multiplier': 2.0,     # 封单阈值加倍
        'drawdown_threshold_adjust': 0.5      # 回撤阈值放宽50%
    }
}

# 全局过滤条件
GLOBAL_FILTERS = {
    'min_trade_amount': 10000000,             # 最小交易金额1000万
    'min_volatility': 0.03,                   # 最小波动率3%
    'exclude_new_stock': True,                # 排除新股(上市<5天)
    'time_exemptions': [('09:25', '09:35')]   # 开盘10分钟豁免
}

# ===== 市场情绪指标配置 =====

# 市场情绪综合评估指标
MARKET_SENTIMENT_INDICATORS = {
    'vix_level': 0.0,           # 恐慌指数（0-100，数值越高越恐慌）
    'advance_decline': 0.0,     # 涨跌比（上涨股票数/下跌股票数）
    'volume_ratio': 0.0,        # 成交量比率（今日量/5日均量）
    'sector_rotation': {},      # 板块轮动状态（各板块涨跌幅）
    'limit_up_count': 0,        # 涨停数量
    'limit_down_count': 0,      # 跌停数量
    'new_high_count': 0,        # 创新高股票数量
    'new_low_count': 0,         # 创新低股票数量
    'turnover_rate': 0.0,       # 市场换手率
    'sentiment_score': 0.0      # 综合情绪得分（-1到1，负值恐慌，正值贪婪）
}

# 情绪阈值配置
SENTIMENT_THRESHOLDS = {
    'extreme_fear': -0.7,       # 极度恐慌阈值
    'fear': -0.3,               # 恐慌阈值
    'neutral': 0.0,             # 中性阈值
    'greed': 0.3,               # 贪婪阈值
    'extreme_greed': 0.7        # 极度贪婪阈值
}

# 情绪调整系数
SENTIMENT_ADJUSTMENTS = {
    'extreme_fear': {
        'drawdown_multiplier': 0.6,     # 极度恐慌时降低回撤阈值40%
        'volume_multiplier': 0.8,       # 降低量能要求
        'ma_tolerance': 1.5             # 增加均线容忍度
    },
    'fear': {
        'drawdown_multiplier': 0.8,     # 恐慌时降低回撤阈值20%
        'volume_multiplier': 0.9,       # 降低量能要求
        'ma_tolerance': 1.2             # 增加均线容忍度
    },
    'neutral': {
        'drawdown_multiplier': 1.0,     # 中性时保持原有阈值
        'volume_multiplier': 1.0,
        'ma_tolerance': 1.0
    },
    'greed': {
        'drawdown_multiplier': 1.2,     # 贪婪时提高回撤阈值20%
        'volume_multiplier': 1.1,       # 提高量能要求
        'ma_tolerance': 0.8             # 降低均线容忍度
    },
    'extreme_greed': {
        'drawdown_multiplier': 1.5,     # 极度贪婪时提高回撤阈值50%
        'volume_multiplier': 1.3,       # 提高量能要求
        'ma_tolerance': 0.6             # 降低均线容忍度
    }
}

def calculate_market_sentiment() -> float:
    """
    计算市场情绪综合得分
    
    返回:
    float: 情绪得分（-1到1，负值恐慌，正值贪婪）
    """
    try:
        indicators = MARKET_SENTIMENT_INDICATORS
        
        # 各指标权重
        weights = {
            'advance_decline': 0.25,    # 涨跌比权重
            'volume_ratio': 0.15,       # 成交量比率权重
            'limit_ratio': 0.20,        # 涨跌停比率权重
            'new_high_low': 0.15,       # 新高新低比率权重
            'turnover': 0.10,           # 换手率权重
            'vix': 0.15                 # 恐慌指数权重
        }
        
        sentiment_score = 0.0
        
        # 1. 涨跌比得分（-1到1）
        if indicators['advance_decline'] > 0:
            ad_score = min(1.0, (indicators['advance_decline'] - 1.0) / 2.0)
        else:
            ad_score = -1.0
        sentiment_score += ad_score * weights['advance_decline']
        
        # 2. 成交量比率得分（-1到1）
        volume_score = min(1.0, max(-1.0, (indicators['volume_ratio'] - 1.0) / 0.5))
        sentiment_score += volume_score * weights['volume_ratio']
        
        # 3. 涨跌停比率得分（-1到1）
        total_limit = indicators['limit_up_count'] + indicators['limit_down_count']
        if total_limit > 0:
            limit_ratio = indicators['limit_up_count'] / total_limit
            limit_score = (limit_ratio - 0.5) * 2  # 转换为-1到1
        else:
            limit_score = 0.0
        sentiment_score += limit_score * weights['limit_ratio']
        
        # 4. 新高新低比率得分（-1到1）
        total_new = indicators['new_high_count'] + indicators['new_low_count']
        if total_new > 0:
            new_ratio = indicators['new_high_count'] / total_new
            new_score = (new_ratio - 0.5) * 2  # 转换为-1到1
        else:
            new_score = 0.0
        sentiment_score += new_score * weights['new_high_low']
        
        # 5. 换手率得分（-1到1）
        # 换手率过高或过低都不好，适中最佳
        if indicators['turnover_rate'] > 0:
            if indicators['turnover_rate'] < 0.02:  # 换手率过低
                turnover_score = -0.5
            elif indicators['turnover_rate'] > 0.08:  # 换手率过高
                turnover_score = -0.3
            else:  # 适中范围
                turnover_score = 0.3
        else:
            turnover_score = 0.0
        sentiment_score += turnover_score * weights['turnover']
        
        # 6. 恐慌指数得分（-1到1）
        if indicators['vix_level'] > 0:
            # VIX越高越恐慌，得分越低
            vix_score = max(-1.0, (30 - indicators['vix_level']) / 30)
        else:
            vix_score = 0.0
        sentiment_score += vix_score * weights['vix']
        
        # 限制在-1到1范围内
        sentiment_score = max(-1.0, min(1.0, sentiment_score))
        
        # 更新全局指标
        MARKET_SENTIMENT_INDICATORS['sentiment_score'] = sentiment_score
        
        return sentiment_score
        
    except Exception as e:
        logger.error(f"计算市场情绪时出错: {str(e)}")
        return 0.0

def get_sentiment_level(sentiment_score: float) -> str:
    """
    根据情绪得分获取情绪等级
    
    参数:
    sentiment_score (float): 情绪得分
    
    返回:
    str: 情绪等级
    """
    thresholds = SENTIMENT_THRESHOLDS
    
    if sentiment_score <= thresholds['extreme_fear']:
        return 'extreme_fear'
    elif sentiment_score <= thresholds['fear']:
        return 'fear'
    elif sentiment_score <= thresholds['neutral']:
        return 'neutral'
    elif sentiment_score <= thresholds['greed']:
        return 'greed'
    else:
        return 'extreme_greed'

def adjust_rules_by_sentiment(sentiment_score: float = None) -> Dict:
    """
    根据市场情绪调整规则敏感度
    
    参数:
    sentiment_score (float): 情绪得分，如果为None则重新计算
    
    返回:
    dict: 调整后的规则参数
    """
    try:
        if sentiment_score is None:
            sentiment_score = calculate_market_sentiment()
        
        sentiment_level = get_sentiment_level(sentiment_score)
        adjustments = SENTIMENT_ADJUSTMENTS[sentiment_level]
        
        # 创建调整后的规则副本
        adjusted_rules = {
            'SELL_RULE1': SELL_RULE1.copy(),
            'SELL_RULE2': SELL_RULE2.copy(),
            'SELL_RULE3': SELL_RULE3.copy(),
            'SELL_RULE4': SELL_RULE4.copy(),
            'SELL_RULE5': SELL_RULE5.copy(),
            'SELL_RULE6': SELL_RULE6.copy(),
            'SELL_RULE7': SELL_RULE7.copy(),
            'SELL_RULE8': SELL_RULE8.copy(),
            'SELL_RULE9': SELL_RULE9.copy()
        }
        
        # 调整回撤相关规则
        for rule_name in ['SELL_RULE1', 'SELL_RULE2', 'SELL_RULE3', 'SELL_RULE4', 'SELL_RULE7']:
            rule = adjusted_rules[rule_name]
            if 'conditions' in rule and 'drawdown_from_high' in rule['conditions']:
                original_drawdown = rule['conditions']['drawdown_from_high']
                rule['conditions']['drawdown_from_high'] = original_drawdown * adjustments['drawdown_multiplier']
        
        # 调整量能相关规则
        for rule_name in ['SELL_RULE1', 'SELL_RULE2', 'SELL_RULE3', 'SELL_RULE4', 'SELL_RULE6', 'SELL_RULE8']:
            rule = adjusted_rules[rule_name]
            if 'conditions' in rule and 'volume_ratio' in rule['conditions']:
                original_volume = rule['conditions']['volume_ratio']
                rule['conditions']['volume_ratio'] = original_volume * adjustments['volume_multiplier']
        
        # 调整均线容忍度
        for rule_name in ['SELL_RULE5', 'SELL_RULE6']:
            rule = adjusted_rules[rule_name]
            if rule_name == 'SELL_RULE5' and 'conditions' in rule and 'ma_distance' in rule['conditions']:
                original_distance = rule['conditions']['ma_distance']
                rule['conditions']['ma_distance'] = original_distance * adjustments['ma_tolerance']
            elif rule_name == 'SELL_RULE6' and 'conditions' in rule and 'ma_support' in rule['conditions']:
                original_support = rule['conditions']['ma_support']
                rule['conditions']['ma_support'] = original_support * adjustments['ma_tolerance']
        
        logger.info(f"根据市场情绪 {sentiment_level}（得分: {sentiment_score:.2f}）调整规则参数")
        logger.info(f"回撤倍数: {adjustments['drawdown_multiplier']:.1f}, 量能倍数: {adjustments['volume_multiplier']:.1f}, 均线容忍度: {adjustments['ma_tolerance']:.1f}")
        
        return {
            'sentiment_score': sentiment_score,
            'sentiment_level': sentiment_level,
            'adjustments': adjustments,
            'rules': adjusted_rules
        }
        
    except Exception as e:
        logger.error(f"根据情绪调整规则时出错: {str(e)}")
        return {
            'sentiment_score': 0.0,
            'sentiment_level': 'neutral',
            'adjustments': SENTIMENT_ADJUSTMENTS['neutral'],
            'rules': {
                'SELL_RULE1': SELL_RULE1,
                'SELL_RULE2': SELL_RULE2,
                'SELL_RULE3': SELL_RULE3,
                'SELL_RULE4': SELL_RULE4,
                'SELL_RULE5': SELL_RULE5,
                'SELL_RULE6': SELL_RULE6,
                'SELL_RULE7': SELL_RULE7,
                'SELL_RULE8': SELL_RULE8,
                'SELL_RULE9': SELL_RULE9
            }
        }

def update_market_sentiment_indicators(market_data: Dict = None) -> bool:
    """
    更新市场情绪指标
    
    参数:
    market_data (dict): 市场数据，如果为None则自动获取
    
    返回:
    bool: 更新是否成功
    """
    try:
        if market_data is None:
            # 这里应该从实际数据源获取市场数据
            # 暂时使用模拟数据
            market_data = _get_market_data_simulation()
        
        # 更新各项指标
        MARKET_SENTIMENT_INDICATORS.update({
            'vix_level': market_data.get('vix_level', 20.0),
            'advance_decline': market_data.get('advance_decline', 1.0),
            'volume_ratio': market_data.get('volume_ratio', 1.0),
            'sector_rotation': market_data.get('sector_rotation', {}),
            'limit_up_count': market_data.get('limit_up_count', 0),
            'limit_down_count': market_data.get('limit_down_count', 0),
            'new_high_count': market_data.get('new_high_count', 0),
            'new_low_count': market_data.get('new_low_count', 0),
            'turnover_rate': market_data.get('turnover_rate', 0.04)
        })
        
        # 重新计算情绪得分
        sentiment_score = calculate_market_sentiment()
        
        logger.info(f"市场情绪指标更新完成，当前情绪得分: {sentiment_score:.2f} ({get_sentiment_level(sentiment_score)})")
        return True
        
    except Exception as e:
        logger.error(f"更新市场情绪指标时出错: {str(e)}")
        return False

def _get_market_data_simulation() -> Dict:
    """
    获取模拟市场数据（实际使用时应替换为真实数据源）
    
    返回:
    dict: 模拟市场数据
    """
    import random
    
    return {
        'vix_level': random.uniform(15, 35),
        'advance_decline': random.uniform(0.5, 2.0),
        'volume_ratio': random.uniform(0.8, 1.5),
        'sector_rotation': {
            '科技': random.uniform(-0.05, 0.05),
            '医药': random.uniform(-0.05, 0.05),
            '消费': random.uniform(-0.05, 0.05),
            '金融': random.uniform(-0.05, 0.05)
        },
        'limit_up_count': random.randint(0, 100),
        'limit_down_count': random.randint(0, 50),
        'new_high_count': random.randint(0, 200),
        'new_low_count': random.randint(0, 150),
        'turnover_rate': random.uniform(0.02, 0.08)
    }

class AdvancedSellStrategy:
    """
    高级卖出策略类 - 基于分时均线的9大核心规则
    """
    
    def __init__(self):
        """初始化高级卖出策略"""
        self.vwap_calculator = VWAPCalculator()
        self.data_manager = get_data_manager()
        
        # 股票状态缓存
        self.stock_states = {}  # 存储每只股票的状态信息
        self.ma_pressure_records = {}  # 记录均线压制情况
        self.seal_amount_records = {}  # 记录封单金额变化
        
        # 市场情绪相关
        self.sentiment_update_interval = 60  # 情绪指标更新间隔（秒）
        self.last_sentiment_update = None  # 上次情绪更新时间
        self.current_sentiment_adjustment = None  # 当前情绪调整参数
        
        # 初始化市场情绪指标
        self._initialize_market_sentiment()
        
        logger.info("高级卖出策略初始化完成（已集成市场情绪指标）")
    
    def check_sell_signals(self, stock_code: str) -> Optional[Dict]:
        """
        检查卖出信号（集成市场情绪调整）
        
        参数:
        stock_code (str): 股票代码
        
        返回:
        dict: 卖出信号信息，如果没有信号则返回None
        """
        try:
            # 更新市场情绪指标（如果需要）
            self._update_sentiment_if_needed()
            
            # 获取股票基础数据
            stock_data = self._get_stock_data(stock_code)
            if not stock_data:
                return None
            
            # 获取分时均线数据
            vwap_data = self.vwap_calculator.get_intraday_vwap_line(stock_code)
            if not vwap_data:
                logger.warning(f"无法获取 {stock_code} 的分时均线数据")
                return None
            
            # 更新股票状态
            self._update_stock_state(stock_code, stock_data, vwap_data)
            
            # 检查全局过滤条件
            if not self._check_global_filters(stock_code, stock_data):
                return None
            
            # 获取当前情绪调整后的规则
            adjusted_rules = self._get_sentiment_adjusted_rules()
            
            # 按优先级检查各个规则（使用调整后的规则）
            rules_to_check = [
                (self._check_rule6_limit_up_break, "规则6-炸板防御", adjusted_rules.get('SELL_RULE6', SELL_RULE6)),
                (self._check_rule7_max_drawdown, "规则7-最大回撤止损", adjusted_rules.get('SELL_RULE7', SELL_RULE7)),
                (self._check_rule8_tail_sell, "规则8-尾盘卖出", adjusted_rules.get('SELL_RULE8', SELL_RULE8)),
                (self._check_rule9_sector_linkage, "规则9-板块联动卖出", adjusted_rules.get('SELL_RULE9', SELL_RULE9)),
                (self._check_rule1_high_open_fall, "规则1-高开冲高回落", adjusted_rules.get('SELL_RULE1', SELL_RULE1)),
                (self._check_rule2_low_open_fall, "规则2-低开冲高回落", adjusted_rules.get('SELL_RULE2', SELL_RULE2)),
                (self._check_rule4_huge_rise_fall, "规则4-巨幅冲高回落", adjusted_rules.get('SELL_RULE4', SELL_RULE4)),
                (self._check_rule3_gain_fall, "规则3-涨幅达标回落", adjusted_rules.get('SELL_RULE3', SELL_RULE3)),
                (self._check_rule5_ma_pressure, "规则5-分时均线压制", adjusted_rules.get('SELL_RULE5', SELL_RULE5))
            ]
            
            for rule_func, rule_name, rule_config in rules_to_check:
                try:
                    signal = rule_func(stock_code, stock_data, vwap_data, rule_config)
                    if signal:
                        signal['rule'] = rule_name
                        signal['timestamp'] = datetime.now()
                        signal['sentiment_info'] = self._get_current_sentiment_info()
                        logger.info(f"🚨 {stock_code} 触发 {rule_name} (情绪: {signal['sentiment_info']['level']})")
                        return signal
                except Exception as e:
                    logger.error(f"检查 {rule_name} 时出错: {str(e)}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"检查 {stock_code} 卖出信号时出错: {str(e)}")
            return None
    
    def _initialize_market_sentiment(self):
        """
        初始化市场情绪指标
        """
        try:
            # 首次更新市场情绪指标
            update_market_sentiment_indicators()
            
            # 获取初始情绪调整参数
            self.current_sentiment_adjustment = adjust_rules_by_sentiment()
            self.last_sentiment_update = datetime.now()
            
            logger.info(f"市场情绪指标初始化完成，当前情绪: {self.current_sentiment_adjustment['sentiment_level']}")
            
        except Exception as e:
            logger.error(f"初始化市场情绪指标时出错: {str(e)}")
            # 使用默认中性情绪
            self.current_sentiment_adjustment = adjust_rules_by_sentiment(0.0)
    
    def _update_sentiment_if_needed(self):
        """
        如果需要则更新市场情绪指标
        """
        try:
            current_time = datetime.now()
            
            # 检查是否需要更新
            if (self.last_sentiment_update is None or 
                (current_time - self.last_sentiment_update).total_seconds() >= self.sentiment_update_interval):
                
                # 更新市场情绪指标
                if update_market_sentiment_indicators():
                    # 重新计算情绪调整参数
                    self.current_sentiment_adjustment = adjust_rules_by_sentiment()
                    self.last_sentiment_update = current_time
                    
                    logger.debug(f"市场情绪指标已更新，当前情绪: {self.current_sentiment_adjustment['sentiment_level']}")
                
        except Exception as e:
            logger.error(f"更新市场情绪指标时出错: {str(e)}")
    
    def _get_sentiment_adjusted_rules(self) -> Dict:
        """
        获取情绪调整后的规则
        
        返回:
        dict: 调整后的规则配置
        """
        if self.current_sentiment_adjustment and 'rules' in self.current_sentiment_adjustment:
            return self.current_sentiment_adjustment['rules']
        else:
            # 返回默认规则
            return {
                'SELL_RULE1': SELL_RULE1,
                'SELL_RULE2': SELL_RULE2,
                'SELL_RULE3': SELL_RULE3,
                'SELL_RULE4': SELL_RULE4,
                'SELL_RULE5': SELL_RULE5,
                'SELL_RULE6': SELL_RULE6,
                'SELL_RULE7': SELL_RULE7,
                'SELL_RULE8': SELL_RULE8,
                'SELL_RULE9': SELL_RULE9
            }
    
    def _get_current_sentiment_info(self) -> Dict:
        """
        获取当前市场情绪信息
        
        返回:
        dict: 情绪信息
        """
        if self.current_sentiment_adjustment:
            return {
                'score': self.current_sentiment_adjustment['sentiment_score'],
                'level': self.current_sentiment_adjustment['sentiment_level'],
                'adjustments': self.current_sentiment_adjustment['adjustments'],
                'last_update': self.last_sentiment_update.strftime('%H:%M:%S') if self.last_sentiment_update else 'N/A'
            }
        else:
            return {
                'score': 0.0,
                'level': 'neutral',
                'adjustments': SENTIMENT_ADJUSTMENTS['neutral'],
                'last_update': 'N/A'
            }
    
    def get_sentiment_status(self) -> Dict:
        """
        获取详细的市场情绪状态（供外部调用）
        
        返回:
        dict: 详细情绪状态
        """
        try:
            sentiment_info = self._get_current_sentiment_info()
            indicators = MARKET_SENTIMENT_INDICATORS.copy()
            
            return {
                'sentiment_score': sentiment_info['score'],
                'sentiment_level': sentiment_info['level'],
                'last_update': sentiment_info['last_update'],
                'indicators': indicators,
                'adjustments': sentiment_info['adjustments'],
                'next_update_in': max(0, self.sentiment_update_interval - 
                                    (datetime.now() - self.last_sentiment_update).total_seconds() 
                                    if self.last_sentiment_update else 0)
            }
            
        except Exception as e:
            logger.error(f"获取情绪状态时出错: {str(e)}")
            return {
                'sentiment_score': 0.0,
                'sentiment_level': 'neutral',
                'last_update': 'Error',
                'indicators': {},
                'adjustments': SENTIMENT_ADJUSTMENTS['neutral'],
                'next_update_in': 0
            }
    
    def _get_stock_data(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票基础数据
        
        参数:
        stock_code (str): 股票代码
        
        返回:
        dict: 股票数据
        """
        try:
            # 获取实时tick数据
            formatted_code = self._format_stock_code(stock_code)
            tick_data = xtdata.get_full_tick([formatted_code])
            
            if not tick_data or formatted_code not in tick_data:
                logger.warning(f"无法获取 {stock_code} 的实时数据")
                return None
            
            tick = tick_data[formatted_code]
            
            # 获取历史数据（用于计算开盘价、昨收价等）
            today = datetime.now().strftime('%Y%m%d')
            start_time = today + '093000'
            end_time = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # 获取1分钟K线数据
            minute_data = xtdata.get_market_data(
                field_list=['time', 'open', 'high', 'low', 'close', 'volume', 'amount'],
                stock_list=[formatted_code],
                period='1m',
                start_time=start_time,
                end_time=end_time
            )
            
            if not minute_data or 'close' not in minute_data:
                logger.warning(f"无法获取 {stock_code} 的分钟数据")
                return None
            
            # 获取昨日收盘价
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            yesterday_data = xtdata.get_market_data(
                field_list=['close'],
                stock_list=[formatted_code],
                period='1d',
                start_time=yesterday,
                end_time=yesterday
            )
            
            yesterday_close = 0
            if yesterday_data and 'close' in yesterday_data:
                yesterday_close_data = yesterday_data['close']
                if formatted_code in yesterday_close_data.index:
                    yesterday_close = float(yesterday_close_data.loc[formatted_code].iloc[-1])
            
            # 构建股票数据
            close_data = minute_data['close'].loc[formatted_code]
            high_data = minute_data['high'].loc[formatted_code]
            volume_data = minute_data['volume'].loc[formatted_code]
            
            current_price = float(tick.get('lastPrice', 0))
            open_price = float(close_data.iloc[0]) if len(close_data) > 0 else current_price
            high_price = float(high_data.max()) if len(high_data) > 0 else current_price
            total_volume = int(volume_data.sum()) if len(volume_data) > 0 else 0
            
            stock_data = {
                'stock_code': stock_code,
                'current_price': current_price,
                'open_price': open_price,
                'high_price': high_price,
                'yesterday_close': yesterday_close,
                'total_volume': total_volume,
                'bid_price': float(tick.get('bidPrice', [0])[0]),
                'ask_price': float(tick.get('askPrice', [0])[0]),
                'bid_volume': int(tick.get('bidVol', [0])[0]),
                'ask_volume': int(tick.get('askVol', [0])[0]),
                'timestamp': datetime.now()
            }
            
            return stock_data
            
        except Exception as e:
            logger.error(f"获取 {stock_code} 股票数据时出错: {str(e)}")
            return None
    
    def _update_stock_state(self, stock_code: str, stock_data: Dict, vwap_data: Dict):
        """
        更新股票状态信息
        
        参数:
        stock_code (str): 股票代码
        stock_data (dict): 股票数据
        vwap_data (dict): VWAP数据
        """
        if stock_code not in self.stock_states:
            self.stock_states[stock_code] = {
                'first_seen': datetime.now(),
                'high_price_today': stock_data['current_price'],
                'ma_pressure_count': 0,
                'last_ma_attempt_time': None,
                'below_ma_start_time': None,
                'seal_amount_history': [],
                'volume_history': []
            }
        
        state = self.stock_states[stock_code]
        current_price = stock_data['current_price']
        current_vwap = vwap_data['current_vwap']
        
        # 更新当日最高价
        if current_price > state['high_price_today']:
            state['high_price_today'] = current_price
        
        # 更新跌破均线时间
        if current_price < current_vwap:
            if state['below_ma_start_time'] is None:
                state['below_ma_start_time'] = datetime.now()
        else:
            state['below_ma_start_time'] = None
        
        # 更新成交量历史
        state['volume_history'].append({
            'time': datetime.now(),
            'volume': stock_data['total_volume'],
            'price': current_price
        })
        
        # 保持历史记录在合理范围内
        if len(state['volume_history']) > 100:
            state['volume_history'] = state['volume_history'][-50:]
    
    def _check_global_filters(self, stock_code: str, stock_data: Dict) -> bool:
        """
        检查全局过滤条件
        
        参数:
        stock_code (str): 股票代码
        stock_data (dict): 股票数据
        
        返回:
        bool: 是否通过过滤条件
        """
        try:
            # 检查交易金额
            current_price = stock_data['current_price']
            total_volume = stock_data['total_volume']
            trade_amount = current_price * total_volume
            
            if trade_amount < GLOBAL_FILTERS['min_trade_amount']:
                logger.debug(f"{stock_code} 交易金额不足: {trade_amount:,.0f}")
                return False
            
            # 检查开盘豁免时间
            current_time = datetime.now().time()
            for start_str, end_str in GLOBAL_FILTERS['time_exemptions']:
                start_time = datetime.strptime(start_str, '%H:%M').time()
                end_time = datetime.strptime(end_str, '%H:%M').time()
                if start_time <= current_time <= end_time:
                    logger.debug(f"{stock_code} 在豁免时间内: {current_time}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查 {stock_code} 全局过滤条件时出错: {str(e)}")
            return False
    
    def _check_rule1_high_open_fall(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则1: 高开冲高回落
        """
        if not SELL_RULE1['enable']:
            return None
        
        try:
            conditions = SELL_RULE1['conditions']
            current_price = stock_data['current_price']
            open_price = stock_data['open_price']
            high_price = stock_data['high_price']
            yesterday_close = stock_data['yesterday_close']
            current_vwap = vwap_data['current_vwap']
            
            # 检查是否高开
            if yesterday_close > 0:
                open_ratio = (open_price - yesterday_close) / yesterday_close
                if open_ratio < HIGH_OPEN_THRESHOLD:
                    return None
            
            # 检查最高价是否高于开盘价足够幅度
            if open_price > 0:
                rise_ratio = (high_price - open_price) / open_price
                if rise_ratio < conditions['rise_above_open']:
                    return None
            
            # 检查是否从最高点回落
            if high_price > 0:
                drawdown = (high_price - current_price) / high_price
                if drawdown < conditions['drawdown_from_high']:
                    return None
            
            # 检查是否跌破分时均线
            if current_price >= current_vwap:
                return None
            
            # 检查跌破均线时间
            state = self.stock_states.get(stock_code, {})
            below_ma_start = state.get('below_ma_start_time')
            if below_ma_start:
                elapsed = (datetime.now() - below_ma_start).total_seconds()
                if elapsed < conditions['ma_recovery_time']:
                    return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.8,
                'reason': f"高开冲高回落: 开盘涨{open_ratio:.1%}, 冲高{rise_ratio:.1%}, 回落{drawdown:.1%}, 跌破均线{elapsed:.0f}秒",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则1时出错: {str(e)}")
            return None
    
    def _check_rule2_low_open_fall(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则2: 低开冲高回落
        """
        if not SELL_RULE2['enable']:
            return None
        
        try:
            conditions = SELL_RULE2['conditions']
            current_price = stock_data['current_price']
            open_price = stock_data['open_price']
            high_price = stock_data['high_price']
            yesterday_close = stock_data['yesterday_close']
            current_vwap = vwap_data['current_vwap']
            
            # 检查是否低开
            if yesterday_close > 0:
                open_ratio = (open_price - yesterday_close) / yesterday_close
                if open_ratio > -LOW_OPEN_THRESHOLD:
                    return None
            
            # 检查最高价是否高于开盘价足够幅度
            if open_price > 0:
                rise_ratio = (high_price - open_price) / open_price
                if rise_ratio < conditions['rise_above_open']:
                    return None
            
            # 检查是否从最高点回落
            if high_price > 0:
                drawdown = (high_price - current_price) / high_price
                if drawdown < conditions['drawdown_from_high']:
                    return None
            
            # 检查是否跌破分时均线
            if current_price >= current_vwap:
                return None
            
            # 检查跌破均线时间
            state = self.stock_states.get(stock_code, {})
            below_ma_start = state.get('below_ma_start_time')
            elapsed = 0
            if below_ma_start:
                elapsed = (datetime.now() - below_ma_start).total_seconds()
                if elapsed < conditions['ma_recovery_time']:
                    return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.8,
                'reason': f"低开冲高回落: 开盘跌{abs(open_ratio):.1%}, 冲高{rise_ratio:.1%}, 回落{drawdown:.1%}, 跌破均线{elapsed:.0f}秒",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则2时出错: {str(e)}")
            return None
    
    def _check_rule3_gain_fall(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则3: 涨幅达标回落
        """
        if not SELL_RULE3['enable']:
            return None
        
        try:
            conditions = SELL_RULE3['conditions']
            current_price = stock_data['current_price']
            high_price = stock_data['high_price']
            yesterday_close = stock_data['yesterday_close']
            current_vwap = vwap_data['current_vwap']
            
            # 检查最高价涨幅是否达标
            if yesterday_close > 0:
                gain_ratio = (high_price - yesterday_close) / yesterday_close
                if gain_ratio < conditions['gain_from_yclose']:
                    return None
            
            # 检查是否从最高点回落
            if high_price > 0:
                drawdown = (high_price - current_price) / high_price
                if drawdown < conditions['drawdown_from_high']:
                    return None
            
            # 检查股价-均线乖离率
            if current_vwap > 0:
                ma_divergence = abs(current_price - current_vwap) / current_vwap
                if ma_divergence < conditions['ma_divergence']:
                    return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.7,
                'reason': f"涨幅达标回落: 最高涨{gain_ratio:.1%}, 回落{drawdown:.1%}, 乖离率{ma_divergence:.1%}",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则3时出错: {str(e)}")
            return None
    
    def _check_rule4_huge_rise_fall(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则4: 巨幅冲高回落
        """
        if not SELL_RULE4['enable']:
            return None
        
        try:
            conditions = SELL_RULE4['conditions']
            current_price = stock_data['current_price']
            high_price = stock_data['high_price']
            yesterday_close = stock_data['yesterday_close']
            current_vwap = vwap_data['current_vwap']
            
            # 检查最高价涨幅是否达到巨幅标准
            if yesterday_close > 0:
                gain_ratio = (high_price - yesterday_close) / yesterday_close
                if gain_ratio < conditions['gain_from_yclose']:
                    return None
            
            # 检查是否从最高点大幅回落
            if high_price > 0:
                drawdown = (high_price - current_price) / high_price
                if drawdown < conditions['drawdown_from_high']:
                    return None
            
            # 检查股价-均线乖离率
            if current_vwap > 0:
                ma_divergence = abs(current_price - current_vwap) / current_vwap
                if ma_divergence < conditions['ma_divergence']:
                    return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.9,
                'reason': f"巨幅冲高回落: 最高涨{gain_ratio:.1%}, 回落{drawdown:.1%}, 乖离率{ma_divergence:.1%}",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则4时出错: {str(e)}")
            return None
    
    def _check_rule5_ma_pressure(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则5: 分时均线压制
        """
        if not SELL_RULE5['enable']:
            return None
        
        try:
            conditions = SELL_RULE5['conditions']
            current_price = stock_data['current_price']
            current_vwap = vwap_data['current_vwap']
            
            # 检查是否接近均线但未突破
            if current_vwap > 0:
                distance_to_ma = abs(current_price - current_vwap) / current_vwap
                if distance_to_ma > conditions['ma_distance']:
                    return None
            
            # 检查上攻失败次数（这里简化处理，实际应该记录历史尝试）
            state = self.stock_states.get(stock_code, {})
            ma_pressure_count = state.get('ma_pressure_count', 0)
            
            # 如果当前价格接近但低于均线，增加压制计数
            if current_price < current_vwap and distance_to_ma <= conditions['ma_distance']:
                state['ma_pressure_count'] = ma_pressure_count + 1
                state['last_ma_attempt_time'] = datetime.now()
            
            if ma_pressure_count < conditions['ma_pressure_attempts']:
                return None
            
            # 检查均线方向（简化处理，通过VWAP序列判断）
            vwap_series = vwap_data.get('intraday_vwap_line', [])
            if len(vwap_series) >= 3:
                recent_vwap = vwap_series[-3:]
                if recent_vwap[-1] >= recent_vwap[0]:  # 均线不是向下
                    return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.6,
                'reason': f"分时均线压制: 上攻失败{ma_pressure_count}次, 距均线{distance_to_ma:.1%}",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则5时出错: {str(e)}")
            return None
    
    def _check_rule6_limit_up_break(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则6: 炸板防御
        """
        if not SELL_RULE6['enable']:
            return None
        
        try:
            conditions = SELL_RULE6['conditions']
            current_price = stock_data['current_price']
            yesterday_close = stock_data['yesterday_close']
            current_vwap = vwap_data['current_vwap']
            
            # 检查是否接近涨停价
            if yesterday_close > 0:
                limit_up_price = yesterday_close * 1.1  # 10%涨停
                if current_price < limit_up_price * 0.995:  # 不在涨停附近
                    return None
            
            # 检查封单金额（简化处理，使用买一档数据估算）
            bid_price = stock_data['bid_price']
            bid_volume = stock_data['bid_volume']
            seal_amount = bid_price * bid_volume
            
            if seal_amount > conditions['seal_amount']:
                return None
            
            # 检查距离均线距离
            if current_vwap > 0:
                distance_to_ma = abs(current_price - current_vwap) / current_vwap
                if distance_to_ma > conditions['ma_support']:
                    return None
            
            # 检查是否在早盘敏感时段
            current_time = datetime.now().time()
            morning_start = datetime.strptime("09:30", "%H:%M").time()
            morning_end = datetime.strptime("10:30", "%H:%M").time()
            is_morning_sensitive = morning_start <= current_time <= morning_end
            
            confidence = 0.9 if is_morning_sensitive else 0.7
            
            return {
                'signal_type': 'SELL',
                'confidence': confidence,
                'reason': f"炸板防御: 封单{seal_amount:,.0f}元, 距均线{distance_to_ma:.1%}, {'早盘敏感' if is_morning_sensitive else '非早盘'}",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则6时出错: {str(e)}")
            return None
    
    def _check_rule7_max_drawdown(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则7: 最大回撤止损
        """
        if not SELL_RULE7['enable']:
            return None
        
        try:
            conditions = SELL_RULE7['conditions']
            current_price = stock_data['current_price']
            current_vwap = vwap_data['current_vwap']
            
            # 获取当日最高价
            state = self.stock_states.get(stock_code, {})
            high_price_today = state.get('high_price_today', current_price)
            
            # 检查最大回撤
            if high_price_today > 0:
                drawdown = (high_price_today - current_price) / high_price_today
                if drawdown < conditions['max_drawdown']:
                    return None
            
            # 检查是否跌破分时均线
            if current_price >= current_vwap:
                return None
            
            # 检查跌破均线持续时间
            below_ma_start = state.get('below_ma_start_time')
            if below_ma_start:
                elapsed = (datetime.now() - below_ma_start).total_seconds()
                if elapsed < conditions['time_elapsed']:
                    return None
            else:
                return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.95,
                'reason': f"最大回撤止损: 从高点{high_price_today:.2f}回撤{drawdown:.1%}, 跌破均线{elapsed:.0f}秒",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则7时出错: {str(e)}")
            return None
    
    def _check_rule8_tail_sell(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则8: 尾盘卖出
        """
        if not SELL_RULE8['enable']:
            return None
        
        try:
            conditions = SELL_RULE8['conditions']
            current_price = stock_data['current_price']
            yesterday_close = stock_data['yesterday_close']
            current_vwap = vwap_data['current_vwap']
            
            # 检查是否在尾盘时段
            current_time = datetime.now().time()
            start_time = datetime.strptime(conditions['time_window'][0], "%H:%M").time()
            end_time = datetime.strptime(conditions['time_window'][1], "%H:%M").time()
            
            if not (start_time <= current_time <= end_time):
                return None
            
            # 检查是否未涨停
            if yesterday_close > 0:
                limit_up_price = yesterday_close * 1.1
                if current_price >= limit_up_price * 0.995:  # 接近涨停
                    return None
            
            # 检查股价是否低于均线
            if current_vwap > 0:
                price_below_ma = (current_vwap - current_price) / current_vwap
                if price_below_ma < conditions['price_below_ma']:
                    return None
            
            return {
                'signal_type': 'SELL',
                'confidence': 0.6,
                'reason': f"尾盘卖出: 时间{current_time}, 低于均线{price_below_ma:.1%}, 未涨停",
                'price': current_price,
                'vwap': current_vwap
            }
            
        except Exception as e:
            logger.error(f"检查规则8时出错: {str(e)}")
            return None
    
    def _check_rule9_sector_linkage(self, stock_code: str, stock_data: Dict, vwap_data: Dict) -> Optional[Dict]:
        """
        规则9: 板块联动卖出（简化实现）
        """
        if not SELL_RULE9['enable']:
            return None
        
        try:
            conditions = SELL_RULE9['conditions']
            current_price = stock_data['current_price']
            current_vwap = vwap_data['current_vwap']
            
            # 检查是否跌破分时均线
            if current_price >= current_vwap:
                return None
            
            # 板块联动检查（简化处理，实际需要板块数据）
            # 这里可以根据实际情况接入板块指数数据
            # 暂时返回None，表示此规则需要更多数据支持
            
            return None
            
        except Exception as e:
            logger.error(f"检查规则9时出错: {str(e)}")
            return None
    
    def _format_stock_code(self, stock_code: str) -> str:
        """
        将股票代码格式化为带市场后缀的格式
        
        参数:
        stock_code (str): 原始股票代码
        
        返回:
        str: 带市场后缀的股票代码
        """
        if not stock_code or len(stock_code) < 6:
            return stock_code
            
        # 如果已经包含后缀，直接返回
        if '.' in stock_code:
            return stock_code
            
        # 处理ETF和股票代码
        prefix_2 = stock_code[:2]
        prefix_1 = stock_code[:1]
        
        # ETF判断
        if prefix_2 in ['51', '56', '58']:
            return f"{stock_code}.SH"
        elif prefix_2 in ['15', '16', '17', '18'] or stock_code.startswith('159'):
            return f"{stock_code}.SZ"
        # 普通股票判断
        elif prefix_1 in ['0', '3']:
            return f"{stock_code}.SZ"
        elif prefix_1 in ['6', '5', '9']:
            return f"{stock_code}.SH"
        elif prefix_1 in ['4', '8']:
            return f"{stock_code}.BJ"
        else:
            logger.warning(f"无法识别股票代码 {stock_code} 的市场，默认使用深圳市场")
            return f"{stock_code}.SZ"

class PositionMonitorSell2:
    """
    持仓监控卖出2.0类 - 集成高级卖出策略
    """
    
    def __init__(self):
        """初始化持仓监控卖出2.0"""
        self.data_manager = get_data_manager()
        self.position_manager = get_position_manager()
        self.trading_executor = get_trading_executor()
        self.sell_strategy = AdvancedSellStrategy()
        
        # 监控控制
        self.monitor_thread = None
        self.stop_flag = False
        self.monitor_interval = 1  # 监控间隔（秒）
        
        # 统计信息
        self.stats = {
            'start_time': None,
            'total_checks': 0,
            'sell_signals': 0,
            'successful_sells': 0,
            'failed_sells': 0,
            'rule_triggers': {}
        }
        
        logger.info("持仓监控卖出2.0模块初始化完成")
    
    def start_monitoring(self):
        """启动持仓监控"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("持仓监控线程已在运行")
            return
        
        logger.info("="*60)
        logger.info("启动持仓监控卖出2.0系统")
        logger.info("="*60)
        
        # 显示当前配置
        self._show_config()
        
        # 显示当前持仓
        self._show_current_positions()
        
        # 启动监控线程
        self.stop_flag = False
        self.stats['start_time'] = datetime.now()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("持仓监控线程已启动，按 Ctrl+C 停止监控")
        
        try:
            # 主线程等待，定期显示统计信息
            while not self.stop_flag:
                time.sleep(30)  # 每30秒显示一次统计
                self._show_stats()
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在停止监控...")
            self.stop_monitoring()
    
    def stop_monitoring(self):
        """停止持仓监控"""
        self.stop_flag = True
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("持仓监控已停止")
        self._show_final_stats()
    
    def _monitor_loop(self):
        """监控循环主函数"""
        logger.info("持仓监控循环开始")
        
        while not self.stop_flag:
            try:
                # 检查是否在交易时间
                if not self._is_trading_time():
                    logger.debug("非交易时间，暂停监控")
                    time.sleep(60)  # 非交易时间每分钟检查一次
                    continue
                
                # 检查是否启用卖出功能
                if not config.ENABLE_ALLOW_SELL:
                    logger.debug("卖出功能已禁用，跳过监控")
                    time.sleep(10)
                    continue
                
                # 获取当前持仓
                positions = self.position_manager.get_all_positions()
                if positions is None or (isinstance(positions, pd.DataFrame) and positions.empty) or (isinstance(positions, dict) and not positions):
                    logger.debug("当前无持仓，无需监控")
                    time.sleep(10)
                    continue
                
                # 监控每只持仓股票
                if isinstance(positions, pd.DataFrame):
                    stock_codes = positions['stock_code'].tolist()
                else:
                    stock_codes = list(positions.keys())
                    
                for stock_code in stock_codes:
                    if self.stop_flag:
                        break
                    
                    try:
                        self._monitor_single_stock(stock_code)
                        self.stats['total_checks'] += 1
                    except Exception as e:
                        logger.error(f"监控 {stock_code} 时出错: {str(e)}")
                
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                logger.error(f"监控循环出错: {str(e)}")
                time.sleep(5)
        
        logger.info("持仓监控循环结束")
    
    def _monitor_single_stock(self, stock_code: str):
        """监控单只股票"""
        try:
            # 获取持仓信息
            position = self.position_manager.get_position(stock_code)
            if not position:
                return
            
            # 检查卖出信号
            sell_signal = self.sell_strategy.check_sell_signals(stock_code)
            if sell_signal:
                self.stats['sell_signals'] += 1
                rule_name = sell_signal.get('rule', '未知规则')
                
                # 统计规则触发次数
                if rule_name not in self.stats['rule_triggers']:
                    self.stats['rule_triggers'][rule_name] = 0
                self.stats['rule_triggers'][rule_name] += 1
                
                logger.warning(f"🚨 {stock_code} 触发卖出信号: {rule_name}")
                logger.info(f"   信号详情: {sell_signal.get('reason', '')}")
                logger.info(f"   信号强度: {sell_signal.get('confidence', 0):.1%}")
                
                # 执行卖出
                if self._execute_sell_order(stock_code, position, sell_signal):
                    self.stats['successful_sells'] += 1
                    logger.info(f"✅ {stock_code} 卖出成功")
                else:
                    self.stats['failed_sells'] += 1
                    logger.error(f"❌ {stock_code} 卖出失败")
            
        except Exception as e:
            logger.error(f"监控 {stock_code} 时出错: {str(e)}")
    
    def _execute_sell_order(self, stock_code: str, position: dict, sell_signal: dict) -> bool:
        """执行卖出订单"""
        try:
            # 获取持仓数量
            available_volume = position.get('available', 0)
            if available_volume <= 0:
                logger.warning(f"{stock_code} 可用持仓为0，无法卖出")
                return False
            
            # 获取当前价格
            current_price = sell_signal.get('price', 0)
            if current_price <= 0:
                latest_data = self.data_manager.get_latest_data(stock_code)
                if not latest_data:
                    logger.error(f"无法获取 {stock_code} 最新价格")
                    return False
                current_price = latest_data.get('lastPrice', 0)
            
            if current_price <= 0:
                logger.error(f"{stock_code} 当前价格无效: {current_price}")
                return False
            
            # 记录卖出前信息
            cost_price = position.get('cost_price', 0)
            profit_ratio = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 else 0
            
            logger.info(f"准备卖出 {stock_code}:")
            logger.info(f"  - 触发规则: {sell_signal.get('rule', '')}")
            logger.info(f"  - 信号强度: {sell_signal.get('confidence', 0):.1%}")
            logger.info(f"  - 持仓数量: {available_volume}")
            logger.info(f"  - 成本价: {cost_price:.2f}")
            logger.info(f"  - 当前价: {current_price:.2f}")
            logger.info(f"  - 分时均线: {sell_signal.get('vwap', 0):.2f}")
            logger.info(f"  - 盈亏比例: {profit_ratio:.2f}%")
            
            # 执行卖出（全仓卖出）
            if config.ENABLE_SIMULATION_MODE:
                # 模拟交易模式
                result = self.position_manager.simulate_sell_position(
                    stock_code=stock_code,
                    sell_volume=available_volume,
                    sell_price=current_price,
                    sell_type='full'
                )
                if result:
                    logger.info(f"[模拟交易] {stock_code} 卖出成功")
                    return True
                else:
                    logger.error(f"[模拟交易] {stock_code} 卖出失败")
                    return False
            else:
                # 实盘交易模式
                result = self.trading_executor.sell_stock(
                    stock_code=stock_code,
                    volume=available_volume,
                    price=current_price,
                    strategy=f"监控卖出2.0-{sell_signal.get('rule', '')}"
                )
                if result:
                    logger.info(f"[实盘交易] {stock_code} 卖出委托提交成功，订单ID: {result}")
                    return True
                else:
                    logger.error(f"[实盘交易] {stock_code} 卖出失败，未获取到订单ID")
                    return False
            
        except Exception as e:
            logger.error(f"执行 {stock_code} 卖出订单时出错: {str(e)}")
            return False
    
    def _show_config(self):
        """显示当前配置"""
        logger.info("当前卖出策略2.0配置:")
        logger.info(f"  - 模拟交易模式: {config.ENABLE_SIMULATION_MODE}")
        logger.info(f"  - 允许卖出: {config.ENABLE_ALLOW_SELL}")
        logger.info(f"  - 监控间隔: {self.monitor_interval}秒")
        logger.info("")
        logger.info("9大核心卖出规则配置:")
        logger.info(f"  规则1 - 高开冲高回落: {'启用' if SELL_RULE1['enable'] else '禁用'}")
        logger.info(f"  规则2 - 低开冲高回落: {'启用' if SELL_RULE2['enable'] else '禁用'}")
        logger.info(f"  规则3 - 涨幅达标回落: {'启用' if SELL_RULE3['enable'] else '禁用'}")
        logger.info(f"  规则4 - 巨幅冲高回落: {'启用' if SELL_RULE4['enable'] else '禁用'}")
        logger.info(f"  规则5 - 分时均线压制: {'启用' if SELL_RULE5['enable'] else '禁用'}")
        logger.info(f"  规则6 - 炸板防御: {'启用' if SELL_RULE6['enable'] else '禁用'}")
        logger.info(f"  规则7 - 最大回撤止损: {'启用' if SELL_RULE7['enable'] else '禁用'}")
        logger.info(f"  规则8 - 尾盘卖出: {'启用' if SELL_RULE8['enable'] else '禁用'}")
        logger.info(f"  规则9 - 板块联动卖出: {'启用' if SELL_RULE9['enable'] else '禁用'}")
        logger.info("")
        logger.info("核心特性:")
        logger.info("  - 基于VWAP分时均线判断")
        logger.info("  - 动态阈值调整")
        logger.info("  - 龙头股特殊处理")
        logger.info("  - 三维度时间敏感")
        logger.info("")
    
    def _show_current_positions(self):
        """显示当前持仓（复用原有逻辑）"""
        try:
            positions = self.position_manager.get_all_positions()
            if positions is None or (hasattr(positions, 'empty') and positions.empty) or (isinstance(positions, dict) and not positions):
                logger.info("当前无持仓")
                return
            
            # 初始化累计变量
            total_profit = 0
            total_cost = 0
            total_market_value = 0

            # 处理DataFrame格式的持仓数据
            if hasattr(positions, 'iterrows'):
                positions_count = len(positions)
                logger.info(f"{Colors.BLUE}{Colors.BOLD}📊 当前持仓 ({positions_count}只):{Colors.END}")
                logger.info(f"{Colors.BLUE}{'=' * 120}{Colors.END}")
                logger.info(f"{Colors.BOLD}{Colors.UNDERLINE}{'股票代码':<8} {'股票名称':<10} {'数量':<8} {'成本价':<8} {'当前价':<8} {'市值':<12} {'盈亏':<12} {'盈亏率':<8} {'分时均线':<8}{Colors.END}")
                logger.info(f"{Colors.BLUE}{'-' * 120}{Colors.END}")
                
                for index, row in positions.iterrows():
                    stock_code = row['stock_code']
                    stock_name = row.get('stock_name', '未知')
                    volume = row.get('volume', 0)
                    cost_price = row.get('cost_price', 0)
                    
                    # 获取实时行情
                    latest_data = self.data_manager.get_latest_data(stock_code)
                    if latest_data:
                        current_price = latest_data.get('lastPrice', 0)
                    else:
                        current_price = 0
                    
                    # 获取分时均线
                    vwap_data = self.sell_strategy.vwap_calculator.get_intraday_vwap_line(stock_code)
                    current_vwap = vwap_data.get('current_vwap', 0) if vwap_data else 0
                    
                    # 计算盈亏
                    market_value = current_price * volume
                    cost_value = cost_price * volume
                    profit = market_value - cost_value
                    profit_ratio = (profit / cost_value * 100) if cost_value > 0 else 0
                    
                    # 累计统计
                    total_cost += cost_value
                    total_market_value += market_value
                    total_profit += profit
                    
                    # 根据盈亏设置颜色
                    if profit > 0:
                        color = Colors.GREEN
                    elif profit < 0:
                        color = Colors.RED
                    else:
                        color = Colors.YELLOW
                    
                    # 显示持仓信息
                    logger.info(f"{Colors.CYAN}{stock_code:<8}{Colors.END} {stock_name:<10} {volume:<8} "
                              f"{cost_price:<8.2f} {current_price:<8.2f} {market_value:<12.2f} "
                              f"{color}{profit:<12.2f}{Colors.END} {color}{profit_ratio:<8.2f}%{Colors.END} "
                              f"{current_vwap:<8.2f}")
            
            # 处理字典格式的持仓数据
            elif isinstance(positions, dict):
                positions_count = len(positions)
                logger.info(f"{Colors.BLUE}{Colors.BOLD}📊 当前持仓 ({positions_count}只):{Colors.END}")
                logger.info(f"{Colors.BLUE}{'=' * 120}{Colors.END}")
                logger.info(f"{Colors.BOLD}{Colors.UNDERLINE}{'股票代码':<8} {'股票名称':<10} {'数量':<8} {'成本价':<8} {'当前价':<8} {'市值':<12} {'盈亏':<12} {'盈亏率':<8} {'分时均线':<8}{Colors.END}")
                logger.info(f"{Colors.BLUE}{'-' * 120}{Colors.END}")
                
                for stock_code, position_info in positions.items():
                    stock_name = position_info.get('stock_name', '未知')
                    volume = position_info.get('volume', 0)
                    cost_price = position_info.get('cost_price', 0)
                    
                    # 获取实时行情
                    latest_data = self.data_manager.get_latest_data(stock_code)
                    if latest_data:
                        current_price = latest_data.get('lastPrice', 0)
                    else:
                        current_price = 0
                    
                    # 获取分时均线
                    vwap_data = self.sell_strategy.vwap_calculator.get_intraday_vwap_line(stock_code)
                    current_vwap = vwap_data.get('current_vwap', 0) if vwap_data else 0
                    
                    # 计算盈亏
                    market_value = current_price * volume
                    cost_value = cost_price * volume
                    profit = market_value - cost_value
                    profit_ratio = (profit / cost_value * 100) if cost_value > 0 else 0
                    
                    # 累计统计
                    total_cost += cost_value
                    total_market_value += market_value
                    total_profit += profit
                    
                    # 根据盈亏设置颜色
                    if profit > 0:
                        color = Colors.GREEN
                    elif profit < 0:
                        color = Colors.RED
                    else:
                        color = Colors.YELLOW
                    
                    # 显示持仓信息
                    logger.info(f"{Colors.CYAN}{stock_code:<8}{Colors.END} {stock_name:<10} {volume:<8} "
                              f"{cost_price:<8.2f} {current_price:<8.2f} {market_value:<12.2f} "
                              f"{color}{profit:<12.2f}{Colors.END} {color}{profit_ratio:<8.2f}%{Colors.END} "
                              f"{current_vwap:<8.2f}")
            
            # 显示汇总信息
            total_profit_ratio = (total_profit / total_cost * 100) if total_cost > 0 else 0
            summary_color = Colors.GREEN if total_profit > 0 else Colors.RED if total_profit < 0 else Colors.YELLOW
            
            logger.info(f"{Colors.BLUE}{'-' * 120}{Colors.END}")
            logger.info(f"{Colors.BOLD}📈 持仓汇总:{Colors.END}")
            logger.info(f"  总成本: {Colors.WHITE}{total_cost:,.2f}{Colors.END}")
            logger.info(f"  总市值: {Colors.WHITE}{total_market_value:,.2f}{Colors.END}")
            logger.info(f"  总盈亏: {summary_color}{total_profit:,.2f}{Colors.END}")
            logger.info(f"  盈亏率: {summary_color}{total_profit_ratio:.2f}%{Colors.END}")
            logger.info(f"{Colors.BLUE}{'=' * 120}{Colors.END}")
            
        except Exception as e:
            logger.error(f"显示当前持仓时出错: {str(e)}")
    
    def _show_stats(self):
        """显示监控统计信息"""
        if not self.stats['start_time']:
            return
        
        elapsed = datetime.now() - self.stats['start_time']
        elapsed_str = str(elapsed).split('.')[0]  # 去掉微秒
        
        logger.info(f"{Colors.MAGENTA}📊 监控统计 (运行时间: {elapsed_str}):{Colors.END}")
        logger.info(f"  检查次数: {self.stats['total_checks']}")
        logger.info(f"  卖出信号: {self.stats['sell_signals']}")
        logger.info(f"  成功卖出: {self.stats['successful_sells']}")
        logger.info(f"  失败卖出: {self.stats['failed_sells']}")
        
        if self.stats['rule_triggers']:
            logger.info("  规则触发统计:")
            for rule, count in self.stats['rule_triggers'].items():
                logger.info(f"    {rule}: {count}次")
        
        logger.info("")
    
    def _show_final_stats(self):
        """显示最终统计信息"""
        if not self.stats['start_time']:
            return
        
        elapsed = datetime.now() - self.stats['start_time']
        elapsed_str = str(elapsed).split('.')[0]
        
        logger.info(f"{Colors.BLUE}{'=' * 60}{Colors.END}")
        logger.info(f"{Colors.BOLD}{Colors.BLUE}📊 最终监控统计报告{Colors.END}")
        logger.info(f"{Colors.BLUE}{'=' * 60}{Colors.END}")
        logger.info(f"运行时间: {elapsed_str}")
        logger.info(f"总检查次数: {self.stats['total_checks']}")
        logger.info(f"卖出信号数: {self.stats['sell_signals']}")
        logger.info(f"成功卖出数: {self.stats['successful_sells']}")
        logger.info(f"失败卖出数: {self.stats['failed_sells']}")
        
        if self.stats['sell_signals'] > 0:
            success_rate = self.stats['successful_sells'] / self.stats['sell_signals'] * 100
            logger.info(f"卖出成功率: {success_rate:.1f}%")
        
        if self.stats['rule_triggers']:
            logger.info("\n规则触发详情:")
            for rule, count in sorted(self.stats['rule_triggers'].items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {rule}: {count}次")
        
        logger.info(f"{Colors.BLUE}{'=' * 60}{Colors.END}")
    
    def _is_trading_time(self) -> bool:
        """
        判断是否为交易时间
        
        返回:
        bool: 是否为交易时间
        """
        now = datetime.now()
        current_time = now.time()
        current_weekday = now.weekday()
        
        # 检查是否为工作日（周一到周五）
        if current_weekday >= 5:  # 周六、周日
            return False
        
        # 检查是否在交易时间段内
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()
        
        is_morning_session = morning_start <= current_time <= morning_end
        is_afternoon_session = afternoon_start <= current_time <= afternoon_end
        
        return is_morning_session or is_afternoon_session

def main():
    """主函数"""
    try:
        logger.info("启动持仓监控卖出2.0测试程序")
        
        # 连接行情服务
        logger.info("正在连接行情服务...")
        if not xtdata.connect():
            logger.error("连接行情服务失败")
            return
        
        logger.info("行情服务连接成功")
        
        # 创建监控实例
        monitor = PositionMonitorSell2()
        
        # 启动监控
        monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
    finally:
        # 断开行情连接
        try:
            xtdata.disconnect()
            logger.info("行情服务连接已断开")
        except:
            pass
        
        logger.info("程序结束")

if __name__ == "__main__":
    main()