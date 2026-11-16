# Stage 1: Build the frontend with Node.js
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python runtime
FROM python:3.12-slim AS runner

# Create non-root system user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -m appuser

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY cli/ ./cli/
COPY backend/ ./backend/
COPY schemas/ ./schemas/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend:/app/cli:/app \
    APP_ENV=production \
    PORT=8000

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
