# ---- Builder Stage ----
FROM python:3.9-slim AS builder

WORKDIR /app

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.9-slim

# Set explicit UID/GID
ARG UID=1000
ARG GID=1000

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY src/ ./src/

# Volumes
VOLUME /app/src/logs

# Explicitly set environment variables
ENV PYTHONUNBUFFERED=1
ENV CREATE_LOG=True \
    API_KEY="" \
    AI_GEMINI_MODEL="gemini-2.0-flash"

# Create user and set permissions
RUN groupadd -g $GID mygroup && \
    useradd -m -u $UID -g $GID -d /app myuser && \
    chown -R $UID:$GID /app && \
    mkdir -p /app/src/logs && \
    chown -R $UID:$GID /app/src/logs

# Activate venv and set logs volume
ENV PATH="/opt/venv/bin:$PATH"

USER $UID

# Expose the application port
EXPOSE 5000

# Run the script
CMD ["python", "/app/src/endpoint.py"]