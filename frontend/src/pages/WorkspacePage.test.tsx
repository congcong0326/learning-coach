import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspacePage } from './WorkspacePage'

describe('WorkspacePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders problem statement and LeetCode link', async () => {
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
            statement_md: '# Two Sum\n\n题面内容',
            leetcode_url: 'https://leetcode-cn.com/problems/two-sum/',
            tags: [],
            categories: [],
            sample_test_case: '[2,7,11,15]\n9',
            python3_snippet: 'class Solution:',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/workspace/two-sum']}>
          <Routes>
            <Route path="/workspace/:slug" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('题面内容')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'LeetCode 原题' })).toHaveAttribute(
      'href',
      'https://leetcode-cn.com/problems/two-sum/',
    )
  })
})
