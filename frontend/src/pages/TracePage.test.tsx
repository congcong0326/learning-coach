import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getAgentTraces } from '../api/trace'
import { TracePage } from './TracePage'

vi.mock('../api/trace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/trace')>()
  return {
    ...actual,
    getAgentTraces: vi.fn(),
  }
})

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

describe('TracePage', () => {
  afterEach(() => vi.mocked(getAgentTraces).mockReset())

  it('renders trace rows from API', async () => {
    vi.mocked(getAgentTraces).mockResolvedValue([
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
          retrieved_chunk_ids: [],
          created_at: '2026-05-26T00:00:00Z',
        },
        {
          id: 2,
          session_id: '100',
          thread_id: 'practice-session-100',
          problem_slug: 'two-sum',
          node_name: 'retrieve_supporting_context',
          phase: 'review_code',
          hint_level: 0,
          model_name: 'gpt-test',
          latency_ms: null,
          stuck_point: null,
          should_reveal_solution: null,
          input_summary: { run_id: 10 },
          output_summary: {
            retrieval_status: 'used',
            selected_chunk_ids: [10, 12],
            filtered_reasons: ['full_solution_blocked'],
          },
          retrieved_chunk_ids: [10, 12],
          created_at: '2026-05-26T00:00:01Z',
        },
      ])

    renderPage('/trace?sessionId=100')

    expect(await screen.findByText('guard_transition')).toBeInTheDocument()
    expect(screen.getAllByText('review_code')).toHaveLength(2)
    expect(screen.getByText('accepted')).toBeInTheDocument()
    expect(screen.getByText('chunks 10, 12')).toBeInTheDocument()
    expect(screen.getByText('full_solution_blocked')).toBeInTheDocument()
    expect(screen.getAllByText('practice-session-100')).toHaveLength(2)
    expect(getAgentTraces).toHaveBeenCalledWith(100)
  })
})
