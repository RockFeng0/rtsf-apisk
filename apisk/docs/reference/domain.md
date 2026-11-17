# 参考：领域协议（Domain / ServiceSpec）

领域协议是**框架与业务之间的唯一接缝**。框架不含任何业务，业务以「领域包」形式声明。

- 教程与动机见 [接入教程](../guide/接入教程.md)
- 脚手架生成的领域包模板见 `python -m apisk.scaffold --name mydomain --out test_mydomain`

---

## 1. 领域包的最小形态

```python
# domain/mydomain_domain.py
from dataclasses import dataclass

from apisk.api import BaseApi
from apisk.domain import Domain, ServiceSpec
from apisk.core import HttpClient


@dataclass(frozen=True)
class MydomainConfig:
    BASE_URL = "http://127.0.0.1:8000"
    TIMEOUT = 15
    PROBE_PATH = "/health"


config = MydomainConfig()


class MydomainApi(BaseApi):
    def health(self, **kwargs):
        return self._get(config.BASE_URL + config.PROBE_PATH, **kwargs)


class MydomainService:
    def __init__(self):
        self.api = MydomainApi(HttpClient(
            base_url=config.BASE_URL,
            timeout=config.TIMEOUT,
        ))

    def health(self):
        return self.api.health()


DOMAIN = Domain(
    name="mydomain",
    apis={"health": MydomainApi},
    services=[ServiceSpec("mydomain", MydomainService)],
    probe=config.BASE_URL + config.PROBE_PATH,
    config=config,
)
```

模块级导出 `DOMAIN`（单个）或 `DOMAINS`（多个，列表/元组）均可；框架按
`DOMAIN` → `DOMAINS` 的顺序取**第一个存在**的名字，不会同时取用。

---

## 2. `Domain` 字段

| 字段 | 类型 | 作用 | 缺省行为 |
|------|------|------|----------|
| `name` | `str` | 领域名，用于去重与日志 | **必填**，为空即抛 `DomainError` |
| `apis` | `{逻辑名: BaseApi 子类}` | 端点类登记表 | 空 |
| `services` | `Sequence[ServiceSpec]` | 服务装配表，决定 `metric_svc.<name>` | 空（`metric_svc` 上无业务属性） |
| `probe` | `str` \| `callable(client) -> (bool, str)` | 服务门禁探测 | 退化为「拿第一个 Service 的 HttpClient 做 GET」 |
| `plugin` | `str` | 领域自带的 pytest 插件模块路径，用于提供领域专属夹具 | 无 |
| `config` | 任意 | 领域配置对象，供套件通过 `apisk_domain_config` 夹具读取 | 无 |

`Domain` 是 frozen dataclass：`apis` 会被包成只读映射，`services` 会被转成元组，
注册后不可变。

### 2.1 冲突与取值规则

* `Domain.name` 重复 → 直接抛 `DomainError`，**不做静默覆盖**；
* `probe` / `config` 这类**框架级槽位**，由「**第一个**
  声明了该项的领域」生效（按加载顺序）。

### 2.2 查询方法

| 方法 | 说明 |
|------|------|
| `domain.api(name)` | 按逻辑名取端点类；未声明时抛 `DomainError`（报错里列出已声明的名字） |
| `domain.service(name)` | 按逻辑名取 `ServiceSpec`；同上 |

---

## 3. `ServiceSpec`

```python
ServiceSpec(name="mydomain", factory=MydomainService)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 装配到 `Services` 上的属性名，即用例里的 `metric_svc.<name>` |
| `factory` | callable | 服务类（或返回服务实例的工厂） |

装配由 `ServiceSpec.build()` 完成——**无参调用 `factory()`**：

```python
spec.build()          # → factory() → 拿到 Service 实例
```

Service 自己的 `__init__` 里自己 new HttpClient、自己管凭据、自己绑 Api——框架不持有、
不注入、不切换。

---

## 4. 领域的加载来源（可并用）

| 来源 | 写法 | 适用 |
|------|------|------|
| 命令行 | `--apisk-domain mydomain`（可重复，也支持逗号分隔） | 临时追加、CI 参数化 |
| `pytest.ini` | `apisk_domains = mydomain`（每行一个，支持逗号分隔） | 套件固定接入（推荐） |
| 环境变量 | `AUTO_TEST_DOMAINS=mydomain,other` | 容器/流水线注入 |
| 入口点 | `[project.entry-points."apisk.domains"]` | 领域包 pip 安装后**自动发现**，套件零声明 |

名称支持逗号与换行分隔，会去重保序。

加载失败（模块不存在、未导出 `DOMAIN`、领域重名等）时，框架在配置阶段抛
`pytest.exit(..., returncode=4)`，并打印四个来源清单 + 「本次声明」+ 修正建议，**不会**
产生 pytest INTERNALERROR。详见 [异常与退出码](exceptions.md)。

---

## 5. 注册时序与冻结语义

* 领域在 pytest 的**配置阶段**（`pytest_configure`）加载，随后注册表立即**冻结**；
* 冻结后再调用 `register_domain()` 一律抛 `DomainError`；
* 因此「已装配的服务清单」在用例执行期间恒定不变。

```python
from apisk.domain import load_domains, loaded_domains, get_domain

load_domains("mydomain", entry_points=True, freeze=True)   # pytest 插件内部就是这么调的
loaded_domains()                                           # 只读快照
get_domain("mydomain")                                     # 按名取；未加载时给出可诊断报错
```

---

## 6. 发布领域包（entry_points，可选但推荐）

```toml
# mydomain/pyproject.toml
[project]
name = "mydomain"
dependencies = ["apisk>=3.0"]

[project.entry-points."apisk.domains"]
mydomain = "mydomain:DOMAIN"
```

装好之后，任何套件**无需任何声明**即可使用 `metric_svc.mydomain.xxx()`。

---

## 7. 相关模块级 API

| 名称 | 说明 |
|------|------|
| `ENTRY_POINT_GROUP` | 入口点组名，固定为 `"apisk.domains"` |
| `DOMAIN_ATTRS` | 领域包导出领域声明的属性名，`("DOMAIN", "DOMAINS")` |
| `load_domains(*names, entry_points=False, freeze=False)` | 导入并登记领域；重复调用幂等 |
| `register_domain(domain)` | 登记单个领域，重名报错 |
| `freeze_domains()` | 冻结注册表 |
| `loaded_domains()` | 当前已加载领域的只读快照 |
| `get_domain(name)` | 按名取领域 |
| `probe_spec()` / `domain_config()` | 供框架夹具解析「该用谁」：第一个声明了该项的领域 |
| `domain_plugins()` | 各领域自带的 pytest 插件模块路径 |
