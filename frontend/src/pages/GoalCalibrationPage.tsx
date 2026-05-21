import { useMutation } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { LlmStreamingPanel } from '../components/LlmStreamingPanel'
import { useLlmRun } from '../hooks/useLlmRun'
import {
  confirmPlan,
  type GoalCalibrationPayload,
  type GoalCalibrationStartResponse,
  type PlanDraftResponse,
} from '../api/learning'

const initialValues: Partial<GoalCalibrationPayload> = {
  weekly_days: 4,
  session_minutes: 60,
  current_level: 'medium_partial',
  preferred_language: 'python3',
  self_reported_weaknesses: [],
  extra_notes: '',
  training_preference: 'independent_first',
}

function normalisePayload(values: GoalCalibrationPayload): GoalCalibrationPayload {
  return {
    ...values,
    self_reported_weaknesses: values.self_reported_weaknesses ?? [],
    extra_notes: values.extra_notes ?? '',
  }
}

export function GoalCalibrationPage() {
  const [draft, setDraft] = useState<GoalCalibrationStartResponse | null>(null)
  const [planDraft, setPlanDraft] = useState<PlanDraftResponse | null>(null)
  const [followupAnswer, setFollowupAnswer] = useState('')
  const navigate = useNavigate()

  const handleCalibrationResult = useCallback((result: unknown) => {
    setDraft(result as GoalCalibrationStartResponse)
    setFollowupAnswer('')
  }, [])
  const handlePlanResult = useCallback((result: unknown) => {
    setPlanDraft(result as PlanDraftResponse)
  }, [])

  const calibrationRun = useLlmRun({ onResult: handleCalibrationResult })
  const planRun = useLlmRun({ onResult: handlePlanResult })
  const confirmMutation = useMutation({
    mutationFn: () => confirmPlan(planDraft?.draft_id ?? 0),
    onSuccess: () => navigate('/study-plan'),
  })

  const hasError = confirmMutation.isError
  const showCalibrationForm =
    !draft && !calibrationRun.isRunning && calibrationRun.status !== 'succeeded'

  function submit(values: GoalCalibrationPayload) {
    setDraft(null)
    setPlanDraft(null)
    void calibrationRun.startRun('goal_followup', normalisePayload(values))
  }

  function submitFollowupAnswer() {
    if (!draft?.draft_id || !draft.followup_question_id || !followupAnswer.trim()) {
      return
    }
    setFollowupAnswer('')
    void calibrationRun.startRun('goal_followup', {
      draft_id: draft.draft_id,
      question_id: draft.followup_question_id,
      answer: followupAnswer,
    })
  }

  function generatePlan() {
    if (!draft?.draft_id) {
      return
    }
    setPlanDraft(null)
    void planRun.startRun('goal_plan_generate', { draft_id: draft.draft_id })
  }

  return (
    <section className="page-section">
      <div className="page-heading">
        <Typography.Title level={2}>目标校准</Typography.Title>
      </div>

      {hasError ? (
        <Alert
          showIcon
          type="error"
          message="目标校准失败"
          className="page-alert"
        />
      ) : null}

      {showCalibrationForm ? (
        <Form
          layout="vertical"
          initialValues={initialValues}
          onFinish={submit}
          className="calibration-form"
        >
          <Form.Item name="goal_type" label="学习目标" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="beginner">刷题入门</Radio>
              <Radio value="interview_sprint">面试冲刺</Radio>
              <Radio value="strengthen_weakness">专项补弱</Radio>
              <Radio value="maintain">保持手感</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            name="target_timeline"
            label="时间线"
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio value="none">无明确时间</Radio>
              <Radio value="within_1_month">1 个月内</Radio>
              <Radio value="one_to_three_months">1 到 3 个月</Radio>
              <Radio value="over_three_months">3 个月以上</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            name="preferred_language"
            label="默认训练语言"
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio value="c">C</Radio>
              <Radio value="go">Go</Radio>
              <Radio value="python3">Python3</Radio>
              <Radio value="javascript">JavaScript</Radio>
              <Radio value="java">Java</Radio>
            </Radio.Group>
          </Form.Item>

          <Space wrap size="large">
            <Form.Item name="weekly_days" label="每周训练天数">
              <InputNumber min={1} max={7} />
            </Form.Item>
            <Form.Item name="session_minutes" label="单次训练分钟">
              <InputNumber min={15} max={180} />
            </Form.Item>
          </Space>

          <Form.Item
            name="current_level"
            label="当前水平"
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio value="new">没系统刷过</Radio>
              <Radio value="easy_started">做过少量 Easy</Radio>
              <Radio value="medium_partial">能做部分 Medium</Radio>
              <Radio value="round_done_unstable">刷过一轮但不稳定</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="self_reported_weaknesses" label="自评弱项">
            <Checkbox.Group
              options={[
                { label: '题意理解', value: 'problem_understanding' },
                { label: '题型识别', value: 'pattern' },
                { label: '复杂度优化', value: 'complexity' },
                { label: '代码实现', value: 'implementation' },
                { label: '边界条件', value: 'edge_case' },
                { label: '面试表达', value: 'interview_expression' },
              ]}
            />
          </Form.Item>

          <Form.Item name="training_preference" label="训练偏好">
            <Radio.Group>
              <Radio value="guided">更希望被引导</Radio>
              <Radio value="independent_first">先独立思考再提示</Radio>
              <Radio value="interviewer_style">偏面试官追问</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="extra_notes" label="补充说明">
            <Input.TextArea rows={4} />
          </Form.Item>

          <Button
            type="primary"
            htmlType="submit"
            loading={calibrationRun.isRunning}
          >
            开始校准
          </Button>
        </Form>
      ) : null}

      {calibrationRun.status !== 'idle' ? (
        <LlmStreamingPanel
          title="目标校准"
          status={calibrationRun.status}
          stage={calibrationRun.stage}
          displayText={calibrationRun.displayText}
          error={calibrationRun.error}
          onCancel={calibrationRun.cancelRun}
        />
      ) : null}

      {draft?.followup_question ? (
        <div className="workflow-panel">
          <Typography.Title level={3}>追问</Typography.Title>
          <Typography.Paragraph>{draft.followup_question}</Typography.Paragraph>
          <Input.TextArea
            value={followupAnswer}
            onChange={(event) => setFollowupAnswer(event.target.value)}
            rows={3}
          />
          <Space wrap>
            <Button
              type="primary"
              onClick={submitFollowupAnswer}
              loading={calibrationRun.isRunning}
              disabled={!followupAnswer.trim() || calibrationRun.isRunning}
            >
              提交回答
            </Button>
            <Button
              onClick={generatePlan}
              loading={planRun.isRunning}
              disabled={planRun.isRunning}
            >
              跳过并生成计划
            </Button>
          </Space>
        </div>
      ) : null}

      {draft && !draft.followup_question && !planDraft ? (
        <Button
          type="primary"
          onClick={generatePlan}
          loading={planRun.isRunning}
          disabled={planRun.isRunning}
        >
          生成计划草稿
        </Button>
      ) : null}

      {planRun.status !== 'idle' ? (
        <LlmStreamingPanel
          title="计划生成"
          status={planRun.status}
          stage={planRun.stage}
          displayText={planRun.displayText}
          error={planRun.error}
          onCancel={planRun.cancelRun}
        />
      ) : null}

      {planDraft ? (
        <div className="workflow-panel">
          <div className="page-heading">
            <Typography.Title level={3}>计划草稿</Typography.Title>
            <Tag color="green">{planDraft.status}</Tag>
          </div>
          <Typography.Paragraph>
            {planDraft.generation_summary_md}
          </Typography.Paragraph>
          <div className="plan-draft-stages">
            {planDraft.stages.map((stage) => (
              <div key={stage.title} className="plan-draft-stage">
                <Typography.Title level={4}>{stage.title}</Typography.Title>
                <Typography.Paragraph>{stage.objective_md}</Typography.Paragraph>
                {stage.items.map((item) => (
                  <div key={item.problem_slug} className="plan-draft-item">
                    {item.order_index}. {item.title || item.problem_slug} ·{' '}
                    {item.difficulty}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <Button
            type="primary"
            onClick={() => confirmMutation.mutate()}
            loading={confirmMutation.isPending}
          >
            确认创建计划
          </Button>
        </div>
      ) : null}
    </section>
  )
}
