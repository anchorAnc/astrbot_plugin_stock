# astrbot_plugin_stock

基于 Tushare Pro 的 A 股行情查询 AstrBot 插件，支持实时和历史日线数据查询。

## 安装

1. 将插件文件夹复制到 AstrBot 插件目录：  
   `AstrBot/data/plugins`  
2. 在 AstrBot 运行环境中安装依赖：  
   ```bash
   python -m pip install -r requirements.txt
   ``` :contentReference[oaicite:0]{index=0}

3. 重启 AstrBot 服务。

## 配置

在 AstrBot 管理面板填写并保存以下配置项：  
- `tushare_token`：Tushare Pro API Token  
- `default_period`：默认周期，可选 `daily`/`weekly`/`monthly` （默认 `daily`）  
- `default_limit`：历史查询默认条数（默认 `5`） :contentReference[oaicite:1]{index=1}

## 使用

- 查询最新行情：  
  ```text
  /price 000001.SZ
