# -*- coding: utf-8 -*-
"""
卖出策略模块 - 实现高级卖出规则
功能包括：
1. 高开/低开后回落卖出策略
2. 涨停炸板监控
3. 尾盘定时卖出
4. 最大回撤保护
5. 委托撤单重下机制
6. 多股票支持
"""

import time
import threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

import config
from logger import get_logger
from data_manager import get_data_manager
from position_manager import get_position_manager
from trading_executor import get_trading_executor

# 获取logger
logger = get_logger("sell_strategy")

class SellStrategy:
    """高级卖出策略类，实现多种卖出规则"""
    
    def __init__(self):
        """初始化卖出策略"""
        self.data_manager = get_data_manager()
        self.position_manager = get_position_manager()
        self.trading_executor = get_trading_executor()
        
        # 策略运行控制
        self.monitor_thread = None
        self.stop_flag = False
        
        # 股票状态跟踪
        self.stock_states = {}  # 存储每只股票的状态信息
        self.pending_orders = {}  # 待处理的委托订单
        self.last_check_time = {}
        
        # 防止频繁交易的冷却时间
        self.trade_cooldown = {}  # 交易冷却时间记录
        
        logger.info("卖出策略模块初始化完成")
    
    def start_monitor(self):
        """启动卖出策略监控线程"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("卖出策略监控线程已在运行")
            return
        
        self.stop_flag = False
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("卖出策略监控线程已启动")
    
    def stop_monitoring(self):
        """停止卖出策略监控线程"""
        self.stop_flag = True
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("卖出策略监控线程已停止")
    
    def start_monitoring(self):
        """启动卖出策略监控线程（别名方法）"""
        self.start_monitor()
    
    def check_sell_signals(self, stock_code: str) -> Optional[dict]:
        """检查单只股票的卖出信号（供strategy.py调用）"""
        try:
            # 检查冷却时间
            if self._is_in_cooldown(stock_code):
                return None
            
            # 获取持仓信息
            position = self.position_manager.get_position(stock_code)
            if not position:
                return None
            
            # 获取最新行情数据
            latest_data = self.data_manager.get_latest_data(stock_code)
            if not latest_data:
                return None
            
            current_price = latest_data.get('lastPrice', 0)
            if current_price <= 0:
                return None
            
            # 获取今日开盘价和最高价
            today_data = self._get_today_market_data(stock_code)
            if not today_data:
                return None
            
            open_price = today_data.get('open', 0)
            high_price = today_data.get('high', 0)
            
            # 初始化股票状态
            if stock_code not in self.stock_states:
                self.stock_states[stock_code] = {
                    'today_high': high_price,
                    'max_drawdown': 0.0,
                    'last_price': current_price,
                    'sell_triggered': False
                }
            
            # 更新股票状态
            state = self.stock_states[stock_code]
            state['today_high'] = max(state['today_high'], high_price)
            
            # 计算回撤
            if state['today_high'] > 0:
                current_drawdown = (state['today_high'] - current_price) / state['today_high']
                state['max_drawdown'] = max(state['max_drawdown'], current_drawdown)
            
            # 检查各个规则
            rules_to_check = [
                (self._check_rule1, "规则1-高开回落"),
                (self._check_rule2, "规则2-低开回落"),
                (self._check_rule3, "规则3-低开涨幅回落"),
                (self._check_rule4, "规则4-通用涨幅回落"),
                (self._check_rule6, "规则6-涨停炸板"),
                (self._check_rule8, "规则8-最大回撤")
            ]
            
            for rule_func, rule_name in rules_to_check:
                if rule_func == self._check_rule6:
                    # 规则6需要传入latest_data
                    if rule_func(stock_code, latest_data, position):
                        return {'rule': rule_name, 'stock_code': stock_code}
                elif rule_func == self._check_rule8:
                    # 规则8只需要传入position
                    if rule_func(stock_code, position):
                        return {'rule': rule_name, 'stock_code': stock_code}
                else:
                    # 规则1-4需要传入价格参数
                    if rule_func(stock_code, open_price, high_price, current_price, position):
                        return {'rule': rule_name, 'stock_code': stock_code}
            
            # 检查尾盘卖出（规则5）
            if self._check_rule5(stock_code, position):
                return {'rule': '规则5-尾盘卖出', 'stock_code': stock_code}
            
            return None
            
        except Exception as e:
            logger.error(f"检查 {stock_code} 卖出信号时出错: {str(e)}")
            return None
    
    def _monitor_loop(self):
        """监控循环主函数"""
        logger.info("卖出策略监控循环开始")
        
        while not self.stop_flag:
            try:
                # 检查是否启用卖出策略
                if not config.ENABLE_ALLOW_SELL:
                    time.sleep(5)
                    continue
                
                # 获取所有持仓股票
                positions = self.position_manager.get_all_positions()
                
                for stock_code, position in positions.items():
                    if self.stop_flag:
                        break
                    
                    try:
                        # 执行各种卖出策略检查
                        self._check_all_sell_rules(stock_code, position)
                        
                        # 检查待处理委托
                        self._check_pending_orders(stock_code)
                        
                    except Exception as e:
                        logger.error(f"检查 {stock_code} 卖出策略时出错: {str(e)}")
                
                # 检查尾盘卖出
                self._check_end_of_day_sell()
                
                time.sleep(config.SELL_STRATEGY_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"卖出策略监控循环出错: {str(e)}")
                time.sleep(5)
        
        logger.info("卖出策略监控循环结束")
    
    def _check_all_sell_rules(self, stock_code: str, position: dict):
        """检查所有卖出规则"""
        try:
            # 获取最新行情数据
            latest_data = self.data_manager.get_latest_data(stock_code)
            if not latest_data:
                return
            
            current_price = latest_data.get('lastPrice', 0)
            if current_price <= 0:
                return
            
            # 获取今日开盘价和最高价
            today_data = self._get_today_market_data(stock_code)
            if not today_data:
                return
            
            open_price = today_data.get('open', 0)
            high_price = today_data.get('high', 0)
            
            # 初始化股票状态
            if stock_code not in self.stock_states:
                self.stock_states[stock_code] = {
                    'today_high': high_price,
                    'max_drawdown': 0.0,
                    'last_price': current_price,
                    'sell_triggered': False
                }
            
            # 更新股票状态
            state = self.stock_states[stock_code]
            state['today_high'] = max(state['today_high'], high_price)
            
            # 计算回撤
            if state['today_high'] > 0:
                current_drawdown = (state['today_high'] - current_price) / state['today_high']
                state['max_drawdown'] = max(state['max_drawdown'], current_drawdown)
            
            # 规则1: 高开 + 最高价高于开盘价N% + 最高点回落M%卖出
            if self._check_rule1(stock_code, open_price, high_price, current_price, position):
                return
            
            # 规则2: 低开 + 最高价高于开盘价N% + 最高点回落M%卖出
            if self._check_rule2(stock_code, open_price, high_price, current_price, position):
                return
            
            # 规则3: 低开 + 最高价涨幅大于N% + 最高点回落M%卖出
            if self._check_rule3(stock_code, open_price, high_price, current_price, position):
                return
            
            # 规则4: 不论高低开 + 最高价涨幅大于N% + 最高点回落M%卖出
            if self._check_rule4(stock_code, open_price, high_price, current_price, position):
                return
            
            # 规则6: 涨停炸板前根据封单金额自动卖出
            if self._check_rule6(stock_code, latest_data, position):
                return
            
            # 规则8: 最大回撤达到x%，就卖出
            if self._check_rule8(stock_code, position):
                return
            
            # 更新最后价格
            state['last_price'] = current_price
            
        except Exception as e:
            logger.error(f"检查 {stock_code} 所有卖出规则时出错: {str(e)}")
    
    def _check_rule1(self, stock_code: str, open_price: float, high_price: float, 
                     current_price: float, position: dict) -> bool:
        """规则1: 高开 + 最高价高于开盘价N% + 最高点回落M%卖出"""
        try:
            yesterday_close = self._get_yesterday_close(stock_code)
            if not yesterday_close:
                return False
            
            # 检查是否高开
            if open_price <= yesterday_close:
                return False
            
            # 检查最高价是否高于开盘价N%
            price_rise_ratio = (high_price - open_price) / open_price
            if price_rise_ratio < config.SELL_RULE1_RISE_THRESHOLD:
                return False
            
            # 检查是否从最高点回落M%
            drawdown_ratio = (high_price - current_price) / high_price
            if drawdown_ratio >= config.SELL_RULE1_DRAWDOWN_THRESHOLD:
                logger.info(f"[规则1] {stock_code} 触发卖出: 高开后涨{price_rise_ratio:.2%}，回落{drawdown_ratio:.2%}")
                return self._execute_sell(stock_code, position, "规则1-高开回落")
            
            return False
            
        except Exception as e:
            logger.error(f"检查规则1时出错: {str(e)}")
            return False
    
    def _check_rule2(self, stock_code: str, open_price: float, high_price: float, 
                     current_price: float, position: dict) -> bool:
        """规则2: 低开 + 最高价高于开盘价N% + 最高点回落M%卖出"""
        try:
            yesterday_close = self._get_yesterday_close(stock_code)
            if not yesterday_close:
                return False
            
            # 检查是否低开
            if open_price >= yesterday_close:
                return False
            
            # 检查最高价是否高于开盘价N%
            price_rise_ratio = (high_price - open_price) / open_price
            if price_rise_ratio < config.SELL_RULE2_RISE_THRESHOLD:
                return False
            
            # 检查是否从最高点回落M%
            drawdown_ratio = (high_price - current_price) / high_price
            if drawdown_ratio >= config.SELL_RULE2_DRAWDOWN_THRESHOLD:
                logger.info(f"[规则2] {stock_code} 触发卖出: 低开后涨{price_rise_ratio:.2%}，回落{drawdown_ratio:.2%}")
                return self._execute_sell(stock_code, position, "规则2-低开回落")
            
            return False
            
        except Exception as e:
            logger.error(f"检查规则2时出错: {str(e)}")
            return False
    
    def _check_rule3(self, stock_code: str, open_price: float, high_price: float, 
                     current_price: float, position: dict) -> bool:
        """规则3: 低开 + 最高价涨幅大于N% + 最高点回落M%卖出"""
        try:
            yesterday_close = self._get_yesterday_close(stock_code)
            if not yesterday_close:
                return False
            
            # 检查是否低开
            if open_price >= yesterday_close:
                return False
            
            # 检查最高价涨幅是否大于N%（相对昨收）
            price_gain_ratio = (high_price - yesterday_close) / yesterday_close
            if price_gain_ratio < config.SELL_RULE3_GAIN_THRESHOLD:
                return False
            
            # 检查是否从最高点回落M%
            drawdown_ratio = (high_price - current_price) / high_price
            if drawdown_ratio >= config.SELL_RULE3_DRAWDOWN_THRESHOLD:
                logger.info(f"[规则3] {stock_code} 触发卖出: 低开涨幅{price_gain_ratio:.2%}，回落{drawdown_ratio:.2%}")
                return self._execute_sell(stock_code, position, "规则3-低开涨幅回落")
            
            return False
            
        except Exception as e:
            logger.error(f"检查规则3时出错: {str(e)}")
            return False
    
    def _check_rule4(self, stock_code: str, open_price: float, high_price: float, 
                     current_price: float, position: dict) -> bool:
        """规则4: 不论高低开 + 最高价涨幅大于N% + 最高点回落M%卖出"""
        try:
            yesterday_close = self._get_yesterday_close(stock_code)
            if not yesterday_close:
                return False
            
            # 检查最高价涨幅是否大于N%（相对昨收）
            price_gain_ratio = (high_price - yesterday_close) / yesterday_close
            if price_gain_ratio < config.SELL_RULE4_GAIN_THRESHOLD:
                return False
            
            # 检查是否从最高点回落M%
            drawdown_ratio = (high_price - current_price) / high_price
            if drawdown_ratio >= config.SELL_RULE4_DRAWDOWN_THRESHOLD:
                logger.info(f"[规则4] {stock_code} 触发卖出: 涨幅{price_gain_ratio:.2%}，回落{drawdown_ratio:.2%}")
                return self._execute_sell(stock_code, position, "规则4-涨幅回落")
            
            return False
            
        except Exception as e:
            logger.error(f"检查规则4时出错: {str(e)}")
            return False
    
    def _check_rule6(self, stock_code: str, latest_data: dict, position: dict) -> bool:
        """规则6: 涨停炸板前根据封单金额自动卖出"""
        try:
            # 获取涨停价
            limit_up_price = latest_data.get('upperLimit', 0)
            current_price = latest_data.get('lastPrice', 0)
            
            if limit_up_price <= 0 or current_price <= 0:
                return False
            
            # 检查是否接近涨停（涨停价的99%以上）
            if current_price < limit_up_price * 0.99:
                return False
            
            # 获取买卖盘数据
            bid_volumes = [latest_data.get(f'bidVol{i}', 0) for i in range(1, 6)]
            ask_volumes = [latest_data.get(f'askVol{i}', 0) for i in range(1, 6)]
            
            # 计算封单金额（买一的量）
            bid1_volume = bid_volumes[0] if bid_volumes else 0
            seal_amount = bid1_volume * current_price
            
            # 如果封单金额小于阈值，可能要炸板，提前卖出
            if seal_amount < config.SELL_RULE6_SEAL_THRESHOLD:
                logger.info(f"[规则6] {stock_code} 触发卖出: 涨停封单不足，封单金额{seal_amount:.0f}万")
                return self._execute_sell(stock_code, position, "规则6-涨停炸板")
            
            return False
            
        except Exception as e:
            logger.error(f"检查规则6时出错: {str(e)}")
            return False
    
    def _check_rule5(self, stock_code: str, position: dict) -> bool:
        """规则5: 尾盘5分钟若未涨停则定时卖出"""
        try:
            if not config.SELL_RULE5_ENABLE:
                return False
            
            now = datetime.now()
            
            # 检查是否在交易时间内
            if not self._is_trading_time(now):
                return False
            
            # 检查是否在尾盘5分钟内（14:55-15:00）
            end_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
            check_time = end_time - timedelta(minutes=5)
            
            if now < check_time:
                return False
            
            # 获取最新行情
            latest_data = self.data_manager.get_latest_data(stock_code)
            if not latest_data:
                return False
            
            current_price = latest_data.get('lastPrice', 0)
            limit_up_price = latest_data.get('upperLimit', 0)
            
            # 检查是否涨停
            if limit_up_price > 0 and current_price >= limit_up_price * 0.999:
                logger.info(f"[规则5] {stock_code} 已涨停，不执行尾盘卖出")
                return False
            
            # 执行尾盘卖出
            logger.info(f"[规则5] {stock_code} 尾盘卖出: 未涨停")
            return self._execute_sell(stock_code, position, "规则5-尾盘卖出")
            
        except Exception as e:
            logger.error(f"检查规则5时出错: {str(e)}")
            return False
    
    def _check_rule8(self, stock_code: str, position: dict) -> bool:
        """规则8: 最大回撤达到x%，就卖出"""
        try:
            if stock_code not in self.stock_states:
                return False
            
            max_drawdown = self.stock_states[stock_code]['max_drawdown']
            
            if max_drawdown >= config.SELL_RULE8_MAX_DRAWDOWN:
                logger.info(f"[规则8] {stock_code} 触发卖出: 最大回撤{max_drawdown:.2%}")
                return self._execute_sell(stock_code, position, "规则8-最大回撤")
            
            return False
            
        except Exception as e:
            logger.error(f"检查规则8时出错: {str(e)}")
            return False
    
    def _check_end_of_day_sell(self):
        """规则5: 尾盘5分钟若未涨停则定时卖出"""
        try:
            now = datetime.now()
            
            # 检查是否在交易时间内
            if not self._is_trading_time(now):
                return
            
            # 检查是否在尾盘5分钟内（14:55-15:00）
            end_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
            check_time = end_time - timedelta(minutes=5)
            
            if now < check_time:
                return
            
            # 获取所有持仓
            positions = self.position_manager.get_all_positions()
            
            for stock_code, position in positions.items():
                try:
                    # 检查是否已经卖出
                    if self.stock_states.get(stock_code, {}).get('sell_triggered', False):
                        continue
                    
                    # 获取最新行情
                    latest_data = self.data_manager.get_latest_data(stock_code)
                    if not latest_data:
                        continue
                    
                    current_price = latest_data.get('lastPrice', 0)
                    limit_up_price = latest_data.get('upperLimit', 0)
                    
                    # 检查是否涨停
                    if limit_up_price > 0 and current_price >= limit_up_price * 0.999:
                        logger.info(f"[规则5] {stock_code} 已涨停，不执行尾盘卖出")
                        continue
                    
                    # 执行尾盘卖出
                    logger.info(f"[规则5] {stock_code} 尾盘卖出: 未涨停")
                    self._execute_sell(stock_code, position, "规则5-尾盘卖出")
                    
                except Exception as e:
                    logger.error(f"检查 {stock_code} 尾盘卖出时出错: {str(e)}")
            
        except Exception as e:
            logger.error(f"检查尾盘卖出时出错: {str(e)}")
    
    def _execute_sell(self, stock_code: str, position: dict, reason: str) -> bool:
        """执行卖出操作"""
        try:
            # 检查冷却时间
            if self._is_in_cooldown(stock_code):
                return False
            
            # 检查是否已经触发卖出
            if self.stock_states.get(stock_code, {}).get('sell_triggered', False):
                return False
            
            volume = position.get('volume', 0)
            if volume <= 0:
                logger.warning(f"{stock_code} 持仓数量为0，无法卖出")
                return False
            
            # 获取卖出价格（使用买三价提高成交概率）
            latest_data = self.data_manager.get_latest_data(stock_code)
            if not latest_data:
                return False
            # 根据配置的价格档位获取卖出价格
            price_level = getattr(config, "SELL_PRICE_LEVEL", 3)  # 默认使用买三价
            
            # 获取买盘价格
            bid_prices = []
            for i in range(1, 6):  # 买一价到买五价
                bid_price = latest_data.get(f"bidPrice{i}", 0)
                bid_prices.append(bid_price)
            
            # 确保价格档位在有效范围内
            if price_level < 1 or price_level > 5:
                price_level = 3  # 默认使用买三价
            
            # 获取对应档位的价格，如果为0则尝试其他档位
            sell_price = 0
            if bid_prices[price_level-1] > 0:
                sell_price = bid_prices[price_level-1]
            else:
                # 如果指定档位价格为0，尝试其他档位
                for price in bid_prices:
                    if price > 0:
                        sell_price = price
                        break
            
            # 如果所有买盘价格都为0，使用当前价
            current_price = latest_data.get("lastPrice", 0)
            if sell_price == 0:
                sell_price = current_price
                
            logger.info(f"卖出价格档位: {price_level}, 使用价格: {sell_price}")

            
            logger.info(f"执行卖出: {stock_code}, 原因: {reason}, 数量: {volume}, 价格: {sell_price}")
            
            # 执行卖出
            order_id = self.trading_executor.sell_stock(
                stock_code=stock_code,
                volume=volume,
                price=sell_price,
                price_type=5,  # 限价单
                strategy=f'sell_strategy_{reason}'
            )
            
            if order_id:
                # 记录待处理委托
                self.pending_orders[order_id] = {
                    'stock_code': stock_code,
                    'order_time': datetime.now(),
                    'reason': reason,
                    'volume': volume,
                    'price': sell_price
                }
                
                # 标记已触发卖出
                if stock_code not in self.stock_states:
                    self.stock_states[stock_code] = {}
                self.stock_states[stock_code]['sell_triggered'] = True
                
                # 设置冷却时间
                self.trade_cooldown[stock_code] = datetime.now()
                
                logger.info(f"{stock_code} 卖出委托提交成功，委托号: {order_id}")
                return True
            else:
                logger.error(f"{stock_code} 卖出委托提交失败")
                return False
            
        except Exception as e:
            logger.error(f"执行 {stock_code} 卖出时出错: {str(e)}")
            return False
    
    def _check_pending_orders(self, stock_code: str):
        """规则7: 卖出委托2秒未成交自动撤单重下"""
        try:
            current_time = datetime.now()
            orders_to_cancel = []
            
            for order_id, order_info in self.pending_orders.items():
                if order_info['stock_code'] != stock_code:
                    continue
                
                # 检查委托是否超过2秒未成交
                if (current_time - order_info['order_time']).total_seconds() > config.SELL_RULE7_CANCEL_TIMEOUT:
                    orders_to_cancel.append(order_id)
            
            for order_id in orders_to_cancel:
                order_info = self.pending_orders[order_id]
                
                # 撤销委托
                if self.trading_executor.cancel_order(order_id):
                    logger.info(f"[规则7] 撤销 {stock_code} 超时委托: {order_id}")
                    
                    # 重新下单
                    position = self.position_manager.get_position(stock_code)
                    if position:
                        # 获取新的卖出价格
                        latest_data = self.data_manager.get_latest_data(stock_code)
                        if latest_data:
                            new_price = latest_data.get('bidPrice3', latest_data.get('lastPrice', 0))
                            
                            # 重新提交卖出委托
                            new_order_id = self.trading_executor.sell_stock(
                                stock_code=stock_code,
                                volume=order_info['volume'],
                                price=new_price,
                                price_type=5,
                                strategy=f"sell_strategy_{order_info['reason']}_retry"
                            )
                            
                            if new_order_id:
                                # 更新待处理委托
                                self.pending_orders[new_order_id] = {
                                    'stock_code': stock_code,
                                    'order_time': datetime.now(),
                                    'reason': order_info['reason'],
                                    'volume': order_info['volume'],
                                    'price': new_price
                                }
                                logger.info(f"[规则7] {stock_code} 重新下单成功，新委托号: {new_order_id}")
                
                # 移除旧委托记录
                del self.pending_orders[order_id]
            
        except Exception as e:
            logger.error(f"检查 {stock_code} 待处理委托时出错: {str(e)}")
    
    def _get_today_market_data(self, stock_code: str) -> Optional[dict]:
        """获取今日市场数据"""
        try:
            # 获取今日K线数据
            today = datetime.now().strftime('%Y%m%d')
            data = self.data_manager.get_market_data(stock_code, period='1d', count=1)
            
            # 修复DataFrame布尔值判断错误
            if data is not None and not data.empty and len(data) > 0:
                return data.iloc[-1].to_dict()
            
            return None
            
        except Exception as e:
            logger.error(f"获取 {stock_code} 今日数据时出错: {str(e)}")
            return None
    
    def _get_yesterday_close(self, stock_code: str) -> Optional[float]:
        """获取昨日收盘价"""
        try:
            data = self.data_manager.get_market_data(stock_code, period='1d', count=2)
            
            # 修复DataFrame布尔值判断错误
            if data is not None and not data.empty and len(data) >= 2:
                return float(data.iloc[-2]['close'])
            
            return None
            
        except Exception as e:
            logger.error(f"获取 {stock_code} 昨日收盘价时出错: {str(e)}")
            return None
    
    def _is_trading_time(self, dt: datetime) -> bool:
        """检查是否在交易时间内"""
        try:
            # 检查是否为工作日
            if dt.weekday() >= 5:  # 周六、周日
                return False
            
            # 检查是否在交易时间段内
            time_str = dt.strftime('%H:%M')
            
            # 上午: 09:30-11:30, 下午: 13:00-15:00
            morning_start = '09:30'
            morning_end = '11:30'
            afternoon_start = '13:00'
            afternoon_end = '15:00'
            
            return (morning_start <= time_str <= morning_end) or \
                   (afternoon_start <= time_str <= afternoon_end)
            
        except Exception as e:
            logger.error(f"检查交易时间时出错: {str(e)}")
            return False
    
    def _is_in_cooldown(self, stock_code: str) -> bool:
        """检查是否在冷却期内"""
        if stock_code not in self.trade_cooldown:
            return False
        
        last_trade_time = self.trade_cooldown[stock_code]
        cooldown_seconds = config.SELL_STRATEGY_COOLDOWN_SECONDS
        
        return (datetime.now() - last_trade_time).total_seconds() < cooldown_seconds
    
    def reset_stock_state(self, stock_code: str):
        """重置股票状态（用于新的交易日）"""
        if stock_code in self.stock_states:
            del self.stock_states[stock_code]
        
        if stock_code in self.trade_cooldown:
            del self.trade_cooldown[stock_code]
        
        logger.info(f"已重置 {stock_code} 的卖出策略状态")
    
    def get_stock_state(self, stock_code: str) -> dict:
        """获取股票状态信息"""
        return self.stock_states.get(stock_code, {})
    
    def manual_trigger_sell(self, stock_code: str, rule_name: str) -> bool:
        """手动触发卖出策略"""
        try:
            position = self.position_manager.get_position(stock_code)
            if not position:
                logger.warning(f"未持有 {stock_code}，无法手动触发卖出")
                return False
            
            return self._execute_sell(stock_code, position, f"手动触发-{rule_name}")
            
        except Exception as e:
            logger.error(f"手动触发 {stock_code} 卖出时出错: {str(e)}")
            return False

# 全局实例
_sell_strategy_instance = None

def get_sell_strategy():
    """获取卖出策略实例（单例模式）"""
    global _sell_strategy_instance
    if _sell_strategy_instance is None:
        _sell_strategy_instance = SellStrategy()
    return _sell_strategy_instance