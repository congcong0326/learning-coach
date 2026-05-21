import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GoalCalibrationPage } from './GoalCalibrationPage'

type Listener = (event: MessageEvent<string>) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly url: string
  private readonly listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(name: string, listener: Listener) {
    const listeners = this.listeners.get(name) ?? []
    listeners.push(listener)
    this.listeners.set(name, listeners)
  }

  close() {
    return undefined
  }

  emit(name: string, payload: unknown) {
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>
    for (const listener of this.listeners.get(name) ?? []) {
      listener(event)
    }
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GoalCalibrationPage />
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

function planDraftPayload() {
  return {
    draft_id: 3,
    status: 'ready_for_review',
    target_snapshot: { goal_type: 'interview_sprint' },
    generation_summary_md: '按两个阶段训练。',
    stages: [
      {
        title: '数组基础',
        objective_md: '先稳住基础题型。',
        focus_tags: ['array'],
        assessment_criteria: ['能讲清思路'],
        items: [
          {
            problem_slug: 'two-sum',
            title: 'Two Sum',
            difficulty: 'Easy',
            skill_tags: ['array'],
            suggested_mode: 'guided',
            recommendation_reason: '训练哈希表入门',
            order_index: 1,
          },
        ],
      },
    ],
    validation_report: { valid: true, issues: [], item_count: 1 },
    repair_log: [],
    uncertainty_notes: [],
  }
}

describe('GoalCalibrationPage', () => {
  afterEach(() => {
    FakeEventSource.instances = []
    vi.unstubAllGlobals()
  })

  it('starts calibration through llm run and shows streaming text', async () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.fn(async () =>
      okJson({
        run_id: 3,
        kind: 'goal_followup',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/3/stream',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(screen.getByLabelText('面试冲刺'))
    fireEvent.click(screen.getByLabelText('1 到 3 个月'))
    fireEvent.click(screen.getByLabelText('Python3'))
    fireEvent.click(screen.getByRole('button', { name: '开始校准' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/llm-runs',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    expect(FakeEventSource.instances[0].url).toBe('/api/llm-runs/3/stream')

    act(() => {
      FakeEventSource.instances[0].emit('delta', {
        run_id: 3,
        text: '正在分析目标。',
      })
    })

    expect(await screen.findByText('正在分析目标。')).toBeInTheDocument()
  })

  it('submits followup answers and plan generation through llm runs', async () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        okJson({
          run_id: 3,
          kind: 'goal_followup',
          status: 'pending',
          stage: 'queued',
          stream_url: '/api/llm-runs/3/stream',
        }),
      )
      .mockResolvedValueOnce(
        okJson({
          run_id: 4,
          kind: 'goal_followup',
          status: 'pending',
          stage: 'queued',
          stream_url: '/api/llm-runs/4/stream',
        }),
      )
      .mockResolvedValueOnce(
        okJson({
          run_id: 5,
          kind: 'goal_plan_generate',
          status: 'pending',
          stage: 'queued',
          stream_url: '/api/llm-runs/5/stream',
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(screen.getByLabelText('面试冲刺'))
    fireEvent.click(screen.getByLabelText('1 到 3 个月'))
    fireEvent.click(screen.getByLabelText('Python3'))
    fireEvent.click(screen.getByRole('button', { name: '开始校准' }))

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    act(() => {
      FakeEventSource.instances[0].emit('result', {
        run_id: 3,
        status: 'succeeded',
        result: {
          draft_id: 3,
          status: 'asking_followup',
          followup_question: '你的面试时间是？',
          followup_question_id: 'q1',
          remaining_followups: 2,
        },
      })
    })

    expect(await screen.findByText('你的面试时间是？')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '三周后面试。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '提交回答' }))

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2))
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/llm-runs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          kind: 'goal_followup',
          payload: {
            draft_id: 3,
            question_id: 'q1',
            answer: '三周后面试。',
          },
        }),
      }),
    )
    act(() => {
      FakeEventSource.instances[1].emit('result', {
        run_id: 4,
        status: 'succeeded',
        result: {
          draft_id: 3,
          status: 'collecting_input',
          followup_question: null,
          followup_question_id: null,
          remaining_followups: 0,
        },
      })
    })

    const generateButton = await screen.findByRole('button', {
      name: '生成计划草稿',
    })
    fireEvent.click(generateButton)

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(3))
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/llm-runs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          kind: 'goal_plan_generate',
          payload: { draft_id: 3 },
        }),
      }),
    )
    act(() => {
      FakeEventSource.instances[2].emit('result', {
        run_id: 5,
        status: 'succeeded',
        result: planDraftPayload(),
      })
    })

    expect(await screen.findByText('按两个阶段训练。')).toBeInTheDocument()
    expect(screen.getByText('数组基础')).toBeInTheDocument()
  })
})
