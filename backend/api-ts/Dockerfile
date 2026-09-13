FROM node:22-alpine

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate \
  && pnpm install --frozen-lockfile || pnpm install

COPY tsconfig.json ./
COPY src ./src

EXPOSE 8000
CMD ["pnpm", "start"]
