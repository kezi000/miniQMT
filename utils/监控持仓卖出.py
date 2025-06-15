#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓监控卖出测试模块
功能：单独运行监控当前持仓，根据8条止盈止损策略进行监控卖出

8条卖出策略：
1. 高开 + 最高价高于开盘价N% + 最高点回落M%卖出
2. 低开 + 最高价高于开盘价N% + 最高点回落M%卖出  
3. 低开 + 最高价涨幅大于N% + 最高点回落M%卖出
4. 不论高低开 + 最高价涨幅大于N% + 最高点回落M%卖出
5. 尾盘5分钟若未涨停则定时卖出
6. 涨停炸板前根据封单金额自动卖出
7. 卖出委托2秒未成交自动撤单重下
8. 最大回撤达到x%，就卖出
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
import pandas as pd

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logger import get_logger
from data_manager import get_data_manager
from position_manager import get_position_manager
from trading_executor import get_trading_executor
from sell_strategy import SellStrategy
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
logger = get_logger("test_监控持仓卖出")

class PositionMonitorSell:
    """持仓监控卖出类"""
    
    def __init__(self):
        """初始化持仓监控卖出"""
        self.data_manager = get_data_manager()
        self.position_manager = get_position_manager()
        self.trading_executor = get_trading_executor()
        self.sell_strategy = SellStrategy()
        
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
        
        logger.info("持仓监控卖出模块初始化完成")
    
    def start_monitoring(self):
        """启动持仓监控"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("持仓监控线程已在运行")
            return
        
        logger.info("="*60)
        logger.info("启动持仓监控卖出系统")
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
                # 修复DataFrame布尔值判断错误
                if positions is None or (isinstance(positions, pd.DataFrame) and positions.empty) or (isinstance(positions, dict) and not positions):
                    logger.debug("当前无持仓，无需监控")
                    time.sleep(10)
                    continue
                
                # 监控每只持仓股票
                # 处理DataFrame和字典两种格式
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
                
                # 执行卖出
                if self._execute_sell_order(stock_code, position, rule_name):
                    self.stats['successful_sells'] += 1
                    logger.info(f"✅ {stock_code} 卖出成功")
                else:
                    self.stats['failed_sells'] += 1
                    logger.error(f"❌ {stock_code} 卖出失败")
            
        except Exception as e:
            logger.error(f"监控 {stock_code} 时出错: {str(e)}")
    
    def _execute_sell_order(self, stock_code: str, position: dict, rule_name: str) -> bool:
        """执行卖出订单"""
        try:
            # 获取持仓数量
            available_volume = position.get('available', 0)
            if available_volume <= 0:
                logger.warning(f"{stock_code} 可用持仓为0，无法卖出")
                return False
            
            # 获取当前价格
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
            logger.info(f"  - 触发规则: {rule_name}")
            logger.info(f"  - 持仓数量: {available_volume}")
            logger.info(f"  - 成本价: {cost_price:.2f}")
            logger.info(f"  - 当前价: {current_price:.2f}")
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
                    strategy=f"监控卖出-{rule_name}"
                )
                # 修复：trading_executor.sell_stock返回的是订单ID(字符串)或None，而不是字典
                if result:  # 如果返回了订单ID，表示成功
                    logger.info(f"[实盘交易] {stock_code} 卖出委托提交成功，订单ID: {result}")
                    return True
                    logger.info(f"[实盘交易] {stock_code} 卖出委托提交成功")
                    return True
                else:
                    logger.error(f"[实盘交易] {stock_code} 卖出失败，未获取到订单ID")
                    return False
            
        except Exception as e:
            logger.error(f"执行 {stock_code} 卖出订单时出错: {str(e)}")
            return False
    
    def _show_config(self):
        """显示当前配置"""
        logger.info("当前卖出策略配置:")
        logger.info(f"  - 模拟交易模式: {config.ENABLE_SIMULATION_MODE}")
        logger.info(f"  - 允许卖出: {config.ENABLE_ALLOW_SELL}")
        logger.info(f"  - 监控间隔: {self.monitor_interval}秒")
        logger.info("")
        logger.info("8条卖出规则配置:")
        logger.info(f"  规则1 - 高开回落: 涨幅>{config.SELL_RULE1_RISE_THRESHOLD:.1%}, 回落>{config.SELL_RULE1_DRAWDOWN_THRESHOLD:.1%}")
        logger.info(f"  规则2 - 低开回落: 涨幅>{config.SELL_RULE2_RISE_THRESHOLD:.1%}, 回落>{config.SELL_RULE2_DRAWDOWN_THRESHOLD:.1%}")
        logger.info(f"  规则3 - 低开涨幅回落: 涨幅>{config.SELL_RULE3_GAIN_THRESHOLD:.1%}, 回落>{config.SELL_RULE3_DRAWDOWN_THRESHOLD:.1%}")
        logger.info(f"  规则4 - 通用涨幅回落: 涨幅>{config.SELL_RULE4_GAIN_THRESHOLD:.1%}, 回落>{config.SELL_RULE4_DRAWDOWN_THRESHOLD:.1%}")
        logger.info(f"  规则5 - 尾盘卖出: {'启用' if config.SELL_RULE5_ENABLE else '禁用'}")
        logger.info(f"  规则6 - 涨停炸板: 封单阈值<{config.SELL_RULE6_SEAL_THRESHOLD:,}元")
        logger.info(f"  规则7 - 委托撤单: 超时>{config.SELL_RULE7_CANCEL_TIMEOUT}秒")
        logger.info(f"  规则8 - 最大回撤: 回撤>{config.SELL_RULE8_MAX_DRAWDOWN:.1%}")
        logger.info("")
    
    def _show_current_positions(self):
        """显示当前持仓"""
        try:
            positions = self.position_manager.get_all_positions()
            # 修复DataFrame布尔判断错误
            if positions is None or (hasattr(positions, 'empty') and positions.empty) or (isinstance(positions, dict) and not positions):
                logger.info("当前无持仓")
                return
            
            # 初始化累计变量
            total_profit = 0
            total_cost = 0
            total_market_value = 0

            # 处理DataFrame格式的持仓数据
            if hasattr(positions, 'iterrows'):
                # DataFrame格式
                positions_count = len(positions)
                logger.info(f"{Colors.BLUE}{Colors.BOLD}📊 当前持仓 ({positions_count}只):{Colors.END}")
                logger.info(f"{Colors.BLUE}{'=' * 110}{Colors.END}")
                logger.info(f"{Colors.BOLD}{Colors.UNDERLINE}{'股票代码':<8} {'股票名称':<10} {'数量':<8} {'成本价':<8} {'当前价':<8} {'盈亏金额':<10} {'盈亏%':<8} {'市值':<12} {'可用':<8} {'状态':<4}{Colors.END}")
                logger.info(f"{Colors.BLUE}{'=' * 110}{Colors.END}")
                
                for index, row in positions.iterrows():
                    try:
                        stock_code = str(row.get('stock_code', '')).strip()
                        # 安全获取股票名称，如果不存在则使用空字符串
                        stock_name = str(row.get('stock_name', stock_code)).strip()[:8]  # 限制名称长度，如果没有名称则使用代码
                        volume = float(row.get('volume', 0))
                        cost_price = float(row.get('cost_price', 0))
                        current_price = float(row.get('current_price', 0))
                        market_value = float(row.get('market_value', 0))
                        available = float(row.get('available', 0))
                        
                        # 过滤无效持仓：跳过数量为0或股票代码异常的记录
                        if volume <= 0 or not stock_code:
                            logger.debug(f"跳过无效持仓: {stock_code}, 数量={volume}, 成本价={cost_price}")
                            continue
                        
                        # 放宽条件，允许成本价为0或股票代码长度小于6
                        if cost_price <= 0:
                            logger.warning(f"持仓 {stock_code} 成本价为0，但仍将显示")
                        if len(stock_code) < 6:
                            logger.warning(f"持仓 {stock_code} 代码长度异常，但仍将显示")
                        
                        # 获取最新价格 (使用xtdata.get_full_tick)
                        try:
                            # 为股票代码添加市场后缀
                            formatted_stock_code = self._format_stock_code(stock_code)
                          
                            logger.debug(f"尝试获取股票 {formatted_stock_code} 的实时行情数据...")
                            
                            tick_data = xtdata.get_full_tick([formatted_stock_code])
                            if tick_data and formatted_stock_code in tick_data and 'lastPrice' in tick_data[formatted_stock_code] and tick_data[formatted_stock_code]['lastPrice'] is not None and float(tick_data[formatted_stock_code]['lastPrice']) > 0:
                                current_price = float(tick_data[formatted_stock_code]['lastPrice'])
                                logger.info(f"获取 {stock_code} 最新价格 (xtdata.get_full_tick): {current_price}")
                            else:
                                logger.warning(f"无法通过xtdata.get_full_tick获取 {stock_code} 最新价格，使用数据库中的价格: {current_price}")
                        except Exception as e:
                            logger.warning(f"通过xtdata.get_full_tick获取 {stock_code} 最新价格失败: {str(e)}，使用数据库中的价格: {current_price}")

                        
                        # 重新计算盈亏比例和盈亏金额，确保准确性
                        if cost_price > 0 and current_price > 0:
                            profit_ratio = round(100 * (current_price - cost_price) / cost_price, 2)
                            profit_amount = round(volume * (current_price - cost_price), 2)
                            logger.info(f"计算 {stock_code} 盈亏: 成本价={cost_price}, 当前价={current_price}, 盈亏比例={profit_ratio}%, 盈亏金额={profit_amount}")
                        else:
                            profit_ratio = 0.0
                            profit_amount = 0.0
                            logger.warning(f"{stock_code} 价格数据异常: 成本价={cost_price}, 当前价={current_price}")
                        
                        # 根据盈亏设置颜色
                        if profit_ratio > 0:
                            profit_color_code = Colors.GREEN
                            profit_icon = "📈"
                        elif profit_ratio < 0:
                            profit_color_code = Colors.RED
                            profit_icon = "📉"
                        else:
                            profit_color_code = Colors.YELLOW
                            profit_icon = "➖"
                        
                        # 格式化显示（带颜色，确保对齐）
                        line = f"{stock_code:<8} {stock_name:<10} {volume:<8.0f} {cost_price:<8.2f} {current_price:<8.2f} {profit_amount:<10.2f} {profit_ratio:<7.2f}% {market_value:<12.2f} {available:<8.0f} {profit_icon:<4}"
                        colored_line = f"{Colors.CYAN}{stock_code:<8}{Colors.END} {Colors.WHITE}{stock_name:<10}{Colors.END} {Colors.WHITE}{volume:<8.0f}{Colors.END} {Colors.WHITE}{cost_price:<8.2f}{Colors.END} {Colors.WHITE}{current_price:<8.2f}{Colors.END} {profit_color_code}{profit_amount:<10.2f}{Colors.END} {profit_color_code}{profit_ratio:<7.2f}%{Colors.END} {Colors.WHITE}{market_value:<12.2f}{Colors.END} {Colors.WHITE}{available:<8.0f}{Colors.END} {profit_color_code}{profit_icon:<4}{Colors.END}"
                        logger.info(colored_line)
                        
                        # 累计总盈亏和总成本
                        total_profit += profit_amount
                        total_cost += volume * cost_price
                        total_market_value += market_value
                    except Exception as e:
                        import traceback
                        logger.error(f"处理持仓行时出错: {str(e)}")
                        logger.error(traceback.format_exc())
                        continue  # 跳过这一行，继续处理其他行
            else:
                # 字典格式（原有逻辑）
                positions_count = len(positions)
                logger.info(f"{Colors.BLUE}{Colors.BOLD}📊 当前持仓 ({positions_count}只):{Colors.END}")
                logger.info(f"{Colors.BLUE}{'=' * 110}{Colors.END}")
                logger.info(f"{Colors.BOLD}{Colors.UNDERLINE}{'股票代码':<8} {'股票名称':<10} {'数量':<8} {'成本价':<8} {'当前价':<8} {'盈亏金额':<10} {'盈亏%':<8} {'市值':<12} {'可用':<8} {'状态':<4}{Colors.END}")
                logger.info(f"{Colors.BLUE}{'=' * 110}{Colors.END}")
                
                for stock_code, position in positions.items():
                    stock_code = str(stock_code).strip()
                    stock_name = str(position.get('stock_name', '')).strip()[:8]
                    volume = float(position.get('volume', 0))
                    cost_price = float(position.get('cost_price', 0))
                    current_price = float(position.get('current_price', 0))
                    market_value = float(position.get('market_value', 0))
                    available = float(position.get('available', 0))
                    
                    # 过滤无效持仓：跳过数量为0或股票代码异常的记录
                    if volume <= 0 or not stock_code:
                        logger.debug(f"跳过无效持仓: {stock_code}, 数量={volume}, 成本价={cost_price}")
                        continue
                    
                    # 放宽条件，允许成本价为0或股票代码长度小于6
                    if cost_price <= 0:
                        logger.warning(f"持仓 {stock_code} 成本价为0，但仍将显示")
                    if len(stock_code) < 6:
                        logger.warning(f"持仓 {stock_code} 代码长度异常，仍将显示")
                    
                    # 获取最新价格 (使用xtdata.get_full_tick)
                    try:
                        # 为股票代码添加市场后缀
                        formatted_stock_code = self._format_stock_code(stock_code)
                        logger.debug(f"尝试获取股票 {formatted_stock_code} 的实时行情数据...")
                        
                        tick_data = xtdata.get_full_tick([formatted_stock_code])
                        if tick_data and formatted_stock_code in tick_data and 'lastPrice' in tick_data[formatted_stock_code] and tick_data[formatted_stock_code]['lastPrice'] is not None and float(tick_data[formatted_stock_code]['lastPrice']) > 0:
                            current_price = float(tick_data[formatted_stock_code]['lastPrice'])
                            logger.info(f"获取 {stock_code} 最新价格 (xtdata.get_full_tick): {current_price}")
                        else:
                            logger.warning(f"无法通过xtdata.get_full_tick获取 {stock_code} 最新价格，使用数据库中的价格: {current_price}")
                    except Exception as e:
                        logger.warning(f"通过xtdata.get_full_tick获取 {stock_code} 最新价格失败: {str(e)}，使用数据库中的价格: {current_price}")
                    
                    # 重新计算盈亏比例和盈亏金额，确保准确性
                    if cost_price > 0 and current_price > 0:
                        profit_ratio = round(100 * (current_price - cost_price) / cost_price, 2)
                        profit_amount = round(volume * (current_price - cost_price), 2)
                        logger.info(f"计算 {stock_code} 盈亏: 成本价={cost_price}, 当前价={current_price}, 盈亏比例={profit_ratio}%, 盈亏金额={profit_amount}")
                    else:
                        profit_ratio = 0.0
                        profit_amount = 0.0
                        logger.warning(f"{stock_code} 价格数据异常: 成本价={cost_price}, 当前价={current_price}")
                    

                    
                    # 根据盈亏设置颜色
                    if profit_ratio > 0:
                        profit_color_code = Colors.GREEN
                        profit_icon = "📈"
                    elif profit_ratio < 0:
                        profit_color_code = Colors.RED
                        profit_icon = "📉"
                    else:
                        profit_color_code = Colors.YELLOW
                        profit_icon = "➖"
                    
                    # 格式化显示（带颜色，确保对齐）
                    line = f"{stock_code:<8} {stock_name:<10} {volume:<8.0f} {cost_price:<8.2f} {current_price:<8.2f} {profit_amount:<10.2f} {profit_ratio:<7.2f}% {market_value:<12.2f} {available:<8.0f} {profit_icon:<4}"
                    colored_line = f"{Colors.CYAN}{stock_code:<8}{Colors.END} {Colors.WHITE}{stock_name:<10}{Colors.END} {Colors.WHITE}{volume:<8.0f}{Colors.END} {Colors.WHITE}{cost_price:<8.2f}{Colors.END} {Colors.WHITE}{current_price:<8.2f}{Colors.END} {profit_color_code}{profit_amount:<10.2f}{Colors.END} {profit_color_code}{profit_ratio:<7.2f}%{Colors.END} {Colors.WHITE}{market_value:<12.2f}{Colors.END} {Colors.WHITE}{available:<8.0f}{Colors.END} {profit_color_code}{profit_icon:<4}{Colors.END}"
                    logger.info(colored_line)
            
            logger.info(f"{Colors.BLUE}{'=' * 110}{Colors.END}")
            
            # 重新计算持仓盈亏
            total_profit = 0
            total_market_value = 0
            total_cost = 0
            
            # 记录计算过程，用于调试
            logger.debug("开始计算持仓盈亏:")
            
            # 根据持仓数据类型选择不同的处理方式
            if isinstance(positions, pd.DataFrame):
                # DataFrame格式
                for index, row in positions.iterrows():
                    volume = float(row.get('volume', 0))
                    cost_price = float(row.get('cost_price', 0))
                    current_price = float(row.get('current_price', 0))
                    
                    if volume > 0:
                        # 计算单只股票的成本、市值和盈亏
                        stock_cost = volume * cost_price
                        stock_market_value = volume * current_price
                        stock_profit = stock_market_value - stock_cost
                        
                        # 累计总成本、总市值和总盈亏
                        total_cost += stock_cost
                        total_market_value += stock_market_value
                        total_profit += stock_profit
                        
                        logger.debug(f"股票: {row.get('stock_code', '')}, 数量: {volume}, 成本价: {cost_price}, 现价: {current_price}")
                        logger.debug(f"  成本: {stock_cost:.2f}, 市值: {stock_market_value:.2f}, 盈亏: {stock_profit:.2f}")
            else:
                # 字典格式
                for stock_code, position in positions.items():
                    stock_code = str(stock_code).strip()
                    volume = float(position.get('volume', 0))
                    cost_price = float(position.get('cost_price', 0))
                    current_price = float(position.get('current_price', 0))
                    
                    if volume > 0:
                        # 计算单只股票的成本、市值和盈亏
                        stock_cost = volume * cost_price
                        stock_market_value = volume * current_price
                        stock_profit = stock_market_value - stock_cost
                        
                        # 累计总成本、总市值和总盈亏
                        total_cost += stock_cost
                        total_market_value += stock_market_value
                        total_profit += stock_profit
                        
                        logger.debug(f"股票: {stock_code}, 数量: {volume}, 成本价: {cost_price}, 现价: {current_price}")
                        logger.debug(f"  成本: {stock_cost:.2f}, 市值: {stock_market_value:.2f}, 盈亏: {stock_profit:.2f}")
            
            # 计算总盈亏比例
            total_profit_ratio = (total_profit / total_cost * 100) if total_cost > 0 else 0
            
            logger.debug(f"计算结果 - 总成本: {total_cost:.2f}, 总市值: {total_market_value:.2f}, 总盈亏: {total_profit:.2f}, 盈亏比例: {total_profit_ratio:.2f}%")
            
            # 根据总盈亏设置颜色
            if total_profit > 0:
                total_color = Colors.GREEN
                profit_status = "📈 盈利"
            elif total_profit < 0:
                total_color = Colors.RED
                profit_status = "📉 亏损"
            else:
                total_color = Colors.YELLOW
                profit_status = "➖ 持平"
            
            logger.info(f"{Colors.MAGENTA}{Colors.BOLD}💰 总计:{Colors.END} {Colors.WHITE}成本={total_cost:,.2f}元{Colors.END}, {Colors.WHITE}市值={total_market_value:,.2f}元{Colors.END}, {total_color}{Colors.BOLD}盈亏={total_profit:+,.2f}元({total_profit_ratio:+.2f}%){Colors.END} {total_color}{profit_status}{Colors.END}")
            logger.info("")
            
        except Exception as e:
            logger.error(f"显示当前持仓时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _show_stats(self):
        """显示统计信息"""
        if not self.stats['start_time']:
            return
        
        runtime = datetime.now() - self.stats['start_time']
        logger.info("="*50)
        logger.info(f"监控统计 (运行时间: {runtime})")
        logger.info(f"  - 总检查次数: {self.stats['total_checks']}")
        logger.info(f"  - 卖出信号: {self.stats['sell_signals']}")
        logger.info(f"  - 成功卖出: {self.stats['successful_sells']}")
        logger.info(f"  - 失败卖出: {self.stats['failed_sells']}")
        
        if self.stats['rule_triggers']:
            logger.info("  规则触发统计:")
            for rule, count in self.stats['rule_triggers'].items():
                logger.info(f"    {rule}: {count}次")
        
        logger.info("="*50)
    
    def _show_final_stats(self):
        """显示最终统计信息"""
        logger.info("="*60)
        logger.info("持仓监控卖出 - 最终统计")
        logger.info("="*60)
        
        if self.stats['start_time']:
            runtime = datetime.now() - self.stats['start_time']
            logger.info(f"总运行时间: {runtime}")
        
        logger.info(f"总检查次数: {self.stats['total_checks']}")
        logger.info(f"卖出信号总数: {self.stats['sell_signals']}")
        logger.info(f"成功卖出: {self.stats['successful_sells']}")
        logger.info(f"失败卖出: {self.stats['failed_sells']}")
        
        if self.stats['rule_triggers']:
            logger.info("\n各规则触发统计:")
            for rule, count in sorted(self.stats['rule_triggers'].items()):
                logger.info(f"  {rule}: {count}次")
        
        # 显示最终持仓
        logger.info("\n最终持仓状态:")
        self._show_current_positions()
        
        logger.info("="*60)
    
    def _format_stock_code(self, stock_code: str) -> str:
        """将股票代码格式化为带市场后缀的格式
        
        Args:
            stock_code: 原始股票代码，如 '001298'
            
        Returns:
            带市场后缀的股票代码，如 '001298.SZ'
        """
        if not stock_code or len(stock_code) < 6:
            return stock_code
            
        # 如果已经包含后缀，直接返回
        if '.' in stock_code:
            return stock_code
            
        # 处理ETF和股票代码
        prefix_2 = stock_code[:2]  # 取前两位用于ETF判断
        prefix_1 = stock_code[:1]  # 取第一位用于普通股票判断
        
        # ETF判断
        if prefix_2 in ['51', '56', '58']:  # 上海ETF
            return f"{stock_code}.SH"
        elif prefix_2 in ['15', '16', '17', '18'] or stock_code.startswith('159'):  # 深圳ETF
            return f"{stock_code}.SZ"
        # 普通股票判断
        elif prefix_1 in ['0', '3']:
            # 深圳市场
            return f"{stock_code}.SZ"
        elif prefix_1 in ['6', '5', '9']:
            # 上海市场
            return f"{stock_code}.SH"
        elif prefix_1 in ['4', '8']:
            # 北京市场
            return f"{stock_code}.BJ"
        else:
            # 默认返回深圳市场
            logger.warning(f"无法识别股票代码 {stock_code} 的市场，默认使用深圳市场")
            return f"{stock_code}.SZ"
    
    def _is_trading_time(self) -> bool:
        """判断是否为交易时间"""
        try:
            return config.is_trade_time()
        except:
            # 如果配置中的函数不可用，使用简单判断
            now = datetime.now()
            weekday = now.weekday()  # 0=周一, 6=周日
            
            # 检查是否为工作日
            if weekday >= 5:  # 周六、周日
                return False
            
            # 检查是否在交易时间内
            current_time = now.time()
            morning_start = datetime.strptime("09:30:00", "%H:%M:%S").time()
            morning_end = datetime.strptime("11:30:00", "%H:%M:%S").time()
            afternoon_start = datetime.strptime("13:00:00", "%H:%M:%S").time()
            afternoon_end = datetime.strptime("15:00:00", "%H:%M:%S").time()
            
            return (morning_start <= current_time <= morning_end) or \
                   (afternoon_start <= current_time <= afternoon_end)

def main():
    """主函数"""
    try:
        logger.info("持仓监控卖出测试程序启动")
        # 确保xtquant已连接
        if not xtdata.connect():
            logger.error("xtquant行情服务连接失败，请检查QMT是否运行或配置是否正确。")
            return
        
        # 创建监控实例
        monitor = PositionMonitorSell()
        
        # 启动监控
        monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        logger.info("程序结束")

if __name__ == "__main__":
    main()