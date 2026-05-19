# API 资产列表化与粘性路由策略设计

## 目标

优化 `/settings/api-keys` 的使用体验，并把“多个 OpenAI API 资产”从简单默认资产升级为可启用、可首选、可自动切换的模型资产池。

用户可以在 API 设置页以表格方式管理多个 API 资产，通过弹窗新增或编辑资产。后端在后续 T1 目标生成、T3 AI 教练和其他 LLM 调用中使用粘性策略：一般保持和当前选中的资产通讯，当该资产连续失败达到 3 次后，自动切换到其他启用且可用的资产。

本设计是 `docs/superpowers/specs/2026-05-19-local-auth-api-asset-design.md` 的增强版，不改变“只支持 OpenAI provider、API key 加密落库、前端不回显明文”的基础决策。

## 已确认决策

- API 设置页采用表格列表形态，不再把新增表单常驻在页面左侧。
- 页面顶部提供“新增 API 资产”按钮。
- 新增和编辑都使用弹窗。
- 每个用户可以保存多个 API 资产。
- 每个资产有启用 / 禁用开关；禁用资产不参与后端自动选择。
- 每个用户最多有一个首选资产。
- 后端采用“首选资产优先 + 粘性通讯 + 连续失败 3 次后切换”策略。
- 第一版连续失败阈值固定为 3，不做页面可配置。
- 第一版不做拖拽排序、不做成本统计、不做复杂负载均衡。

## 页面设计

### API 设置页 `/settings/api-keys`

页面结构：

- 顶部：标题 `API 设置`，右侧按钮 `新增 API 资产`。
- 主体：API 资产表格。
- 弹窗：新增资产弹窗、编辑资产弹窗。

表格字段：

| 字段 | 用途 |
| --- | --- |
| 名称 | 展示用户自定义的 `display_name`，用于区分多个 key。 |
| Provider | 第一版固定展示 `openai`。 |
| 模型 | 展示 `model_name`，后续 LLM 调用使用该值。 |
| Base URL | 展示 `base_url`，用于支持 OpenAI 或 OpenAI-compatible endpoint。 |
| API key | 展示 `api_key_mask`，不展示明文。 |
| 启用 | 开关控制 `is_enabled`，关闭后不参与自动选择。 |
| 状态 | 展示 `status`：未测试、可用、不可用。 |
| 连续失败 | 展示 `failure_count`，帮助用户理解为什么发生切换。 |
| 标记 | 展示“首选”和“当前通讯中”。 |
| 操作 | 测试连接、设为首选、编辑、删除。 |

新增弹窗字段：

| 字段 | 用途 |
| --- | --- |
| `display_name` | 资产名称，必填。 |
| `provider` | 固定为 `openai`，禁用编辑。 |
| `base_url` | API base URL，默认 `https://api.openai.com/v1`。 |
| `model_name` | 模型名称，必填。 |
| `api_key` | API key，必填；提交后后端加密落库。 |
| `is_enabled` | 是否启用，默认启用。 |
| `is_preferred` | 是否设为首选，默认如果用户没有首选资产则为 true，否则为 false。 |

编辑弹窗字段：

- 与新增弹窗基本一致。
- `api_key` 可留空，留空表示不覆盖原 key。
- 重新填写 `api_key` 时，后端重新加密保存，更新 `api_key_mask`，并将状态重置为 `untested`、失败次数重置为 0。

删除行为：

- 删除普通资产直接删除。
- 删除首选资产或当前通讯资产时，后端清理相关标记。
- 如果删除后用户没有可用资产，后续 LLM 调用返回明确错误，引导用户新增或启用资产。

## 数据模型调整

在 `llm_credential` 上新增字段：

