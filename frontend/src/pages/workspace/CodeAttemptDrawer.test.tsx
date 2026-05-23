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
    quality_status: 'ready_to_submit' as const,
    quality_comment: '可以去 LeetCode 尝试提交。',
    created_at: '2026-05-23T00:02:00Z',
  },
]

describe('CodeAttemptDrawer', () => {
  it('shows attempt statuses and comments', async () => {
    render(<CodeAttemptDrawer open attempts={attempts} onClose={() => undefined} />)

    expect(screen.getByText('第 1 次尝试')).toBeInTheDocument()
    expect(screen.getByText('待评估')).toBeInTheDocument()
    expect(screen.getByText('建议修改')).toBeInTheDocument()
    expect(screen.getByText('可尝试提交')).toBeInTheDocument()

    fireEvent.mouseOver(screen.getAllByLabelText('AI 简评')[0])
    expect(await screen.findByText('当前代码直接返回空列表，不建议提交。')).toBeInTheDocument()
  })

  it('shows an empty state', () => {
    render(<CodeAttemptDrawer open attempts={[]} onClose={() => undefined} />)

    expect(screen.getByText('暂无代码尝试记录')).toBeInTheDocument()
  })
})
