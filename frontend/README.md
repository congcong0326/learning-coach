# Learning Coach Frontend

当前前端使用 Vite、React、TypeScript、Ant Design、React Router 和 TanStack Query。

## 本地命令

建议通过 Corepack 调用当前项目声明的 pnpm 版本，避免依赖全局 pnpm：

```bash
corepack pnpm install
corepack pnpm dev
corepack pnpm lint
corepack pnpm test
corepack pnpm build
```

开发服务默认运行在 Vite 端口，`/api` 请求会代理到 `http://localhost:8000`。
