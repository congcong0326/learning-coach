import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspacePage } from './WorkspacePage'

describe('WorkspacePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubProblem(statement_md: string) {
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
            statement_md,
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
  }

  function renderWorkspace() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/workspace/two-sum']}>
          <Routes>
            <Route path="/workspace/:slug" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('renders problem statement and LeetCode link', async () => {
    stubProblem('# Two Sum\n\n题面内容')
    renderWorkspace()

    expect(await screen.findByText('题面内容')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'LeetCode 原题' })).toHaveAttribute(
      'href',
      'https://leetcode-cn.com/problems/two-sum/',
    )
  })

  it('prefers translated markdown statement and renders markdown html', async () => {
    const { container } = renderWorkspaceWithStatement(
      [
        '# Permutations 全排列',
        '',
        'Given a collection of **distinct** integers, return all possible permutations.',
        '',
        '<pre><strong>Input:</strong> [1,2,3]</pre>',
        '',
        '## 翻译',
        '',
        '给定一个 **没有重复** 数字的序列，返回其所有可能的全排列。',
        '',
        '<pre><strong>输入:</strong> [1,2,3]</pre>',
      ].join('\n'),
    )

    expect(
      await screen.findByText('给定一个', { exact: false }),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Given a collection', { exact: false }),
    ).not.toBeInTheDocument()
    expect(container.querySelector('.markdown-statement strong')).toHaveTextContent(
      '没有重复',
    )
    expect(
      container.querySelector('.markdown-statement pre strong'),
    ).toHaveTextContent('输入:')
  })

  it('renders problem images without leaking localhost as referer', async () => {
    const { container } = renderWorkspaceWithStatement(
      [
        '# Trapping Rain Water 接雨水',
        '',
        'Given n bars.',
        '',
        '## 翻译',
        '',
        '给定柱子高度图。',
        '',
        '![](https://assets.leetcode-cn.com/aliyun-lc-upload/uploads/2018/10/22/rainwatertrap.png)',
      ].join('\n'),
    )

    await screen.findByText('给定柱子高度图。')
    const image = container.querySelector('.markdown-statement img')

    expect(image).toHaveAttribute(
      'src',
      'https://assets.leetcode-cn.com/aliyun-lc-upload/uploads/2018/10/22/rainwatertrap.png',
    )
    expect(image).toHaveAttribute('referrerpolicy', 'no-referrer')
    expect(container.querySelector('.markdown-statement img')).toBe(image)
  })
})

function renderWorkspaceWithStatement(statement_md: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: 46,
          frontend_id: '46',
          slug: 'permutations',
          title: 'Permutations',
          translated_title: '全排列',
          difficulty: 'Medium',
          statement_md,
          leetcode_url: 'https://leetcode-cn.com/problems/permutations/',
          tags: [],
          categories: [],
          sample_test_case: '[1,2,3]',
          python3_snippet: 'class Solution:',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/workspace/permutations']}>
        <Routes>
          <Route path="/workspace/:slug" element={<WorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
