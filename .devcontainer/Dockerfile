FROM mcr.microsoft.com/devcontainers/python:3.11-bullseye

# Install system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        mongodb-org \
        mongodb-org-server \
        mongodb-org-shell \
        mongodb-org-tools \
        git \
        curl \
        build-essential \
        libssl-dev \
        pkg-config \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install MongoDB as a service
RUN mkdir -p /data/db /var/log/mongodb
RUN mongod --version

# Set working directory
WORKDIR /workspace

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Install sentence transformers (large model)
RUN pip install --no-cache-dir sentence-transformers

# Create non-root user for security
RUN useradd -m -u 1000 vscode && \
    chown -R vscode:vscode /workspace

# Switch to non-root user
USER vscode

# Default command
CMD ["/bin/bash"]
