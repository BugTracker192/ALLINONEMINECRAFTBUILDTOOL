FROM node:22-bookworm-slim AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/protocol/package.json packages/protocol/package.json
COPY packages/renderer/package.json packages/renderer/package.json
RUN pnpm install --no-frozen-lockfile
COPY apps/web apps/web
COPY packages/protocol packages/protocol
COPY packages/renderer packages/renderer
RUN pnpm --filter @mbi/web build

FROM nginx:1.29-alpine
COPY infrastructure/docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
