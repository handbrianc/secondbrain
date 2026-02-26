# Dockerfile for building secondbrain single executable
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy source code first (required for src layout)
COPY src/ src/
COPY pyproject.toml .

# Create placeholder README for build
RUN echo "# Secondbrain" > README.md

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Install PyInstaller
RUN pip install pyinstaller

# Create the executable - run from the directory where the module is importable
WORKDIR /app/src
RUN PYTHONPATH=/app/src:$PYTHONPATH pyinstaller --onefile --name secondbrain \
    --collect-all click \
    --collect-all pydantic \
    --collect-all pydantic_settings \
    --hidden-import=pymongo \
    --hidden-import=httpx \
    --hidden-import=docling \
    --hidden-import=docling_backend \
    --console \
    secondbrain/cli/__init__.py

# Final stage - minimal runtime
FROM python:3.11-slim

WORKDIR /app

# Copy only the executable from build stage
COPY --from=builder /app/src/dist/secondbrain .

# Ensure executable
RUN chmod +x secondbrain

ENV PATH=/app:$PATH

ENTRYPOINT ["./secondbrain"]
