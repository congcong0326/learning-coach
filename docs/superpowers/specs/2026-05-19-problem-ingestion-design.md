# 题库初始化与题目浏览设计

## 目标

完成 Agentic Coding Learning Coach 的第一块产品数据底座：把第三方 LeetCode 题库材料在数据准备阶段清洗成结构化 seed 文件，再由应用导入数据库，让前端题库列表和做题工作台可以读取真实题目数据。

这个设计只覆盖题库数据准备、数据库 seed、题目浏览、单题详情和分类模型。不实现 AI 教练、训练会话、RAG、代码执行、复盘画像和 LangGraph 状态机。

## 已确认决策

- 第一版原始数据参考 `https://github.com/fishjar/leetcode-problemset`。
- 原始参考仓库只用于数据准备阶段，放在本地忽略目录，例如 `data/sources/leetcode-problemset/`，不得提交。
- 使用 Python 脚本把原始 Markdown / JSON 清洗为结构化 seed 文件。
- 应用运行时和 Docker 打包只依赖 seed 文件，不依赖原始参考仓库，也不在运行时解析第三方仓库结构。
- seed 文件包含题面内容，默认不提交到公开 Git 仓库；本地或私有 Docker 镜像可以把 seed 文件打包进去。
- 题目主数据存入 `problem` 表，表中只保留应用运行需要的字段。
- 第一版不把题解入库；准备脚本会丢弃 `## solution 题解` 之后的内容。
- 不在 `problem` 表上增加 `is_hot100`、`hot100_order` 这类特定题单字段。
- 分类采用通用关联表设计：`problem_category` + `problem_category_item`。
- 当前全量题库导入时不写默认分类数据；有明确分类时才写分类和关联数据。
- `make db-seed` 从结构化 seed 文件导入数据库，替换当前占位输出。
- Docker packaged mode 可以通过启动前 seed 或 one-shot seed 服务导入 seed 文件，但导入必须幂等。

## 参考仓库检查结果

设计阶段已临时克隆参考仓库到 `/tmp/learning-coach-reference-leetcode-problemset`，用于确认数据结构。当前检查到的 commit 为：

```text
6bd9323f1a542eac6997f9f76656842333d96c45
```

仓库结构中和第一版相关的目录是：

```text
problemset_md/
  0000001.two-sum.md
  0000002.add-two-numbers.md
  ...

problemset/
  0000001.two-sum.json
  0000002.add-two-numbers.json
  ...

directory.md
problemset.json
```

当前抽样结果：

- `problemset_md/` 有 1828 个 Markdown 文件。
- `problemset/` 有 1828 个 JSON 文件。
- Markdown 文件名格式稳定为 `{zero_padded_problem_id}.{slug}.md`。
- JSON 文件名格式稳定为 `{zero_padded_problem_id}.{slug}.json`。
- Markdown 通常包含 `## 翻译` 和 `## solution 题解`。
- JSON 中包含更稳定的结构化字段，例如 `questionFrontendId`、`titleSlug`、`difficulty`、`topicTags`、`translatedContent`、`codeSnippets`、`sampleTestCase`、`metaData`。

## 非目标

- 不在应用启动时从 GitHub 拉取题库。
- 不把原始第三方题库仓库提交进当前仓库。
- 不把包含完整题面的 seed 文件提交到公开 Git 仓库。
- 不解析或存储 LeetCode 隐藏测试。
- 不实现 Hot 100 的具体题单导入。
- 不实现用户训练状态、平均提示等级、最近训练时间等学习记录字段。
- 不实现完整搜索引擎；第一版使用数据库筛选和关键词匹配。
- 不把题解内容导入 `problem` 表，也不接入任何 AI prompt。

## 数据准备目录

仓库根目录约定两个本地数据目录：

```text
data/
  sources/
    leetcode-problemset/
      problemset_md/
      problemset/
      directory.md
      problemset.json
  seed/
    .gitkeep
    manifest.json
    problems.jsonl
    problem_categories.jsonl
    problem_category_items.jsonl
```

`data/sources/` 保存原始第三方仓库，必须被 Git 忽略。

`data/seed/` 保存清洗后的 seed 文件。由于 `problems.jsonl` 包含完整题面，默认也不提交到公开 Git 仓库；如果当前仓库和 Docker 镜像只在本地或私有环境使用，可以在构建前生成并打包进镜像。

`data/seed/.gitkeep` 可以提交，用于保证 Docker build context 中目录存在；具体 seed 数据文件仍保持忽略。

