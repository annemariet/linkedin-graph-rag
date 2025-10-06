FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and static analysis tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    curl \
    wget \
    nodejs \
    npm \
    openjdk-11-jdk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js tools for JavaScript/TypeScript analysis
RUN npm install -g eslint prettier typescript @typescript-eslint/parser @typescript-eslint/eslint-plugin

# Install uv for faster Python package management
RUN pip install --no-cache-dir uv

# Install additional static analysis tools
RUN uv pip install --no-cache-dir \
    semgrep \
    gitpython \
    truffleHog \
    && semgrep --config=auto --dryrun /tmp || true

# Install Python dependencies
COPY pyproject.toml ./
RUN uv sync --all-extras

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]