import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../api/client'
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
  message?: string | null
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
    message: payload.message ?? payload.error_message ?? '生成失败，请稍后重试',
  }
}

export function useLlmRun() {
  const [state, setState] = useState<LlmRunState>(initialState)
  const sourceRef = useRef<EventSource | null>(null)
  const runIdRef = useRef<number | null>(null)
  const requestSeqRef = useRef(0)
  const pendingCreateSeqRef = useRef<number | null>(null)
  const canceledCreateSeqsRef = useRef(new Set<number>())

  const closeSource = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  const openStream = useCallback(
    (streamUrl: string, runId: number, requestSeq: number) => {
      closeSource()

      const source = new EventSource(streamUrl)
      sourceRef.current = source

      function isCurrentEvent(payload?: SsePayload) {
        if (sourceRef.current !== source || requestSeqRef.current !== requestSeq) {
          return false
        }
        return payload?.run_id === undefined || payload.run_id === runId
      }

      source.addEventListener('started', (event) => {
        const payload = parsePayload(event)
        if (!isCurrentEvent(payload)) {
          return
        }
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
        if (!isCurrentEvent(payload)) {
          return
        }
        setState((current) => ({
          ...current,
          stage: payload.stage ?? current.stage,
        }))
      })

      source.addEventListener('delta', (event) => {
        const payload = parsePayload(event)
        if (!isCurrentEvent(payload)) {
          return
        }
        setState((current) => ({
          ...current,
          displayText: `${current.displayText}${payload.text ?? ''}`,
        }))
      })

      source.addEventListener('result', (event) => {
        const payload = parsePayload(event)
        if (!isCurrentEvent(payload)) {
          return
        }
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
        if (!isCurrentEvent(payload)) {
          return
        }
        setState((current) => ({
          ...current,
          status: 'failed',
          stage: payload.stage ?? current.stage,
          error: toRunError(payload),
        }))
        runIdRef.current = null
        closeSource()
      })

      source.addEventListener('canceled', (event) => {
        const payload = parsePayload(event)
        if (!isCurrentEvent(payload)) {
          return
        }
        setState((current) => ({
          ...current,
          status: 'canceled',
          stage: payload.stage ?? 'canceled',
          error: payload.error_code || payload.error_message ? toRunError(payload) : null,
        }))
        runIdRef.current = null
        closeSource()
      })

      source.addEventListener('done', () => {
        if (sourceRef.current === source && requestSeqRef.current === requestSeq) {
          runIdRef.current = null
          closeSource()
        }
      })
    },
    [closeSource],
  )

  const startRun = useCallback(
    async (kind: LlmRunKind, payload: Record<string, unknown>) => {
      const requestSeq = requestSeqRef.current + 1
      requestSeqRef.current = requestSeq
      pendingCreateSeqRef.current = requestSeq
      closeSource()
      runIdRef.current = null
      setState({
        ...initialState,
        status: 'pending',
        stage: 'queued',
      })

      let created: Awaited<ReturnType<typeof createLlmRun>>
      try {
        created = await createLlmRun(kind, payload)
      } catch (error) {
        if (requestSeqRef.current === requestSeq) {
          pendingCreateSeqRef.current = null
          setState((current) => ({
            ...current,
            status: 'failed',
            stage: 'failed',
            error: {
              code: 'request_failed',
              message:
                error instanceof ApiError
                  ? error.detail
                  : '创建生成任务失败，请稍后重试',
            },
          }))
        }
        throw error
      }

      const shouldCancelCreated = canceledCreateSeqsRef.current.has(requestSeq)
      canceledCreateSeqsRef.current.delete(requestSeq)
      if (requestSeqRef.current !== requestSeq) {
        if (shouldCancelCreated) {
          await cancelLlmRun(created.run_id)
        }
        return created
      }
      pendingCreateSeqRef.current = null

      if (shouldCancelCreated) {
        const canceled = await cancelLlmRun(created.run_id)
        if (requestSeqRef.current === requestSeq) {
          runIdRef.current = null
          setState((current) => ({
            ...current,
            runId: created.run_id,
            status: canceled.status,
            stage: 'canceled',
            error: null,
          }))
        }
        return created
      }

      runIdRef.current = created.run_id
      setState({
        runId: created.run_id,
        status: created.status,
        stage: created.stage,
        displayText: '',
        result: null,
        error: null,
      })
      openStream(created.stream_url, created.run_id, requestSeq)
      return created
    },
    [closeSource, openStream],
  )

  const cancelRun = useCallback(async () => {
    const runId = runIdRef.current
    if (runId === null) {
      if (pendingCreateSeqRef.current !== null) {
        canceledCreateSeqsRef.current.add(pendingCreateSeqRef.current)
        setState((current) => ({
          ...current,
          status: 'canceled',
          stage: 'canceled',
          error: null,
        }))
      }
      return null
    }

    closeSource()
    runIdRef.current = null
    const requestSeq = requestSeqRef.current
    const canceled = await cancelLlmRun(runId)
    if (requestSeqRef.current === requestSeq) {
      setState((current) => ({
        ...current,
        status: canceled.status,
        stage: 'canceled',
        error: null,
      }))
    }
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
