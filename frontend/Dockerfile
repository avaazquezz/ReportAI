# ── Builder stage: full install (build needs devDependencies: tailwind, gsap) ─
FROM node:22-alpine AS builder

WORKDIR /app

# npm ci runs `postinstall: nuxt prepare`, which needs the source present —
# so copy everything before installing instead of the usual lockfile-first split.
COPY . .

RUN npm ci && npm run build

# ── Runtime stage: only the self-contained Nitro output, non-root user ───────
FROM node:22-alpine AS runtime

WORKDIR /app

COPY --from=builder /app/.output ./.output

RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app

USER appuser

ENV NUXT_PUBLIC_API_BASE=/api

# alpine ships wget (busybox), not curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["node", ".output/server/index.mjs"]
