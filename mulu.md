
mcp依赖 python 版本3.9
pip install uv   
uvx mcp-feedback-enhanced@latest 
项目 依赖库 
pip install xtquant pandas requests baostock flask flask_cors mootdx adata pywencai 

# miniQMT 项目目录结构

## 一、系统架构设计

### 1. 核心模块

| 文件名             | 描述                               |
| :----------------- | :--------------------------------- |
| `config.py`        | **集中管理所有可配置参数**         |
| `data_manager.py`  | 历史数据获取存储（xtdata接口）     |
| `indicator_calculator.py` | 多周期均线/MACD计算（pandas向量化计算） |
| `strategy.py`      | **交易策略逻辑实现**               |
| `trading_executor.py` | 交易指令执行器（xttrader接口）     |
| `position_manager.py` | **持仓管理与止盈止损计算**         |
| `grid_trader.py`   | 网格交易模块                       |
| `risk_mgr.py`      | 风控校验模块                       |

### 2. 其他模块与目录

| 文件/目录名        | 描述                               |
| :----------------- | :--------------------------------- |
| `.conda/`          | Conda 环境相关文件                 |
| `.gitignore`       | Git 忽略文件                       |
| `.trae/`           | Trae IDE 相关配置                  |
| `Methods.py`       | 通用方法或辅助函数                 |
| `MiniQMT.md`       | 项目说明文档                       |
| `MyTT.py`          | 技术指标库                         |
| `README.md`        | 项目自述文件                       |
| `WebBuyTest.py`    | Web 购买测试脚本                   |
| `__pycache__/`     | Python 字节码缓存                  |
| `data/`            | 数据存储目录                       |
| `docs/`            | 项目文档                           |
| `easy_qmt_trader.py` | 简易 QMT 交易器                    |
| `logger.py`        | 日志模块                           |
| `main.py`          | 主程序入口                         |
| `stock_pool.json`  | 股票池配置                         |
| `test/`            | 测试文件目录                       |
| `utils.py`         | 工具函数                           |
| `utils/`           | 更多工具函数和辅助脚本             |
| `web1.0/`          | Web 界面相关文件                   |
| `web_api_test.log` | Web API 测试日志                   |
| `web_server.py`    | Web 服务器                         |
| `xtquant/`         | 迅投 QMT API 库                    |

## 二、关键实现要点 (待实现或优化)

1.  **数据管理 (`data_manager.py`)**
    *   使用 `xtdata.get_market_data` 获取股票历史数据。
    *   采用 HDF5 存储高频数据，SQLite 存储元数据。
    *   实现增量更新机制：`last_update_date` 字段记录最后更新时间。

2.  **指标计算 (`indicator_calculator.py`)**
    *   `calculate_emas(df, periods=[10,20,30,60])`: 带异常值处理的多周期均线计算，使用 pandas 的滚动窗口计算。
    *   `calculate_macd(df, fast=12, slow=26, signal=9)`: MACD 指标计算（兼容空值处理）。

3.  **策略引擎 (`strategy.py`)**
    *   `class TradingStrategy`: 实现 QMT 的事件驱动机制。
    *   `on_tick(self, context)`: 包含分仓补仓逻辑和动态止盈逻辑。

4.  **交易执行 (`trading_executor.py`)**
    *   `class TradeExecutor`:
        *   `smart_order(self, symbol, price, amount)`: 智能下单模块，根据买三/卖三价动态调整委托价格，校验当日剩余交易额度，自动拆分大单（单笔≤1000股）。

5.  **风控管理 (`risk_mgr.py`)**
    *   `check_position_risk(position)`: 实时计算持仓盈亏，整体亏损 > 9.5% 时触发全平仓，个股持仓突破网格阈值触发交易。

## 三、QMT API 特别注意事项

1.  必须实现 `init` 和 `handlebar` 方法。
2.  使用 `ContextInfo` 对象传递策略上下文。
3.  区分模拟交易和实盘交易模式。
4.  使用 `xtdata` 订阅实时行情数据。
5.  采用异步订单查询接口。

## 四、调试建议

1.  在 `config.py` 设置 `DEBUG` 模式：
    ```python
    DEBUG = True  # 启用详细日志输出
    SIMULATION = True # 使用模拟交易模式
    ```
2.  日志管理建议：
    *   使用 `RotatingFileHandler` 实现日志轮换。
    *   保留最近 7 天日志，单个日志 ≤ 10MB。




# miniQMT
- miniQMT for Arthur
新的改变
我希望让AI帮我设计量化代码，包括系统架构与具体实现，以下是我的提词，请你给出修改建议，以让AI模型更精准地生成可用代码：

