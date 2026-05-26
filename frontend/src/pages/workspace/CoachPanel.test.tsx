import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
}))

vi.mock('antd', async (importActual) => {
  const actual = await importActual<typeof import('antd')>()
  return {
    ...actual,
    message: {
      ...actual.message,
      error: toastMock.error,
    },
  }
})

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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve
    reject = innerReject
  })
  return { promise, resolve, reject }
}

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
    toastMock.error.mockReset()
  })

  it('shows chat-first controls and code attempt entry', () => {
    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.getByRole('button', { name: '代码尝试记录' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'LeetCode 已 AC' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '回填未通过结果' })).toBeInTheDocument()
    expect(screen.getByLabelText('发送给教练')).toBeInTheDocument()
    expect(screen.queryByText('画像来源')).not.toBeInTheDocument()
    expect(screen.queryByText('事件时间线')).not.toBeInTheDocument()
  })

  it('opens non-AC feedback modal and renders feedback history', () => {
    render(
      <CoachPanel
        session={{
          ...stubSession(),
          submission_feedbacks: [
            {
              id: 801,
              event_id: 802,
              code_snapshot_id: 777,
              result: 'wa',
              failed_case_text: 'nums=[3,3], target=6',
              error_message: 'expected [0,1], got []',
              note_md: '怀疑哈希表更新顺序',
              runtime_ms: null,
              memory_kb: null,
              created_at: '2026-05-24T00:00:00Z',
            },
          ],
        }}
        onSessionRefresh={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '回填未通过结果' }))

    expect(screen.getByRole('dialog', { name: '未通过结果回填' })).toBeInTheDocument()
    expect(screen.getByLabelText('LeetCode 结果')).toBeInTheDocument()
    expect(screen.getAllByText('WA').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('nums=[3,3], target=6')).toBeInTheDocument()
    expect(screen.getByText('expected [0,1], got []')).toBeInTheDocument()
    expect(screen.getByText('怀疑哈希表更新顺序')).toBeInTheDocument()
  })

  it('submits non-AC feedback and starts feedback analysis run', async () => {
    practiceApiMock.submitLeetCodeFeedback.mockResolvedValue({
      id: 811,
      result: 'wa',
      event_id: 812,
      code_snapshot_id: 777,
      note_md: '',
      created_at: '2026-05-24T00:00:00Z',
    })
    llmRunMock.startRun.mockResolvedValue({ run_id: 813 })
    const refresh = vi.fn()

    render(
      <CoachPanel
        session={{
          ...stubSession(),
          code_attempts: [stubCodeAttempt(777)],
        }}
        onSessionRefresh={refresh}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '回填未通过结果' }))
    fireEvent.change(screen.getByLabelText('失败用例'), {
      target: { value: 'nums=[3,3], target=6' },
    })
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() =>
      expect(practiceApiMock.submitLeetCodeFeedback).toHaveBeenCalledWith(100, {
        result: 'wa',
        failed_case_text: 'nums=[3,3], target=6',
        code_snapshot_id: 777,
        runtime_ms: null,
        memory_kb: null,
      }),
    )
    expect(refresh).toHaveBeenCalled()
    expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_turn', {
      session_id: 100,
      user_event_id: 812,
      trigger: 'submit_feedback',
    })
  })

  it('keeps internal status and structured events out of the chat surface', () => {
    render(
      <CoachPanel
        session={{
          ...stubSession(),
          phase: 'summarize',
          status: 'summarizing',
          visible_hint_gear: 'questioning',
          events: [
            {
              id: 701,
              event_type: 'session_started',
              role: 'system',
              phase: 'understand_problem',
              intent: null,
              content_md: '',
              payload: {},
              hint_level: 'questioning',
              visible_hint_gear: 'questioning',
              created_at: '2026-05-22T00:00:00Z',
            },
            {
              id: 702,
              event_type: 'user_message',
              role: 'user',
              phase: 'understand_problem',
              intent: 'unknown',
              content_md: '我用哈希表记录已经看过的数字。',
              payload: {},
              hint_level: null,
              visible_hint_gear: 'questioning',
              created_at: '2026-05-22T00:01:00Z',
            },
            {
              id: 703,
              event_type: 'assistant_message',
              role: 'assistant',
              phase: 'define_invariant',
              intent: null,
              content_md: '继续说一下 key 和 value 分别是什么。',
              payload: {},
              hint_level: null,
              visible_hint_gear: 'questioning',
              created_at: '2026-05-22T00:02:00Z',
            },
            {
              id: 704,
              event_type: 'submission_feedback',
              role: 'user',
              phase: 'summarize',
              intent: 'submit_feedback',
              content_md: '',
              payload: { result: 'ac' },
              hint_level: 'questioning',
              visible_hint_gear: 'questioning',
              created_at: '2026-05-22T00:03:00Z',
            },
            {
              id: 705,
              event_type: 'phase_changed',
              role: 'system',
              phase: 'summarize',
              intent: null,
              content_md: '',
              payload: {},
              hint_level: 'questioning',
              visible_hint_gear: 'questioning',
              created_at: '2026-05-22T00:04:00Z',
            },
          ],
        }}
        onSessionRefresh={vi.fn()}
      />,
    )

    expect(screen.getByText('我用哈希表记录已经看过的数字。')).toBeInTheDocument()
    expect(screen.getByText('继续说一下 key 和 value 分别是什么。')).toBeInTheDocument()
    expect(screen.queryByText('单题复盘')).not.toBeInTheDocument()
    expect(screen.queryByText('summarizing')).not.toBeInTheDocument()
    expect(screen.queryByText('追问档')).not.toBeInTheDocument()
    expect(screen.queryByText('系统')).not.toBeInTheDocument()
    expect(screen.queryByText('理解题意')).not.toBeInTheDocument()
    expect(screen.queryByText('session_started')).not.toBeInTheDocument()
    expect(screen.queryByText('已记录 LeetCode 结果')).not.toBeInTheDocument()
  })

  it('renders markdown for coach chat messages', () => {
    render(
      <CoachPanel
        session={{
          ...stubSession(),
          events: [
            {
              id: 706,
              event_type: 'assistant_message',
              role: 'assistant',
              phase: 'summarize',
              intent: null,
              content_md: '## 单题复盘\n\n- **本题最终结果**：AC\n- 下一步：复述复杂度',
              payload: {},
              hint_level: null,
              visible_hint_gear: 'reflection',
              created_at: '2026-05-22T00:05:00Z',
            },
          ],
        }}
        onSessionRefresh={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: '单题复盘' })).toBeInTheDocument()
    expect(screen.getByText('本题最终结果')).toBeInTheDocument()
  })

  it('renders markdown for streaming coach output', () => {
    llmRunState.isRunning = true
    llmRunState.displayText = '## 正在复盘\n\n- **本题最终结果**：AC'

    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '正在复盘' })).toBeInTheDocument()
    expect(screen.getByText('本题最终结果')).toBeInTheDocument()
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

  it('adds my message to the chat immediately while the send request is in flight', async () => {
    const messageCreate = deferred<{ event_id: number; run_id: number; session_id: number }>()
    practiceApiMock.sendPracticeMessage.mockReturnValue(messageCreate.promise)
    llmRunMock.startRun.mockResolvedValue({ run_id: 99 })

    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('发送给教练'), {
      target: { value: '我先用哈希表记录已经访问过的数字。' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发\s*送/ }))

    const timeline = screen.getByLabelText('教练聊天记录')
    expect(
      await within(timeline).findByText('我先用哈希表记录已经访问过的数字。'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('发送给教练')).toHaveValue('')

    messageCreate.resolve({ event_id: 607, run_id: 0, session_id: 100 })
    await waitFor(() =>
      expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_turn', {
        session_id: 100,
        user_event_id: 607,
        trigger: 'unknown',
      }),
    )
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

  it('uses the latest code attempt when marking LeetCode AC', async () => {
    practiceApiMock.submitLeetCodeFeedback.mockResolvedValue({
      id: 903,
      result: 'ac',
      event_id: 904,
      code_snapshot_id: 888,
      created_at: '2026-05-23T00:00:00Z',
    })
    llmRunMock.startRun.mockResolvedValue({ run_id: 1002 })

    render(
      <CoachPanel
        session={{
          ...stubSession(),
          code_attempts: [stubCodeAttempt(111), stubCodeAttempt(888)],
        }}
        onSessionRefresh={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'LeetCode 已 AC' }))

    await waitFor(() =>
      expect(practiceApiMock.submitLeetCodeFeedback).toHaveBeenCalledWith(100, {
        result: 'ac',
        code_snapshot_id: 888,
      }),
    )
  })

  it('keeps AC recorded when summary generation fails', async () => {
    practiceApiMock.submitLeetCodeFeedback.mockResolvedValue({
      id: 905,
      result: 'ac',
      event_id: 906,
      code_snapshot_id: null,
      created_at: '2026-05-23T00:00:00Z',
    })
    llmRunMock.startRun.mockRejectedValue(new Error('run creation failed'))
    const refresh = vi.fn()

    render(<CoachPanel session={stubSession()} onSessionRefresh={refresh} />)

    fireEvent.click(screen.getByRole('button', { name: 'LeetCode 已 AC' }))

    await waitFor(() =>
      expect(practiceApiMock.submitLeetCodeFeedback).toHaveBeenCalledTimes(1),
    )
    expect(refresh).toHaveBeenCalled()
    expect(toastMock.error).toHaveBeenCalledWith(
      'AC 已记录，复盘生成失败，请稍后重试',
    )
    expect(toastMock.error).not.toHaveBeenCalledWith('AC 状态记录失败，请稍后重试')
  })

  it('shows one lightweight backend status line while a coach run is active', () => {
    llmRunState.displayText = '正在生成新的教练回复'
    llmRunState.stage = '正在调用大模型'
    llmRunState.isRunning = true

    const { container, rerender } = render(
      <CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />,
    )

    expect(screen.getByText('正在调用大模型')).toHaveClass('coach-run-status-text')
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('教练聊天记录')).getByText(
      '正在生成新的教练回复',
    )).toBeInTheDocument()
    expect(container.querySelector('.coach-run-output')).toBeNull()
    expect(screen.queryByText('状态 正在调用大模型')).not.toBeInTheDocument()

    llmRunState.isRunning = false
    rerender(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.queryByText('正在调用大模型')).not.toBeInTheDocument()
    expect(container.querySelector('.coach-run-output')).toBeNull()
  })

  it('renders running coach output as an assistant chat bubble', () => {
    llmRunState.displayText = '你这个方向可以，下一步说清楚哈希表里存什么。'
    llmRunState.stage = '正在调用大模型'
    llmRunState.isRunning = true

    const { container } = render(
      <CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />,
    )

    const timeline = screen.getByLabelText('教练聊天记录')
    expect(
      within(timeline).getByText('你这个方向可以，下一步说清楚哈希表里存什么。'),
    ).toBeInTheDocument()
    expect(container.querySelector('.coach-run-output')).toBeNull()
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
        event_type: 'assistant_message',
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
    submission_feedbacks: [],
    created_at: '2026-05-22T00:00:00Z',
    updated_at: '2026-05-22T00:00:00Z',
  }
}

function stubCodeAttempt(snapshotId: number): WorkspacePracticeSession['code_attempts'][number] {
  return {
    snapshot_id: snapshotId,
    event_id: 600,
    language: 'python3',
    source: 'manual_save',
    client_revision: 1,
    code_hash: 'abc123',
    code_preview: 'class Solution:\n    pass',
    code_text: 'class Solution:\n    pass',
    quality_status: 'pending',
    quality_comment: '',
    created_at: '2026-05-22T00:00:00Z',
  }
}