`.gitignore` 需要加入：

```gitignore
# Local third-party datasets and generated seed data
data/sources/
data/seed/*.jsonl
data/seed/manifest.json
!data/seed/.gitkeep
```

`.dockerignore` 不应忽略 `data/seed/`，这样本地执行 Docker package 时可以把已生成的 seed 文件复制进镜像。

## 数据准备脚本

新增数据准备脚本：

```text
scripts/prepare_problem_seed.py
```

推荐命令：

```bash
uv run python scripts/prepare_problem_seed.py \
  --source data/sources/leetcode-problemset \
  --output data/seed
```

脚本职责：

- 检查原始参考仓库目录是否存在。
- 扫描 `problemset_md/` 和 `problemset/`。
- 按 slug 配对 Markdown 和 JSON。
- 从 Markdown 中截断 `## solution 题解` 之前的内容作为 `statement_md`。
- 丢弃 `## solution 题解` 及之后的题解内容。
- 从 JSON 中提取标题、难度、标签、样例、函数签名和 Python3 代码模板。
- 生成 `data/seed/problems.jsonl`。
- 生成空的 `problem_categories.jsonl` 和 `problem_category_items.jsonl`，为后续 Hot 100 等题单预留。
- 生成 `manifest.json`，记录生成时间、参考仓库 commit、题目数量和脚本版本。

准备阶段失败策略：

- 原始数据目录不存在：直接失败。
- 单题缺少 Markdown 或 JSON：跳过该题并记录错误。
- JSON 解析失败：跳过该题并记录错误。
- 任一题失败时最终返回非零退出码，避免悄悄生成不完整数据。

## Seed 文件格式

### manifest.json

`manifest.json` 保存整个 seed 数据集的来源和生成信息。来源信息放在 manifest 中，不重复写入每道题。

```json
{
  "dataset": "leetcode-problemset",
  "source_repo": "https://github.com/fishjar/leetcode-problemset",
  "source_commit": "6bd9323f1a542eac6997f9f76656842333d96c45",
  "generated_at": "2026-05-19T00:00:00Z",
  "problem_count": 1828,
  "category_count": 0,
  "category_item_count": 0,
  "schema_version": 1
}
```

### problems.jsonl

一行一个题目对象。使用 JSONL 而不是 CSV，是因为 Markdown 题面包含换行、HTML、代码块和转义字符，JSONL 更稳定。

```json
{
  "frontend_id": "1",
  "slug": "two-sum",
  "title": "Two Sum",
  "translated_title": "两数之和",
  "difficulty": "Easy",
  "statement_md": "# Two Sum 两数之和\n\n...",
  "leetcode_url": "https://leetcode-cn.com/problems/two-sum/",
  "is_paid_only": false,
  "metadata": {
    "topic_tags": [
      {
        "name": "Array",
        "slug": "array",
        "translated_name": "数组"
      }
    ],
    "similar_questions": [],
    "sample_test_case": "[2,7,11,15]\n9",
    "function_meta": {},
    "python3_snippet": "class Solution:\n    def twoSum(...)"
  }
}
```

`problems.jsonl` 不包含题解字段。

### problem_categories.jsonl

第一版可以是空文件。后续新增题单时一行一个分类对象。

```json
{
  "slug": "hot_100",
  "name": "Hot 100",
  "description": "LeetCode Hot 100 题单"
}
```

### problem_category_items.jsonl

第一版可以是空文件。后续新增题单时一行一个题目分类关系。

```json
{
  "category_slug": "hot_100",
  "problem_slug": "two-sum",
  "sort_order": 1
}
```

## 数据模型

### problem

`problem` 是题目主表，只保存应用运行时需要的稳定字段。

```text
problem
- id
- frontend_id
- slug
- title
- translated_title
- difficulty
- statement_md
- metadata_json
- leetcode_url
- is_paid_only
- created_at
- updated_at
```

字段说明：

- `id`：数据库内部主键。
- `frontend_id`：LeetCode 展示题号，例如 `1`。
- `slug`：题目 slug，例如 `two-sum`，全局唯一。
- `title`：英文标题，例如 `Two Sum`。
- `translated_title`：中文标题，例如 `两数之和`。
- `difficulty`：题目难度，取值为 `Easy`、`Medium`、`Hard`。
- `statement_md`：清洗后的题面 Markdown，不包含 `## solution 题解` 之后的内容。
- `metadata_json`：标签、相似题、样例、函数签名和 Python3 模板等结构化补充数据。
- `leetcode_url`：原题链接。
- `is_paid_only`：是否 Plus 题。
- `created_at`：数据库创建时间。
- `updated_at`：数据库更新时间。