使用python写一个用迅投miniqmt进行量化交易的系统，功能包括：
1. 股票历史数据的获取并存储；对历史数据进行计算；
2. 计算的指标因子包括macd，换手率，10日均线，20日均线，30日均线，60日均线等；
3. 通过各个指标因子的权重发出自动交易指令，同时提供手动交易操作接口；
4. 存储当天交易成交的信息,必要时存储（用sqlite）持仓个股的价格信息，用于计算止盈止损；

交易策略遵循以下规则：
1. 分仓买入：（如每次20000元）按建仓成本价百分比向下买入补仓，如93%，86%等，达到仓位上限（如60000元）后停止买入；
2. 严格止损：整体持仓成本损失大于某个百分比（如-9.5%）后全仓止损；
3. 动态止盈：浮盈比例越大，动态止盈位越高，允许股价回调空间越大；首次浮盈大于一定比例时卖出一定仓位(如50%）仓以保证胜率，余下仓位按动态止盈位置卖出，比如以建仓后股价上涨到的最高价为基准，
   a) 最高价相比持仓成本价，小于10%时，止盈位为最高价*93%
   b) 最高价相比持仓成本价，小于15%时，止盈位为最高价*90%
   c) 最高价相比持仓成本价，小于30%时，止盈位为最高价*87%
   d) 最高价相比持仓成本价，大于30%时，止盈位为最高价*85%
4. 网格交易：自动对持仓个股进行网格交易，网格和交易仓位可配置（比如网格高度为5%，10%，15%等，交易仓位为持仓个股数量*20%）；
5. 买入卖出时需要提前计算交易手数，避免资金不足或者仓位不足，以及交易所的规则（比如交易手数不能低于过100股，不能超过当日交易额度等）；为了保证交易成功，交易价格需要根据市场情况动态调整，比如根据市场卖三价和买三价，避免价格过低和过高；

设计原则遵循以下规则：
1. 每个功能用一个py文件存储；
2. 所有可配置参数集中管理，有调试开关和丰富的代码注释和调试信息；
3. 如果有log文件，定期清理，不过多占用存储空间；
4. xtquant的api参考https://dict.thinktrader.net；

# AI 优化提词
请按照以下架构使用QMT Python API实现量化交易系统：
```python
一、系统架构设计
1. 核心模块
|-- config.py          # **集中管理所有可配置参数**
|-- data_mgr.py    	   # 历史数据获取存储（xtdata接口）
|-- indicator_calc.py  # 多周期均线/MACD计算（pandas向量化计算）
|-- strategy_engine.py # **交易策略逻辑实现**
|-- trade_executor.py  # 交易指令执行器（xttrader接口）
|-- position_mgr.py    # **持仓管理与止盈止损计算**
|-- grid_trader.py     # 网格交易模块
|-- risk_mgr.py        # 风控校验模块
具体项目目录结构,先查看根目录下的mulu.md
二、关键实现要点
1. 数据管理 (data_mgr.py)
- 使用xtdata.get_market_data获取股票历史数据
- 采用HDF5存储高频数据，SQLite存储元数据
- **实现增量更新机制**：last_update_date字段记录最后更新时间

2. 指标计算 (indicator_calc.py)
def calculate_emas(df, periods=[10,20,30,60]):
    """带异常值处理的多周期均线计算"""
    # 使用pandas的滚动窗口计算

def calculate_macd(df, fast=12, slow=26, signal=9):
    """MACD指标计算（兼容空值处理）"""

3. 策略引擎 (strategy_engine.py)
class TradingStrategy:
    def __init__(self, context):
        # 初始化策略参数（从configs.py加载）
        
    def on_tick(self, context):
        """**实现QMT的事件驱动机制**"""
        # 分仓补仓逻辑（示例）：
        if current_price < avg_cost * 0.93:
            self._add_position(context)
            
        # 动态止盈逻辑
        if max_gain > 0.15:
            self._dynamic_profit_control(context)

4. 交易执行 (trade_executor.py)
class TradeExecutor:
    def smart_order(self, symbol, price, amount):
        """**智能下单模块**
        - 根据买三/卖三价动态调整委托价格
        - 校验当日剩余交易额度
        - 自动拆分大单（单笔≤1000股）"""
        
5. 风控管理 (risk_mgr.py)
def check_position_risk(position):
    """实时计算持仓盈亏
    - 整体亏损>9.5%时触发全平仓
    - 个股持仓突破网格阈值触发交易"""

三、QMT API特别注意事项
1. 必须实现init和handlebar方法
2. 使用ContextInfo对象传递策略上下文
3. 区分模拟交易和实盘交易模式
4. 使用xtdata订阅实时行情数据
5. 采用异步订单查询接口

四、调试建议
1. 在config.py设置DEBUG模式：
   DEBUG = True  # 启用详细日志输出
   SIMULATION = True # 使用模拟交易模式

2. 日志管理建议：
   - 使用RotatingFileHandler实现日志轮换
   - 保留最近7天日志，单个日志≤10MB
   
