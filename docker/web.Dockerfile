FROM node:22-alpine AS dependencies
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM dependencies AS builder
COPY apps/web apps/web
RUN pnpm --filter @fleetpulse/web build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production
WORKDIR /app
RUN addgroup -S fleetpulse && adduser -S fleetpulse -G fleetpulse
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
USER fleetpulse
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
