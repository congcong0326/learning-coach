import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StudyPlanPage } from './StudyPlanPage'

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StudyPlanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function studyPlanPayload() {
  return {
    id: 10,
    title: '3 个月 Java 面试冲刺计划',
    status: 'active',
    active_version_number: 1,
    active_version: {
      id: 20,
      version_number: 1,
      status: 'active',
      target_snapshot: { preferred_language: 'java' },
      generation_summary_md: '基于面试冲刺生成。',
      adjustment_summary_md: '',
      stages: [
        {
          id: 30,
          stage_index: 1,
          title: '数组基础',
          objective_md: '补齐数组基础。',
          focus_tags: ['array'],
          assessment_criteria: ['能讲清哈希表'],
          status: 'in_progress',
          items: [
            {
              id: 40,
              problem_slug: 'two-sum',
              frontend_id: '1',
              title: 'Two Sum',
              translated_title: '两数之和',
              difficulty: 'Easy',
              skill_tags: ['array'],
              suggested_mode: 'guided',
              recommendation_reason: '练 complement 查找。',
              status: 'pending',
              order_index: 1,
              locked: false,
            },
            {
              id: 41,
              problem_slug: 'valid-parentheses',
              frontend_id: '20',
              title: 'Valid Parentheses',
              translated_title: '有效的括号',
              difficulty: 'Easy',
              skill_tags: ['stack'],
              suggested_mode: 'independent',
              recommendation_reason: '练栈匹配。',
              status: 'in_progress',
              order_index: 2,
              locked: false,
            },
            {
              id: 42,
              problem_slug: 'binary-search',
              frontend_id: '704',
              title: 'Binary Search',
              translated_title: '二分查找',
              difficulty: 'Easy',
              skill_tags: ['binary-search'],
              suggested_mode: 'independent',
              recommendation_reason: '练边界。',
              status: 'completed',
              order_index: 3,
              locked: false,
            },
            {
              id: 43,
              problem_slug: 'merge-intervals',
              frontend_id: '56',
              title: 'Merge Intervals',
              translated_title: '合并区间',
              difficulty: 'Medium',
              skill_tags: ['interval'],
              suggested_mode: 'guided',
              recommendation_reason: '练排序合并。',
              status: 'skipped',
              order_index: 4,
              locked: false,
            },
            {
              id: 44,
              problem_slug: 'climbing-stairs',
              frontend_id: '70',
              title: 'Climbing Stairs',
              translated_title: '爬楼梯',
              difficulty: 'Easy',
              skill_tags: ['dynamic-programming'],
              suggested_mode: 'independent',
              recommendation_reason: '练状态转移。',
              status: 'locked_completed',
              order_index: 5,
              locked: true,
            },
          ],
        },
      ],
    },
  }
}

describe('StudyPlanPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders active plan stages and current-stage items', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => okJson(studyPlanPayload())),
    )

    renderPage()

    expect(await screen.findByText('3 个月 Java 面试冲刺计划')).toBeInTheDocument()
    expect(screen.getByText('数组基础')).toBeInTheDocument()
    expect(screen.getByText('Two Sum')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /1\. Two Sum/ })).toHaveAttribute(
      'href',
      '/workspace/items/40',
    )
    expect(screen.getByText('练 complement 查找。')).toBeInTheDocument()
    expect(screen.getByText('未开始')).toHaveClass('ant-tag-default')
    expect(screen.getByText('编码中')).toHaveClass('ant-tag-blue')
    const acTags = screen.getAllByText('已AC')
    expect(acTags).toHaveLength(2)
    acTags.forEach((tag) => expect(tag).toHaveClass('ant-tag-green'))
    expect(screen.getByText('已跳过')).toHaveClass('ant-tag-orange')
  })

  it('does not render removed enhancement actions', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson(studyPlanPayload())))

    renderPage()

    expect(await screen.findByText('3 个月 Java 面试冲刺计划')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看画像与补强' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '计划历史' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '调整计划' })).not.toBeInTheDocument()
  })
})
