# 题库初始化与题目浏览设计

## 目标

完成 Agentic Coding Learning Coach 的第一块产品数据底座：从本地参考仓库导入 LeetCode 题库，保存题目主数据，严格隔离题面和题解，并让前端题库列表和做题工作台可以读取真实题目数据。

这个设计只覆盖题库导入、题目浏览、单题详情和分类模型。不实现 AI 教练、训练会话、RAG、代码执行、复盘画像和 LangGraph 状态机。

## 已确认决策

- 第一版主数据源使用 `https://github.com/fishjar/leetcode-problemset`。
- 参考仓库应拉到本地忽略目录，例如 `data/sources/leetcode-problemset/`，不得提交题库原文。
- 导入逻辑只提交代码、migration、测试和文档，不提交第三方题库 Markdown 或 JSON 数据。
- 题目主数据存入 `problem` 表。
- 题面和题解必须隔离：`statement_md` 可用于前端展示和低风险 AI 上下文，`solution_md` 默认不得进入 AI 上下文。
- 不在 `problem` 表上增加 `is_hot100`、`hot100_order` 这类特定题单字段。
- 分类采用通用关联表设计：`problem_category` + `problem_category_item`。
- 当前导入全量题库时不写默认分类数据；有明确分类时才写分类和关联数据。
- 题库同步入口接入 `make db-seed`，替换当前占位输出。

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

- 不自动从远程 GitHub 拉取最新题库。
- 不把第三方题库数据提交进当前仓库。
- 不解析或存储 LeetCode 隐藏测试。
- 不实现 Hot 100 的具体题单导入。
- 不实现用户训练状态、平均提示等级、最近训练时间等学习记录字段。
- 不实现完整搜索引擎；第一版使用数据库筛选和关键词匹配。
- 不把 `solution_md` 接入任何 AI prompt。

## 本地数据源目录

实现时在仓库根目录约定本地数据源目录：

```text
data/
  sources/
    leetcode-problemset/
      problemset_md/
      problemset/
      directory.md
      problemset.json
```

`.gitignore` 需要加入：

```gitignore
# Local third-party datasets
data/sources/
```

导入命令默认读取：

```text
data/sources/leetcode-problemset
```

后端配置允许通过环境变量覆盖：

```text
LEETCODE_PROBLEMSET_PATH=/absolute/path/to/leetcode-problemset
```

如果路径不存在，导入命令应失败并输出清晰错误，提示用户先 clone 参考仓库到本地数据源目录。

## 数据模型

### problem

`problem` 是题目主表，只保存题目本身稳定属性和来源信息。

```text
problem
- id
- problem_id
- frontend_id
- title
- translated_title
- slug
- difficulty
- statement_md
- solution_md
- metadata_json
- leetcode_url
- source_repo
- source_path
- source_commit
- content_hash
- priority
- is_paid_only
- created_at
- updated_at
```

字段说明：

- `problem_id`：LeetCode 内部 questionId，数字字符串可转整数时按整数保存。
- `frontend_id`：展示用题号，例如 `1`。
- `title`：英文标题，例如 `Two Sum`。
- `translated_title`：中文标题，例如 `两数之和`。
- `slug`：题目 slug，例如 `two-sum`，全局唯一。
- `difficulty`：`Easy`、`Medium`、`Hard`。
- `statement_md`：不含 `## solution 题解` 的题面 Markdown。
- `solution_md`：从 `## solution 题解` 开始的题解、代码模板或解法内容。
- `metadata_json`：标签、相似题、代码片段、样例、函数签名等结构化补充数据。
- `leetcode_url`：原题链接。
- `source_repo`：固定为 `https://github.com/fishjar/leetcode-problemset`。
- `source_path`：源文件相对路径，例如 `problemset_md/0000001.two-sum.md`。
- `source_commit`：导入时参考仓库 commit。
- `content_hash`：基于 Markdown 和 JSON 关键内容生成，用于判断是否需要更新。
- `priority`：第一版保留字段，默认 `0`，后续推荐排序可使用。
- `is_paid_only`：是否 Plus 题。

