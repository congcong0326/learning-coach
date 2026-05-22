import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CoachPanel } from './CoachPanel'
import type { WorkspacePracticeSession } from './types'

const llmRunMock = vi.hoisted(() => ({
  startRun: vi.fn(),
  cancelRun: vi.fn(),
}))

const practiceApiMock = vi.hoisted(() => ({
  sendPracticeMessage: vi.fn(),
  submitLeetCodeFeedback: vi.fn(),
}))

vi.mock('../../hooks/useLlmRun', () => ({
  useLlmRun: () => ({
    startRun: llmRunMock.startRun,
    cancelRun: llmRunMock.cancelRun,
    isRunning: false,
    displayText: '',
    stage: '',
    error: null,
    result: null,
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
    practiceApiMock.sendPracticeMessage.mockReset()
    practiceApiMock.submitLeetCodeFeedback.mockReset()
  })

  it('shows profile source and confidence from session snapshot', () => {
    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.getByText('画像来源')).toBeInTheDocument()
    expect(screen.getByText('historical_profile')).toBeInTheDocument()
    expect(screen.getByText('置信度')).toBeInTheDocument()
    expect(screen.getByText('medium')).toBeInTheDocument()
  })

  it('shows submission feedback entry', () => {
    render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

    expect(screen.getByRole('button', { name: '提交回填' })).toBeInTheDocument()
  })

  it('passes saved code snapshot id to submission feedback modal', async () => {
    practiceApiMock.submitLeetCodeFeedback.mockResolvedValue({
      id: 1,
      result: 'unknown',
      event_id: 2,
      code_snapshot_id: 777,
      created_at: '2026-05-22T00:00:00Z',
    })

    render(
      <CoachPanel
        session={stubSession()}
        codeSnapshotId={777}
        onSessionRefresh={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '提交回填' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /保\s*存/ }))

    await waitFor(() =>
      expect(practiceApiMock.submitLeetCodeFeedback).toHaveBeenCalledWith(
        100,
        expect.objectContaining({ code_snapshot_id: 777, result: 'unknown' }),
      ),
    )
  })

  it('shows summary action after accepted submission', () => {
    render(
      <CoachPanel
        session={{ ...stubSession(), final_result: 'ac', phase: 'summarize' }}
        onSessionRefresh={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '进入复盘' }))

    expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_summary', {
      session_id: 100,
      trigger: 'request_summary',
    })
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
    created_at: '2026-05-22T00:00:00Z',
    updated_at: '2026-05-22T00:00:00Z',
  }
}
