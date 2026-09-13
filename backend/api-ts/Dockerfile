FROM node:22-alpine

WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=8000
ENV DATABASE_URL=file:/app/data/atlas.db

COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate \
  && pnpm install --frozen-lockfile || pnpm install

COPY tsconfig.json ./
COPY src ./src
RUN mkdir -p /app/data /app/uploads /app/artifacts

EXPOSE 8000
CMD ["pnpm", "start"]
