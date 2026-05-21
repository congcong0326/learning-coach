import { useCallback, useEffect, useRef, useState } from 'react'

import {
  cancelLlmRun,
  createLlmRun,
  type LlmRunKind,
  type LlmRunStatus,
} from '../api/llmRuns'

type HookStatus = 'idle' | LlmRunStatus

type RunError = {
  code: string
  message: string
}

type LlmRunState = {
  runId: number | null
  status: HookStatus
  stage: string
  displayText: string
  result: unknown | null
  error: RunError | null
}

type SsePayload = {
  run_id?: number
  status?: LlmRunStatus
  stage?: string
  message?: string
  text?: string
  result?: unknown
  error_code?: string | null
  error_message?: string | null
}

const initialState: LlmRunState = {
  runId: null,
  status: 'idle',
  stage: '',
  displayText: '',
  result: null,
  error: null,
}

function parsePayload(event: Event): SsePayload {
  const data = (event as MessageEvent<string>).data
  if (!data) {
    return {}
  }
  return JSON.parse(data) as SsePayload
}

function toRunError(payload: SsePayload): RunError {
  return {
    code: payload.error_code ?? 'llm_run_error',
    message: payload.error_message ?? '生成失败，请稍后重试',
  }
}

export function useLlmRun() {
  const [state, setState] = useState<LlmRunState>(initialState)
  const sourceRef = useRef<EventSource | null>(null)
  const runIdRef = useRef<number | null>(null)

  const closeSource = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  const openStream = useCallback(
    (streamUrl: string) => {
      closeSource()

      const source = new EventSource(streamUrl)
      sourceRef.current = source

      source.addEventListener('started', (event) => {
        const payload = parsePayload(event)
        runIdRef.current = payload.run_id ?? runIdRef.current
        setState((current) => ({
          ...current,
          runId: payload.run_id ?? current.runId,
          status: payload.status ?? 'running',
          stage: payload.stage ?? current.stage,
          error: null,
        }))
      })

      source.addEventListener('progress', (event) => {
        const payload = parsePayload(event)
        setState((current) => ({
          ...current,
          stage: payload.stage ?? current.stage,
        }))
      })

      source.addEventListener('delta', (event) => {
        const payload = parsePayload(event)
        setState((current) => ({
          ...current,
          displayText: `${current.displayText}${payload.text ?? ''}`,
        }))
      })

      source.addEventListener('result', (event) => {
        const payload = parsePayload(event)
        setState((current) => ({
          ...current,
          status: payload.status ?? 'succeeded',
          stage: payload.stage ?? current.stage,
          result: payload.result ?? null,
          error: null,
        }))
      })

      source.addEventListener('error', (event) => {
        const payload = parsePayload(event)
        setState((current) => ({
          ...current,
          status: 'failed',
          stage: payload.stage ?? current.stage,
          error: toRunError(payload),
        }))
        closeSource()
      })

      source.addEventListener('canceled', (event) => {
        const payload = parsePayload(event)
        setState((current) => ({
          ...current,
          status: 'canceled',
          stage: payload.stage ?? 'canceled',
          error: payload.error_code || payload.error_message ? toRunError(payload) : null,
        }))
        closeSource()
      })

      source.addEventListener('done', () => {
        closeSource()
      })
    },
    [closeSource],
  )

  const startRun = useCallback(
    async (kind: LlmRunKind, payload: Record<string, unknown>) => {
      closeSource()
      runIdRef.current = null
      setState({
        ...initialState,
        status: 'pending',
        stage: 'queued',
      })

      const created = await createLlmRun(kind, payload)
      runIdRef.current = created.run_id
      setState({
        runId: created.run_id,
        status: created.status,
        stage: created.stage,
        displayText: '',
        result: null,
        error: null,
      })
      openStream(created.stream_url)
      return created
    },
    [closeSource, openStream],
  )

  const cancelRun = useCallback(async () => {
    const runId = runIdRef.current
    if (runId === null) {
      return null
    }

    closeSource()
    const canceled = await cancelLlmRun(runId)
    setState((current) => ({
      ...current,
      status: canceled.status,
      stage: canceled.stage,
      displayText: canceled.display_text_md ?? current.displayText,
      result: canceled.result ?? null,
      error:
        canceled.error_code || canceled.error_message
          ? {
              code: canceled.error_code ?? 'run_canceled',
              message: canceled.error_message ?? '已停止生成',
            }
          : null,
    }))
    return canceled
  }, [closeSource])

  useEffect(() => closeSource, [closeSource])

  return {
    ...state,
    startRun,
    cancelRun,
    isRunning: state.status === 'pending' || state.status === 'running',
  }
}
