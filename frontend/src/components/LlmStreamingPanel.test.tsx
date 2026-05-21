import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LlmStreamingPanel } from './LlmStreamingPanel'

describe('LlmStreamingPanel', () => {
  it('renders running progress and calls cancel from the active state', () => {
    const onCancel = vi.fn()

    render(
      <LlmStreamingPanel
        title="学习计划生成"
        status="running"
        stage="正在生成训练阶段"
        displayText="先补齐数组和哈希表，再进入动态规划。"
        error={null}
        onCancel={onCancel}
      >
        <span>预计需要几十秒</span>
      </LlmStreamingPanel>,
    )

    expect(screen.getByText('学习计划生成')).toBeInTheDocument()
    expect(screen.getByText('正在生成训练阶段')).toBeInTheDocument()
    expect(screen.getByText('先补齐数组和哈希表，再进入动态规划。')).toBeInTheDocument()
    expect(screen.getByText('预计需要几十秒')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '取消生成' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('renders successful output without the cancel action', () => {
    render(
      <LlmStreamingPanel
        title="复盘建议"
        status="succeeded"
        stage="生成完成"
        displayText="建议下次先写边界条件，再实现主流程。"
        error={null}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.getByText('复盘建议')).toBeInTheDocument()
    expect(screen.getByText('生成完成')).toBeInTheDocument()
    expect(screen.getByText('建议下次先写边界条件，再实现主流程。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '取消生成' })).not.toBeInTheDocument()
  })
})
