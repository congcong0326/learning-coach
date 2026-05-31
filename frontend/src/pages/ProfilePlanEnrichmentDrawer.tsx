import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Radio,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'

import { getPracticeDashboard, type PracticeDashboard } from '../api/dashboard'
import {
  confirmProfilePlanEnrichment,
  type ProfilePlanEnrichmentDifficulty,
  type ProfilePlanEnrichmentDraft,
  type ProfilePlanEnrichmentItem,
  type ProfilePlanEnrichmentPayload,
  type StudyPlan,
} from '../api/learning'
import { LlmStreamingPanel } from '../components/LlmStreamingPanel'
import { useLlmRun } from '../hooks/useLlmRun'

type ProfilePlanEnrichmentDrawerProps = {
  open: boolean
  plan: StudyPlan
  onClose: () => void
  onPlanUpdated: (plan: StudyPlan) => void
}

type FormValues = ProfilePlanEnrichmentPayload

const languageLabels: Record<string, string> = {
  c: 'C',
  go: 'Go',
  java: 'Java',
  javascript: 'JavaScript',
  python3: 'Python 3',
}

const goalLabels: Record<string, string> = {
  beginner: '入门训练',
  interview_sprint: '面试冲刺',
  strengthen_weakness: '弱项强化',
  maintain: '保持手感',
}

const levelLabels: Record<string, string> = {
  new: '刚开始',
  easy_started: 'Easy 起步',
  medium_partial: '部分 Medium',
  round_done_unstable: '刷过一轮但不稳定',
}

const preferenceLabels: Record<string, string> = {
  guided: '引导训练',
  independent_first: '先独立思考',
  interviewer_style: '面试官风格',
}

const difficultyLabels: Record<ProfilePlanEnrichmentDifficulty, string> = {
  foundational: '补基础',
  keep_current: '保持当前',
  stretch: '挑战一点',
}

const gapLevelLabels: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  insufficient_evidence: '证据不足',
}

const hintLabels: Record<string, string> = {
  questioning: '追问档',
  direction: '方向档',
  key_hint: '关键档',
  reflection: '复盘档',
}

function stringValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value : ''
}

function numberValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
}

function stringList(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter(
    (item): item is string => typeof item === 'string' && item.trim().length > 0,
  )
}

function labeledValue(value: unknown, labels: Record<string, string>) {
  const raw = stringValue(value)
  return raw ? labels[raw] ?? raw : '暂无'
}

function draftFromResult(result: unknown): ProfilePlanEnrichmentDraft | null {
  if (!result || typeof result !== 'object') {
    return null
  }
  if ('draft_id' in result) {
    return result as ProfilePlanEnrichmentDraft
  }
  if ('draft' in result) {
    const draft = (result as { draft?: unknown }).draft
    if (draft && typeof draft === 'object' && 'draft_id' in draft) {
      return draft as ProfilePlanEnrichmentDraft
    }
  }
  return null
}

function ProfileBaseline({
  dashboard,
  dashboardError,
  dashboardLoading,
  plan,
}: {
  dashboard: PracticeDashboard | undefined
  dashboardError: boolean
  dashboardLoading: boolean
  plan: StudyPlan
}) {
  const snapshot = plan.active_version?.target_snapshot ?? {}
  const weaknesses = stringList(snapshot.self_reported_weaknesses)
  const weeklyDays = numberValue(snapshot.weekly_days)
  const sessionMinutes = numberValue(snapshot.session_minutes)
  const profileSummary =
    dashboard?.recent_profile_summary ||
    stringValue(snapshot.recent_profile_summary) ||
    '当前训练证据还不够，建议先完成 1-2 道计划题后再生成补强题。'
  const stuckPoints = dashboard?.common_stuck_points ?? []

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <section aria-label="当前画像仪表盘">
        <Typography.Title level={4}>当前画像仪表盘</Typography.Title>
        {dashboardError ? (
          <Alert showIcon type="warning" message="画像仪表盘加载失败，暂时只展示计划基线。" />
        ) : null}
        <div className="dashboard-metric-grid">
          <div className="dashboard-metric">
            <span className="dashboard-metric-label">完成题数</span>
            <strong>
              {dashboardLoading ? '-' : dashboard?.completed_problem_count ?? 0}
            </strong>
          </div>
          <div className="dashboard-metric">
            <span className="dashboard-metric-label">平均提示档位</span>
            <strong>{dashboardLoading ? '-' : dashboard?.average_hint_gear ?? '-'}</strong>
          </div>
          <div className="dashboard-metric">
            <span className="dashboard-metric-label">最高提示档位</span>
            <strong>
              {dashboardLoading
                ? '-'
                : dashboard?.highest_hint_level
                  ? hintLabels[dashboard.highest_hint_level] ?? dashboard.highest_hint_level
                  : '-'}
            </strong>
          </div>
        </div>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="最近画像摘要">
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              {profileSummary}
            </Typography.Paragraph>
          </Descriptions.Item>
          <Descriptions.Item label="常见卡点">
            {stuckPoints.length ? (
              <Space size={[4, 4]} wrap>
                {stuckPoints.map((item) => (
                  <Tag key={item.stuck_point}>
                    {item.stuck_point} x{item.count}
                  </Tag>
                ))}
              </Space>
            ) : (
              '暂无'
            )}
          </Descriptions.Item>
        </Descriptions>
      </section>

      <section aria-label="当前画像与计划基线">
        <Typography.Title level={4}>当前画像与计划基线</Typography.Title>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="训练语言">
            {labeledValue(snapshot.preferred_language, languageLabels)}
          </Descriptions.Item>
          <Descriptions.Item label="训练目标">
            {labeledValue(snapshot.goal_type, goalLabels)}
          </Descriptions.Item>
          <Descriptions.Item label="当前水平">
            {labeledValue(snapshot.current_level, levelLabels)}
          </Descriptions.Item>
          <Descriptions.Item label="训练方式">
            {labeledValue(snapshot.training_preference, preferenceLabels)}
          </Descriptions.Item>
          <Descriptions.Item label="投入节奏">
            {weeklyDays && sessionMinutes ? `每周 ${weeklyDays} 天，每次 ${sessionMinutes} 分钟` : '暂无'}
          </Descriptions.Item>
          <Descriptions.Item label="自评弱项">
            {weaknesses.length ? (
              <Space size={[4, 4]} wrap>
                {weaknesses.map((weakness) => (
                  <Tag key={weakness}>{weakness}</Tag>
                ))}
              </Space>
            ) : (
              '暂无'
            )}
          </Descriptions.Item>
        </Descriptions>
      </section>
    </Space>
  )
}