唯一约束：

```text
problem.slug
problem.frontend_id
```

索引：

```text
problem.difficulty
problem.priority
problem.updated_at
```

### problem_category

`problem_category` 表示一个题目集合或题单定义。第一版全量导入时可以没有任何分类记录。

```text
problem_category
- id
- slug
- name
- description
- source
- metadata_json
- created_at
- updated_at
```

示例：

```text
slug: hot_100
name: Hot 100
source: leetcode
```

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
- priority
- metadata_json
- created_at
- updated_at
```

字段说明：

- `sort_order`：分类内顺序，例如 Hot 100 中的第几题。
- `priority`：分类内推荐权重，默认 `0`。
- `metadata_json`：分类来源补充信息，例如原始题单名称、备注、导入批次。

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

导入器必须按以下规则生成 `statement_md` 和 `solution_md`：

1. 读取 `problemset_md/{id}.{slug}.md`。
2. 查找二级标题 `## solution 题解`。
3. 标题之前的内容写入 `statement_md`。
4. 标题及之后的内容写入 `solution_md`。
5. 如果未找到 `## solution 题解`，整个 Markdown 写入 `statement_md`，`solution_md` 写空字符串。
6. `metadata_json` 可以保存 JSON 中的 `hints` 和 `codeSnippets`，但 API 默认不向前端题目详情返回 `solution_md`。

第一版不尝试用正则识别每种语言的具体题解质量。只要内容位于 `## solution 题解` 后，都视为高风险解法内容。

## 元数据提取策略

导入器同时读取 Markdown 和 JSON：

- Markdown 负责生成可渲染的 `statement_md` 和 `solution_md`。
- JSON 负责提取稳定结构化字段。

优先使用 JSON 字段：

```text
question.questionId
question.questionFrontendId
question.title
question.translatedTitle
question.titleSlug
question.difficulty
question.isPaidOnly
question.topicTags
question.similarQuestions
question.codeSnippets
question.sampleTestCase
question.metaData
```

`metadata_json` 第一版结构：

```json
{
  "topic_tags": [
    {
      "name": "Array",
      "slug": "array",
      "translated_name": "数组"
    }
  ],
  "similar_questions": [],
  "code_snippets": [],
  "sample_test_case": "[2,7,11,15]\n9",
  "function_meta": {},
  "source": {
    "json_path": "problemset/0000001.two-sum.json",
    "markdown_path": "problemset_md/0000001.two-sum.md"
  }
}
```

如果 JSON 解析失败但 Markdown 存在，导入器应跳过该题并记录错误，不写入不完整题目。第一版不做部分导入。

## 导入流程

导入流程分为五步：

```text
检查数据源目录
-> 扫描 problemset_md 和 problemset
-> 逐题解析 Markdown 与 JSON
-> upsert problem
-> 输出导入统计
```

导入命令必须幂等。重复执行时：

- `slug` 已存在且 `content_hash` 未变化：跳过更新。
- `slug` 已存在且 `content_hash` 变化：更新题目字段和 `updated_at`。
- `slug` 不存在：插入新题。
- 源文件损坏：跳过该题，记录错误数量，最终返回非零退出码。

第一版不自动删除数据库中已存在但源仓库不存在的题目，避免误删用户后续训练数据。后续可以新增显式 `--prune` 模式。

## 后端模块边界

新增或修改的后端职责边界：

```text
backend/app/models/problem.py
  SQLAlchemy problem、problem_category、problem_category_item 模型。

backend/app/schemas/problem.py
  题库列表和题目详情响应模型。

backend/app/services/problem_importer.py
  本地参考仓库扫描、解析、hash、upsert。

backend/app/services/problem_service.py
  题库查询、筛选、单题详情读取。

backend/app/api/problems.py
  题库 HTTP API。

backend/app/core/config.py
  新增 LEETCODE_PROBLEMSET_PATH 配置。

backend/app/db/migrations/versions/
  新增 problem 相关 migration。
```

