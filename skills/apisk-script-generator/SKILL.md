---
name: apisk-script-generator
description: One-sentence-to-script generator for apisk framework. Routes via api-index.md, pulls realtime endpoint details, writes domain + test code, and verifies collection. Use when the user describes a test scenario in natural language and asks to generate scripts or test cases. Do not use for manual endpoint exploration or when the user only wants to read docs.
---

# 一句话变脚本

把用户一句自然语言需求，变成 apisk 框架下可执行的领域包 + 测试用例。固定五步，严格串行。

---

## 不可违反的三条铁律

| # | 规矩 | 违反即返工 |
|---|------|-----------|
| **1** | **仅依据 apisk 框架约定生成脚本** —— 所有 import 必须是 apisk 包提供的符号（`BaseApi` / `HttpClient` / `Domain` / `ServiceSpec` / `metric_svc` / `report_data` / `markers`）。不写任何 apisk 之外的基础设施代码、不引入自定义基类、不造新 fixture。 | 生成代码里出现 `requests.get`、`sys.path.insert`、自定义 `BaseTest` 基类、非 apisk fixture 定义 |
| **2** | **默认只写正向 / 场景用例** —— 用户没提异常参数、权限错误、空值边界等异常场景时，不自动生成。异常用例只在用户明确列出时才写。 | 用户说"写一个批量评估脚本"，生成了 12 个用例其中 8 个是 token 过期 / 空文件 / 参数缺失 —— 这些必须用户点名才写 |
| **3** | **场景串联必须给顺序，不擅自加步骤** —— 用户说"批量评估创建→取消"，就只生成这两步，不额外加"查状态"、"验证取消成功"这种用户没提的链路。用户没说串联关系时，接口独立成单用例。 | 用户说"batch-eval 创建 + 取消"，Service 层里偷偷加了 `create → poll_until_running → cancel → verify_cancelled` 四步 |

---

## Step 0 — 项目发现（动态，必须先做）

apisk 框架**不限定项目目录布局**，每个项目的测试根目录名、领域包放置位置、套件工程组织方式都可能不同。生成代码前**必须动态发现**以下位置，绝不硬编码：

### 0.1 发现测试根目录

从项目根开始，扫描所有子目录，按优先级取第一个符合条件的：

1. **含 `conftest.py` + import 了 apisk 的目录** —— 读该目录下的 `conftest.py`，检查是否有 `import apisk` / `from apisk` / `pytest_plugins = ["apisk.pytest_plugin"]`
2. **含 `pytest.ini` 或 `pyproject.toml` 且声明了 `apisk_domains` 的目录** —— 读配置文件确认
3. **含子目录 `domain/` 或 `domains/` 且里面有 `*_domain.py` 的目录** —— 有领域包就是 apisk 项目

找到后记为 **`<TEST_ROOT>`**，后续所有路径都相对它推导。

### 0.2 发现已有领域包（作为模板源）

在 `<TEST_ROOT>` 下扫描所有 `*_domain.py` 文件（或 `domain/*.py` / `domains/*.py`）。取第一个作为编码模板，重点提取：

- frozen dataclass config 写法（BASE_URL / TIMEOUT / 鉴权常量）
- `from apisk.api import BaseApi` + `from apisk.core import HttpClient` 的端点层签名
- `from apisk.domain import Domain, ServiceSpec` 的领域声明骨架
- Service 层的 `__init__` 模式（无参构造 → 自己 new HttpClient）

### 0.3 发现 OpenAPI 源和索引

- **索引文件**：优先在项目根找 `apisk_knowledge/api-index.md`；找不到则提示用户先跑 `apisk-index-sync`
- **OpenAPI 源**：从索引文件的 ref 列解析。ref 格式 `<source>#<jsonpath>` → `<source>` 就是源文件，相对于索引文件所在目录

**如果上述发现均失败**：明确告诉用户"当前目录下找不到 apisk 项目结构"，列出扫描到的目录树摘要，请求确认项目根。

---

## Step 1 — 索引定位（语义匹配）

1. 从用户一句话提取核心意图：动作（对比/评估/查询/删除）+ 目标资源（批量任务/报表/对比）+ 输入约束（job_id/roc_id/阈值）。
2. 读 Step 0.3 发现的索引文件，语义匹配最相关的行。匹配依据：路径片段、描述文本、方法类型的组合。
3. 输出候选接口列表：每行必须带 `ref` 列的完整值。候选接口不超过 5 个，超过则按用户需求进一步收窄。

**严禁**：全量读 OpenAPI 源文件。这一步只读索引文件。