唯一约束：

```text
problem.slug
problem.frontend_id
```

索引：

```text
problem.difficulty
problem.updated_at
```

第一版不在 `problem` 表保存来源仓库、来源路径、来源 commit、内容 hash、题解、Hot 100 标记或推荐权重。来源信息属于 seed 数据集级别，保存在 `manifest.json` 或 `app_metadata`。

### problem_category

`problem_category` 表示一个题目集合或题单定义。第一版全量导入时可以没有任何分类记录。

```text
problem_category
- id
- slug
- name
- description
- created_at
- updated_at
```

字段说明：

- `id`：数据库内部主键。
- `slug`：分类稳定标识，例如 `hot_100`、`blind_75`、`neetcode_150`。
- `name`：前端展示名称，例如 `Hot 100`。
- `description`：分类说明，可为空字符串。
- `created_at`：数据库创建时间。
- `updated_at`：数据库更新时间。

唯一约束：

```text
problem_category.slug
```

### problem_category_item

`problem_category_item` 表示题目和分类的多对多关系。

```text
problem_category_item
- id
- category_id
- problem_id
- sort_order
- created_at
- updated_at
```

字段说明：

- `id`：数据库内部主键。
- `category_id`：关联 `problem_category.id`。
- `problem_id`：关联 `problem.id`。
- `sort_order`：分类内顺序，例如 Hot 100 中的第几题；没有顺序时为空。
- `created_at`：数据库创建时间。
- `updated_at`：数据库更新时间。

唯一约束：

```text
problem_category_item.category_id + problem_category_item.problem_id
```

索引：

```text
problem_category_item.category_id + sort_order
problem_category_item.problem_id
```

## 题面与题解隔离策略

隔离发生在数据准备阶段，而不是应用运行时。

准备脚本必须按以下规则生成 `statement_md`：

1. 读取 `problemset_md/{id}.{slug}.md`。
2. 查找二级标题 `## solution 题解`。
3. 标题之前的内容写入 seed 文件的 `statement_md`。
4. 标题及之后的内容不写入任何第一版 seed 文件。
5. 如果未找到 `## solution 题解`，整个 Markdown 写入 `statement_md`，并在准备日志中记录 warning。

第一版数据库不建 `solution_md` 字段。后续如果高提示等级或复盘确实需要题解，应单独设计 `problem_solution` 表和权限控制，不应把题解混入题目详情 API。

## 数据库导入流程

导入器从 `data/seed/` 读取结构化 seed 文件，而不是读取原始参考仓库。

导入流程：

```text
检查 seed 目录
-> 读取 manifest.json
-> 导入 problems.jsonl
-> 导入 problem_categories.jsonl
-> 导入 problem_category_items.jsonl
-> 记录导入统计
```

导入命令必须幂等。重复执行时：

- `problem.slug` 已存在：跳过该题，不更新题目正文。
- `problem.slug` 不存在：插入新题。
- `problem_category.slug` 已存在：跳过该分类。
- 分类关系已存在：跳过该关系。
- seed 文件缺失或格式错误：停止导入并返回非零退出码。

题目被视为静态基础数据，第一版不做按 hash 更新。后续如果要升级 seed 数据集，应提供显式重建或同步策略，而不是在普通启动流程里隐式覆盖。

## 启动与 Docker 打包

开发环境推荐显式执行：

```bash
uv run python scripts/prepare_problem_seed.py \
  --source data/sources/leetcode-problemset \
  --output data/seed
make db-migrate
make db-seed
```

Docker 打包时：

- backend 镜像复制 `data/seed/` 到镜像内，例如 `/app/data/seed/`。
- 如果 seed 文件不存在，镜像仍可构建，但执行 seed 时应给出清晰错误。
- packaged compose 可以用 one-shot `seed` 服务执行导入。
- 如果采用 backend 启动时自动导入，必须通过环境变量显式开启，例如 `SEED_PROBLEMS_ON_STARTUP=true`。
- 启动自动导入只能在 `problem` 表为空时执行，并使用 PostgreSQL advisory lock 防止多实例并发导入。

推荐默认路径：

```text
PROBLEM_SEED_PATH=data/seed
```

## 后端模块边界

新增或修改的后端职责边界：

