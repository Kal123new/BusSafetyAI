FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements*.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-space.txt ultralytics==8.4.127
COPY backend ./backend
COPY models ./models
COPY --from=frontend /build/dist ./dist
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
ENV HOME=/home/appuser YOLO_MODEL_PATH=/app/models/best.pt PORT=7860 SAFESENSE_MODE=production
EXPOSE 7860
CMD ["python", "-m", "backend.run_space"]
