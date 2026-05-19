# 本地用户与 OpenAI API 资产设计

## 目标

在 T1 目标校准接入大模型之前，先完成本地用户体系和用户级 OpenAI API 资产管理。用户可以本地注册、登录、退出，并在设置页保存自己的 OpenAI API key、base URL 和模型名称。后续目标生成、AI 教练、RAG 总结和代码 review 都从当前登录用户的默认 API 资产读取模型配置。

这个设计是新的 T0，优先级高于 T1。它替代此前 T1 spec 中的 `local-user` 假设和全局环境变量模型配置假设。

## 参考文档

- `docs/prd/prd.md`：产品是登录后的训练工作台，长期记忆和训练记录均围绕 `user_id`。
- `docs/project-todolist.md`：项目总体进度和任务顺序。
- `docs/architecture/foundation.md`：前端只通过 HTTP API 与后端交互，后端负责 LLM、数据库和业务边界。
- `docs/superpowers/specs/2026-05-19-goal-calibration-study-plan-design.md`：T1 目标校准与学习计划设计，后续要改为依赖本设计。
- OpenAI 官方 API 文档：API key 使用 Bearer authentication，API key 不应暴露在客户端；`/v1/models` 可列出当前可用模型；新项目推荐使用 Responses API。

官方参考链接：

- https://platform.openai.com/docs/api-reference/authentication
- https://platform.openai.com/docs/api-reference/models/list
- https://platform.openai.com/docs/api-reference/responses
- https://platform.openai.com/docs/guides/responses-vs-chat-completions

## 已确认决策

- 第一版只支持本地账号注册和登录，不接 OAuth、邮箱验证、找回密码、组织或团队。
- 第一版只支持 OpenAI provider；保留 `base_url` 字段，允许用户配置 OpenAI-compatible endpoint，但 provider 仍记录为 `openai`。
- API key 落库必须加密保存，不能明文保存。
- 前端和 API 永远不返回 API key 明文，只返回 mask 后的 `api_key_mask`。
- API key 支持覆盖更新，不支持查看明文。
- 每个用户可以保存多个 API 资产，但同时只能有一个默认资产。
- 默认资产是后续 T1 目标生成和 T3 AI 教练的模型配置来源。
- 登录态使用后端 session + HttpOnly cookie；不在 localStorage 保存 token。
- 前端整体风格向 ChatGPT 的工作台体验靠拢：左侧窄导航、主内容聚焦、留白克制、输入表单安静、操作路径清晰，但不复制 ChatGPT 品牌、Logo、配色或文案。

## 非目标

- 不实现第三方登录、OAuth、邮箱验证、找回密码。
- 不实现管理员后台、用户封禁、角色权限、组织空间。
- 不支持 Anthropic、Gemini、DeepSeek 等 provider；后续通过 provider 枚举扩展。
- 不实现用量统计、账单、token 成本分析。
- 不实现模型自动发现后的复杂选择器；第一版保留用户填写 `model_name`，测试连接时校验模型可用性。
- 不在浏览器端直接调用 OpenAI API。

## 用户流程

```text
首次访问应用
  -> 未登录：进入 /login
  -> 没有账号：进入 /register
  -> 注册成功后自动登录
  -> 如果当前用户没有默认 API 资产：进入 /settings/api-keys
  -> 用户填写 OpenAI API key、base URL、模型名称
  -> 后端加密保存 API key
  -> 用户点击测试连接
  -> 测试通过后设置为默认资产
  -> 进入后续 T1 目标校准

已有账号访问应用
  -> 登录
  -> 后端通过 session cookie 识别当前用户
  -> 前端通过 /api/auth/me 获取用户信息
  -> 后续所有目标、计划、训练记录、API 资产都绑定当前 user_id
```

## 信息架构与页面

### 登录页 `/login`

用途：

- 用户输入账号和密码登录。
- 登录成功后进入应用主界面。
- 如果用户没有 API 资产，跳转 API 资产配置页；如果已有默认 API 资产，跳转目标校准或学习计划。