```text
backend/app/models/problem.py
  SQLAlchemy problem、problem_category、problem_category_item 模型。

backend/app/schemas/problem.py
  题库列表、分类列表和题目详情响应模型。

backend/app/services/problem_seed.py
  从结构化 seed 文件导入数据库。

backend/app/services/problem_service.py
  题库查询、筛选、单题详情读取。

backend/app/api/problems.py
  题库 HTTP API。

backend/app/core/config.py
  新增 PROBLEM_SEED_PATH 和可选 SEED_PROBLEMS_ON_STARTUP 配置。

backend/app/db/migrations/versions/
  新增 problem 相关 migration。

scripts/prepare_problem_seed.py
  原始参考仓库到 seed 文件的数据准备脚本。
```

命令入口：

```text
backend/app/cli/problem_seed.py
```

`make db-seed` 调用：

```bash
uv run python -m backend.app.cli.problem_seed
```

建议新增数据准备命令：

```bash
make prepare-problem-seed
```

## API 设计

### GET /api/problems

题库列表查询。

查询参数：

```text
keyword
difficulty
tag
category
status
sort
page
page_size
```

第一版行为：

- `keyword` 匹配英文标题、中文标题和 slug。
- `difficulty` 支持 `Easy`、`Medium`、`Hard`。
- `tag` 匹配 `metadata_json.topic_tags[].slug`。
- `category` 通过 `problem_category.slug` 过滤；没有分类数据时返回空集合。
- `status` 预留，第一版没有训练记录时忽略或固定返回未开始。
- `sort` 支持 `frontend_id`、`difficulty`、`title`。

响应示例：

```json
{
  "items": [
    {
      "id": 1,
      "frontend_id": "1",
      "slug": "two-sum",
      "title": "Two Sum",
      "translated_title": "两数之和",
      "difficulty": "Easy",
      "tags": [
        {
          "slug": "array",
          "name": "Array",
          "translated_name": "数组"
        }
      ],
      "categories": [],
      "status": "not_started",
      "last_practiced_at": null,
      "avg_hint_level": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### GET /api/problems/{slug}

单题详情查询。

响应示例：

```json
{
  "id": 1,
  "frontend_id": "1",
  "slug": "two-sum",
  "title": "Two Sum",
  "translated_title": "两数之和",
  "difficulty": "Easy",
  "statement_md": "# Two Sum 两数之和\n\n...",
  "leetcode_url": "https://leetcode-cn.com/problems/two-sum/",
  "tags": [],
  "categories": [],
  "sample_test_case": "[2,7,11,15]\n9",
  "python3_snippet": "class Solution:\n    def twoSum(...)"
}
```

该接口不得返回题解内容。

### GET /api/problem-categories

分类列表查询。

第一版如果没有分类数据，返回空数组。

响应示例：

```json
{
  "items": []
}
```

## 前端设计

### 题库列表页

当前 `frontend/src/pages/ProblemLibraryPage.tsx` 使用静态 Two Sum 数据。第一版改为通过 TanStack Query 请求 `GET /api/problems`。

页面能力：

- 展示题号、标题、难度、标签、分类、用户状态、最近训练时间、平均提示等级。
- 支持关键词搜索。
- 支持难度筛选。
- 支持标签筛选。
- 支持分类筛选；无分类数据时分类筛选为空。
- 点击题目进入工作台。

用户状态字段第一版可以由后端固定返回 `not_started`，后续训练会话实现后再接真实状态。

### 做题工作台

当前 `frontend/src/pages/WorkspacePage.tsx` 只有三栏壳层。第一版接入 `GET /api/problems/{slug}`：

- 左侧渲染 `statement_md`。
- 顶部展示题号、标题、难度、标签和 LeetCode 原题链接。
- 中间保留 Python 编辑区容器，Monaco 具体训练能力可以在后续工作台任务中完善。
- 右侧教练区保持占位，不接 AI。

如果路由中没有 slug，可以默认打开题库列表中的第一题，或显示选择题目的空状态。第一版推荐使用 `/workspace/:slug`，避免隐式选题。

## 错误处理

数据准备错误：

- 原始数据源不存在：直接失败，提示 clone 路径。
- 单题 JSON 或 Markdown 缺失：记录该题失败，继续处理其他题，最终返回非零退出码。
- JSON 结构缺少必要字段：记录该题失败，继续处理其他题，最终返回非零退出码。

数据库导入错误：

- seed 目录不存在：直接失败，提示先运行数据准备命令。
- `manifest.json` 或 `problems.jsonl` 缺失：直接失败。
- JSONL 行格式错误：停止导入并返回非零退出码。
- 数据库写入失败：回滚当前事务，输出异常并返回非零退出码。

API 错误：

- 题目不存在返回 `404`。
- 非法 difficulty、sort 参数返回 `422`。
- 数据库异常返回 `500`，不暴露内部 SQL。

## 测试策略

后端测试：

- 数据准备：含 `## solution 题解` 时只输出题面，不输出题解。
- 数据准备：不含题解标题时输出全文题面并记录 warning。
- 数据准备：能提取 Two Sum 的 slug、难度、标签、Python3 snippet。
- seed 导入：重复导入不重复插入。
- seed 导入：分类 seed 为空时不创建默认分类。
- seed 导入：分类和题目关联能按 slug 正确建立。
- API：列表不返回题解内容。
- API：详情不返回题解内容。
- API：分类为空时列表仍可正常返回题目。

