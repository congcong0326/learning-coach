# RAG Materials Candidate List

## 0. 文档信息

| 字段 | 内容 |
| --- | --- |
| 文档目的 | 罗列适合进入算法教练 RAG 的候选材料 |
| 调研日期 | 2026-05-19 |
| 使用方式 | 用户自行下载或整理到本地，系统后续只负责解析、清洗、切块和抽取教练卡片 |
| 入库目标 | 优先抽取 concept_card、pattern_card、invariant_card、common_bug_card、hint_card、interview_expression_card |
| 产品要求 | RAG 使用目标、提示档位边界和验收标准见 `docs/prd/rag-prd.md` |

本清单只说明材料候选和入库优先级。材料进入系统后应优先被抽取为可过滤的教练卡片，不应默认作为完整原文或完整题解注入 AI 上下文。

------

## 1. P0：第一批优先引入

这些材料最贴近 LeetCode / 面试刷题场景，适合作为第一版 RAG 的主语料。

| 材料 | 类型 | 语言 | 适合抽取 | 来源 |
| --- | --- | --- | --- | --- |
| 代码随想录 | 刷题路线 / 图文教程 / 题单 | 中文 | problem_coach_card、pattern_card、common_bug_card、hint_card | https://programmercarl.com/ |
| labuladong 的算法笔记 | 刷题方法论 / 算法模板 | 中文 | pattern_card、invariant_card、hint_card、interview_expression_card | https://labuladong.online/ |
| Hello 算法 | 数据结构与算法入门书 | 中文 / 英文 | concept_card、pattern_card、基础术语解释 | https://www.hello-algo.com/ |
| LeetCode 101 | LeetCode 分类刷题书 | 中文 / 英文 | pattern_card、problem_coach_card、common_bug_card | https://github.com/changgyhub/leetcode_101 |
| NeetCode Roadmap / NeetCode 150 | 刷题路线 / 题型地图 | 英文 | 题型标签体系、problem_coach_card、学习路径 | https://neetcode.io/roadmap |
| AlgoMonster | 面试题型模式课程 | 英文 | pattern_card、模板识别信号、hint_card | https://algo.monster/ |
| Grokking the Coding Interview | 面试题型模式课程 | 英文 | pattern_card、problem_coach_card、interview_expression_card | https://www.designgurus.io/course/grokking-the-coding-interview |
| Tech Interview Handbook / Grind 75 | 面试准备指南 / 题单 | 英文 | 学习路径、题目优先级、面试表达模板 | https://www.techinterviewhandbook.org/grind75/ |
| Sean Prashad LeetCode Patterns | LeetCode 题型清单 | 英文 | 题型标签体系、problem_coach_card 索引 | https://seanprashad.com/leetcode-patterns/ |
| Striver A2Z DSA Course Sheet | DSA 学习路线 / 题单 | 英文 | 学习路径、pattern_card、problem_coach_card 索引 | https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2/ |

------

## 2. P1：基础算法与数据结构教材

这些材料不一定直接面向 LeetCode，但适合补强概念解释、复杂度分析、证明思路和算法设计方法。

| 材料 | 类型 | 语言 | 适合抽取 | 来源 |
| --- | --- | --- | --- | --- |
| Introduction to Algorithms, 4th Edition | 算法教材 | 英文 | concept_card、复杂度分析、算法设计范式 | https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/ |
| Algorithms, 4th Edition | 算法教材 / 在线 booksite | 英文 | concept_card、基础数据结构、排序、图算法 | https://algs4.cs.princeton.edu/home/ |
| The Algorithm Design Manual | 算法设计教材 | 英文 | pattern_card、设计思路、常见建模方法 | https://link.springer.com/book/10.1007/978-3-030-54256-6 |
| Algorithm Design | 算法设计教材 | 英文 | 贪心、DP、图算法、证明思路 | https://www.pearson.com/en-us/subject-catalog/p/algorithm-design/P200000003218 |
| Algorithms Illuminated | 算法教材 / 课程书 | 英文 | concept_card、算法直觉、复杂度解释 | https://www.algorithmsilluminated.org/ |
| Algorithms by Jeff Erickson | 免费算法教材 | 英文 | concept_card、DP、图算法、证明思路 | https://jeffe.cs.illinois.edu/teaching/algorithms/ |
| Open Data Structures | 数据结构教材 | 英文 | concept_card、数据结构实现、复杂度 | https://opendatastructures.org/ |
| Problem Solving with Algorithms and Data Structures Using Python | Python 算法教材 | 英文 | Python 实现讲解、基础数据结构、递归 | https://runestone.academy/ns/books/published/pythonds3/index.html |
| Data Structures and Algorithms in Python | Python 数据结构教材 | 英文 | Python 实现、基础数据结构、代码审查参考 | https://www.wiley.com/en-us/Data+Structures+and+Algorithms+in+Python-p-9781118290279 |
| MIT 6.006 Introduction to Algorithms | 公开课 | 英文 | concept_card、课程讲义、复杂度解释 | https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/ |

