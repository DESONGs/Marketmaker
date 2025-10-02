## 支持的交易所

- Backpack
- Aster
- Websea
- Apex Omni

## 核心功能

### 做市策略
- 自动挂撤单循环，维持买卖价差
- 动态价格调整，适应市场波动
- 多层级订单管理

### 仓位管理（永续合约）
- 目标仓位追踪
- 风险中性维持机制
- 超额仓位自动减仓
- 动态报价偏移

### 运行模式
- **Maker模式**: 限价单挂撤循环
- **Taker模式**: IOC订单快速成交

### 其他特性
- WebSocket实时行情
- 详细日志记录
- 命令行操作
- 交互式界面

## 安装

### 依赖环境

- Python 3.8+
- Anaconda（推荐）

### 下载代码

```bash
git clone https://github.com/DESONGs/Marketmaker.git
cd Marketmaker
```

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置API密钥

复制 `.env.example` 为 `.env` 并填入你的API密钥：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# Backpack Exchange
BACKPACK_KEY=your_api_key
BACKPACK_SECRET=your_secret_key

# Aster Exchange
ASTER_API_KEY=your_api_key
ASTER_SECRET_KEY=your_secret_key

# Websea Exchange
WEBSEA_TOKEN=your_token
WEBSEA_SECRET=your_secret
```

### 配置Apex Omni（可选）

复制 `apex-taker/omni_config.json.example` 为 `omni_config.json` 并填入配置：

```bash
cd apex-taker
cp omni_config.json.example omni_config.json
```

编辑 `omni_config.json`，填入账户信息。

## 使用方法

### Backpack永续合约做市

```bash
python run.py --exchange backpack --market-type perp --symbol SOL_USDC_PERP \
  --spread 0.02 --quantity 0.1 --max-orders 2 \
  --target-position 0 --max-position 0.5 --position-threshold 0.4 \
  --duration 999999999 --interval 10
```

### Aster永续合约做市

```bash
python run.py --exchange aster --market-type perp --symbol SOLUSDT \
  --spread 0.02 --quantity 0.1 --max-orders 2 \
  --target-position 0 --max-position 0.5 --position-threshold 0.4 \
  --duration 999999999 --interval 10
```

### Apex Omni Taker模式

```bash
python run_apex_taker.py --symbol BTCUSDT --quantity 0.001 \
  --spread 0.05 --max-orders 3 --interval 10 --duration 3600
```

## 参数说明

### 基本参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--exchange` | 交易所 | `backpack`, `aster`, `websea` |
| `--market-type` | 市场类型 | `spot`, `perp` |
| `--symbol` | 交易对 | `SOL_USDC_PERP`, `BTCUSDT` |
| `--spread` | 价差百分比 | `0.02` (0.02%) |
| `--quantity` | 订单数量 | `0.1` |
| `--max-orders` | 每侧最大订单数 | `2` |
| `--interval` | 更新间隔（秒） | `10` |
| `--duration` | 运行时长（秒） | `999999999` |

### 永续合约参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--target-position` | 目标净仓位 | `0` |
| `--max-position` | 最大允许仓位 | `0.5` |
| `--position-threshold` | 减仓触发阈值 | `0.4` |
| `--inventory-skew` | 报价偏移系数 | `0` |

### 模式切换

| 参数 | 说明 |
|------|------|
| `--mode maker` | 限价单循环（默认） |
| `--mode taker` | IOC快速成交 |

## 工作原理

### 做市逻辑

1. 根据中间价和价差计算买卖报价
2. 在买卖两侧挂限价单
3. 等待间隔时间
4. 撤销未成交订单
5. 重复循环

### 仓位管理

| 当前仓位 | 目标 | 阈值 | 最大 | 动作 |
|---------|------|------|------|------|
| 0.1 SOL | 0 | 0.2 | 0.4 | 无操作 |
| 0.25 SOL | 0 | 0.2 | 0.4 | 减仓0.05 |
| 0.5 SOL | 0 | 0.2 | 0.4 | 减仓0.1 |

### 日志示例

```
=== 市场状态 ===
盘口: Bid 239.379 | Ask 239.447 | 价差 0.068 (0.028%)
中间价: 239.408
持仓: 空头 6.000 SOL | 目标: 0.0 | 上限: 1.0

=== 价格计算 ===
原始报价: 买 238.800 | 卖 239.996
调整后: 买 238.800 | 卖 239.996

=== 执行结果 ===
成交: 买入 0.200 | 卖出 0.150
盈亏: +2.45 USDT (手续费: 0.12)
累计: +15.23 USDT
```

## 交易所链接

- [Aster推荐链接](https://www.asterdex.com/en/referral/fc51fF)
- [Backpack推荐链接](https://backpack.exchange/join/9gq7rl2r)

## 风险提示

**交易有风险，使用需谨慎**

- 建议小资金测试
- 定期检查运行状态
- 监控仓位和盈亏
- 根据市场调整参数

## 项目结构

```
.
├── api/                    # 交易所API客户端
│   ├── backpack_client.py
│   ├── aster_client.py
│   ├── apex_client.py
│   └── ...
├── strategies/             # 做市策略
│   ├── market_maker.py
│   ├── perp_market_maker.py
│   └── components/         # 策略组件
├── run.py                  # 主运行程序
├── config.py               # 配置文件
└── requirements.txt        # 依赖清单
```

## 更新日志

查看 [CHANGELOG.md](CHANGELOG.md)

## License

MIT
