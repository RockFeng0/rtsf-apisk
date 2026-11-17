# APISK 快速开始：用 AI 技能生成第一个用例

本教程把「装技能 → 备料 → 同步索引 → 生成脚本 → 验收」完整走一遍，全程不手写领域包。

> 适用工具：支持 `SKILL.md` 约定的 AI 工具（WorkBuddy、Claude Code 等）。
> 前置：Python 3.9+、已 `pip install apisk`、被测项目可被 pytest 采集。
> 耗时：约 5 分钟。

---

## Step 0：先认两个技能

`skills/` 下是两个技能，一个负责"接口有哪些"，一个负责"用例怎么写"：

| Skill | 作用 | 输入 | 产物 |
|---|---|---|---|
| `apisk-index-sync` | 把接口索引与 Apifox / OpenAPI 对齐，支持差异刷新与全量重建 | OpenAPI JSON/YAML、Apifox | `apisk_knowledge/api-index.md` |
| `apisk-script-generator` | 按一句自然语言定位接口，生成领域包 + 用例 | 一句话需求 + 索引 | `domain/*_domain.py`、`test_*.py` |

之所以拆成两个，是为了**解耦"接口全量"和"这次要拉什么详情"**：索引只存四列（方法 / 路径 / 描述 / ref），
生成脚本时按 ref 定点拉取单个接口的 schema，永远不会把整份 OpenAPI 读进上下文。

两个技能不含任何业务配置，只使用本仓库的约定。

---

## Step 1：安装技能（30 秒）

技能就是普通目录，拷到 AI 工具读取技能的位置即可：

```bash
# WorkBuddy：用户级（所有项目可用）
cp -r skills/apisk-index-sync skills/apisk-script-generator ~/.workbuddy/skills/

# WorkBuddy：项目级（只让当前项目用）
mkdir -p .workbuddy/skills && cp -r skills/* .workbuddy/skills/

# Claude Code
cp -r skills/* ~/.claude/skills/
```

拷贝后**新开一个会话**，技能才会被加载。验证方式：问一句「现在有哪些 apisk 技能」，
两个名字都出现即安装成功。

---

## Step 2：备料（1 分钟）

在**被测项目根目录**准备一份 OpenAPI 导出文件，两个技能都以它为唯一数据源：

```
your-test-project/
├── apisk_knowledge/
│   ├── example.openapi.json   # Apifox / Swagger 导出（按 ref 定点读，不会全量塞进上下文）
│   └── api-index.md           # Step 3 自动生成，勿手写
├── conftest.py                # 有 import apisk 或 pytest_plugins 声明
└── pytest.ini                 # 声明 apisk_domains
```

被测项目还没落地的话，先用脚手架生成一份：

```bash
python -m apisk.scaffold --name mydomain --base-url http://127.0.0.1:8000 \
    --probe /api/v1/ping --out test_mydomain
```

`apisk-index-sync` 支持四种数据源，按手头条件选一种即可：

| 数据源 | 前置条件 |
|---|---|
| 本地 OpenAPI 文件 | 导出的 JSON/YAML 路径（**最省事，推荐**） |
| Apifox MCP Server | IDE 已配置 `apifox-mcp-server`，`APIFOX_ACCESS_TOKEN` 已设置 |
| Apifox CLI | 已安装 `apifox` CLI，项目 ID 已知 |
| Apifox Open API | 项目 ID + API Token |

---

## Step 3：先同步索引（2 分钟）

在 AI 对话里直接说：

> 用 apisk-index-sync 同步接口索引，数据源是本地文件 apisk_knowledge/example.openapi.json

默认走**差异刷新**（只写新增和变更，已下线的条目保留原位并追加 `~~已下线~~`）；
要清空重建则明确说"全量覆盖"，技能会再向你确认一次。

产物只有四列，内部接口折叠并标注「不测」：

