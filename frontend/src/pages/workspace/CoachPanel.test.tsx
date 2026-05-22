import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CoachPanel } from './CoachPanel'
import type { WorkspacePracticeSession } from './types'

vi.mock('../../hooks/useLlmRun', () => ({
  useLlmRun: () => ({
    startRun: vi.fn(),
    cancelRun: vi.fn(),
    isRunning: false,
    displayText: '',
    stage: '',
    error: null,
    result: null,
  }),
}))

describe('CoachPanel', () => {
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
