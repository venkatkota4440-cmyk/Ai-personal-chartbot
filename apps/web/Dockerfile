# Build from the repository root:  docker build -f apps/web/Dockerfile .
FROM node:22-slim AS deps
WORKDIR /srv/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-slim AS build
WORKDIR /srv
COPY --from=deps /srv/apps/web/node_modules ./apps/web/node_modules
COPY packages ./packages
COPY apps/web ./apps/web
WORKDIR /srv/apps/web
ENV NEXT_TELEMETRY_DISABLED=1
# Next.js bakes rewrite destinations into the build, so the internal API URL is a build argument.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
RUN npm run build

FROM node:22-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
# Standalone output contains only the files the server needs; no dev dependencies or sources.
COPY --from=build --chown=node:node /srv/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /srv/apps/web/.next/static ./.next/static
COPY --from=build --chown=node:node /srv/apps/web/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
