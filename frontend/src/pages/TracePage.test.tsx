import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TracePage } from './TracePage'

function renderPage(route = '/trace') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <TracePage />
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

describe('TracePage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders trace rows from API', async () => {
    const fetchMock = vi.fn(async () =>
      okJson([
        {
          id: 1,
          session_id: '100',
          thread_id: 'practice-session-100',
          problem_slug: 'two-sum',
          node_name: 'guard_transition',
          phase: 'review_code',
          hint_level: 0,
          model_name: 'gpt-test',
          latency_ms: null,
          stuck_point: 'edge_case_missing',
          should_reveal_solution: false,
          input_summary: { model_phase_after: 'review_code' },
          output_summary: { guard_accepted: true, guard_reason: 'accepted' },
          created_at: '2026-05-26T00:00:00Z',
        },
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage('/trace?sessionId=100')

    expect(await screen.findByText('guard_transition')).toBeInTheDocument()
    expect(screen.getByText('review_code')).toBeInTheDocument()
    expect(screen.getByText('accepted')).toBeInTheDocument()
    expect(screen.getByText('practice-session-100')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/traces?session_id=100', {
      credentials: 'include',
      headers: { Accept: 'application/json' },
      method: 'GET',
    })
  })
})
