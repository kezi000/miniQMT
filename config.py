"""配置参数管理模块，集中管理所有可配置参数
优化版本：增强止盈止损配置的清晰度
"""
import os
import json
from datetime import datetime

# ===============================================================================
# 1. 系统基础配置
# ===============================================================================

# 调试配置
DEBUG = False                       # 调试模式开关
DEBUG_SIMU_STOCK_DATA = False       # 模拟股票数据调试开关

# 日志配置
LOG_LEVEL = "INFO"                  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = "qmt_trading.log"        # 日志文件名
LOG_MAX_SIZE = 10 * 1024 * 1024     # 日志文件最大大小：10MB
LOG_BACKUP_COUNT = 5                # 日志备份文件数量
LOG_CLEANUP_DAYS = 30               # 日志保留天数
LOG_CLEANUP_TIME = "00:00:00"       # 日志清理时间

# Web服务配置
WEB_SERVER_HOST = "localhost"       # Web服务器主机
WEB_SERVER_PORT = 5000              # Web服务器端口
WEB_SERVER_DEBUG = True             # Web服务器调试模式

# ===============================================================================
# 2. 功能开关配置
# ===============================================================================

# 核心功能开关
ENABLE_SIMULATION_MODE = False      # 模拟交易模式开关（True=模拟，False=实盘）
ENABLE_AUTO_TRADING = False         # 自动交易总开关：控制是否执行交易决策
ENABLE_MONITORING = False           # 前端UI监控状态开关

# 交易操作开关
ENABLE_ALLOW_BUY = True             # 是否允许买入操作
ENABLE_ALLOW_SELL = True            # 是否允许卖出操作

# 策略功能模块开关
ENABLE_DYNAMIC_STOP_PROFIT = True   # 止盈止损功能开关
ENABLE_GRID_TRADING = False         # 网格交易功能开关
ENABLE_SELL_STRATEGY = True         # 卖出策略总开关

# 数据与监控开关
ENABLE_DATA_SYNC = True             # 数据同步开关
ENABLE_POSITION_MONITOR = True      # 持仓监控开关
ENABLE_LOG_CLEANUP = True           # 日志清理开关

# 功能说明：
# - 策略线程始终运行，进行信号检测和监控
# - ENABLE_AUTO_TRADING 控制是否执行检测到的交易信号
# - ENABLE_DYNAMIC_STOP_PROFIT 控制止盈止损模块
# - ENABLE_GRID_TRADING 控制网格交易模块
# - ENABLE_SIMULATION_MODE 控制交易执行方式（模拟/实盘）

# ===============================================================================
# 3. 数据存储与行情配置
# ===============================================================================

# 数据存储配置
DATA_DIR = "data"                                   # 数据存储目录
DB_PATH = os.path.join(DATA_DIR, "trading.db")     # SQLite数据库路径
STOCK2BUY_FILE = os.path.join(DATA_DIR, "stock2buy.json")  # 备选股票池文件

# 行情数据配置
PERIODS = ["1d", "1h", "30m", "15m", "5m", "1m"]   # 支持的数据周期
DEFAULT_PERIOD = "1d"                              # 默认数据周期
INITIAL_DAYS = 365                                 # 历史数据初始获取天数
UPDATE_INTERVAL = 60                               # 数据更新间隔（秒）

# 实时数据源配置
REALTIME_DATA_CONFIG = {
    'enable_multi_source': True,        # 启用多数据源
    'health_check_interval': 30,        # 健康检查间隔（秒）
    'source_timeout': 5,                # 数据源超时时间（秒）
    'max_error_count': 3,               # 最大错误次数
    'preferred_sources': [              # 首选数据源列表
        'XtQuant',
        'Mootdx'
    ]
}

# ===============================================================================
# 4. 交易账户与连接配置
# ===============================================================================

# 交易账户配置
ACCOUNT_CONFIG_FILE = "account_config.json"                    # 账户配置文件
QMT_PATH = r'd:/江海证券QMT实盘_交易/userdata_mini'              # QMT客户端路径

