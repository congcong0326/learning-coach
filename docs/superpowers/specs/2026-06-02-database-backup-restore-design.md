# 全库备份恢复设计

## 目标

为本地优先的训练应用提供手动全库备份恢复能力。登录用户可在前端导出 PostgreSQL custom dump 文件，也可上传该文件恢复全库；备份文件不加密。

## 设计

- 后端新增 `/api/database-backups/export` 和 `/api/database-backups/restore`，复用现有 HttpOnly session 登录态。
- 导出使用 `pg_dump --format=custom --compress=9 --no-owner --no-privileges`，返回 `.dump` 文件下载。
- 恢复使用原始二进制请求体上传文件，先校验 `PGDMP` 文件头并执行 `pg_restore --list`，再用 `pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction --exit-on-error` 覆盖当前数据库。
- 后端用进程内锁避免并发备份/恢复；忙碌时返回 `409 backup_restore_busy`。
- 前端新增 `/settings/backup-restore` 页面；没有默认 API 资产的登录用户也可以访问，便于先恢复旧数据。

## 风险控制

- 备份文件不加密，用户需要自行保管。
- 恢复覆盖全库，包括用户、session、API 资产密文、训练记录、Trace、RAG 数据和 Alembic 版本。
- 恢复成功后清空前端 query cache，并在非测试环境短延迟刷新页面；当前 session 可能失效。
- 日志只记录 `user_id`、操作、状态、文件大小和错误摘要，不记录数据库密码、完整连接串或备份内容。

## 验收

- 未登录用户无法调用导出或恢复接口。
- 已登录用户可以下载 `.dump` 文件。
- 上传无效文件返回 `400 invalid_backup_file`。
- 上传超限文件返回 `413 backup_file_too_large`。
- 并发操作返回 `409 backup_restore_busy`。
- 后端镜像包含 `postgresql-client`。
