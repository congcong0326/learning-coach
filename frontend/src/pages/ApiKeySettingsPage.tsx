import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'

import {
  createLlmCredential,
  deleteLlmCredential,
  listLlmCredentials,
  setPreferredLlmCredential,
  testLlmCredential,
  updateLlmCredential,
  type LlmCredential,
  type LlmCredentialPayload,
  type LlmCredentialUpdatePayload,
} from '../api/llmCredentials'
import { currentUserQueryKey } from '../routes/authState'

const credentialQueryKey = ['llm-credentials']

const initialValues: LlmCredentialPayload = {
  display_name: '',
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_mode: 'responses',
  model_name: '',
  api_key: '',
  is_enabled: true,
  is_preferred: false,
}

function statusColor(status: LlmCredential['status']) {
  if (status === 'valid') {
    return 'success'
  }
  if (status === 'invalid') {
    return 'error'
  }
  return 'default'
}

function statusLabel(status: LlmCredential['status']) {
  if (status === 'valid') {
    return '可用'
  }
  if (status === 'invalid') {
    return '不可用'
  }
  return '未测试'
}

export function ApiKeySettingsPage() {
  const [form] = Form.useForm<LlmCredentialPayload>()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingCredential, setEditingCredential] =
    useState<LlmCredential | null>(null)
  const queryClient = useQueryClient()
  const credentialsQuery = useQuery({
    queryKey: credentialQueryKey,
    queryFn: listLlmCredentials,
  })

  const refreshCredentials = async () => {
    await queryClient.invalidateQueries({ queryKey: credentialQueryKey })
    await queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
  }

  function closeModal() {
    createMutation.reset()
    updateMutation.reset()
    setModalOpen(false)
    setEditingCredential(null)
    form.resetFields()
  }

  const createMutation = useMutation({
    mutationFn: createLlmCredential,
    onSuccess: async () => {
      closeModal()
      await refreshCredentials()
    },
  })
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: LlmCredentialUpdatePayload
    }) => updateLlmCredential(id, payload),
    onSuccess: async () => {
      closeModal()
      await refreshCredentials()
    },
  })
  const toggleEnabledMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateLlmCredential(id, { is_enabled: enabled }),
    onSuccess: refreshCredentials,
  })
  const testMutation = useMutation({
    mutationFn: testLlmCredential,
    onSuccess: refreshCredentials,
  })
  const preferredMutation = useMutation({
    mutationFn: setPreferredLlmCredential,
    onSuccess: refreshCredentials,
  })
  const deleteMutation = useMutation({
    mutationFn: deleteLlmCredential,
    onSuccess: refreshCredentials,
  })

  const credentials = credentialsQuery.data?.items ?? []
  const submitMutation = editingCredential ? updateMutation : createMutation

  function openCreateModal() {
    createMutation.reset()
    updateMutation.reset()
    setEditingCredential(null)
    form.setFieldsValue(initialValues)
    setModalOpen(true)
  }

  function openEditModal(credential: LlmCredential) {
    createMutation.reset()
    updateMutation.reset()
    setEditingCredential(credential)
    form.setFieldsValue({
      display_name: credential.display_name,
      provider: 'openai',
      base_url: credential.base_url,
      api_mode: 'responses',
      model_name: credential.model_name,
      api_key: '',
      is_enabled: credential.is_enabled,
      is_preferred: credential.is_preferred,
    })
    setModalOpen(true)
  }

  function submitCredential(values: LlmCredentialPayload) {
    if (!editingCredential) {
      createMutation.mutate(values)
      return
    }

    const updatePayload: LlmCredentialUpdatePayload = {
      display_name: values.display_name,
      base_url: values.base_url,
      api_mode: values.api_mode,
      model_name: values.model_name,
      is_enabled: values.is_enabled,
    }
    if (values.api_key) {
      updatePayload.api_key = values.api_key
    }
    updateMutation.mutate({
      id: editingCredential.id,
      payload: updatePayload,
    })
  }

  return (
    <section className="page-section settings-page">
      <div className="page-heading">
        <Typography.Title level={2}>API 设置</Typography.Title>
        <Button type="primary" onClick={openCreateModal}>
          新增 API 资产
        </Button>
      </div>

      {credentialsQuery.isError ? (
        <Alert
          showIcon
          type="error"
          message="API 资产加载失败"
          className="page-alert"
        />
      ) : null}

      <div className="settings-table-wrap">
        <table className="settings-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>Provider</th>
              <th>模型</th>
              <th>Base URL</th>
              <th>API key</th>
              <th>启用</th>
              <th>状态</th>
              <th>连续失败</th>
              <th>标记</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {credentials.map((credential) => (
              <tr key={credential.id}>
                <td>{credential.display_name}</td>
                <td>{credential.provider}</td>
                <td>{credential.model_name}</td>
                <td>{credential.base_url}</td>
                <td>{credential.api_key_mask}</td>
                <td>
                  <Switch
                    checked={credential.is_enabled}
                    aria-label={`${credential.display_name} 启用`}
                    loading={
                      toggleEnabledMutation.isPending &&
                      toggleEnabledMutation.variables?.id === credential.id
                    }
                    onChange={(checked) =>
                      toggleEnabledMutation.mutate({
                        id: credential.id,
                        enabled: checked,
                      })
                    }
                  />
                </td>
                <td>
                  <Tag color={statusColor(credential.status)}>
                    {statusLabel(credential.status)}
                  </Tag>
                </td>
                <td>{credential.failure_count}</td>
                <td>
                  <Space wrap>
                    {credential.is_preferred ? (
                      <Tag color="blue">首选</Tag>
                    ) : null}
                    {credential.is_active ? (
                      <Tag color="green">当前通讯中</Tag>
                    ) : null}
                  </Space>
                </td>
                <td>
                  <Space wrap>
                    <Button
                      onClick={() => testMutation.mutate(credential.id)}
                      loading={
                        testMutation.isPending &&
                        testMutation.variables === credential.id
                      }
                    >
                      测试连接
                    </Button>
                    <Button
                      disabled={credential.is_preferred}
                      onClick={() => preferredMutation.mutate(credential.id)}
                      loading={
                        preferredMutation.isPending &&
                        preferredMutation.variables === credential.id
                      }
                    >
                      设为首选
                    </Button>
                    <Button
                      aria-label={`编辑 ${credential.display_name}`}
                      onClick={() => openEditModal(credential)}
                    >
                      编辑
                    </Button>
                    <Button
                      danger
                      aria-label={`删除 ${credential.display_name}`}
                      onClick={() => deleteMutation.mutate(credential.id)}
                      loading={
                        deleteMutation.isPending &&
                        deleteMutation.variables === credential.id
                      }
                    >
                      删除
                    </Button>
                  </Space>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {credentialsQuery.isLoading ? (
          <div className="empty-settings">加载中...</div>
        ) : null}
        {credentials.length === 0 && !credentialsQuery.isLoading ? (
          <div className="empty-settings">暂无 API 资产</div>
        ) : null}
      </div>

      <Modal
        title={editingCredential ? '编辑 API 资产' : '新增 API 资产'}
        open={modalOpen}
        destroyOnHidden
        onCancel={closeModal}
        footer={[
          <button
            key="cancel"
            type="button"
            className="ant-btn css-var-root ant-btn-default ant-btn-color-default ant-btn-variant-outlined"
            onClick={closeModal}
          >
            取消
          </button>,
          <button
            key="submit"
            type="button"
            className="ant-btn css-var-root ant-btn-primary ant-btn-color-primary ant-btn-variant-solid"
            disabled={submitMutation.isPending}
            onClick={() => form.submit()}
          >
            {editingCredential ? '更新' : '创建'}
          </button>,
        ]}
      >
        {modalOpen && submitMutation.isError ? (
          <Alert
            showIcon
            type="error"
            message="保存 API 资产失败"
            className="page-alert"
          />
        ) : null}
        <Form<LlmCredentialPayload>
          form={form}
          layout="vertical"
          requiredMark={false}
          initialValues={initialValues}
          onFinish={submitCredential}
        >
          <Form.Item
            label="名称"
            name="display_name"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="Provider" name="provider">
            <Input disabled />
          </Form.Item>
          <Form.Item
            label="Base URL"
            name="base_url"
            rules={[{ required: true, message: '请输入 Base URL' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="API Mode" name="api_mode">
            <Input disabled />
          </Form.Item>
          <Form.Item
            label="模型名称"
            name="model_name"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label="API key"
            name="api_key"
            rules={
              editingCredential
                ? []
                : [{ required: true, message: '请输入 API key' }]
            }
          >
            <Input.Password autoComplete="off" />
          </Form.Item>
          <Form.Item name="is_enabled" valuePropName="checked">
            <Checkbox>启用资产</Checkbox>
          </Form.Item>
          {!editingCredential ? (
            <Form.Item name="is_preferred" valuePropName="checked">
              <Checkbox>设为首选资产</Checkbox>
            </Form.Item>
          ) : null}
        </Form>
      </Modal>
    </section>
  )
}