```text
llm_credential
- is_enabled              # 是否启用，禁用后不参与自动选择
- is_preferred            # 是否为用户首选资产
- is_active               # 是否为当前粘性通讯资产
- failure_count           # 连续失败次数
- last_used_at            # 最近一次被后端 LLM 调用选择的时间
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `is_enabled` | 用户控制资产是否参与自动选择；禁用资产仍保留配置但不会被 LLM 调用使用。 |
| `is_preferred` | 用户首选资产；同一用户最多一个，用于故障恢复后优先回到用户指定资产。 |
| `is_active` | 当前粘性通讯资产；后端优先继续使用它，避免每次请求都随机切换。 |
| `failure_count` | 当前资产连续失败次数；成功调用后清零，失败调用后递增。 |
| `last_used_at` | 最近一次被选为 LLM 调用资产的时间，用于审计和页面展示。 |

兼容策略：

- 现有 `is_default` 保留一版兼容，但语义迁移为 `is_preferred`。
- API 响应可以同时返回 `is_default` 和 `is_preferred`，前端只展示“首选”。
- 旧的 `POST /default` 接口保留兼容，内部调用新的设为首选逻辑。

约束：

- 同一用户最多一个 `is_preferred = true`。
- 同一用户最多一个 `is_active = true`。
- `is_enabled = false` 时，该资产不能被设为当前通讯资产。
- `failure_count` 最小为 0。

## 后端路由策略

固定参数：

```text
LLM_CREDENTIAL_FAILURE_THRESHOLD = 3
```

选择算法：

1. 查找当前用户 `is_active = true` 的资产。
2. 如果当前通讯资产存在，且 `is_enabled = true`，且 `failure_count < 3`，继续使用它。
3. 否则查找首选资产：`is_preferred = true`、`is_enabled = true`、`failure_count < 3`。
4. 如果首选资产可用，将它设为 `is_active = true` 并使用。
5. 如果首选资产不可用，查找其他启用且 `failure_count < 3` 的资产，按 `status = valid` 优先、`last_used_at` 较旧优先、`id` 升序选择。
6. 如果没有可用资产，返回 `llm_credential_unavailable`，前端引导用户新增、启用或测试资产。

调用结果回写：

- 调用成功：
  - 当前资产 `failure_count = 0`。
  - 当前资产 `status = valid`。
  - 当前资产 `last_error = ""`。
  - 当前资产 `last_used_at = now`。
- 调用失败：
  - 当前资产 `failure_count += 1`。
  - 当前资产 `status = invalid`。
  - 当前资产 `last_error` 保存截断后的错误摘要。
  - 如果 `failure_count >= 3`，清理当前资产 `is_active = false`，下一次调用触发重新选择。

说明：

- 第一版切换发生在下一次 LLM 调用，不在同一次请求里自动重试另一个 key，避免一次用户请求消耗多个资产。
- `测试连接` 只验证单个资产，并不自动把它设为首选或当前通讯资产；用户需要显式点击“设为首选”。
- 禁用当前通讯资产时，后端立即清理该资产的 `is_active`。

## API 调整

### 列表

`GET /api/me/llm-credentials`

返回新增字段：

```json
{
  "items": [
    {
      "id": 1,
      "provider": "openai",
      "display_name": "个人 OpenAI",
      "base_url": "https://api.openai.com/v1",
      "api_mode": "responses",
      "model_name": "gpt-4.1-mini",
      "api_key_mask": "sk-...abcd",
      "is_enabled": true,
      "is_preferred": true,
      "is_active": true,
      "failure_count": 0,
      "status": "valid",
      "last_used_at": "2026-05-19T10:00:00Z",
      "last_tested_at": "2026-05-19T09:55:00Z",
      "last_error": ""
    }
  ]
}
```

### 创建

`POST /api/me/llm-credentials`

新增请求字段：

- `is_enabled`
- `is_preferred`

如果用户创建第一个资产，即使请求没有传 `is_preferred = true`，服务层也可以将其设为首选，减少首次配置步骤。

### 更新

`PATCH /api/me/llm-credentials/{id}`

支持更新：

- `display_name`
- `base_url`
- `api_mode`
- `model_name`
- `api_key`
- `is_enabled`

禁用资产时：

- 如果该资产是当前通讯资产，清理 `is_active`。
- 如果该资产是首选资产，保留 `is_preferred`，但它不参与选择；用户重新启用后可恢复首选作用。

### 设置首选

`POST /api/me/llm-credentials/{id}/preferred`

行为：

- 清理同用户其他资产的 `is_preferred`。
- 将目标资产设为 `is_preferred = true`。
- 如果目标资产已启用且 `failure_count < 3`，也可以设为 `is_active = true`，让后续调用立即粘住新首选。

### 兼容默认资产

`POST /api/me/llm-credentials/{id}/default`

保留一版兼容，内部调用设为首选逻辑。响应继续返回 `is_default`，其值等同 `is_preferred`。

## 与后续 T1/T3 的关系

后续所有 LLM 调用都不直接读取“默认资产”，而是调用统一服务方法：

```text
select_llm_credential_for_user(user_id)
record_llm_credential_success(credential_id)
record_llm_credential_failure(credential_id, error_summary)
```

这样 T1 目标生成、T3 AI 教练、RAG 总结和代码 review 都复用同一套资产选择和故障切换规则。

## 测试要求

后端测试：

- 创建多个资产时可设置启用和首选。
- 同一用户只能有一个首选资产。
- 禁用资产不参与选择。
- 当前通讯资产未达到失败阈值时保持粘性。
- 当前通讯资产连续失败 3 次后，下一次选择切换到其他启用资产。
- 成功调用后清零失败次数。
- 旧 `/default` 接口仍可使用，并等同设置首选。

前端测试：

- API 设置页展示表格列表和“新增 API 资产”按钮。
- 点击新增打开弹窗并提交创建请求。
- 点击编辑打开弹窗，API key 留空时不提交覆盖字段。
- 启用开关触发 PATCH。
- 点击设为首选调用 `/preferred`。
- 表格展示首选、当前通讯中、连续失败次数和脱敏 key。

## 风险与约束

- 自动切换不能掩盖配置错误；达到阈值后仍应在表格中显示失败次数和最近错误。
- 第一版不做同一次请求内重试，避免一次用户动作消耗多个 key，也避免错误定位复杂化。
- `is_default` 与 `is_preferred` 短期共存会带来命名冗余；后续稳定后可以移除 `is_default`。
- 如果用户禁用所有资产，后续 LLM 功能必须返回明确错误，不能回退到全局环境变量。
