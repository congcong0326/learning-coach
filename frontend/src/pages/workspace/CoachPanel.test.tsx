import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CoachPanel } from './CoachPanel'
import type { WorkspacePracticeSession } from './types'

const llmRunMock = vi.hoisted(() => ({
  startRun: vi.fn(),
  cancelRun: vi.fn(),
}))

const llmRunState = vi.hoisted(() => ({
  isRunning: false,
  displayText: '',
  stage: '',
  error: null as { message: string } | null,
  result: null,
}))

const practiceApiMock = vi.hoisted(() => ({
  sendPracticeMessage: vi.fn(),
  submitLeetCodeFeedback: vi.fn(),
}))

vi.mock('../../hooks/useLlmRun', () => ({
  useLlmRun: () => ({
    startRun: llmRunMock.startRun,
    cancelRun: llmRunMock.cancelRun,
    isRunning: llmRunState.isRunning,
    displayText: llmRunState.displayText,
    stage: llmRunState.stage,
    error: llmRunState.error,
    result: llmRunState.result,
  }),
}))

vi.mock('../../api/practice', () => ({
  sendPracticeMessage: practiceApiMock.sendPracticeMessage,
  submitLeetCodeFeedback: practiceApiMock.submitLeetCodeFeedback,
}))

describe('CoachPanel', () => {
  beforeEach(() => {
    llmRunMock.startRun.mockReset()
    llmRunMock.cancelRun.mockReset()
    llmRunState.isRunning = false
    llmRunState.displayText = ''
    llmRunState.stage = ''
    llmRunState.error = null
    llmRunState.result = null
    practiceApiMock.sendPracticeMessage.mockReset()
    practiceApiMock.submitLeetCodeFeedback.mockReset()
  })

  it('shows chat-first controls and code attempt entry', () => {
    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.getByRole('button', { name: '代码尝试记录' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'LeetCode 已 AC' })).toBeInTheDocument()
    expect(screen.getByLabelText('发送给教练')).toBeInTheDocument()
    expect(screen.queryByText('画像来源')).not.toBeInTheDocument()
    expect(screen.queryByText('事件时间线')).not.toBeInTheDocument()
  })

  it('keeps the message composer conversational without intent or hint selects', () => {
    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.queryByLabelText('消息意图')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('提示档位')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '请求提示' })).toBeInTheDocument()
  })

  it('sends normal messages as unknown intent for model-side classification', async () => {
    practiceApiMock.sendPracticeMessage.mockResolvedValue({
      event_id: 601,
      run_id: 0,
      session_id: 100,
    })
    llmRunMock.startRun.mockResolvedValue({ run_id: 99 })

    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('发送给教练'), {
      target: { value: '我想用哈希表记录已经遍历过的数字。' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发\s*送/ }))

    await waitFor(() =>
      expect(practiceApiMock.sendPracticeMessage).toHaveBeenCalledWith(100, {
        intent: 'unknown',
        content_md: '我想用哈希表记录已经遍历过的数字。',
        requested_hint_level: null,
      }),
    )
    expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_turn', {
      session_id: 100,
      user_event_id: 601,
      trigger: 'unknown',
    })
  })

  it('sends request hint as an explicit action without exposing a dropdown', async () => {
    practiceApiMock.sendPracticeMessage.mockResolvedValue({
      event_id: 602,
      run_id: 0,
      session_id: 100,
    })
    llmRunMock.startRun.mockResolvedValue({ run_id: 1000 })

    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: '请求提示' }))

    await waitFor(() =>
      expect(practiceApiMock.sendPracticeMessage).toHaveBeenCalledWith(100, {
        intent: 'request_hint',
        content_md: '我需要一个提示。',
        requested_hint_level: null,
      }),
    )
    expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_turn', {
      session_id: 100,
      user_event_id: 602,
      trigger: 'request_hint',
    })
  })

  it('marks the session as LeetCode AC and starts summary', async () => {
    practiceApiMock.submitLeetCodeFeedback.mockResolvedValue({
      id: 901,
      result: 'ac',
      event_id: 902,
      code_snapshot_id: null,
      created_at: '2026-05-23T00:00:00Z',
    })
    llmRunMock.startRun.mockResolvedValue({ run_id: 1001 })
    const refresh = vi.fn()

    render(<CoachPanel session={stubSession()} onSessionRefresh={refresh} />)

    fireEvent.click(screen.getByRole('button', { name: 'LeetCode 已 AC' }))

    await waitFor(() =>
      expect(practiceApiMock.submitLeetCodeFeedback).toHaveBeenCalledWith(100, {
        result: 'ac',
        code_snapshot_id: null,
      }),
    )
    expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_summary', {
      session_id: 100,
      trigger: 'request_summary',
    })
    expect(refresh).toHaveBeenCalled()
  })

  it('shows streaming output only while a coach run is active', () => {
    llmRunState.displayText = '正在生成新的教练回复'
    llmRunState.stage = '正在生成教练回复'
    llmRunState.isRunning = true

    const { container, rerender } = render(
      <CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />,
    )

    expect(container.querySelector('.coach-run-output')).toHaveTextContent(
      '正在生成新的教练回复',
    )
    expect(screen.getByText('状态 正在生成教练回复')).toBeInTheDocument()

    llmRunState.isRunning = false
    rerender(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(container.querySelector('.coach-run-output')).toBeNull()
    expect(screen.queryByText('状态 正在生成教练回复')).not.toBeInTheDocument()
  })
})

function stubSession(): WorkspacePracticeSession {
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
      id: 12,
      version: 'v3',
      source: 'historical_profile',
      confidence: 'medium',
      overall_level: 'intermediate',
      preferred_training_mode: 'guided',
      weak_stuck_points: ['边界用例'],
      strong_skill_tags: ['hash-table'],
      weak_skill_tags: ['array'],
      recent_summary: '最近能说明哈希表思路，但边界检查不稳定。',
      hint_policy_hint: '先追问，再给方向。',
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
        content_md: '先说一下输入输出。',
        payload: {},
        hint_level: null,
        visible_hint_gear: 'questioning',
        created_at: '2026-05-22T00:00:00Z',
      },
    ],
    code_attempts: [],
    created_at: '2026-05-22T00:00:00Z',
    updated_at: '2026-05-22T00:00:00Z',
  }
}
