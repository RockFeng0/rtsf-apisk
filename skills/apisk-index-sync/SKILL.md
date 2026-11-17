---
name: apisk-index-sync
description: Sync apisk_knowledge/api-index.md with the latest Apifox spec or interface docs. Supports full rebuild and diff refresh. Use when the user asks to sync API index, refresh api-index, or align with Apifox. Do not use for fetching full endpoint details.
---

# API 索引同步

把 `apisk_knowledge/api-index.md` 与 Apifox 最新 Spec 或接口文档对齐。

## 四条不可违反的约束

1. **绝对禁止一次性全量读 Spec 来"记忆"所有接口**。只拉接口列表的轻量摘要（method + path + description + ref），详情永远下游实时拉。
2. **索引只存四列**：`| 方法 | 路径 | 描述 | ref |`，不写参数结构、请求体、响应体等任何详情。
3. **内部接口**：路径中含独立 `/internal/` 段（`/api/internal/xxx`、`/internal/xxx`、`/api/internal/v1/xxx` 均算），用 markdown `<details>` 折叠块单独包裹，并在折叠标签中标记「不测」。
4. **正式拉取前先 refresh 再 read**，确保拿到服务器最新版。

## ref 列硬约束

ref 必须能被下游 **无歧义地解析到实际数据位置**，不得使用伪造路径。

**生成规则**：`<source-filename>#paths.<path>.<method>`

- `source-filename`：本次同步的 OpenAPI 源文件名（如 `example.openapi.json`），不含路径
- `paths.<path>.<method>`：OpenAPI 文件内部的标准 JSONPath，注意 `<path>` 是字符串字面量（含 `/`、`{param}`），`<method>` 是大写 HTTP 方法

示例：
```
POST /api/items            → example.openapi.json#paths./api/items.POST
GET  /api/jobs/{job_id} → example.openapi.json#paths./api/jobs/{job_id}.GET
```

**严禁**将 `/` 替换为 `_`、`{param}` 做 URL 编码、编造不存在的 `.json` 虚拟路径、或将源文件中的非标准参数语法（如 `<roc_id>`）自动改写为标准花括号。ref 的 path 部分必须与源文件的 `paths` key **一字不差**。

## 前置条件

执行前必须确认以下信息：

- **数据源类型**：从 Apifox MCP Server / Apifox CLI / Apifox Open API / 本地 OpenAPI 文件 中选一种
- **访问凭据**：
  - MCP Server：已在 IDE 配置 `apifox-mcp-server`，环境变量 `APIFOX_ACCESS_TOKEN` 已设置
  - CLI：已安装 `apifox` CLI，项目 ID 已知
  - Open API：项目 ID + API Token
  - 本地文件：OpenAPI JSON/YAML 文件路径

## 执行流程

### Step 0 — Refresh（必须）

确保拉取的是服务器最新版：

- **MCP Server**：向 MCP Server 发送 refresh 请求（通常由 MCP Server 自动缓存刷新，若需强制刷新则重启 MCP 会话）
- **CLI / Open API**：记录当前 Apifox 项目版本号或最后更新时间戳，作为后续 read 的前置校验
- **本地文件**：确认文件最后修改时间不早于上次同步；如需强制刷新则先从 Apifox 导出最新 OpenAPI 文件

### Step 1 — Read 接口列表（轻量模式）

只提取四元组：`(method, path, description, ref)`。

按数据源选择方式：

| 数据源 | 操作 |
|--------|------|
| MCP Server | 调用 MCP 的 endpoint list 工具，遍历获取所有 HTTP 接口的 method + path + description |
| CLI | `apifox endpoint list --project <project-id> --format json` |
| Open API | `GET https://api.apifox.com/api/v1/projects/{id}/endpoints`（Authorization: Bearer {token}） |
| 本地 OpenAPI | 解析 `paths.{path}.{method}` 的 keys + summary + description + ref |

**严禁**在这一步获取任何参数结构、请求体 schema、响应体定义。

### Step 2 — 过滤内部接口

遍历 Step 1 的结果，按 path 中是否包含独立 `/internal/` 路径段分两组：

- **对外接口**（路径不含 `/internal/` 段）：进入主表格
- **内部接口**（路径含 `/internal/` 段，如 `/api/internal/xxx`、`/internal/xxx`、`/api/internal/v1/xxx`）：收集到 internal 列表，后续用 `<details>` 包裹

实现提示：用 `re.search(r"/internal/", path)` 判定即可。

### Step 3 — 计算差异

以 `(method, path)` 作为唯一对齐主键。读取当前 `apisk_knowledge/api-index.md`，解析出已有条目集合，与 Step 2 的新集合做差集：

- **新增**：新集合有、旧集合没有的条目
- **变更**：主键相同但 description 或 ref 发生变化的条目
- **删除**：旧集合有、新集合没有的条目

### Step 4 — 应用变更

根据用户指定的刷新模式：

#### 差异刷新（默认）

只写入新增和变更的条目，已删除的条目保留在原位但在描述列末尾追加 `~~已下线~~` 标记。不做物理删除，防止误删。

#### 全量覆盖

清空旧索引，用 Step 2 生成的新集合完整重写。**执行前必须再次向用户确认**，因为物理删除已下线条目不可恢复。

### Step 5 — 写入 api-index.md

输出格式：

```markdown
| 方法 | 路径 | 描述  | ref |
|:----:|:---:|:---:|:---|
| POST | /api/items | 单个对比 | example.openapi.json#paths./api/items.POST |
| GET | /api/jobs/{job_id} | 查询评估状态 | example.openapi.json#paths./api/jobs/{job_id}.GET |
| ...  | ... | ... | ... |

<details>
<summary>内部接口（不测）— 共 N 条</summary>

| 方法 | 路径 | 描述  | ref |
|:----:|:---:|:---:|:---|
| GET  | /api/internal/xxx | ... | example.openapi.json#paths./api/internal/xxx.GET |

</details>
```

## 产物校验

写入完成后自检：

1. 主表格是否全部为对外接口（无任何含 `/internal/` 段的路径）
2. 内部接口是否全部被 `<details>` 包裹且折叠标签包含「不测」
3. 每行列数是否固定为 4（方法/路径/描述/ref）
4. 内部接口统计数是否与 `<details>` 标签中的数字一致
5. **ref 可解析**：每条 ref 的 `<source-filename>#paths.<path>.<method>` 必须能在源文件 JSON 中精确匹配到 `paths[<path>][<method>]` 节点。任一条 ref 无法解析都视为失败