function PreviewItem({ item }: { item: ProfilePlanEnrichmentItem }) {
  return (
    <article
      style={{
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: 14,
      }}
    >
      <Space align="start" direction="vertical" size={8} style={{ width: '100%' }}>
        <Space wrap>
          <Typography.Text strong>{item.title}</Typography.Text>
          {item.translated_title ? (
            <Typography.Text type="secondary">{item.translated_title}</Typography.Text>
          ) : null}
          <Tag>{item.difficulty}</Tag>
          <Tag color="blue">{item.target_stage_title}</Tag>
        </Space>
        <Space size={[4, 4]} wrap>
          {item.weakness_targets.map((target) => (
            <Tag color="orange" key={target}>
              {target}
            </Tag>
          ))}
          {item.skill_tags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </Space>
        <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
          {item.recommendation_reason_md}
        </Typography.Paragraph>
        <Typography.Text type="secondary">起手提示：{item.first_question_hint || '暂无'}</Typography.Text>
        <Typography.Text type="secondary">复盘重点：{item.review_focus || '暂无'}</Typography.Text>
      </Space>
    </article>
  )
}

function DraftPreview({ draft }: { draft: ProfilePlanEnrichmentDraft }) {
  const assessment = draft.plan_gap_assessment

  return (
    <section aria-label="补强预览">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap>
          <Typography.Title level={4} style={{ margin: 0 }}>
            补强预览
          </Typography.Title>
          {draft.enrichment_theme ? <Tag color="purple">{draft.enrichment_theme}</Tag> : null}
          <Tag>{difficultyLabels[draft.difficulty_preference]}</Tag>
        </Space>

        {assessment ? (
          <Alert
            showIcon
            type="info"
            message={`计划缺口：${gapLevelLabels[assessment.gap_level] ?? assessment.gap_level}`}
            description={assessment.summary_md || '暂无缺口摘要'}
          />
        ) : null}

        {draft.overall_reason_md ? (
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
            {draft.overall_reason_md}
          </Typography.Paragraph>
        ) : null}

        {draft.items.length ? (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            {draft.items.map((item) => (
              <PreviewItem item={item} key={`${item.problem_id}-${item.problem_slug}`} />
            ))}
          </Space>
        ) : (
          <Empty description={draft.not_added_reason_md || '暂无可加入题目'} />
        )}
      </Space>
    </section>
  )
}

export function ProfilePlanEnrichmentDrawer({
  open,
  plan,
  onClose,
  onPlanUpdated,
}: ProfilePlanEnrichmentDrawerProps) {
  const [form] = Form.useForm<FormValues>()
  const [draft, setDraft] = useState<ProfilePlanEnrichmentDraft | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState('')
  const [confirmSuccess, setConfirmSuccess] = useState('')
  const [resultError, setResultError] = useState('')
  const [confirmedDraftId, setConfirmedDraftId] = useState<number | null>(null)
  const confirmInFlightRef = useRef(false)
  const dashboardQuery = useQuery({
    enabled: open,
    queryKey: ['practice-dashboard'],
    queryFn: getPracticeDashboard,
    retry: false,
  })
  const initialValues = useMemo<FormValues>(
    () => ({
      user_intent_md: '',
      item_count: 3,
      difficulty_preference: 'keep_current',
    }),
    [],
  )
  const llmRun = useLlmRun({
    onResult: (result) => {
      const nextDraft = draftFromResult(result)
      if (!nextDraft) {
        setResultError('生成结果缺少补强草稿，请稍后重试。')
        return
      }
      setDraft(nextDraft)
      setResultError('')
      setConfirmError('')
      setConfirmSuccess('')
      setConfirmedDraftId(nextDraft.status === 'confirmed' ? nextDraft.draft_id : null)
    },
  })

  async function handleSubmit(values: FormValues) {
    setDraft(null)
    setResultError('')
    setConfirmError('')
    setConfirmSuccess('')
    setConfirmedDraftId(null)
    await llmRun.startRun('profile_plan_enrichment', {
      plan_id: plan.id,
      user_intent_md: values.user_intent_md.trim(),
      item_count: values.item_count,
      difficulty_preference: values.difficulty_preference,
    })
  }

  async function handleConfirm() {
    if (
      !draft ||
      confirmInFlightRef.current ||
      draft.status === 'confirmed' ||
      confirmedDraftId === draft.draft_id
    ) {
      return
    }
    confirmInFlightRef.current = true
    setConfirming(true)
    setConfirmError('')
    setConfirmSuccess('')
    try {
      const updatedPlan = await confirmProfilePlanEnrichment(plan.id, draft.draft_id)
      setConfirmedDraftId(draft.draft_id)
      setDraft({
        ...draft,
        status: 'confirmed',
        confirmed_at: new Date().toISOString(),
      })
      setConfirmSuccess('已加入当前计划，计划列表已刷新。')
      onPlanUpdated(updatedPlan)
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : '确认补强失败，请稍后重试。')
    } finally {
      confirmInFlightRef.current = false
      setConfirming(false)
    }
  }

  function handleClose() {
    if (llmRun.isRunning) {
      void llmRun.cancelRun()
    }
    onClose()
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      form.resetFields()
      setDraft(null)
      setResultError('')
      setConfirmError('')
      setConfirmSuccess('')
      setConfirmedDraftId(null)
      confirmInFlightRef.current = false
    }
  }

  const draftConfirmed =
    !!draft &&
    (draft.status === 'confirmed' || Boolean(draft.confirmed_at) || confirmedDraftId === draft.draft_id)

  return (
    <Drawer
      afterOpenChange={handleOpenChange}
      destroyOnHidden
      onClose={handleClose}
      open={open}
      title="画像与计划补强"
      width={720}
    >
      <Space direction="vertical" size={18} style={{ width: '100%' }}>
        <ProfileBaseline
          dashboard={dashboardQuery.data}
          dashboardError={dashboardQuery.isError}
          dashboardLoading={dashboardQuery.isLoading}
          plan={plan}
        />

        <Alert
          showIcon
          type="warning"
          message="补强生成会调用大模型"
          description="生成只会创建可确认的预览草稿；确认前不会把题目加入当前学习计划。"
        />

        <Form
          form={form}
          initialValues={initialValues}
          layout="vertical"
          onFinish={(values) => void handleSubmit(values)}
        >
          <Form.Item name="user_intent_md" label="这次你希望怎么补强？">
            <Input.TextArea
              disabled={llmRun.isRunning}
              maxLength={2000}
              placeholder="例如：最近做 DP 容易卡在状态定义，想加入 2 道能暴露边界问题的题。"
              rows={4}
            />
          </Form.Item>

          <Form.Item label="补强题数" name="item_count">
            <Radio.Group disabled={llmRun.isRunning}>
              <Radio.Button value={2}>2 题</Radio.Button>
              <Radio.Button value={3}>3 题</Radio.Button>
              <Radio.Button value={5}>5 题</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item label="难度偏好" name="difficulty_preference">
            <Radio.Group disabled={llmRun.isRunning}>
              <Radio.Button value="foundational">补基础</Radio.Button>
              <Radio.Button value="keep_current">保持当前</Radio.Button>
              <Radio.Button value="stretch">挑战一点</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Button htmlType="submit" loading={llmRun.isRunning} type="primary">
            生成补强预览
          </Button>
        </Form>

        <LlmStreamingPanel
          displayText={llmRun.displayText}
          error={llmRun.error}
          onCancel={() => void llmRun.cancelRun()}
          stage={llmRun.stage}
          status={llmRun.status}
          title="补强生成状态"
        />

        {resultError ? <Alert showIcon type="error" message={resultError} /> : null}
        {confirmError ? <Alert showIcon type="error" message={confirmError} /> : null}
        {confirmSuccess ? <Alert showIcon type="success" message={confirmSuccess} /> : null}

        {draft ? <DraftPreview draft={draft} /> : null}

        <Space>
          <Button
            onClick={handleConfirm}
            loading={confirming}
            disabled={!draft || draft.items.length === 0 || llmRun.isRunning || draftConfirmed}
          >
            {draftConfirmed ? '已加入当前计划' : '确认加入当前计划'}
          </Button>
          <Button onClick={handleClose}>关闭</Button>
        </Space>
      </Space>
    </Drawer>
  )
}
