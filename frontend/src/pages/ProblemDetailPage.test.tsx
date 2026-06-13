import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProblemDetailPage } from './ProblemDetailPage'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/problems/two-sum']}>
        <Routes>
          <Route path="/problems/:slug" element={<ProblemDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProblemDetailPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders problem metadata and Chinese statement content', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: 1,
            frontend_id: '1',
            slug: 'two-sum',
            title: 'Two Sum',
            translated_title: '两数之和',
            difficulty: 'Easy',
            tags: [{ slug: 'array', name: 'Array', translated_name: '数组' }],
            categories: [{ slug: 'hot-100', name: 'Hot 100', description: '' }],
            statement_md: '# Two Sum\n\n## 翻译\n\n给定一个整数数组。',
            leetcode_url: 'https://leetcode.cn/problems/two-sum/',
            sample_test_case: '',
            python3_snippet: '',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: '1. 两数之和' })).toBeInTheDocument()
    expect(screen.getByText('Easy')).toBeInTheDocument()
    expect(screen.getByText('数组')).toBeInTheDocument()
    expect(screen.getByText('给定一个整数数组。')).toBeInTheDocument()
    expect(screen.queryByText('Two Sum', { selector: 'h1' })).not.toBeInTheDocument()
  })
})