---

## Step 2 — 实时拉取详情（按 ref 定点）

对 Step 1 匹配到的每个接口，解析 `ref` 字段定位到 JSONPath，只拉该节点的详情：

```
ref 格式：example.openapi.json#paths./api/items.POST
解析     →  源文件 = apisk_knowledge/example.openapi.json  (相对索引文件目录)
           →  JSONPath = paths["./api/items"]["post"]
拉取     →  summary / description / requestBody / parameters / responses
```

对每个接口，只提取编码所需的最小信息：

| 字段 | 用途 |
|------|------|
| HTTP method + path | BaseApi 端点方法签名 |
| requestBody schema | 构造 json_body 参数 |
| parameters（query/path/header） | 构造 URL 参数 |
| responses.200 | Service 层返回断言字段 |

**严禁**：把整个 OpenAPI JSON 读入上下文。用 `paths` 字典的定点属性访问，每个接口只拉自己那一个节点。

---

## Step 3 — 领域编码（apisk 框架固定结构）

复用 Step 0.2 发现的领域包模板 + apisk 框架固定约束，生成两层文件。

### 3.1 Domain 包

**目标路径**：`<TEST_ROOT>/domain/<domain_name>_domain.py`
（若 Step 0.2 发现领域包在 `<TEST_ROOT>/domains/` 下，就用 `domains/`；两者都没有时默认 `domain/`）

**固定骨架**（来源：Step 0.2 发现的已有领域包模板）：

```python
#! python3
# -*- encoding: utf-8 -*-

"""<domain_name> 领域包。"""

from dataclasses import dataclass
from typing import Dict, Optional

# ===== 以下三行 import 是 apisk 框架固定约束，不能改 =====
from apisk.api import BaseApi
from apisk.core import HttpClient
from apisk.domain import Domain, ServiceSpec
# =======================================================


# ============ 领域配置（frozen dataclass，全部业务常量内联） ============

@dataclass(frozen=True)
class <DomainName>Config:
    BASE_URL = "<实际 base_url>"
    TIMEOUT = 60
    # ... 其他业务常量（鉴权 token / 阈值 / 探测路径等）


config = <DomainName>Config()


# ============ 端点层（继承 BaseApi，端点方法传完整 path） ============

class <DomainName>Api(BaseApi):
    """<domain_name> 端点。"""

    def __init__(self):
        super().__init__(HttpClient(
            base_url=config.BASE_URL,
            token="<若需要鉴权则填，否则删这行>",
            timeout=config.TIMEOUT,
        ))

    def <action>(self, <params>):
        """<endpoint summary>"""
        return self._post("<完整 path>", json_body={...})

    # 多方法同一路径时，method 名按 HTTP 动词区分，如 <action>_get / <action>_delete
    def <action>_get(self, ...):
        return self._get("<完整 path>")


# ============ 服务层（无参构造，自己 new HttpClient，封装业务链） ============

class <DomainName>Service:
    """<domain_name> 服务（无参构造）。"""

    def __init__(self):
        self.api = <DomainName>Api()

    def <business_method>(self, ...):
        """高层业务方法，封装 HTTP 调用链 + 断言。"""
        response = self.api.<action>(...)
        data = response.json
        assert response.status_code == 200, f"...{response.status_code}..."
        return data.get("data") or {}


# ============ 领域声明（注册到 apisk 容器） ============

DOMAIN = Domain(
    name="<domain_name>",
    apis={"<api_group>": <DomainName>Api},
    services=[ServiceSpec("<svc_name>", <DomainName>Service)],
    probe="<probe_path 或 probe_credentials 函数>",
    config=config,
)

__all__ = ["DOMAIN", "<DomainName>Api", "<DomainName>Service", "config"]
```

### 3.2 测试用例

**目标路径**：`<TEST_ROOT>/<suite_name>/test_<scenario>.py`
（`<suite_name>` 由用户需求描述推导，如 `batch_eval` / `report` / `compare`）

**默认只生成正向 / 场景用例（铁律 2）**：
- 用户没提异常参数、权限错误、空值边界、网络超时等异常场景时，**不自动生成**
- 异常用例只在用户明确列出时才写（如"再加 3 个异常用例：空文件 / 超长文件名 / 无权限"）

**场景串联必须给顺序（铁律 3）**：
- 用户描述里有明确串联关系（"创建 → 查询 → 取消" / "先生成报表再获取结果"），按顺序写
- 用户只列了接口名没说串联，**每个接口独立成单用例**，Service 层也不擅自加跨接口方法