命令入口：

```text
backend/app/cli/problem_import.py
```

`make db-seed` 调用：

```bash
uv run python -m backend.app.cli.problem_import
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
- `sort` 支持 `frontend_id`、`difficulty`、`priority`。

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

该接口不得返回 `solution_md`。

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

导入错误分为三类：

- 数据源不存在：直接失败，提示 clone 路径。
- 单题 JSON 或 Markdown 缺失：记录该题失败，继续处理其他题，最终返回非零退出码。
- 数据库写入失败：回滚当前事务，输出异常并返回非零退出码。

API 错误：

- 题目不存在返回 `404`。
- 非法 difficulty、sort 参数返回 `422`。
- 数据库异常返回 `500`，不暴露内部 SQL。

## 测试策略

后端测试：

- Markdown 切分：含 `## solution 题解` 时正确拆分题面和题解。
- Markdown 切分：不含题解标题时 `solution_md` 为空。
- JSON 解析：能提取 Two Sum 的 slug、难度、标签、Python3 snippet。
- content_hash：相同内容 hash 稳定，内容变化 hash 改变。
- upsert：重复导入不重复插入。
- API：列表不返回 `solution_md`。
- API：详情不返回 `solution_md`。
- API：分类为空时列表仍可正常返回题目。

前端测试：

- 题库页渲染 API 返回的题目。
- 难度和关键词筛选会更新请求参数。
- 工作台渲染 Markdown 题面。
- 工作台显示 LeetCode 原题链接。

集成验证：

```bash
make db-migrate
make db-seed
make test
make build
```

Docker smoke 后续可以扩展 `make smoke`，检查至少存在一条题目数据；是否纳入本任务实现阶段再按成本决定。

## 文档影响

实现该设计时需要同步维护：

- `docs/index.md`：新增题库导入 CLI、problem 模型/API 职责说明。
- `docs/architecture/foundation.md`：如果 `make db-seed` 从占位变成题库导入入口，需要更新后续里程碑当前状态。
- `docs/architecture/makefile.md`：更新 `make db-seed` 的命令内容和成功标准。
- `docs/dev-setup.md`：补充本地 clone 参考仓库到 `data/sources/leetcode-problemset/` 的步骤。
- `docs/prd/prd.md`：将 `is_hot100` / `hot100_order` 调整为分类关联表设计。

## 验收标准

- 本地参考仓库目录被 `.gitignore` 忽略，不会提交题库原文。
- 运行 `make db-seed` 能从本地参考仓库导入题目。
- 重复运行 `make db-seed` 不产生重复题目。
- `problem` 表中 `statement_md` 和 `solution_md` 分离。
- `GET /api/problems` 能返回分页题库列表。
- `GET /api/problems/{slug}` 能返回题目详情且不包含 `solution_md`。
- 题库列表页展示真实题目数据。
- 工作台能按 slug 展示真实 Markdown 题面。
- 没有分类数据时题库列表仍正常工作。
- 后续新增 Hot 100 只需要写入 `problem_category` 和 `problem_category_item`，不需要修改 `problem` 表。

## 风险与应对

- 风险：Markdown 标题格式未来变化，导致题面题解切分失败。
  应对：切分函数有单元测试；未匹配题解标题时保守地把全文当题面并记录 warning。

- 风险：JSON 和 Markdown 数量或 slug 不一致。
  应对：以 slug 配对；缺任一文件则跳过该题并在导入统计中输出。

- 风险：第三方题库包含完整题解，后续被 AI 误用。
  应对：API 默认不返回 `solution_md`；AI/RAG 任务必须显式设计权限控制后才能读取。

- 风险：全量导入对开发数据库造成重复或污染。
  应对：使用 `slug` 唯一约束和 `content_hash` 幂等 upsert。

- 风险：题库分类被误解为必填字段。
  应对：分类是可选关系；无分类数据时不写 `problem_category` 和 `problem_category_item`。
