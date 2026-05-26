import { useQuery } from '@tanstack/react-query'
import { Alert, Table, Tag, Typography } from 'antd'
import { useSearchParams } from 'react-router-dom'

import { getAgentTraces, type AgentTrace } from '../api/trace'

function outputReason(trace: AgentTrace) {
  const guardReason = trace.output_summary.guard_reason
  if (typeof guardReason === 'string' && guardReason) {
    return guardReason
  }
  const retrievalStatus = trace.output_summary.retrieval_status
  if (typeof retrievalStatus === 'string' && retrievalStatus) {
    return retrievalStatus
  }
  const status = trace.output_summary.status
  if (typeof status === 'string' && status) {
    return status
  }
  return '-'
}

export function TracePage() {
  const [params] = useSearchParams()
  const sessionIdText = params.get('sessionId')
  const sessionId = sessionIdText && /^\d+$/.test(sessionIdText)
    ? Number(sessionIdText)
    : null
  const traceQuery = useQuery({
    queryKey: ['agent-traces', sessionId],
    queryFn: () => getAgentTraces(sessionId),
    retry: false,
  })

  return (
    <section className="page-section">
      <Typography.Title level={2}>Trace</Typography.Title>
      {traceQuery.isError ? (
        <Alert showIcon type="error" message="Trace 加载失败" className="page-alert" />
      ) : null}
      <Table<AgentTrace>
        rowKey="id"
        size="middle"
        loading={traceQuery.isLoading}
        pagination={false}
        dataSource={traceQuery.data ?? []}
        columns={[
          { title: '节点', dataIndex: 'node_name' },
          { title: '线程', dataIndex: 'thread_id' },
          { title: '题目', dataIndex: 'problem_slug' },
          { title: '阶段', dataIndex: 'phase' },
          {
            title: '提示',
            dataIndex: 'hint_level',
            render: (value: number | null) =>
              value === null ? '-' : <Tag>{`L${value}`}</Tag>,
          },
          {
            title: '模型',
            dataIndex: 'model_name',
            render: (value: string | null) => value || '-',
          },
          {
            title: '结果',
            key: 'result',
            render: (_, trace) => outputReason(trace),
          },
          {
            title: '耗时',
            dataIndex: 'latency_ms',
            render: (value: number | null) => (value === null ? '-' : `${value}ms`),
          },
        ]}
      />
    </section>
  )
}
