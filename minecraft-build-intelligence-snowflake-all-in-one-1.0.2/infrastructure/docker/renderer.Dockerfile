FROM mcr.microsoft.com/playwright:v1.55.0-noble
RUN corepack enable && useradd --create-home --uid 10001 mbi
WORKDIR /app
COPY apps/renderer-service/package.json ./package.json
RUN pnpm install --no-frozen-lockfile
COPY apps/renderer-service/tsconfig.json ./tsconfig.json
COPY apps/renderer-service/src ./src
RUN pnpm build
USER mbi
EXPOSE 8090
CMD ["node", "dist/server.js"]