def get_account_config():
    """从外部文件读取账号配置"""
    try:
        with open(ACCOUNT_CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # 如果配置文件不存在，返回默认配置
        return {"account_id": "80392832", "account_type": "STOCK"}

# 账号信息
ACCOUNT_CONFIG = get_account_config()

# 交易时间配置
TRADE_TIME = {
    "morning_start": "09:30:00",        # 上午开盘时间
    "morning_end": "11:30:00",          # 上午收盘时间
    "afternoon_start": "13:00:00",      # 下午开盘时间
    "afternoon_end": "15:00:00",        # 下午收盘时间
    "trade_days": [1, 2, 3, 4, 5]       # 交易日（周一至周五）
}

def is_trade_time():
    """判断当前是否为交易时间"""
    if DEBUG_SIMU_STOCK_DATA:
        return True

    now = datetime.now()
    weekday = now.weekday() + 1  # 转换为1-7表示周一至周日
    
    if weekday not in TRADE_TIME["trade_days"]:
        return False
    
    current_time = now.strftime("%H:%M:%S")
    if (TRADE_TIME["morning_start"] <= current_time <= TRADE_TIME["morning_end"]) or \
       (TRADE_TIME["afternoon_start"] <= current_time <= TRADE_TIME["afternoon_end"]):
        return True
    
    return False

# ===============================================================================
# 5. 交易策略配置
# ===============================================================================

# 仓位管理配置
POSITION_UNIT = 5000               # 每次买入金额（元）
MAX_POSITION_VALUE = 10000              # 单只股票最大持仓金额（元）
MAX_TOTAL_POSITION_RATIO = 0.95         # 最大总持仓比例（占总资金）
SIMULATION_BALANCE = 1000000            # 模拟交易初始资金（元）

# 买入策略配置
BUY_GRID_LEVELS = [1.0, 0.93, 0.86]    # 建仓价格网格（初次建仓、补仓价格比例）
BUY_AMOUNT_RATIO = [0.4, 0.3, 0.3]     # 每次买入金额占单元的比例

# 网格交易配置
GRID_TRADING_ENABLED = False            # 网格交易功能开关
GRID_STEP_RATIO = 0.03                 # 网格步长（价格变动3%创建一个网格）
GRID_POSITION_RATIO = 0.2              # 每个网格交易的仓位比例
GRID_MAX_LEVELS = 6                    # 最大网格数量

# ===============================================================================
# 6. 止盈止损策略配置
# ===============================================================================

# 止损配置
STOP_LOSS_RATIO = -0.07                # 固定止损比例：成本价下跌7%触发止损

# 动态止盈配置
INITIAL_TAKE_PROFIT_RATIO = 0.05       # 首次止盈触发阈值：盈利5%时触发
INITIAL_TAKE_PROFIT_RATIO_PERCENTAGE = 0.5  # 首次止盈卖出比例：50%（半仓）

# 分级动态止盈设置（已触发首次止盈后的动态止盈位）
# 格式：(最高盈利比例阈值, 止盈位系数)
# 说明：当最高盈利达到阈值后，止盈位 = 最高价 × 系数
DYNAMIC_TAKE_PROFIT = [
    (0.05, 0.96),  # 最高浮盈达5%时，止盈位为最高价的96%
    (0.10, 0.93),  # 最高浮盈达10%时，止盈位为最高价的93%
    (0.15, 0.90),  # 最高浮盈达15%时，止盈位为最高价的90%
    (0.30, 0.87),  # 最高浮盈达30%时，止盈位为最高价的87%
    (0.40, 0.85)   # 最高浮盈达40%时，止盈位为最高价的85%
]

# 止盈止损优先级说明：
# 1. 止损检查优先级最高
# 2. 未触发首次止盈时：盈利5%触发首次止盈（卖出50%）
# 3. 已触发首次止盈后：使用动态止盈位进行全仓止盈
# 4. 止损价格计算：未触发首次止盈时为成本价×(1-7%)，已触发后为最高价×对应系数

# ===============================================================================
# 7. 技术指标配置
# ===============================================================================

# MACD指标参数
MACD_FAST = 12                          # MACD快线周期
MACD_SLOW = 26                          # MACD慢线周期
MACD_SIGNAL = 9                         # MACD信号线周期

# 移动平均线参数
MA_PERIODS = [10, 20, 30, 60]           # 均线周期列表

# ===============================================================================
# 8. 卖出策略配置
# ===============================================================================

# 卖出策略基础配置
SELL_STRATEGY_CHECK_INTERVAL = 1        # 卖出策略检查间隔（秒）
SELL_STRATEGY_COOLDOWN_SECONDS = 30     # 卖出策略冷却时间（秒）

# 卖出价格档位配置 (1-5对应买一价到买五价)
# 1: 买一价 - 最高价格，成交概率最低
# 2: 买二价
# 3: 买三价 - 默认设置
# 4: 买四价
# 5: 买五价 - 最低价格，成交概率最高
SELL_PRICE_LEVEL = 3                    # 默认卖出价格档位

# 卖出规则配置
# 规则1: 高开 + 最高高于开盘价N% + 最高点回落M%卖出
SELL_RULE1_RISE_THRESHOLD = 0.03        # 最高价高于开盘价3%
SELL_RULE1_DRAWDOWN_THRESHOLD = 0.015    # 从最高点回落2%

# 规则2: 低开 + 最高价高于开盘价N% + 最高点回落M%卖出
SELL_RULE2_RISE_THRESHOLD = 0.05        # 最高价高于开盘价5%
SELL_RULE2_DRAWDOWN_THRESHOLD = 0.02    # 从最高点回落3%

# 规则3: 低开 + 最高价涨幅大于N% + 最高点回落M%卖出
SELL_RULE3_GAIN_THRESHOLD = 0.06        # 最高价涨幅大于6%（相对昨收）
SELL_RULE3_DRAWDOWN_THRESHOLD = 0.03    # 从最高点回落3%

# 规则4: 不论高低开 + 最高价涨幅大于N% + 最高点回落M%卖出
SELL_RULE4_GAIN_THRESHOLD = 0.08        # 最高价涨幅大于8%（相对昨收）
SELL_RULE4_DRAWDOWN_THRESHOLD = 0.04    # 从最高点回落4%

# 规则5: 尾盘5分钟若未涨停则定时卖出（在代码中硬编码为14:55-15:00）
SELL_RULE5_ENABLE = True                # 尾盘定时卖出开关

# 规则6: 涨停炸板前根据封单金额自动卖出
SELL_RULE6_SEAL_THRESHOLD = 10000000    # 封单金额阈值（1000万元）

# 规则7: 卖出委托2秒未成交自动撤单重下
SELL_RULE7_CANCEL_TIMEOUT = 2           # 委托超时时间（秒）

# 规则8: 最大回撤达到x%，就卖出
SELL_RULE8_MAX_DRAWDOWN = 0.05          # 最大回撤5%,基于当日最高价

# ===============================================================================
# 9. 参数校验配置
# ===============================================================================

# 基础参数范围定义（用于前后端校验）
CONFIG_PARAM_RANGES = {
    "singleBuyAmount": {"min": 1000, "max": 100000, "type": "float", "desc": "单只单次买入金额"},
    "firstProfitSell": {"min": 1.0, "max": 20.0, "type": "float", "desc": "首次止盈比例(%)"},
    "stockGainSellPencent": {"min": 1.0, "max": 100.0, "type": "float", "desc": "首次盈利平仓卖出比例(%)"},
    "stopLossBuy": {"min": 1.0, "max": 20.0, "type": "float", "desc": "补仓跌幅(%)"},
    "stockStopLoss": {"min": 1.0, "max": 20.0, "type": "float", "desc": "止损比例(%)"},
    "singleStockMaxPosition": {"min": 10000, "max": 100000, "type": "float", "desc": "单只股票最大持仓"},
    "totalMaxPosition": {"min": 50000, "max": 1000000, "type": "float", "desc": "最大总持仓"},
    "connectPort": {"min": 1, "max": 65535, "type": "int", "desc": "连接端口"}
}

# 卖出策略参数范围定义（用于Web界面参数验证）
SELL_STRATEGY_PARAM_RANGES = {
    "rule1_rise": {"min": 0.01, "max": 0.20, "type": "float", "desc": "规则1涨幅阈值(%)"},
    "rule1_drawdown": {"min": 0.01, "max": 0.10, "type": "float", "desc": "规则1回落阈值(%)"},
    "rule2_rise": {"min": 0.01, "max": 0.20, "type": "float", "desc": "规则2涨幅阈值(%)"},
    "rule2_drawdown": {"min": 0.01, "max": 0.10, "type": "float", "desc": "规则2回落阈值(%)"},
    "rule3_gain": {"min": 0.01, "max": 0.20, "type": "float", "desc": "规则3涨幅阈值(%)"},
    "rule3_drawdown": {"min": 0.01, "max": 0.10, "type": "float", "desc": "规则3回落阈值(%)"},
    "rule4_gain": {"min": 0.01, "max": 0.20, "type": "float", "desc": "规则4涨幅阈值(%)"},
    "rule4_drawdown": {"min": 0.01, "max": 0.10, "type": "float", "desc": "规则4回落阈值(%)"},
    "rule6_seal": {"min": 100000, "max": 50000000, "type": "int", "desc": "规则6封单阈值(元)"},
    "rule7_timeout": {"min": 1, "max": 10, "type": "int", "desc": "规则7超时时间(秒)"},
    "rule8_drawdown": {"min": 0.01, "max": 0.20, "type": "float", "desc": "规则8最大回撤(%)"}
}

def validate_config_param(param_name, value):
    """验证配置参数是否在有效范围内"""
    if param_name not in CONFIG_PARAM_RANGES:
        return True, ""  # 未定义范围的参数默认通过
        
    param_range = CONFIG_PARAM_RANGES[param_name]
    param_type = param_range.get("type", "float")
    param_min = param_range.get("min")
    param_max = param_range.get("max")
    
    try:
        # 类型转换
        if param_type == "float":
            value = float(value)
        elif param_type == "int":
            value = int(value)
            
        # 范围检查
        if param_min is not None and value < param_min:
            return False, f"{param_range['desc']}不能小于{param_min}"
            
        if param_max is not None and value > param_max:
            return False, f"{param_range['desc']}不能大于{param_max}"
            
        return True, ""
    except (ValueError, TypeError):
        return False, f"{param_range['desc']}必须是{param_type}类型"

# ===============================================================================
# 10. 股票池配置
# ===============================================================================

# 预设股票池
DEFAULT_STOCK_POOL = [
    "000001.SZ",  # 平安银行
    "600036.SH",  # 招商银行
    "000333.SZ",  # 美的集团
    "600519.SH",  # 贵州茅台
    "000858.SZ",  # 五粮液
]

# 股票池文件配置
STOCK_POOL_FILE = "stock_pool.json"     # 股票池配置文件

def load_stock_pool(file_path=STOCK_POOL_FILE):
    """从外部文件加载股票池"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return DEFAULT_STOCK_POOL

# 实际使用的股票池
STOCK_POOL = load_stock_pool()