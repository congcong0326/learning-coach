import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getLlmRunStatus } from '../api/llmRuns'
import { useLlmRun } from './useLlmRun'

type Listener = (event: MessageEvent<string>) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly url: string
  closed = false
  private readonly listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(eventName: string, listener: Listener) {
    const listeners = this.listeners.get(eventName) ?? []
    listeners.push(listener)
    this.listeners.set(eventName, listeners)
  }

  removeEventListener(eventName: string, listener: Listener) {
    const listeners = this.listeners.get(eventName) ?? []
    this.listeners.set(
      eventName,
      listeners.filter((candidate) => candidate !== listener),
    )
  }

  close() {
    this.closed = true
  }

  emit(eventName: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>
    for (const listener of this.listeners.get(eventName) ?? []) {
      listener(event)
    }
  }
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve
  })
  return { promise, resolve }
}

describe('useLlmRun', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a run, accumulates delta text, and closes the stream when done', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        run_id: 88,
        kind: 'goal_plan_generate',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/88/stream',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useLlmRun())

    await act(async () => {
      await result.current.startRun('goal_plan_generate', { draft_id: 123 })
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/llm-runs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          kind: 'goal_plan_generate',
          payload: { draft_id: 123 },
        }),
      }),
    )
    expect(result.current.runId).toBe(88)
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toBe('/api/llm-runs/88/stream')

    act(() => {
      const source = FakeEventSource.instances[0]
      source.emit('started', { run_id: 88, status: 'running', stage: 'streaming_model' })
      source.emit('progress', { run_id: 88, stage: 'validating', message: '正在校验题库' })
      source.emit('delta', { run_id: 88, text: '先拆成题型识别' })
      source.emit('delta', { run_id: 88, text: '和边界条件两个阶段。' })
      source.emit('result', {
        run_id: 88,
        status: 'succeeded',
        result: { draft_id: 123, stage_count: 2 },
      })
      source.emit('done', { run_id: 88 })
    })

    await waitFor(() => expect(result.current.status).toBe('succeeded'))
    expect(result.current.stage).toBe('validating')
    expect(result.current.displayText).toBe('先拆成题型识别和边界条件两个阶段。')
    expect(result.current.result).toEqual({ draft_id: 123, stage_count: 2 })
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('posts cancel for the active run and closes the stream', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        okJson({
          run_id: 99,
          kind: 'coach_message',
          status: 'pending',
          stage: 'queued',
          stream_url: '/api/llm-runs/99/stream',
        }),
      )
      .mockResolvedValueOnce(
        okJson({
          run_id: 99,
          status: 'canceled',
          cancel_requested: true,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useLlmRun())

    await act(async () => {
      await result.current.startRun('coach_message', { message: '给我一个提示' })
      await result.current.cancelRun()
    })

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/llm-runs/99/cancel',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.current.status).toBe('canceled')
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('stores SSE errors and closes the stream', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        run_id: 101,
        kind: 'code_review',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/101/stream',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useLlmRun())

    await act(async () => {
      await result.current.startRun('code_review', { session_id: 7 })
    })
    act(() => {
      FakeEventSource.instances[0].emit('error', {
        run_id: 101,
        stage: 'streaming_model',
        error_code: 'llm_provider_error',
        message: '模型服务暂时不可用',
      })
    })

    expect(result.current.status).toBe('failed')
    expect(result.current.stage).toBe('streaming_model')
    expect(result.current.error).toEqual({
      code: 'llm_provider_error',
      message: '模型服务暂时不可用',
    })
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('handles server canceled events and closes the stream', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        run_id: 102,
        kind: 'reflection',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/102/stream',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useLlmRun())

    await act(async () => {
      await result.current.startRun('reflection', { session_id: 8 })
    })
    act(() => {
      FakeEventSource.instances[0].emit('canceled', {
        run_id: 102,
        stage: 'canceled',
      })
    })

    expect(result.current.status).toBe('canceled')
    expect(result.current.stage).toBe('canceled')
    expect(result.current.error).toBeNull()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('closes an open EventSource when the hook unmounts', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        run_id: 100,
        kind: 'coach_message',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/100/stream',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result, unmount } = renderHook(() => useLlmRun())

    await act(async () => {
      await result.current.startRun('coach_message', { message: '继续' })
    })
    unmount()

    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('wraps the run status endpoint', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        run_id: 77,
        kind: 'goal_followup',
        status: 'succeeded',
        stage: 'completed',
        display_text_md: '信息足够',
        result: { draft_id: 5 },
        error_code: null,
        error_message: null,
        can_retry: false,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getLlmRunStatus(77)).resolves.toMatchObject({
      run_id: 77,
      status: 'succeeded',
      display_text_md: '信息足够',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/llm-runs/77',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('ignores stale create responses and stale stream events', async () => {
    const first = deferred<Response>()
    const second = deferred<Response>()
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useLlmRun())

    let firstStart!: Promise<unknown>
    let secondStart!: Promise<unknown>
    act(() => {
      firstStart = result.current.startRun('coach_message', { message: 'first' })
    })
    act(() => {
      secondStart = result.current.startRun('coach_message', { message: 'second' })
    })

    second.resolve(
      okJson({
        run_id: 202,
        kind: 'coach_message',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/202/stream',
      }),
    )
    await act(async () => {
      await secondStart
    })

    expect(result.current.runId).toBe(202)
    expect(FakeEventSource.instances).toHaveLength(1)

    first.resolve(
      okJson({
        run_id: 201,
        kind: 'coach_message',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/201/stream',
      }),
    )
    await act(async () => {
      await firstStart
    })

    expect(result.current.runId).toBe(202)
    expect(FakeEventSource.instances).toHaveLength(1)

    act(() => {
      FakeEventSource.instances[0].emit('delta', {
        run_id: 201,
        text: '旧输出',
      })
      FakeEventSource.instances[0].emit('delta', {
        run_id: 202,
        text: '新输出',
      })
    })

    expect(result.current.displayText).toBe('新输出')
  })

  it('cancels a run that resolves after cancel was requested', async () => {
    const create = deferred<Response>()
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(create.promise)
      .mockResolvedValueOnce(
        okJson({
          run_id: 303,
          status: 'canceled',
          cancel_requested: true,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useLlmRun())

    let start!: Promise<unknown>
    act(() => {
      start = result.current.startRun('coach_message', { message: 'cancel soon' })
    })
    await act(async () => {
      await result.current.cancelRun()
    })
    create.resolve(
      okJson({
        run_id: 303,
        kind: 'coach_message',
        status: 'pending',
        stage: 'queued',
        stream_url: '/api/llm-runs/303/stream',
      }),
    )
    await act(async () => {
      await start
    })

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/llm-runs/303/cancel',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.current.status).toBe('canceled')
    expect(FakeEventSource.instances).toHaveLength(0)
  })
})
