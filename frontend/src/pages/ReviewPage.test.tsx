import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReviewPage } from './ReviewPage'

function renderPage(route = '/review?sessionId=100') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <ReviewPage />
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

describe('ReviewPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders persisted session review data from API', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        session_id: 100,
        summary_id: 200,
        problem_id: 1,
        problem_slug: 'two-sum',
        final_result: 'ac',
        training_mode: 'guided',
        phases_visited: ['understand_problem', 'review_code', 'summarize'],
        main_stuck_points: ['edge_case_missing'],
        error_types: ['wa'],
        max_hint_level_used: 'key_hint',
        attempt_count: 2,
        complexity_analysis: {},
        core_idea_md: '哈希表维护已访问数字。',
        review_summary_md: '主要问题是重复元素边界。',
        profile_signals: { final_result: 'ac', max_hint_level_used: 'key_hint' },
        profile_update_suggestion: {
          recent_summary: '本题 AC，但边界用例需要加强。',
        },
        profile_delta: { id: 300, status: 'accepted', next_snapshot_id: 301 },
        next_recommendation: {
          review_focus: '下一题先列边界用例。',
        },
        updated_at: '2026-05-26T00:00:00Z',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('two-sum')).toBeInTheDocument()
    expect(screen.getByText('AC')).toBeInTheDocument()
    expect(screen.getByText('understand_problem -> review_code -> summarize')).toBeInTheDocument()
    expect(screen.getByText('edge_case_missing')).toBeInTheDocument()
    expect(screen.getByText('本题 AC，但边界用例需要加强。')).toBeInTheDocument()
    expect(screen.getByText('下一题先列边界用例。')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/practice-sessions/100/review', {
      credentials: 'include',
      headers: { Accept: 'application/json' },
      method: 'GET',
    })
  })

  it('asks for a session id when opened directly', () => {
    renderPage('/review')

    expect(screen.getByText('请先从工作台复盘入口进入。')).toBeInTheDocument()
  })
})
