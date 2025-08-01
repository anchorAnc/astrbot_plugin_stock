# AstrBot 股票与数字货币行情插件

基于 AkShare 和 Binance API 的综合金融行情查询插件，为 AstrBot 机器人提供专业的股市和数字货币数据查询功能。

## 🚀 功能特色

- **多市场支持**: A股、港股、美股及主要指数
- **数字货币**: 基于币安API的实时加密货币行情
- **实时行情**: 股票和数字货币实时价格、涨跌幅、成交量等
- **历史数据**: 支持多粒度股票历史数据查询
- **专业图表**: K线图表，包含技术指标（MACD、KDJ等）
- **智能纠错**: 自动识别和纠正常见股票代码格式

## 📦 安装

```bash
cd AstrBot/data/plugins/
git clone https://github.com/anchorAnc/astrbot_plugin_stock.git
cd astrbot_plugin_stock
pip install -r requirements.txt
```
重启 AstrBot 即可使用。

## 🎯 指令使用

### 📈 股票功能
```bash
/price_now 000001.SZ                 # A股实时行情
/price_now 00700.HK                  # 港股实时行情  
/price_now AAPL.US                   # 美股实时行情
/price 000001.SZ                     # 历史数据
/price 600519.SH 20210101 20210131   # 指定时间范围
/price_chart 000001.SZ               # 日K线图
/price_chart 000001.SZ hourly 48     # 48小时K线
/index sh                            # 上证指数（简写）
/index_chart sz                      # 深证成指K线图
```

### 🪙 数字货币功能
```bash
/crypto BTC                          # 比特币实时价格
/crypto ETH USDT                     # 以太坊对USDT价格
/crypto_list                         # 热门数字货币列表
/crypto_list 20                      # 前20热门数字货币
/crypto_history BTC                  # 比特币历史行情
/crypto_chart BTC                    # 比特币日K线图
/crypto_chart ETH hourly 48          # 以太坊48小时K线图
/crypto_market                       # 数字货币市场概览
/crypto_info                         # 币安交易所信息
```

### 🧪 快速测试
```bash
/help_stock                         # 查看帮助
```

## ⚙️ 配置选项

插件支持丰富的配置选项，可在 AstrBot 管理面板中调整：

- **数据显示**: 默认显示条数、缓存时间等
- **图表样式**: 尺寸、颜色主题、技术指标开关等  
- **功能开关**: 图表生成、技术分析、自动纠错、数字货币等
- **数字货币**: 币安API设置、超时时间、计价货币等

## 📊 支持的数据类型

| 类型 | 支持格式 | 示例 | 数据源 |
|------|---------|------|-------|
| A股 | 000000.SZ/SH | 000001.SZ, 600000.SH | AkShare |
| 港股 | 00000.HK | 00700.HK, 09988.HK | AkShare |
| 美股 | SYMBOL.US | AAPL.US, TSLA.US | AkShare |
| 指数 | 000000.SH | 000001.SH | AkShare |
| 数字货币 | SYMBOL 或 SYMBOLUSDT | BTC, ETH, BTCUSDT | Binance API |

## 🛠️ 技术指标

K线图表包含以下技术指标：
- **移动平均线**: MA5, MA10, MA20
- **MACD**: 12日, 26日指数移动平均
- **KDJ**: 随机指标
- **成交量**: 成交量柱状图及均线

## ⚠️ 使用须知

- 数据来源为 AkShare，遵循其使用条款
- 请合理使用，避免频繁请求
- 本插件**不构成投资建议**

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 🔮 未来计划

- **更多图表类型**: 分时图、深度图等
- **数字货币高级功能**: 价格预警、定时推送、DeFi数据等
- **模拟交易**: 虚拟炒股功能
- **定时订阅**: 行情推送和提醒
- **AI分析**: 智能预测和分析
- **股票名称匹配**: 支持通过公司名称模糊搜索股票代码
- **字体优化**: 内置宋体、楷体、微软雅黑等字体，解决跨平台字体显示问题

## 🛡️ 免责声明

### 数据免责
- 本插件数据来源于 AkShare 和 Binance API，数据的准确性、完整性由数据提供方负责
- 实时数据可能存在延迟，仅供技术研究参考
- **不提供任何投资建议**：所有数据展示仅供参考，使用者应独立判断并承担投资风险

### 数字货币特别提示
- 数字货币价格波动巨大，投资需谨慎
- 币安API数据仅供参考，交易决策请以官方平台为准

### 开发免责
本插件为开源项目，作者不对以下情况负责：
- 因使用插件导致的交易损失
- 因API接口变动导致的插件功能异常  
- 因不可抗力导致的服务中断
- **禁止**将本插件用于商业售卖、非法荐股等用途

## 🔄 更新日志

### v1.2.2
- 🐛 修复了部分历史行情显示最早数据而非最新数据的问题

### v1.2.1
- 🔧 改进了图表字体文件读取逻辑，内置了中文字体文件

### v1.2.0
- ✨ 新增数字货币功能：基于币安API的实时行情、历史数据、K线图表
- ✨ 新增数字货币对比分析和市场概览功能  
- 🏗️ 完成代码模块化重构：拆分为独立的命令和工具模块
- 🎨 优化K线图表显示和技术指标
- 🔧 改进错误处理和超时机制

### v1.1.1
- 支持多市场股票查询（A股、港股、美股）
- 支持多粒度K线图表（日/小时/分钟级）
- 智能股票代码自动纠错
- 丰富的技术指标显示

---

*数据来源: [AkShare](https://akshare.akfamily.xyz/) & [Binance API](https://binance-docs.github.io/apidocs/)*
