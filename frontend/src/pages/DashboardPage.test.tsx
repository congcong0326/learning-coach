import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from './DashboardPage'

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
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

describe('DashboardPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders minimal learning dashboard metrics from API', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        completed_problem_count: 3,
        common_stuck_points: [
          { stuck_point: 'submission_wa', count: 2 },
          { stuck_point: 'user_reported_stuck', count: 1 },
        ],
        average_hint_gear: 1.7,
        highest_hint_level: 'key_hint',
        recent_profile_summary: '最近 AC 但边界用例需要加强。',
        profile_snapshot_id: 9,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByText('submission_wa x2')).toBeInTheDocument()
    expect(screen.getByText('1.7')).toBeInTheDocument()
    expect(screen.getByText('关键档')).toBeInTheDocument()
    expect(screen.getByText('最近 AC 但边界用例需要加强。')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/practice-dashboard', {
      credentials: 'include',
      headers: { Accept: 'application/json' },
      method: 'GET',
    })
  })
})
