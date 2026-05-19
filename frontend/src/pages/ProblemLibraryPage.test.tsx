import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProblemLibraryPage } from './ProblemLibraryPage'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProblemLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProblemLibraryPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders static problem fields from the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            items: [
              {
                id: 1,
                frontend_id: '1',
                slug: 'two-sum',
                title: 'Two Sum',
                translated_title: '两数之和',
                difficulty: 'Easy',
                tags: [{ slug: 'array', name: 'Array', translated_name: '数组' }],
                categories: [],
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    renderPage()

    expect(await screen.findByText('Two Sum')).toBeInTheDocument()
    expect(screen.getByText('两数之和')).toBeInTheDocument()
    expect(screen.getByText('数组')).toBeInTheDocument()
    expect(screen.queryByText('未开始')).not.toBeInTheDocument()
  })
})