页面风格：

- 居中窄面板，背景简洁，表单控件紧凑。
- 页面不做营销 hero，不放大段功能说明。
- 视觉上接近 ChatGPT 登录后的安静产品气质，但使用本项目自己的标题和导航。

### 注册页 `/register`

用途：

- 用户输入用户名、邮箱、密码注册本地账号。
- 注册成功后自动创建登录 session。
- 注册后引导到 API 资产配置页。

字段：

- `username`：显示名和本地登录标识之一。
- `email`：本地登录标识之一。
- `password`：明文只在请求中出现，后端保存 hash。

### API 资产配置页 `/settings/api-keys`

用途：

- 管理当前用户的 OpenAI API 资产。
- 创建、更新、删除、测试连接、设为默认。

表单字段：

- `display_name`：用户可读名称，例如“个人 OpenAI key”。
- `provider`：第一版固定为 `openai`。
- `base_url`：默认 `https://api.openai.com/v1`。
- `api_key`：用户输入的 API key，仅创建或覆盖时提交。
- `model_name`：用户填写模型名称，例如 `gpt-4.1-mini` 或后续可用模型。
- `api_mode`：默认 `responses`；后续如需兼容旧模型可扩展 `chat_completions`。
- `is_default`：是否作为当前用户默认 API 资产。

页面风格：

- 登录后应用使用左侧窄导航，导航项包含“学习计划”“题库”“工作台”“API 设置”等。
- API 设置页主区域保持类似 ChatGPT 设置面板的克制风格：列表在左或上方，详情表单在主区域，不做卡片套卡片。
- API key 输入框默认密码模式；保存后只显示 mask，例如 `sk-...abcd`。
- 测试连接结果使用简短状态：未测试、可用、不可用。

## 数据模型

### app_user

保存本地用户账号。

```text
app_user
- id
- username
- email
- password_hash
- display_name
- status                 # active / disabled
- created_at
- updated_at
- last_login_at
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | 用户主键，后续目标、计划、训练记录和 API 资产都关联该 ID。 |
| `username` | 本地用户名，可用于登录和页面展示。 |
| `email` | 用户邮箱，可用于登录和后续找回密码扩展；T0 不发送邮件。 |
| `password_hash` | 密码 hash，不能保存明文密码。 |
| `display_name` | 页面展示名，默认可等于 username。 |
| `status` | 用户状态；第一版主要使用 `active`，`disabled` 为后续禁用账号预留。 |
| `created_at` | 账号创建时间。 |
| `updated_at` | 账号更新时间。 |
| `last_login_at` | 最近登录时间，用于审计和用户体验。 |

约束：

- `username` 唯一。
- `email` 唯一。
- `password_hash` 必填。

### auth_session

保存后端登录 session。

```text
auth_session
- id
- user_id
- session_token_hash
- expires_at
- revoked_at
- created_at
- last_seen_at
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | session 主键。 |
| `user_id` | 关联登录用户。 |
| `session_token_hash` | session token 的 hash。cookie 保存原始 token，数据库只保存 hash。 |
| `expires_at` | session 过期时间。 |
| `revoked_at` | 退出登录或强制失效时间。 |
| `created_at` | session 创建时间。 |
| `last_seen_at` | 最近一次请求时间，用于审计和后续自动续期。 |

### llm_credential

保存用户级 OpenAI API 资产。

