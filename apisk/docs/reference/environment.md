# 参考：框架行为开关

**框架零业务配置、零身份概念、零 env var**——业务常量（base_url、端点路径、阈值）
归属各领域包自己的 frozen dataclass，框架不持有也不注入。

框架本身只读取**两个行为开关**（领域加载来源 / 报告输出目录），外加一个 ini 选项：

---

## 1. 领域加载来源（可并用，优先级从高到低）

| 优先级 | 来源 | 写法 |
|--------|------|------|
| 1 | 命令行 | `--apisk-domain mydomain`（可重复，也支持逗号分隔） |
| 2 | `pytest.ini` | `apisk_domains = mydomain`（每行一个，支持逗号分隔） |
| 3 | 环境变量 | `AUTO_TEST_DOMAINS=mydomain,other` |
| 4 | 入口点 | pip 安装的领域包通过 `apisk.domains` entry group 自动发现 |

---

## 2. 报告目录

| 来源 | 写法 |
|------|------|
| 环境变量 | `AUTO_TEST_REPORT_DIR=/path/to/reports` |
| 缺省 | `<pytest rootdir>/reports` |

HTML 报告落点钉在 `<报告目录>/report.html`，`--apisk-dump-http` 的 JSON 落盘在
`<报告目录>/http/<用例>.json`。

---

## 3. 用法示例

```bash
# 切领域
pytest --apisk-domain domain.mydomain_domain

# 临时追加
AUTO_TEST_DOMAINS=mydomain,other pytest

# 报告写到别处
AUTO_TEST_REPORT_DIR=D:\ci\reports pytest
```

运行期首行会打印一次生效上下文，便于确认领域是否加载正确：

```
[apisk] domains=domain.asr_domain, domain.anti_domain
```
