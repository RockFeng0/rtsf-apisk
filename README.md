# apisk

基于 pytest 的接口自动化测试框架：**框架不含任何业务、不含身份概念**。
端点、服务、门禁探测、业务常量都由**领域包**声明，框架只负责装配、探测与报告。

```
┌──────────────────────┐
│ apisk（src/apisk）    │  通用原语：HTTP / 门禁 / 夹具 / 标记 / 报告
└──────────┬───────────┘
           │  Domain 协议
┌──────────▼───────────┐
│ 领域包（写业务的地方）  │  端点类 + 服务 + 探活 + 业务常量
└──────────┬───────────┘
           │ pip install 后 entry point 自动注册
┌──────────▼───────────┐
│ 套件工程（写用例的地方）│  用例 + conftest.py / pytest.ini
└──────────────────────┘
```

## 项目结构

```
rtsf-apisk/
├── apisk/                # 框架包
│   ├── core/             # HttpClient / 响应包装 / 现场留痕 / 异常 / 日志
│   ├── services/         # 服务容器（按声明装配）
│   ├── support/          # 标记辅助 / 报告修补 / 语料工具
│   ├── docs/             # 随包分发的文档
│   ├── domain.py         # Domain 扩展协议
│   ├── pytest_plugin.py  # 夹具、选项、钩子
│   ├── runner.py         # 套件运行器
│   └── scaffold.py       # 骨架生成器
├── examples/demo_get/    # 可运行的最小示例（GET + 查询串）
├── skills/               # 可选的 AI 辅助工作流（SKILL.md 约定）
├── tests/                # 框架自身的单元测试（离线，不联网）
└── pyproject.toml
```

## 安装

```bash
# 从源码（当前方式）
git clone <repo-url> && cd apisk
pip install -e ".[dev]"

# 发布到 PyPI 之后
pip install apisk
```

安装后 pytest 通过 `pytest11` 入口点自动加载插件，**无需**在 `conftest.py` 里写
`pytest_plugins`。

> **为什么包名不叫 `pytest-apisk`**：apisk 技术上确实是一个 pytest 插件（`pytest11` 入口点 +
> `Framework :: Pytest` 分类），所以 `pytest -p no:apisk` 能整体关掉它。但 `pytest-` 前缀只是
> "纯插件"的发现性约定，不是加载要求——apisk 的第一身份是测试框架（pytest 只是运行器），
> 同类先例有 `anyio`、`hypothesis`、`syrupy`。

## 五分钟跑通第一个用例

```bash
python -m apisk.scaffold --name mydomain --base-url http://127.0.0.1:8000 \
    --probe /api/v1/ping --out test_mydomain

cd test_mydomain
pytest
```

生成的结构：

```
test_mydomain/
├── pytest.ini            # 唯一 rootdir
├── config.py             # 共享业务常量
├── conftest.py           # 顶层共享夹具
├── run.py                # 继承 SuiteRunner 的入口
├── domain/
│   └── mydomain_domain.py   # Api / Service / DOMAIN
└── mydomain/
    ├── config.py
    ├── conftest.py
    └── test_mydomain.py     # 冒烟用例
```

仓库内还有一个更小的手写示例：[examples/demo_get](examples/demo_get)，
演示 GET 查询串的构造与断言：

```bash
cd examples/demo_get && pytest
```

## 领域包怎么写

领域包是框架与业务之间的**唯一接缝**：

```python
from dataclasses import dataclass

from apisk.api import BaseApi
from apisk.core import HttpClient
from apisk.domain import Domain, ServiceSpec


@dataclass(frozen=True)
class DeviceConfig:
    BASE_URL = "https://api.example.com"
    TIMEOUT = 15


config = DeviceConfig()


class DeviceApi(BaseApi):
    def get_device(self, device_id: str):
        return self._get(f"/api/v1/devices/{device_id}")


class DeviceService:
    def __init__(self):
        self.api = DeviceApi(HttpClient(config.BASE_URL, timeout=config.TIMEOUT))

    def get_device(self, device_id: str):
        return self.api.get_device(device_id)


DOMAIN = Domain(
    name="device",
    apis={"device": DeviceApi},
    services=[ServiceSpec("device", DeviceService)],
    probe="/api/v1/devices",
    config=config,
)
```

框架据此装配服务容器，用例侧即可直接写：

```python
def test_get_device(metric_svc, require_service, report_data):
    resp = metric_svc.device.get_device("d-1")
    report_data("status_code", resp.status_code)
    assert resp.status_code == 200
```

