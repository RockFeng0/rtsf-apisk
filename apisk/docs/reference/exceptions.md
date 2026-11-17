# 参考：异常与退出码

## 1. 一条设计约定

**契约层面的失败一律用断言表达，不抛异常。** 本框架的异常只用于「测试代码自身无法继续」
的场景（领域声明错误、运行期非法操作），以免把环境问题伪装成用例失败。

---

## 2. 异常层级

```
AutoTestError            # 本框架所有异常的基类
└── DomainError          # 业务领域声明或加载错误
```

| 异常 | 触发场景 | 典型修复 |
|------|----------|----------|
| `DomainError` | 领域包无法导入 / 未导出 `DOMAIN` / 领域重名 / `Domain.name` 为空 / 注册表冻结后再注册 / 访问未声明的端点或服务 / 访问未装配的服务属性 | 见下文逐条对照 |

### 2.1 `DomainError` 的常见消息与含义

| 消息片段 | 含义 | 修复 |
|----------|------|------|
| `无法导入领域包 'x'` | 模块不存在或不在 `sys.path` | 确认写的是**点号分隔的可导入路径**，并在套件 `pytest.ini` 加 `pythonpath = .` |
| `领域包 'x' 未导出 DOMAIN / DOMAINS 声明` | 包里没有模块级 `DOMAIN` / `DOMAINS` | 在领域包导出 `DOMAIN = Domain(...)` |
| `领域 'x' 已注册，请检查是否重复加载` | 同一领域名被声明两次 | 去掉重复的声明来源（如 ini 与命令行同时写了） |
| `Domain 需要 name` | 构造 `Domain` 时没给 `name` | 补上领域名 |
| `领域注册已冻结…` | 运行期（配置阶段之后）尝试注册领域 | 领域必须在 pytest 配置阶段声明；不要在用例里 `load_domains()` |
| `领域 'x' 未声明端点 / 服务 'y'` | 用了 `domain.api()` / `domain.service()` 取未声明的名字 | 对照 `Domain.apis` / `Domain.services` 补声明 |

---

## 3. 领域加载失败：友好退出而非 INTERNALERROR

领域声明写错时，框架在 `pytest_configure` 阶段捕获 `DomainError` / `ImportError`，转为
`pytest.exit(..., returncode=4)` 并打印可操作的提示：

```
Exit: 领域加载失败: 无法导入领域包 'no.such.domain': No module named 'no'

领域声明来源（可并用，本次已尝试）：
  --apisk-domain MODULE   命令行
  apisk_domains = MODULE  pytest.ini
  AUTO_TEST_DOMAINS      环境变量
  apisk.domains           入口点（pip 安装的领域包自动发现）
  本次声明: no.such.domain, domain.mydomain_domain

请确认写的是**可导入的模块路径**（点号分隔），例如：
  apisk_domains = domain.mydomain_domain
且该模块所在目录在 sys.path 上（套件 pytest.ini 可加 pythonpath = .）。
```

提示里会列出**本次实际尝试过的全部声明**，方便定位是哪一处写错了。

---

## 4. pytest 退出码对照

| 退出码 | 含义 | 本框架下的常见原因 |
|--------|------|--------------------|
| `0` | 全部通过（skip 不影响） | 正常 |
| `1` | 有用例失败 | 断言不成立；加 `--apisk-dump-http` 可拿到失败用例的 HTTP 现场 |
| `2` | 执行被中断 | `Ctrl+C`；或收集期错误 |
| `3` | 内部错误 | pytest 自身异常，通常伴随 INTERNALERROR |
| `4` | 用法 / 配置错误 | **领域加载失败**（见上节） |
| `5` | 未收集到用例 | 收集范围内没有 `test_*.py`；例如在框架包目录 `apisk/` 直接执行 `pytest` |

---

## 5. 常见错误与对策速查

| 现象 | 原因 | 对策 |
|------|------|------|
| 用例全被 skip，原因含 `UNREACHABLE` | 门禁探测认为服务不可用 | 检查领域的 `probe` 端点是否正确、Service 的 `HttpClient.base_url` 是否指向正确的服务 |
| 报告没生成 | 缺 pytest-html | `pip install pytest-html`（框架会在告警里提示） |
| `pytest` 在 `apisk/` 目录下报「无用例」（退出码 5） | 框架包目录不含用例 | 这是预期行为：先 `python -m apisk.scaffold --name mydomain --out test_mydomain` 生成骨架，再 `cd test_mydomain && pytest` |
| 断言失败只看到一行 `assert ...` | 用的是裸 `assert`，没有现场信息 | 加 `--apisk-dump-http` 开启 HTTP 现场落盘，失败用例的完整请求/响应会写进报告目录下的 http/ 子目录 |
