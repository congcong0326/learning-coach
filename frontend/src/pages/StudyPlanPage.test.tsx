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

describe('StudyPlanPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders active plan stages and current-stage items', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        okJson({
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
                ],
              },
            ],
          },
        }),
      ),
    )

    renderPage()

    expect(await screen.findByText('3 个月 Java 面试冲刺计划')).toBeInTheDocument()
    expect(screen.getByText('数组基础')).toBeInTheDocument()
    expect(screen.getByText('Two Sum')).toBeInTheDocument()
    expect(screen.getByText('练 complement 查找。')).toBeInTheDocument()
  })
})