```text
llm_credential
- id
- user_id
- provider               # openai
- display_name
- base_url
- api_mode               # responses
- model_name
- api_key_ciphertext
- api_key_mask
- is_default
- status                 # untested / valid / invalid
- last_tested_at
- last_error
- created_at
- updated_at
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | API 资产主键。 |
| `user_id` | 绑定资产所属用户；不同用户的 key 互相隔离。 |
| `provider` | 模型服务商；T0 固定为 `openai`。 |
| `display_name` | 用户自定义名称，便于区分多个 key。 |
| `base_url` | OpenAI API base URL，默认 `https://api.openai.com/v1`。 |
| `api_mode` | 调用模式；T0 默认 `responses`，后续可扩展旧 Chat Completions。 |
| `model_name` | 模型名称，后续 LLM 调用使用该值。 |
| `api_key_ciphertext` | 加密后的 API key 密文。 |
| `api_key_mask` | 脱敏展示值，例如 `sk-...abcd`，用于前端列表展示。 |
| `is_default` | 是否为当前用户默认 API 资产。 |
| `status` | 测试状态：未测试、可用、不可用。 |
| `last_tested_at` | 最近一次测试连接时间。 |
| `last_error` | 最近一次测试失败原因，截断保存，不记录完整敏感响应。 |
| `created_at` | 资产创建时间。 |
| `updated_at` | 资产更新时间。 |

约束：

- `provider` 第一版只允许 `openai`。
- `base_url` 必须是 `http://` 或 `https://` URL。
- 同一用户只允许一个 `is_default = true` 的资产，服务层在设置默认时清理其他默认项。
- 删除默认资产后，如果用户还有其他资产，前端提示用户重新选择默认资产；服务层不自动猜默认项。

## 密钥与密码安全

### 密码 hash

- 后端使用 Argon2 或 bcrypt 这类专用密码 hash 算法。
- 注册和登录接口永远不返回 `password_hash`。
- 登录失败返回统一错误，避免区分用户不存在和密码错误。

### API key 加密

- 后端使用对称加密保存 API key，例如 `cryptography` 的 Fernet。
- 加密密钥来自环境变量 `CREDENTIAL_ENCRYPTION_KEY`。
- `CREDENTIAL_ENCRYPTION_KEY` 不提交 Git，不通过前端暴露。
- 测试环境使用固定测试 key。
- 如果加密密钥缺失，创建或测试 API 资产接口返回明确错误，避免写入不可解密数据。
- API key 更新采用覆盖写入：用户重新输入 key，后端重新加密保存并更新 mask。

### Cookie

- 登录成功后设置 HttpOnly cookie，例如 `learning_coach_session`。
- SameSite 使用 `Lax`。
- 本地开发可以 `Secure=false`；生产或 HTTPS 环境应使用 `Secure=true`。
- 退出登录时服务端 revoke session，并清除 cookie。

## 后端模块

新增文件：

```text
backend/app/models/auth.py
backend/app/models/llm_credential.py
backend/app/schemas/auth.py
backend/app/schemas/llm_credential.py
backend/app/services/auth_service.py
backend/app/services/credential_crypto.py
backend/app/services/llm_credential_service.py
backend/app/services/openai_connection_service.py
backend/app/api/auth.py
backend/app/api/llm_credentials.py
backend/app/db/migrations/versions/20260519_0003_auth_llm_credentials.py
backend/tests/test_auth_api.py
backend/tests/test_llm_credentials_api.py
backend/tests/test_credential_crypto.py
```

修改文件：

```text
backend/app/main.py
backend/app/core/config.py
backend/app/models/__init__.py
```

模块职责：

- `auth_service.py`：注册、登录、退出、session 校验、当前用户读取。
- `credential_crypto.py`：API key 加密、解密和 mask。
- `llm_credential_service.py`：API 资产 CRUD、默认资产管理、用户隔离。
- `openai_connection_service.py`：使用用户资产测试 OpenAI 连接，后续 T1/T3 复用此客户端构建逻辑。

## API 设计

### POST /api/auth/register

注册本地用户并自动登录。

请求：

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "local-password"
}
```

响应：

```json
{
  "user": {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "display_name": "alice"
  }
}
```

错误：

- 用户名或邮箱重复：409 `user_already_exists`
- 密码过短：422

### POST /api/auth/login

登录本地用户。

请求：

```json
{
  "login": "alice",
  "password": "local-password"
}
```

`login` 可以是 username 或 email。

错误：

- 用户不存在或密码错误：401 `invalid_credentials`
- 用户禁用：403 `user_disabled`

### POST /api/auth/logout

退出当前 session。

响应：

```json
{"status":"ok"}
```

### GET /api/auth/me

读取当前登录用户。

响应：

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "display_name": "alice",
  "has_default_llm_credential": true
}
```

