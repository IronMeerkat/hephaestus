# 🔨 Hephaestus Base Image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

FROM base AS dev

# Copy the rest of the application
COPY . ./hephaestus/

# Install hephaestus package
RUN uv pip install -e ./hephaestus/

# # Set Python path to include installed package
# ENV PYTHONPATH="/app/src:${PYTHONPATH}"

# # Default command (can be overridden in derived images)
# RUN python -c "import hephaestus; print('🔨 Hephaestus development build complete!')"

FROM base AS prod

# Build the wheel package
COPY src/ ./src/
COPY README.md ./
RUN uv build --wheel --out-dir /tmp/dist

# Install the built wheel
RUN uv pip install /tmp/dist/*.whl

# Clean up build artifacts
RUN rm -rf /tmp/dist ./src ./README.md

# Verify installation
# RUN python -c "import hephaestus; print('🔨 Hephaestus production build complete!')"

