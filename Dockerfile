# Stage 1: Build
FROM python:3.10-slim AS builder

# Install system dependencies required for building Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (pin version for reproducibility)
ARG POETRY_VERSION=1.8.4
RUN pip install "poetry==${POETRY_VERSION}"

# Set working directory
WORKDIR /app

# Configure Poetry to not create virtual environments (we are in a container)
RUN poetry config virtualenvs.create false

# Copy project files and install dependencies
COPY pyproject.toml poetry.lock* ./
# Install only production dependencies
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Stage 2: Runtime (Minimal image)
FROM python:3.10-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app

# Install runtime utilities needed for health checks
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Run as a non-root user (Section 2.4)
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR ${APP_HOME}

# Copy built dependencies from the builder stage
# Ensure correct paths for site-packages
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the application source code
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser config ./config

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Container health check hitting the FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Command to run the application
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