**固定骨架**（参考 Step 0.2 发现的已有用例结构）：

```python
#! python3
# -*- encoding: utf-8 -*-

"""<场景描述>。"""

import pytest

# ===== 以下 import 是 apisk 框架固定约束，不能改 =====
from apisk.support.markers import feature, story, title
# =======================================================

pytestmark = [feature("<功能>"), story("<场景>")]


@title("<用例标题>")
def test_<scenario>(metric_svc, report_data):
    result = metric_svc.<svc_name>.<business_method>(...)
    report_data("<key>", result["<field>"])
    assert result.get("status") == "OK"
```

**关键 fixture**（apisk pytest plugin 自动注册，任何 apisk 项目都能直接用）：
- `metric_svc` —— Services 容器，自动装配所有声明的 Domain
- `report_data` —— 写入指标到 HTML 报告（直接操作 `request.node.user_properties`）

### 3.3 编码禁令（apisk 框架硬性约束 + 铁律汇总）

- 禁止 `sys.path` 注入、手动注册 `pytest_plugins`、自定义 Service 构造参数
- 禁止把 BASE_URL / Token 写进 Service `__init__` 参数——全部走 frozen dataclass config
- 禁止 Service 持有 state 或全局单例——每次 new 独立 HttpClient
- 禁止用 `import apisk` 之外的方式接入框架（铁律 1）
- 禁止擅自给用例加异常场景（铁律 2）
- 禁止擅自给用户没说的串联链路加步骤（铁律 3）

---

## Step 4 — 采集校验（只 collect，不执行）

写完代码后，**只采集不执行**。命令中的 `<TEST_ROOT>` 用 Step 0.1 发现的路径：

```powershell
uv run pytest <TEST_ROOT> --collect-only -q --no-header 2>&1
```

**必须通过**：退出码为 0。逐项排查：

| 错误类型 | 定位 |
|---------|------|
| ImportError / ModuleNotFoundError | 新领域包的 import 路径（可能需要在 `<TEST_ROOT>/conftest.py` 或项目根 `pytest.ini` 声明 `apisk_domains`） |
| fixture not found | 用例目录下必须有 `__init__.py` 且其父级能访问到顶层 conftest 的 fixture；子模块 conftest 必须 import 顶层 conftest |
| ServiceSpec 重复 | 新 Domain 的 `name` 和已有 Domain 冲突 → 改名 |
| DomainError | 领域包模块级 `DOMAIN` 声明有问题 → 检查 `ServiceSpec` 参数顺序、`Api` 类是否继承 `BaseApi` |

---

## Step 5 — 交付说明（必须列出）

采集通过后，输出**明确的交付清单**：

```
## 生成完成

### 新增文件
- <TEST_ROOT>/domain/<name>_domain.py  (Domain + ServiceSpec + Service)
- <TEST_ROOT>/<suite>/test_<scenario>.py  (N 个用例)

### 覆盖接口
| HTTP | Path | 来源 ref |
|------|------|----------|
| POST | /api/items | example.openapi.json#paths./api/items.POST |

### 用例清单
| 用例名 | 场景 | 关键断言 |
|--------|------|----------|
| test_xxx | <title> | assert ... |

### 运行方式
```powershell
uv run pytest <TEST_ROOT>/<suite> -v --html=reports/<name>.html --self-contained-html
```
```

---

## 与 apisk-index-sync 的协作

本 skill 依赖索引文件作为接口定位唯一入口。若索引不存在或过期，提示用户先运行 `apisk-index-sync` 刷新再继续。**永远不绕过索引直接读 OpenAPI**——索引的作用就是把"要拉什么详情"和"接口全量"解耦。

---

## apisk 框架速查（任何项目都适用）

以下符号由 apisk pip 包提供，与项目目录无关：

| 符号 | 来源 | 用途 |
|------|------|------|
| `BaseApi` | `apisk.api` | 端点基类，提供 `_post` / `_get` / `_delete` 等方法 |
| `HttpClient` | `apisk.core.http_client` | 自己 new 的 HTTP 客户端，不持有凭据 |
| `Domain` | `apisk.domain` | 领域声明（name / apis / services / probe / config） |
| `ServiceSpec` | `apisk.domain` | 服务装配声明（name + factory） |
| `Services` | `apisk.services` | 容器（pytest plugin 自动装配） |
| `metric_svc` | pytest plugin fixture | Services 容器实例 |
| `report_data` | pytest plugin fixture | HTML 报告指标写入 |
| `feature / story / title` | `apisk.support.markers` | 场景标记 |
