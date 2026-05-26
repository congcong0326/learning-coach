import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { StudyPlan } from '../api/learning'
import { ProfilePlanEnrichmentDrawer } from './ProfilePlanEnrichmentDrawer'

const llmRunMock = vi.hoisted(() => ({
  startRun: vi.fn(),
  cancelRun: vi.fn(),
}))

const llmRunState = vi.hoisted(() => ({
  isRunning: false,
  status: 'idle',
  stage: '',
  displayText: '',
  error: null as { message: string } | null,
  onResult: null as ((result: unknown) => void) | null,
}))

vi.mock('../hooks/useLlmRun', () => ({
  useLlmRun: (options?: { onResult?: (result: unknown) => void }) => {
    llmRunState.onResult = options?.onResult ?? null
    return {
      startRun: llmRunMock.startRun,
      cancelRun: llmRunMock.cancelRun,
      isRunning: llmRunState.isRunning,
      status: llmRunState.status,
      stage: llmRunState.stage,
      displayText: llmRunState.displayText,
      error: llmRunState.error,
    }
  },
}))

function renderDrawer(props: Partial<ComponentProps<typeof ProfilePlanEnrichmentDrawer>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ProfilePlanEnrichmentDrawer
        open
        plan={stubPlan()}
        onClose={vi.fn()}
        onPlanUpdated={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function dashboardPayload() {
  return {
    completed_problem_count: 4,
    common_stuck_points: [{ stuck_point: '边界条件', count: 2 }],
    average_hint_gear: 1.5,
    highest_hint_level: 'key_hint',
    recent_profile_summary: '最近 AC 但边界用例需要加强。',
    profile_snapshot_id: 31,
  }
}

describe('ProfilePlanEnrichmentDrawer', () => {
  beforeEach(() => {
    llmRunMock.startRun.mockReset()
    llmRunMock.cancelRun.mockReset()
    llmRunState.isRunning = false
    llmRunState.status = 'idle'
    llmRunState.stage = ''
    llmRunState.displayText = ''
    llmRunState.error = null
    llmRunState.onResult = null
    vi.unstubAllGlobals()
  })

  it('renders profile summary and enrichment controls', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson(dashboardPayload())))

    renderDrawer()

    expect(screen.getByText('画像与计划补强')).toBeInTheDocument()
    expect(screen.getByText('当前画像与计划基线')).toBeInTheDocument()
    expect(screen.getByText('Java')).toBeInTheDocument()
    expect(screen.getByText('面试冲刺')).toBeInTheDocument()
    expect(screen.getByText('边界条件')).toBeInTheDocument()
    expect(await screen.findByText('最近画像摘要')).toBeInTheDocument()
    expect(await screen.findByText('最近 AC 但边界用例需要加强。')).toBeInTheDocument()
    expect(screen.getByText('完成题数')).toBeInTheDocument()
    expect(screen.getByText('常见卡点')).toBeInTheDocument()
    expect(await screen.findByText('边界条件 x2')).toBeInTheDocument()
    expect(screen.getByText('补强生成会调用大模型')).toBeInTheDocument()
    expect(screen.getByLabelText('这次你希望怎么补强？')).toBeInTheDocument()
    expect(screen.getByLabelText('2 题')).toBeInTheDocument()
    expect(screen.getByLabelText('3 题')).toBeChecked()
    expect(screen.getByLabelText('5 题')).toBeInTheDocument()
    expect(screen.getByLabelText('保持当前')).toBeChecked()
    expect(screen.getByRole('button', { name: '生成补强预览' })).toBeInTheDocument()
  })

  it('generates a preview and confirms the draft', async () => {
    const onPlanUpdated = vi.fn()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(dashboardPayload()))
      .mockResolvedValueOnce(okJson({ ...stubPlan(), title: '更新后的计划' }))
    vi.stubGlobal('fetch', fetchMock)
    llmRunMock.startRun.mockImplementation(async () => {
      llmRunState.onResult?.(stubDraft())
      return { run_id: 99 }
    })

    renderDrawer({ onPlanUpdated })

    fireEvent.change(screen.getByLabelText('这次你希望怎么补强？'), {
      target: { value: '想补动态规划和边界条件。' },
    })
    fireEvent.click(screen.getByLabelText('2 题'))
    fireEvent.click(screen.getByLabelText('挑战一点'))
    fireEvent.click(screen.getByRole('button', { name: '生成补强预览' }))

    await waitFor(() =>
      expect(llmRunMock.startRun).toHaveBeenCalledWith('profile_plan_enrichment', {
        plan_id: 10,
        user_intent_md: '想补动态规划和边界条件。',
        item_count: 2,
        difficulty_preference: 'stretch',
      }),
    )
    expect(await screen.findByText('计划缺少能暴露 DP 状态定义问题的题。')).toBeInTheDocument()
    expect(screen.getByText('House Robber')).toBeInTheDocument()
    expect(screen.getByText('状态定义')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '确认加入当前计划' }))

    await waitFor(() => expect(onPlanUpdated).toHaveBeenCalledWith(expect.objectContaining({ title: '更新后的计划' })))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/study-plans/10/profile-enrichments/700/confirm',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    )
  })
})

function stubPlan(): StudyPlan {
  return {
    id: 10,
    title: '3 个月 Java 面试冲刺计划',
    status: 'active',
    active_version_number: 1,
    active_version: {
      id: 20,
      version_number: 1,
      status: 'active',
      target_snapshot: {
        preferred_language: 'java',
        goal_type: 'interview_sprint',
        current_level: 'medium_partial',
        training_preference: 'independent_first',
        self_reported_weaknesses: ['边界条件', '动态规划'],
        weekly_days: 4,
        session_minutes: 60,
      },
      generation_summary_md: '围绕中等题稳定性生成。',
      adjustment_summary_md: '',
      stages: [],
    },
  }
}

function stubDraft() {
  return {
    draft_id: 700,
    status: 'generated',
    plan_id: 10,
    plan_version_id: 20,
    profile_snapshot_id: 30,
    user_intent_md: '想补动态规划和边界条件。',
    item_count: 2,
    difficulty_preference: 'stretch',
    enrichment_theme: 'DP 状态定义补强',
    plan_gap_assessment: {
      gap_level: 'medium',
      summary_md: '计划缺少能暴露 DP 状态定义问题的题。',
    },
    overall_reason_md: '基于最近画像，优先补齐状态定义与边界推导。',
    not_added_reason_md: '',
    items: [
      {
        problem_id: 198,
        problem_slug: 'house-robber',
        title: 'House Robber',
        translated_title: '打家劫舍',
        difficulty: 'Medium',
        skill_tags: ['dynamic-programming'],
        target_stage_id: 51,
        target_stage_title: '动态规划基础',
        weakness_targets: ['状态定义', '边界条件'],
        recommendation_reason_md: '用相邻约束训练状态选择。',
        first_question_hint: '先定义 dp[i] 的含义。',
        review_focus: '检查初始状态和转移顺序。',
        suggested_mode: 'independent',
      },
    ],
    validation_report: { valid: true },
    created_at: '2026-05-26T00:00:00Z',
    updated_at: '2026-05-26T00:00:00Z',
    confirmed_at: null,
  }
}
