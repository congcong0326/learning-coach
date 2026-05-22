import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

  it('loads practice session from planned item entry', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url === '/api/study-plan/items/40/practice-session') {
        expect(init?.method).toBe('POST')
        return okJson(stubPracticeSession())
      }
      if (url === '/api/problems/two-sum') {
        return okJson(stubProblemDetail('# Two Sum\n\n## 翻译\n\n计划题题面'))
      }
      return new Response('not found', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWorkspaceAt('/workspace/items/40', '/workspace/items/:itemId')

    expect(await screen.findByText('计划题题面')).toBeInTheDocument()
    expect(screen.getByText('画像来源')).toBeInTheDocument()
    expect(screen.getByText('baseline')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '提交回填' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/study-plan/items/40/practice-session',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('preserves code draft when problem detail finishes loading after the session', async () => {
    let resolveProblem: (response: Response) => void = () => undefined
    const delayedProblem = new Promise<Response>((resolve) => {
      resolveProblem = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = input.toString()
        if (url === '/api/study-plan/items/40/practice-session') {
          expect(init?.method).toBe('POST')
          return okJson(stubPracticeSession())
        }
        if (url === '/api/problems/two-sum') {
          return delayedProblem
        }
        return new Response('not found', { status: 404 })
      }),
    )

    renderWorkspaceAt('/workspace/items/40', '/workspace/items/:itemId')

    const draftInput = await screen.findByLabelText('代码草稿')
    fireEvent.change(draftInput, {
      target: { value: 'class Solution:\n    def twoSum(self, nums, target): pass' },
    })
    resolveProblem(okJson(stubProblemDetail('# Two Sum\n\n## 翻译\n\n延迟题面')))

    expect(await screen.findByText('延迟题面')).toBeInTheDocument()
    expect(screen.getByLabelText('代码草稿')).toHaveValue(
      'class Solution:\n    def twoSum(self, nums, target): pass',
    )
  })

  it('uses saved code snapshot when submitting LeetCode feedback', async () => {
    const feedbackBodies: unknown[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = input.toString()
        if (url === '/api/study-plan/items/40/practice-session') {
          return okJson(stubPracticeSession())
        }
        if (url === '/api/problems/two-sum') {
          return okJson(stubProblemDetail('# Two Sum\n\n## 翻译\n\n计划题题面'))
        }
        if (url === '/api/practice-sessions/100/code-snapshots') {
          return okJson({
            id: 777,
            language: 'python3',
            source: 'manual_save',
            client_revision: 1,
            code_hash: 'hash',
            created_at: '2026-05-22T00:00:00Z',
          })
        }
        if (url === '/api/practice-sessions/100/submission-feedback') {
          feedbackBodies.push(JSON.parse(String(init?.body)))
          return okJson({
            id: 900,
            result: 'unknown',
            event_id: 901,
            code_snapshot_id: 777,
            created_at: '2026-05-22T00:00:00Z',
          })
        }
        return new Response('not found', { status: 404 })
      }),
    )

    renderWorkspaceAt('/workspace/items/40', '/workspace/items/:itemId')

    expect(await screen.findByText('计划题题面')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('代码草稿'), {
      target: { value: 'class Solution:\n    pass' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存快照' }))
    await waitFor(() =>
      expect(screen.getByText('上次保存', { exact: false })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: '提交回填' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(feedbackBodies).toHaveLength(1))
    expect(feedbackBodies[0]).toMatchObject({
      code_snapshot_id: 777,
      result: 'unknown',
    })
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

function renderWorkspaceAt(entry: string, routePath: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={routePath} element={<WorkspacePage />} />
        </Routes>
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

function stubProblemDetail(statement_md: string) {
  return {
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
  }
}

function stubPracticeSession() {
  return {
    id: 100,
    study_plan_id: 10,
    problem_id: 1,
    problem_slug: 'two-sum',
    latest_plan_version_id: 20,
    latest_plan_item_id: 40,
    training_mode: 'guided',
    phase: 'understand_problem',
    status: 'active',
    current_hint_level: 'questioning',
    visible_hint_gear: 'questioning',
    max_hint_level_used: null,
    attempt_count: 0,
    final_result: null,
    profile_snapshot: {
      id: null,
      version: 'v0',
      source: 'baseline',
      confidence: 'low',
      overall_level: 'beginner',
      preferred_training_mode: 'guided',
      weak_stuck_points: ['题意拆解'],
      strong_skill_tags: [],
      weak_skill_tags: ['array'],
      recent_summary: '暂无历史训练。',
      hint_policy_hint: '优先追问。',
      coach_strategy: {},
      evidence: [],
    },
    events: [
      {
        id: 501,
        event_type: 'message',
        role: 'assistant',
        phase: 'understand_problem',
        intent: null,
        content_md: '先复述题意。',
        payload: {},
        hint_level: null,
        visible_hint_gear: 'questioning',
        created_at: '2026-05-22T00:00:00Z',
      },
    ],
    created_at: '2026-05-22T00:00:00Z',
    updated_at: '2026-05-22T00:00:00Z',
  }
}
