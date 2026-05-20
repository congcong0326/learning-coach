import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StudyPlanHistoryPage } from './StudyPlanHistoryPage'

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StudyPlanHistoryPage />
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

describe('StudyPlanHistoryPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders plans and activates a paused plan', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/study-plans/2/activate' && init?.method === 'POST') {
        return okJson({
          id: 2,
          title: '动态规划专项',
          status: 'active',
          active_version_number: 1,
          active_version: { stages: [] },
        })
      }
      return okJson({
        items: [
          { id: 1, title: '面试冲刺', status: 'active', active_version_number: 1 },
          { id: 2, title: '动态规划专项', status: 'paused', active_version_number: 2 },
        ],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('面试冲刺')).toBeInTheDocument()
    expect(screen.getByText('动态规划专项')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '激活' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/study-plans/2/activate',
        expect.objectContaining({ method: 'POST', credentials: 'include' }),
      ),
    )
  })
})
