# Web GĐ2: build frontend (Node) → nginx phục vụ SPA + proxy /api sang service api. Build từ gốc repo:
#   docker build -f docker/web.Dockerfile .
# Chế độ HTTP (mặc định) hoặc HTTPS (compose.tls.yaml: GPU_TLS=1 + chứng chỉ .pem) — chọn lúc khởi động bởi
# /docker-entrypoint.d/40-gpu-mode.sh (docker/nginx/). Cùng 1 image cho cả hai chế độ.
FROM node:22-alpine AS build
WORKDIR /srv/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx/app.conf docker/nginx/headers.conf docker/nginx/http.conf docker/nginx/https.conf /etc/nginx/gpu/
COPY docker/nginx/40-gpu-mode.sh /docker-entrypoint.d/40-gpu-mode.sh
RUN chmod +x /docker-entrypoint.d/40-gpu-mode.sh \
 && cp /etc/nginx/gpu/http.conf /etc/nginx/conf.d/default.conf \
 && touch /etc/nginx/gpu/realip.conf /etc/nginx/gpu/tls-headers.conf
COPY --from=build /srv/frontend/dist /usr/share/nginx/html
EXPOSE 80 443
