FROM node:24-alpine AS deps

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:24-alpine AS builder

WORKDIR /app

# Reuse the pnpm package-manager cache prepared in the deps stage.
# Without this copy, Corepack may try to download pnpm again during `pnpm build`,
# which makes Docker builds fragile on unstable networks.
COPY --from=deps /root/.cache/node/corepack /root/.cache/node/corepack
RUN corepack enable

ARG API_PROXY_URL=http://localhost:8000/api/:path*
ENV API_PROXY_URL=$API_PROXY_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN pnpm build

FROM node:24-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Next standalone server reads HOSTNAME and PORT from environment variables.
# In Docker, the default HOSTNAME is the container id, so bind explicitly to
# 0.0.0.0 to let health checks, Nginx and other containers reach the UI.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN addgroup -S nextjs && adduser -S nextjs -G nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