前端测试：

- 题库页渲染 API 返回的题目。
- 难度和关键词筛选会更新请求参数。
- 工作台渲染 Markdown 题面。
- 工作台显示 LeetCode 原题链接。

集成验证：

```bash
uv run python scripts/prepare_problem_seed.py \
  --source data/sources/leetcode-problemset \
  --output data/seed
make db-migrate
make db-seed
make test
make build
```

Docker smoke 后续可以扩展 `make smoke`，检查至少存在一条题目数据；是否纳入本任务实现阶段再按成本决定。

## 文档影响

实现该设计时需要同步维护：

- `docs/index.md`：新增题库 seed CLI、problem 模型/API、数据准备脚本职责说明。
- `docs/architecture/foundation.md`：说明题库数据从 seed 文件导入，不在运行时解析参考仓库。
- `docs/architecture/docker.md`：说明 Docker packaged mode 如何包含 `data/seed/`，以及 seed-on-startup 或 one-shot seed 服务策略。
- `docs/architecture/makefile.md`：更新 `make prepare-problem-seed` 和 `make db-seed` 的命令内容与成功标准。
- `docs/dev-setup.md`：补充本地 clone 参考仓库、生成 seed 文件、导入数据库的步骤。
- `docs/prd/prd.md`：将 `is_hot100` / `hot100_order` 调整为分类关联表设计，并说明题解第一版不入 `problem` 表。

## 验收标准

- 原始参考仓库目录被 `.gitignore` 忽略，不会提交第三方原始数据。
- seed 文件由 `scripts/prepare_problem_seed.py` 从原始参考仓库生成。
- 生成的 `problems.jsonl` 不包含题解内容。
- `problem` 表不包含来源仓库、来源路径、来源 commit、内容 hash、题解、Hot 100 标记或推荐权重字段。
- 运行 `make db-seed` 能从 seed 文件导入题目。
- 重复运行 `make db-seed` 不产生重复题目。
- 没有分类 seed 数据时不创建默认分类。
- `GET /api/problems` 能返回分页题库列表。
- `GET /api/problems/{slug}` 能返回题目详情且不包含题解内容。
- 题库列表页展示真实题目数据。
- 工作台能按 slug 展示真实 Markdown 题面。
- 后续新增 Hot 100 只需要写入 `problem_category` 和 `problem_category_item` 对应 seed 文件，不需要修改 `problem` 表。

## 风险与应对

- 风险：Markdown 标题格式未来变化，导致题面题解切分失败。
  应对：准备脚本有单元测试；未匹配题解标题时保守地输出全文题面并记录 warning。

- 风险：JSON 和 Markdown 数量或 slug 不一致。
  应对：以 slug 配对；缺任一文件则跳过该题并在准备统计中输出。

- 风险：seed 文件包含完整题面，被误提交到公开仓库。
  应对：`.gitignore` 忽略 `data/seed/*.jsonl` 和 `data/seed/manifest.json`；最终提交前检查 `git status`。

- 风险：Docker 镜像打包了题面数据后被公开发布。
  应对：文档明确 packaged 镜像默认面向本地或私有环境；公开发布前必须移除 seed 文件或确认授权。

- 风险：题解内容被 AI 误用。
  应对：第一版不导入题解；数据库和 API 都没有题解字段。

- 风险：启动自动导入在多实例环境中重复执行。
  应对：默认推荐显式 `make db-seed` 或 one-shot seed 服务；如果启用 `SEED_PROBLEMS_ON_STARTUP`，必须检查空库并使用 PostgreSQL advisory lock。

- 风险：题库分类被误解为必填字段。
  应对：分类是可选关系；无分类 seed 数据时不写 `problem_category` 和 `problem_category_item`。
