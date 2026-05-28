import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('requests the selected page from the API', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      const page = url.searchParams.get('page') ?? '1'
      const item =
        page === '2'
          ? {
              id: 21,
              frontend_id: '21',
              slug: 'problem-21',
              title: 'Problem 21',
              translated_title: '题目 21',
              difficulty: 'Medium',
              tags: [],
              categories: [],
            }
          : {
              id: 1,
              frontend_id: '1',
              slug: 'problem-1',
              title: 'Problem 1',
              translated_title: '题目 1',
              difficulty: 'Easy',
              tags: [],
              categories: [],
            }

      return new Response(
        JSON.stringify({
          items: [item],
          total: 21,
          page: Number(page),
          page_size: 20,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('Problem 1')).toBeInTheDocument()
    const pageTwo = screen.getByTitle('2')
    fireEvent.click(pageTwo.querySelector('a') ?? pageTwo)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toBe('/api/problems?page=2&page_size=20')
    expect(await screen.findByText('Problem 21')).toBeInTheDocument()
  })
})
