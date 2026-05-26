import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CodeAttemptDrawer } from './CodeAttemptDrawer'

const attempts = [
  {
    snapshot_id: 1,
    event_id: 11,
    language: 'python3',
    source: 'chat_review',
    client_revision: 1,
    code_hash: 'hash-1',
    code_preview: 'class Solution:\n    pass',
    code_text: 'class Solution:\n    pass',
    quality_status: 'pending' as const,
    quality_comment: '',
    created_at: '2026-05-23T00:00:00Z',
  },
  {
    snapshot_id: 2,
    event_id: 12,
    language: 'python3',
    source: 'chat_review',
    client_revision: 2,
    code_hash: 'hash-2',
    code_preview: 'class Solution:\n    def twoSum(self, nums, target):\n        return []',
    code_text:
      'class Solution:\n' +
      '    def twoSum(self, nums, target):\n' +
      '        seen = {}\n' +
      Array.from(
        { length: 80 },
        (_, index) => `        # preserve full submitted code line ${index}`,
      ).join('\n') +
      '\n        return []',
    quality_status: 'needs_fix' as const,
    quality_comment: '当前代码直接返回空列表，不建议提交。',
    created_at: '2026-05-23T00:01:00Z',
  },
  {
    snapshot_id: 3,
    event_id: 13,
    language: 'python3',
    source: 'chat_review',
    client_revision: 3,
    code_hash: 'hash-3',
    code_preview: 'class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]',
    code_text: 'class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]',
    quality_status: 'ready_to_submit' as const,
    quality_comment: '可以去 LeetCode 尝试提交。',
    created_at: '2026-05-23T00:02:00Z',
  },
]

describe('CodeAttemptDrawer', () => {
  it('shows attempt statuses and comments', async () => {
    render(<CodeAttemptDrawer open attempts={attempts} onClose={() => undefined} />)

    expect(screen.getByRole('dialog', { name: '代码尝试记录' })).toBeInTheDocument()
    expect(screen.getByText('第 1 次尝试')).toBeInTheDocument()
    expect(screen.getByText('待评估')).toBeInTheDocument()
    expect(screen.getByText('建议修改')).toBeInTheDocument()
    expect(screen.getByText('可尝试提交')).toBeInTheDocument()

    fireEvent.mouseOver(screen.getAllByLabelText('AI 简评')[0])
    expect(await screen.findByText('当前代码直接返回空列表，不建议提交。')).toBeInTheDocument()
  })

  it('keeps full code collapsed by default and expands the selected attempt', () => {
    render(<CodeAttemptDrawer open attempts={attempts} onClose={() => undefined} />)

    expect(screen.queryByText(/preserve full submitted code line 79/)).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: '完整代码' })[1])

    expect(screen.getByText(/preserve full submitted code line 79/)).toBeInTheDocument()
  })

  it('resets expanded code after closing and reopening', () => {
    const { rerender } = render(
      <CodeAttemptDrawer open attempts={attempts} onClose={() => undefined} />,
    )

    fireEvent.click(screen.getAllByRole('button', { name: '完整代码' })[1])
    expect(screen.getByText(/preserve full submitted code line 79/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByText(/preserve full submitted code line 79/)).not.toBeInTheDocument()
    rerender(<CodeAttemptDrawer open={false} attempts={attempts} onClose={() => undefined} />)
    rerender(<CodeAttemptDrawer open attempts={attempts} onClose={() => undefined} />)

    expect(screen.queryByText(/preserve full submitted code line 79/)).not.toBeInTheDocument()
  })

  it('shows an empty state', () => {
    render(<CodeAttemptDrawer open attempts={[]} onClose={() => undefined} />)

    expect(screen.getByText('暂无代码尝试记录')).toBeInTheDocument()
  })
})
