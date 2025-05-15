# astrbot_plugin_stock

基于 Tushare Pro 的 A 股行情查询 AstrBot 插件，支持实时和历史日线数据查询。

## 安装🚀

1. 将插件文件夹复制到 AstrBot 插件目录：  
   `AstrBot/data/plugins`  
2. 在 AstrBot 运行环境中安装依赖：  
   ```bash
   python -m pip install -r requirements.txt
   ```

3. 重启 AstrBot 服务 🚀🔄

## 配置⚙️

在 AstrBot 管理面板填写并保存以下配置项：📝  
- `tushare_token`：Tushare Pro API Token  （https://tushare.pro/user/token）
- `default_period`：默认周期，可选 `daily`/`weekly`/`monthly` （默认 `daily`）  
- `default_limit`：历史查询默认条数（默认 `5`）

## 使用✅

- 查询最新行情：  
  ```text
  /price 000001.SZ
  ```

## 未来更新🛠️

#### 1、绘图💡
#### 2、加入别的数字产品（炒币）💡
#### 3、模拟炒股💡
#### 4、定时订阅💡
#### 5、ai预测💡

## 免责声明🛡️

- 数据免责
   本插件数据来源于 Tushare Pro，数据的准确性、完整性由 Tushare 提供方负责。
不提供任何投资建议：所有数据展示仅供技术研究参考，使用者应独立判断并承担投资风险。

- 开发免责
   本插件为开源项目，作者不对以下情况负责：
因使用插件导致的交易损失
因API接口变动导致的插件功能异常
因不可抗力导致的服务中断
禁止将本插件用于商业售卖、非法荐股等用途。
