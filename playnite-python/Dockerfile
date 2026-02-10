# Multi-stage build for smaller image size

# Stage 1: Builder
FROM python:3.11-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 playnite && \
    mkdir -p /app /data /captures && \
    chown -R playnite:playnite /app /data /captures

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/playnite/.local

# Copy application code
COPY --chown=playnite:playnite src/ ./src/
COPY --chown=playnite:playnite setup.py pyproject.toml README.md ./

# Switch to non-root user
USER playnite

# Add local pip to PATH
ENV PATH=/home/playnite/.local/bin:$PATH

# Install application
RUN pip install --no-cache-dir --user -e .

# Expose ports
EXPOSE 5555 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5555/api/v1/health/live')" || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite:////data/playnite_python.db \
    CAPTURE_BASE_PATH=/captures \
    LOG_FILE=/data/logs/playnite_python.log

# Create data directories
RUN mkdir -p /data/logs

# Run the application
CMD ["python", "-m", "uvicorn", "playnite_python.api.app:app", "--host", "0.0.0.0", "--port", "5555"]
