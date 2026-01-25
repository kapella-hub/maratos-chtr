# Build frontend
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Build backend
FROM python:3.11-slim AS backend
WORKDIR /app

# Install uv
RUN pip install uv

# Copy backend
COPY backend/pyproject.toml ./
RUN uv pip install --system -e .

COPY backend/ ./

# Copy built frontend
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Create data directory
RUN mkdir -p data

EXPOSE 8000

CMD ["python", "run.py"]
