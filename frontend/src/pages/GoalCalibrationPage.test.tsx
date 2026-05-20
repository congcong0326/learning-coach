import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GoalCalibrationPage } from './GoalCalibrationPage'

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GoalCalibrationPage />
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

describe('GoalCalibrationPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('submits calibration and shows followup question', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        draft_id: 3,
        status: 'asking_followup',
        followup_question: '你的面试时间是？',
        followup_question_id: 'q1',
        remaining_followups: 2,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(screen.getByLabelText('面试冲刺'))
    fireEvent.click(screen.getByLabelText('1 到 3 个月'))
    fireEvent.click(screen.getByLabelText('Python3'))
    fireEvent.click(screen.getByRole('button', { name: '开始校准' }))

    expect(await screen.findByText('你的面试时间是？')).toBeInTheDocument()
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/goal-calibration',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })
})
