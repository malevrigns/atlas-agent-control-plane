FROM node:22-bookworm-slim

WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=8100
ENV WORKSPACE_DIR=/workspace

RUN apt-get update \
  && apt-get install -y --no-install-recommends bash fluxbox websockify x11vnc xvfb \
  && rm -rf /var/lib/apt/lists/*

COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate \
  && pnpm install --frozen-lockfile || pnpm install

COPY tsconfig.json ./
COPY src ./src
COPY scripts ./scripts
RUN chmod +x ./scripts/start.sh

EXPOSE 8100 5900 6080
CMD ["./scripts/start.sh"]
