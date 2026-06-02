import {
  DownloadOutlined,
  ExclamationCircleOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Modal, Space, Typography } from 'antd'
import { useState } from 'react'

import {
  exportDatabaseBackup,
  restoreDatabaseBackup,
  type RestoreDatabaseBackupResult,
} from '../api/databaseBackups'

function formatBytes(value: number) {
  if (value >= 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MB`
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  return `${value} B`
}

export function BackupRestorePage() {
  const queryClient = useQueryClient()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [restoreResult, setRestoreResult] =
    useState<RestoreDatabaseBackupResult | null>(null)

  const exportMutation = useMutation({
    mutationFn: exportDatabaseBackup,
  })
  const restoreMutation = useMutation({
    mutationFn: restoreDatabaseBackup,
    onSuccess: (result) => {
      setRestoreResult(result)
      queryClient.clear()
      setConfirmOpen(false)
      setSelectedFile(null)
      if (import.meta.env.MODE !== 'test') {
        window.setTimeout(() => window.location.reload(), 800)
      }
    },
  })

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    setRestoreResult(null)
    restoreMutation.reset()
    const file = event.target.files?.[0] ?? null
    setSelectedFile(file)
  }

  function confirmRestore() {
    if (selectedFile) {
      restoreMutation.mutate(selectedFile)
    }
  }

  return (
    <section className="page-section backup-restore-page">
      <div className="page-heading">
        <Typography.Title level={2}>备份恢复</Typography.Title>
      </div>

      <div className="backup-restore-grid">
        <div className="backup-restore-panel">
          <Typography.Title level={3}>数据库备份</Typography.Title>
          <Button
            type="primary"
            aria-label="导出备份"
            icon={<DownloadOutlined />}
            loading={exportMutation.isPending}
            onClick={() => exportMutation.mutate()}
          >
            导出备份
          </Button>
          {exportMutation.isError ? (
            <Alert
              showIcon
              type="error"
              title="备份导出失败"
              className="page-alert"
            />
          ) : null}
        </div>

        <div className="backup-restore-panel">
          <Typography.Title level={3}>数据库恢复</Typography.Title>
          <Alert
            showIcon
            type="warning"
            title="恢复会覆盖当前全库数据，备份文件未加密。"
            className="page-alert"
          />
          <Space orientation="vertical" align="start" size={12}>
            <label className="backup-file-picker">
              <span>备份文件</span>
              <input
                aria-label="备份文件"
                type="file"
                accept=".dump,application/octet-stream"
                onChange={handleFileChange}
              />
            </label>
            {selectedFile ? (
              <span className="backup-selected-file">
                {selectedFile.name} · {formatBytes(selectedFile.size)}
              </span>
            ) : null}
            <Button
              danger
              aria-label="恢复数据"
              icon={<UploadOutlined />}
              disabled={!selectedFile}
              loading={restoreMutation.isPending}
              onClick={() => setConfirmOpen(true)}
            >
              恢复数据
            </Button>
          </Space>
          {restoreMutation.isError ? (
            <Alert
              showIcon
              type="error"
              title="数据恢复失败"
              className="page-alert"
            />
          ) : null}
          {restoreResult ? (
            <Alert
              showIcon
              type="success"
              title="恢复完成"
              description={`文件大小 ${formatBytes(restoreResult.file_size_bytes)}`}
              className="page-alert"
            />
          ) : null}
        </div>
      </div>

      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined />
            <span>确认恢复</span>
          </Space>
        }
        open={confirmOpen}
        onCancel={() => setConfirmOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setConfirmOpen(false)}>
            取消
          </Button>,
          <Button
            key="restore"
            danger
            type="primary"
            loading={restoreMutation.isPending}
            onClick={confirmRestore}
          >
            确认恢复
          </Button>,
        ]}
      >
        <Typography.Paragraph>
          当前数据库内容会被上传的备份文件覆盖。
        </Typography.Paragraph>
      </Modal>
    </section>
  )
}