------

## 3. P1：竞赛算法与进阶专题

这些材料适合补充图论、动态规划、字符串、数学、数据结构进阶内容。第一版可以先按需引入，不必一次性全量入库。

| 材料 | 类型 | 语言 | 适合抽取 | 来源 |
| --- | --- | --- | --- | --- |
| CP-Algorithms | 竞赛算法知识库 | 英文 | concept_card、pattern_card、common_bug_card、代码模板标注 | https://cp-algorithms.com/ |
| OI Wiki | 竞赛算法知识库 | 中文 | concept_card、pattern_card、进阶算法解释 | https://oi-wiki.org/ |
| USACO Guide | 竞赛算法学习路线 | 英文 | 学习路径、难度分层、专题知识卡片 | https://usaco.guide/ |
| Competitive Programmer's Handbook | 竞赛算法书 | 英文 | 模板、专题算法、复杂度分析 | https://cses.fi/book/book.pdf |
| CSES Problem Set | 竞赛题单 | 英文 | 题目标签体系、练习路线、同类题推荐 | https://cses.fi/problemset/ |
| TheAlgorithms/Python | 算法实现仓库 | 英文 | Python 代码模板、实现对照、代码 review 参考 | https://github.com/TheAlgorithms/Python |

------

## 4. P2：面试表达与综合训练材料

这些材料适合在复盘阶段使用，帮助用户把“会做题”转化为“会解释思路”。

| 材料 | 类型 | 语言 | 适合抽取 | 来源 |
| --- | --- | --- | --- | --- |
| Elements of Programming Interviews in Python | 面试算法书 | 英文 | interview_expression_card、代码审查参考、problem_coach_card | http://elementsofprogramminginterviews.com/ |
| Cracking the Coding Interview | 面试书 | 英文 | 面试表达、常见题型、思路组织 | https://www.crackingthecodinginterview.com/ |
| Beyond Cracking the Coding Interview | 面试准备资料 | 英文 | 面试表达、沟通策略、复杂度讲解 | https://www.beyondctci.com/ |
| LeetCode Explore | 官方学习卡片 | 英文 / 中文 | concept_card、题型专题、problem_coach_card 索引 | https://leetcode.com/explore/ |
| InterviewBit Programming | 面试题库 / 训练路线 | 英文 | 题型标签、学习路径、problem_coach_card 索引 | https://www.interviewbit.com/courses/programming/ |

------

## 5. 建议入库顺序

第一批：

```text
代码随想录
-> labuladong 的算法笔记
-> Hello 算法
-> LeetCode 101
-> NeetCode Roadmap / NeetCode 150
-> AlgoMonster 或 Grokking the Coding Interview
```

第二批：

```text
CP-Algorithms
-> OI Wiki
-> USACO Guide
-> CLRS
-> Algorithms, 4th Edition
-> Algorithms Illuminated
```

第三批：

```text
EPI Python
-> Cracking the Coding Interview
-> Tech Interview Handbook / Grind 75
-> TheAlgorithms/Python
-> LeetCode Explore
```

------

## 6. 入库时的材料标注建议

每份材料下载到本地后，建议在导入配置中补充以下字段：

```json
{
  "source_name": "string",
  "source_type": "book | tutorial | blog | course | problem_list | repository",
  "language": "zh | en",
  "priority": "P0 | P1 | P2",
  "main_usage": ["concept_card", "pattern_card", "common_bug_card"],
  "local_path": "string",
  "notes": "string"
}
```

------

## 7. 暂不优先入库的材料类型

- 只有 AC 代码、没有解释的题解仓库。
- 大量复制 LeetCode 官方题解、缺少个人讲解结构的内容。
- 没有目录、标签和章节结构的零散文章合集。
- 只有视频、没有字幕或讲义的课程。
- 和算法刷题关系弱的通用编程语言教程。