未登录返回 401 `not_authenticated`。

### GET /api/me/llm-credentials

列出当前用户的 API 资产。

响应：

```json
{
  "items": [
    {
      "id": 10,
      "provider": "openai",
      "display_name": "个人 OpenAI key",
      "base_url": "https://api.openai.com/v1",
      "api_mode": "responses",
      "model_name": "gpt-4.1-mini",
      "api_key_mask": "sk-...abcd",
      "is_default": true,
      "status": "valid",
      "last_tested_at": "2026-05-19T00:00:00Z",
      "last_error": ""
    }
  ]
}
```

### POST /api/me/llm-credentials

创建 API 资产。

请求：

```json
{
  "display_name": "个人 OpenAI key",
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "api_mode": "responses",
  "model_name": "gpt-4.1-mini",
  "api_key": "sk-...",
  "is_default": true
}
```

响应不返回 `api_key` 明文，只返回 `api_key_mask`。

### PATCH /api/me/llm-credentials/{credential_id}

更新 API 资产。

允许更新：

- `display_name`
- `base_url`
- `api_mode`
- `model_name`
- `api_key`

如果请求包含 `api_key`，后端覆盖旧密文并重新计算 mask；如果不包含，保留旧 key。

### POST /api/me/llm-credentials/{credential_id}/default

设置当前资产为默认资产。

服务层必须保证同一用户只有一个默认资产。

### POST /api/me/llm-credentials/{credential_id}/test

测试连接。

测试规则：

- 解密 API key。
- 使用 Bearer authentication 调用 `{base_url}/models`。
- 如果 `model_name` 出现在模型列表中，标记为 `valid`。
- 如果模型列表可访问但目标模型不存在，标记为 `invalid`，错误为 `model_not_found`。
- 如果认证失败，标记为 `invalid`，错误为 `authentication_failed`。
- 如果网络或 base_url 错误，标记为 `invalid`，错误为 `connection_failed`。

响应：

```json
{
  "status": "valid",
  "message": "connection_ok",
  "model_name": "gpt-4.1-mini"
}
```

### DELETE /api/me/llm-credentials/{credential_id}

删除当前用户的 API 资产。

要求：

- 只能删除自己的资产。
- 删除默认资产后，`GET /api/auth/me` 返回 `has_default_llm_credential = false`，引导用户重新设置。

## T1 接入方式

T1 目标校准需要改为：

```text
用户填写自身情况
  -> 后端读取当前登录用户
  -> 后端读取用户默认 llm_credential
  -> 调用 OpenAI Responses API 生成 GoalPlanDraft
  -> 前端展示草稿
  -> 用户确认
  -> 落库 user_learning_goal / study_plan / study_plan_item
```

如果用户没有默认 API 资产，T1 草稿生成接口返回 409：

```json
{"detail":"default_llm_credential_required"}
```

## 前端设计

新增文件：

```text
frontend/src/api/auth.ts
frontend/src/api/llmCredentials.ts
frontend/src/pages/LoginPage.tsx
frontend/src/pages/RegisterPage.tsx
frontend/src/pages/ApiKeySettingsPage.tsx
frontend/src/routes/ProtectedRoute.tsx
frontend/src/routes/AuthRedirect.tsx
frontend/src/pages/LoginPage.test.tsx
frontend/src/pages/RegisterPage.test.tsx
frontend/src/pages/ApiKeySettingsPage.test.tsx
```

修改文件：

```text
frontend/src/App.tsx
frontend/src/routes/AppRoutes.tsx
frontend/src/styles/app.css
```

### 路由

```text
/login
/register
/settings/api-keys
/
/study-plan
/problems
/workspace/:slug
```

需要登录的路由统一经过 `ProtectedRoute`。未登录访问受保护页面时跳转 `/login`。

