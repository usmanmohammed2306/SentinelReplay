FROM node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install --global pnpm@12.6.0
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN addgroup -g 10001 sentinel && adduser -D -u 10001 -G sentinel sentinel
COPY --from=build --chown=sentinel:sentinel /app/.next/standalone ./
COPY --from=build --chown=sentinel:sentinel /app/.next/static ./.next/static
COPY --from=build --chown=sentinel:sentinel /app/public ./public
USER sentinel
EXPOSE 3000
CMD ["node", "server.js"]