```markdown
| 方法 | 路径 | 描述 | ref |
|:----:|:---:|:---:|:---|
| POST | /api/items | 单个对比 | example.openapi.json#paths./api/items.POST |
| GET  | /api/jobs/{job_id} | 查询评估状态 | example.openapi.json#paths./api/jobs/{job_id}.GET |

<details>
<summary>内部接口（不测）— 共 1 条</summary>

| 方法 | 路径 | 描述 | ref |
|:----:|:---:|:---:|:---|
| GET | /api/internal/xxx | ... | example.openapi.json#paths./api/internal/xxx.GET |

</details>
```

**ref 是可解析的硬约束**，格式为 `<源文件名>#paths.<path>.<method>`，其中 `<path>` 必须与源文件
`paths` 的 key 一字不差（含 `/` 和 `{param}`）。写完技能会自检五条：主表无内部接口、
内部接口全部折叠且标注「不测」、每行固定四列、折叠块计数一致、每条 ref 能在源文件里精确命中。

---

## Step 4：再生成脚本（1 分钟）

索引就位后，一句话提需求：

> 用 apisk-script-generator 写一个「创建批量评估 → 取消任务」的用例

技能固定五步执行：**发现项目结构 → 索引语义定位 → 按 ref 定点拉接口详情 → 生成领域包 + 用例 → 只 collect 不执行地校验**。

生成物示例：

```
test_mydomain/
├── domain/
│   └── batch_eval_domain.py      # Config + Api + Service + DOMAIN
└── batch_eval/
    └── test_batch_eval.py        # 2 个用例（创建、创建后取消）
```

三条不能破的规矩，写进技能里也是这么执行的：

| 规矩 | 表现 |
|---|---|
| 只用 apisk 符号 | `BaseApi` / `HttpClient` / `Domain` / `ServiceSpec` / `metric_svc` / `report_data`，不出现 `requests`、`sys.path`、自定义基类 |
| 默认只写正向用例 | 用户没点名"空文件 / 无权限 / 参数缺失"，就不生成异常用例 |
| 场景串联不擅自加步骤 | 说"创建→取消"就两步，不偷偷插入"轮询状态""验证取消成功" |

---

## Step 5：验收（10 秒）

```bash
pytest <TEST_ROOT> --collect-only -q     # 采集必须退出码 0
pytest <TEST_ROOT>/<suite> -v --html=reports/run.html --self-contained-html
```

采集通过说明 import 链路、`apisk_domains` 声明、fixture 可见性全部打通；执行通过才说明业务断言成立。

---

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 提示"找不到 apisk 项目结构" | 当前目录不是被测项目根 | 切到含 `conftest.py` / `apisk_domains` 的目录再重试 |
| 提示先跑 `apisk-index-sync` | `apisk_knowledge/api-index.md` 缺失或过期 | 回到 Step 3 刷新索引 |
| 采集报 `ImportError` | 新领域包未声明 | 在 `pytest.ini` 的 `apisk_domains` 加模块路径（点号分隔，不是文件路径） |
| 采集报 `fixture not found` | 用例目录缺 `__init__.py`，导致同名模块/夹具解析不到 | 补 `__init__.py`（顶层 conftest 的夹具会自动下传到子包，不需要手动 import） |
| 采集报 `DomainError` | `DOMAIN` 声明有问题 | 检查 `ServiceSpec(name, factory)` 参数顺序、Api 是否继承 `BaseApi` |
| `ServiceSpec 重复` | 新 Domain 的 `name` 与已有冲突 | 换个领域名 |
| 技能没被识别 | 拷完没重启会话 | 新开会话；仍不行则确认目录下有 `SKILL.md` |

---

## 附：边界与顺序

```
OpenAPI / Apifox
      │  apisk-index-sync
      ▼
api-index.md（四列，只存"有哪些接口"）
      │  apisk-script-generator   ← 一句话需求
      ▼
domain/*_domain.py + test_*.py
```

- `apisk-index-sync` **只写索引，不碰代码**；
- `apisk-script-generator` **只读索引，不重复读全量 OpenAPI**；
- 所以顺序不能反：索引缺失时，脚本生成会直接提示你先同步。

框架自身的接入方式（不用 AI、纯手工）见 [快速接入-百度搜索示例](快速接入-百度搜索示例.md)，
领域包字段详解见 [domain.md](../reference/domain.md)。