### ChatGPT 风格约束

这里的“ChatGPT 风格”指产品交互气质和布局密度，不复制品牌资产。

- 登录页：居中表单、少量文字、明确主按钮。
- 登录后：左侧窄导航 + 主内容区。
- 主内容：宽度适中，表单和列表以清晰分组呈现，不使用大面积营销式 hero。
- 色彩：浅色背景、低饱和边框、主按钮突出但克制。
- 操作：保存、测试连接、设为默认等主动作靠近对应配置项。
- 文案：短句、直接、偏工具化，不在页面内解释过多功能背景。
- 状态：API key 使用 mask；测试连接状态用简短标签，不展示敏感错误原文。

## 错误处理

- 未登录访问受保护 API：401 `not_authenticated`。
- 登录失败：401 `invalid_credentials`。
- 注册重复：409 `user_already_exists`。
- 未配置加密密钥：500 `credential_encryption_key_missing`。
- API 资产不存在或不属于当前用户：404 `llm_credential_not_found`。
- API key 测试认证失败：返回 200，body 中 `status=invalid`、`message=authentication_failed`，同时更新资产状态。
- API key 测试网络失败：返回 200，body 中 `status=invalid`、`message=connection_failed`，同时更新资产状态。
- 后续 T1 需要默认 API 资产但缺失：409 `default_llm_credential_required`。

## 测试策略

### 后端测试

- 注册成功会创建用户、hash 密码、设置 session cookie。
- 重复 username 或 email 返回 409。
- 登录成功会设置 HttpOnly cookie，并更新 `last_login_at`。
- 登录失败不暴露用户是否存在。
- 登出会 revoke session。
- `/api/auth/me` 未登录返回 401，登录后返回用户信息。
- 创建 API 资产会加密保存 key，并只返回 mask。
- 更新 API 资产时，不传 `api_key` 会保留旧密文；传 `api_key` 会覆盖密文和 mask。
- 同一用户设置默认资产时，其他资产自动变为非默认。
- 用户不能读取、更新、删除其他用户的 API 资产。
- 测试连接使用 fake OpenAI client，覆盖 valid、model_not_found、authentication_failed、connection_failed。

### 前端测试

- 未登录访问受保护路由跳转 `/login`。
- 登录页提交成功后进入下一步。
- 注册页提交成功后进入 API 设置页。
- API 设置页创建资产后不展示明文 key，只展示 mask。
- 点击“测试连接”后展示可用或不可用状态。
- 点击“设为默认”后刷新列表并标记默认资产。
- 没有默认 API 资产时，应用入口引导到 `/settings/api-keys`。

### 验证命令

实现完成后至少运行：

```bash
uv run pytest backend/tests/test_auth_api.py backend/tests/test_llm_credentials_api.py backend/tests/test_credential_crypto.py -q
cd frontend && corepack pnpm test
make build
```

## 文档影响

实现 T0 后需要更新：

- `docs/project-todolist.md`：把 T0 标为已完成，当前任务推进到 T1。
- `docs/architecture/foundation.md`：补充本地用户、session 和 API 资产边界。
- `docs/dev-setup.md`：补充 `CREDENTIAL_ENCRYPTION_KEY` 等本地环境变量。
- `docs/prd/prd.md`：补充第一版目标校准依赖用户级 API 资产和 LLM 草稿确认流程。
- T1 spec：从规则生成计划改为 LLM 生成草稿、用户确认后落库。

## 验收标准

- 用户可以注册、登录、退出。
- 受保护页面和 API 必须识别当前登录用户。
- 用户可以新增、编辑、删除、测试 OpenAI API 资产。
- API key 加密落库，前端和 API 不返回明文。
- 每个用户可以设置一个默认 API 资产。
- 后续 T1 可以通过当前用户默认 API 资产调用 OpenAI 模型生成目标和计划草稿。
- 前端登录、注册和 API 设置页面形成接近 ChatGPT 的安静工作台体验，但保持本项目独立视觉身份。
