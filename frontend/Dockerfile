# syntax=docker/dockerfile:1
# Builds the SPA and serves it with Caddy, which is also the reverse proxy for
# /api (Caddyfile mounted from deploy/caddy by docker-compose.yml).

FROM node:26.13.1-trixie-slim AS build
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN npm install --global pnpm@12.21.0
WORKDIR /srv/frontend
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM caddy:2.11.9-alpine AS runtime
COPY --from=build /srv/frontend/dist /srv/www