领域声明有五个来源，可并用：命令行 `--apisk-domain`、`pytest.ini` 的
`apisk_domains`、环境变量 `AUTO_TEST_DOMAINS`、套件根 `conftest.py` 的
`APIAT_DOMAINS`、以及 `apisk.domains` 入口点。

## 核心能力

| 能力 | 说明 |
|---|---|
| 领域扩展协议 | 业务全部外置，框架零业务 |
| 凭据不可变 | token 在 `HttpClient.__init__` 写入并冻结，用例之间无法互相污染 |
| 按需门禁 | 服务不可用时 skip 而非 fail，用 `require_service` 或身份夹具触发 |
| 现场留痕 | `--apisk-dump-http` 把失败用例的请求/响应（已脱敏）写到报告目录 |
| 报告修补 | 自动修复 pytest-html 在中文路径下 `file://` 打开时的排序/筛选失效 |
| 骨架生成 | `python -m apisk.scaffold` 一条命令生成可跑套件 |

## AI 辅助工作流（可选）

`skills/` 下提供两个遵循 `SKILL.md` 约定的技能，供支持该约定的 AI 工具使用：

| Skill | 作用 | 输入 | 产物 |
|---|---|---|---|
| `apisk-index-sync` | 从 OpenAPI / Apifox 同步轻量接口索引，支持差异刷新与全量重建 | OpenAPI JSON/YAML、Apifox | `apisk_knowledge/api-index.md` |
| `apisk-script-generator` | 按一句自然语言定位索引条目，生成领域包 + 用例 | 一句话需求 + 索引 | `domain/*_domain.py`、`test_*.py` |

两个技能不含任何业务配置，只使用本仓库的约定。

### 快速开始

```bash
# 装技能（WorkBuddy 用户级；项目级用 .workbuddy/skills/，Claude Code 用 ~/.claude/skills/）
cp -r skills/apisk-index-sync skills/apisk-script-generator ~/.workbuddy/skills/
```

之后在被测项目根目录（含 `conftest.py` + `apisk_domains`）按顺序走四步：

| 步骤 | 做什么 | 说什么 / 跑什么 |
|---|---|---|
| 1 | 备料：放一份 OpenAPI 导出到 `apisk_knowledge/example.openapi.json` | — |
| 2 | 同步索引 | 「用 apisk-index-sync 同步接口索引，数据源是本地文件 `apisk_knowledge/example.openapi.json`」 |
| 3 | 生成脚本 | 「用 apisk-script-generator 写一个『创建批量评估 → 取消任务』的用例」 |
| 4 | 验收 | `pytest <TEST_ROOT> --collect-only -q` |

两个技能的分工是硬边界：`apisk-index-sync` 只写索引、不碰代码；`apisk-script-generator`
只读索引、不重复读全量 OpenAPI，**顺序不能反**。

完整步骤（四种数据源、ref 硬约束、生成物结构、七条报错排查）见
[skills 快速开始](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/guide/skills快速开始.md)。

## 文档

| 需求 | 文档 |
|---|---|
| 从零跑通一个用例 | [快速接入：公开站点示例](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/guide/快速接入-百度搜索示例.md) |
| 理解领域包怎么写 | [接入教程](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/guide/接入教程.md) |
| 用 AI 生成用例 | [skills 快速开始](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/guide/skills快速开始.md) |
| Domain / ServiceSpec 字段详解 | [domain.md](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/reference/domain.md) |
| 全部夹具 / 标记 / 命令行选项 | [fixtures.md](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/reference/fixtures.md) |
| 框架行为开关 | [environment.md](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/reference/environment.md) |
| 异常类型与 pytest 退出码 | [exceptions.md](https://github.com/RockFeng0/rtsf-apisk/blob/main/apisk/docs/reference/exceptions.md) |

## 三条设计约束

1. **框架不含业务、不含身份、零 env var**：所有业务配置（base_url、端点路径、阈值）
   下放到领域包自己的 frozen dataclass；
2. **Service 自己构造 HttpClient**：框架不持有凭据、不注入身份；
3. **配置期出错必须可操作**：领域名写错等一律转成带修复建议的 `pytest.exit`
   （退出码 4），不让 pytest 抛 `INTERNALERROR`。

## 开发与测试

```bash
pip install -e ".[dev]"
pytest                           # 单元测试，全部离线
pytest --cov=apisk               # 带覆盖率
cd examples/demo_get && pytest   # 示例（需要联网）
```

测试不访问外部网络：需要 HTTP 行为的用例打在本进程内的回显服务上。

## License

[MIT](LICENSE)。
