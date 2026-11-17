# 参考：夹具、标记与断言

apisk 框架通过 `pip install apisk` 的 `pytest11` entry_point 自动注册——
套件工程不需要在 conftest.py 里声明 `pytest_plugins`。本页是框架对外提供的
全部能力清单。

---

## 1. 夹具总表

| 分组 | 夹具 | 作用域 | 依赖 | 说明 |
|------|------|--------|------|------|
| **容器** | `metric_svc` | session | — | `Services()` 无参构造，按所有领域的 ServiceSpec 装配；用例里 `metric_svc.<name>.<method>()` |
| **门禁** | `service_status` | session | — | 服务可用性探测，session 内只探一次，返回 `(是否可用, 原因)` |
| | `require_service` | session | `service_status` | 服务不可用时 **skip 而非 fail**；`metric_svc` 已内置它 |
| **编排** | `report_path` | session | — | 报告输出目录（`str`），与 HTML 落点一致 |
| **报告** | `report_data` | function | `request` | 把指标写进报告表格：`report_data("status_code", 200)` |
| **自省** | `apisk_domains` | session | — | 当前已加载的领域声明（只读元组） |
| | `apisk_domain_config` | session | — | 第一个携带配置对象的领域的配置；无领域时为 `None` |

领域专属夹具（语料池、评估器、第三方客户端等）由领域自己的 `pytest_plugin.py` 提供
（`Domain.plugin` 声明），框架加载领域时自动注册，套件无需感知。

---

## 2. 服务门禁

门禁**不需要按目录配白名单**：

* 需要被测服务的用例：签名里带上 `metric_svc`（它内置
  `require_service`），服务没起就 skip；
* **纯本地用例**：不碰 `metric_svc`，任何环境下都真实执行，不受门禁影响。

`service_status` 的探测策略来自 `Domain.probe`：端点 URL 字符串、`callable(client) ->
(bool, str)`，或未声明时退化为「拿第一个 Service 的 HttpClient 做 GET」。

---

## 3. 用例标记

三个语义标记由框架插件统一注册（无需在 `pytest.ini` 重复声明，配合 `--strict-markers`
可防拼错）：

```python
from apisk.support.markers import feature, story, title

pytestmark = [feature("设备管理"), story("设备注册")]      # 模块级


@title("TC-D1-013 收齐 N 条完成注册")                      # 单条用例标题
def test_d1_013(metric_svc, report_data):
    ...
```

```bash
pytest -m "feature: 设备管理"
pytest -m "story: 设备注册"
```

`@title` 的文案会作为「测试用例」列出现在 HTML 报告里（未加时退回 nodeid）。

---

## 4. 报告

### 4.1 一行接入：`apisk_report()`

```python
from apisk.support.reporting import apisk_report

apisk_report(
    title="百度demo测试报告",
    metrics=(("status_code", "状态码"), ("elapsed_ms", "响应时间(ms)")),
)
```

| 参数 | 缺省 | 说明 |
|------|------|------|
| `title` | `None` | 报告标题；`None` 时沿用框架缺省标题 |
| `metrics` | `(("status_code", "状态码"), ("elapsed_ms", "响应时间(ms)"))` | 渲染成列的指标 `((键, 列名), ...)`；传空元组即只要中文列名 |
| `report_dir` | `None` | 报告目录；`None` 时取 `AUTO_TEST_REPORT_DIR` → `<rootdir>/reports` |
| `report_filename` | `None` | 报告文件名；`None` 时按 pytest 收集目标**自动推导**（见下文） |

#### 报告文件名自动推导

不传 `report_filename` 时，框架根据 `pytest` 的位置参数自动决定报告名，避免多场景覆盖：

| 命令 | 报告文件 |
|------|----------|
| `pytest test_asr.py` | `reports/test_asr.html` |
| `pytest jk_model/` | `reports/jk_model.html` |
| `pytest`（全量收集） | `reports/report.html` |
| `pytest a.py b.py`（多个） | `reports/report.html`（退化为默认） |

#### 优先级

用户手动传 `--html xxx.html` **优先级最高**，会覆盖自动推导和 `report_filename`。
不传 `--html` 时，`report_filename` → 自动推导 → 硬编码 `report.html`。

它把 `--html` 钉住（单文件、自包含），换工作目录执行也不会跑偏；
`--self-contained-html` 无条件开启（框架偏好：单文件部署、邮件发报告不带 assets）。

### 4.2 写入指标：`report_data`

```python
def test_home(metric_svc, report_data):
    resp = metric_svc.baidu.home()
    report_data("status_code", resp.status_code)
    report_data("elapsed_ms", round(resp.exchange.elapsed_ms, 1))
```

* 键必须与 `apisk_report(metrics=...)` 声明的键一致，才会渲染成列；缺值留空；
* 也可直接用 `resp.exchange.elapsed_ms` 取框架记录的端到端耗时。

---

## 5. 命令行选项与 ini 选项

| 形式 | 名称 | 说明 |
|------|------|------|
| 命令行 | `--apisk-domain MODULE` | 加载的业务领域包（可重复，也支持逗号分隔） |
| 命令行 | `--apisk-dump-http` | 失败用例的 HTTP 请求/响应现场写入 `<报告目录>/http/<用例>.json`（凭据字段已脱敏） |
| `pytest.ini` | `apisk_domains` | 领域包列表（linelist，支持逗号分隔） |

运行期首行会打印一次运行上下文，便于排查「领域到底加载上没有」：

```
[apisk] domains=domain.asr_domain, domain.anti_domain
```
