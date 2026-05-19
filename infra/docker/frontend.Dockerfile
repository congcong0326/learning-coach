FROM node:22-bookworm-slim AS base

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

WORKDIR /app/frontend

RUN corepack enable && corepack prepare pnpm@11.1.3 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS dev

COPY frontend ./

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0"]

FROM base AS build

COPY frontend ./
RUN pnpm build

FROM nginx:1.29-alpine AS runtime

COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
