import { useQuery } from '@tanstack/react-query'
import { Alert, Descriptions, Spin, Tag, Typography } from 'antd'
import { useSearchParams } from 'react-router-dom'

import { getPracticeReview } from '../api/review'
import type { HintLevel } from '../api/practice'

const resultLabels: Record<string, string> = {
  ac: 'AC',
  accepted: 'AC',
  wa: 'WA',
  tle: 'TLE',
  re: 'RE',
  mle: 'MLE',
  ce: 'CE',
  unknown: 'UNKNOWN',
}

const hintLabels: Record<HintLevel, string> = {
  questioning: '追问档',
  direction: '方向档',
  key_hint: '关键档',
  reflection: '复盘档',
}

function resultLabel(value: string) {
  return resultLabels[value.toLowerCase()] ?? value
}

function textFromRecord(record: Record<string, unknown>, key: string) {
  const value = record[key]
  return typeof value === 'string' && value.trim() ? value : '-'
}

export function ReviewPage() {
  const [params] = useSearchParams()
  const sessionIdText = params.get('sessionId')
  const sessionId = sessionIdText && /^\d+$/.test(sessionIdText)
    ? Number(sessionIdText)
    : null
  const reviewQuery = useQuery({
    queryKey: ['practice-review', sessionId],
    queryFn: () => getPracticeReview(sessionId ?? 0),
    enabled: sessionId !== null,
    retry: false,
  })

  if (sessionId === null) {
    return (
      <section className="page-section">
        <Typography.Title level={2}>复盘</Typography.Title>
        <Alert showIcon type="info" message="请先从工作台复盘入口进入。" />
      </section>
    )
  }

  if (reviewQuery.isLoading) {
    return (
      <section className="page-section">
        <Typography.Title level={2}>复盘</Typography.Title>
        <Spin />
      </section>
    )
  }

  if (reviewQuery.isError || !reviewQuery.data) {
    return (
      <section className="page-section">
        <Typography.Title level={2}>复盘</Typography.Title>
        <Alert showIcon type="error" message="复盘加载失败" />
      </section>
    )
  }

  const review = reviewQuery.data
  return (
    <section className="page-section">
      <Typography.Title level={2}>复盘</Typography.Title>
      <Descriptions
        bordered
        size="middle"
        column={1}
        items={[
          {
            key: 'problem',
            label: '题目',
            children: review.problem_slug,
          },
          {
            key: 'result',
            label: '最终结果',
            children: <Tag color="green">{resultLabel(review.final_result)}</Tag>,
          },
          {
            key: 'phase',
            label: '阶段轨迹',
            children: review.phases_visited.join(' -> ') || '-',
          },
          {
            key: 'stuck',
            label: '主要卡点',
            children: review.main_stuck_points.join('、') || '-',
          },
          {
            key: 'hint',
            label: '最高提示等级',
            children: review.max_hint_level_used
              ? hintLabels[review.max_hint_level_used]
              : '-',
          },
          {
            key: 'attempt',
            label: '提交/回填次数',
            children: review.attempt_count,
          },
          {
            key: 'review',
            label: '代码/提交错因',
            children: review.review_summary_md || review.error_types.join('、') || '-',
          },
          {
            key: 'core',
            label: '复杂度/核心思路',
            children: review.core_idea_md || '-',
          },
          {
            key: 'profile',
            label: '画像更新',
            children: textFromRecord(
              review.profile_update_suggestion,
              'recent_summary',
            ),
          },
          {
            key: 'profile-delta',
            label: '画像增量状态',
            children: textFromRecord(review.profile_delta, 'status'),
          },
          {
            key: 'next',
            label: '下一题建议',
            children: textFromRecord(review.next_recommendation, 'review_focus'),
          },
        ]}
      />
    </section>
  )
}
