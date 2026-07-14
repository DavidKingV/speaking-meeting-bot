FROM python:3.11-slim

WORKDIR /app

# Install system dependencies 
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not use virtualenvs inside Docker
RUN poetry config virtualenvs.create false

# Install runtime dependencies only. Dev deps are skipped: they pull an ancient
# grpcio-tools (1.30.0) that fails to build under Python 3.11 (no pkg_resources
# in the PEP517 build env). We don't need it — protobufs are pre-generated.
RUN poetry lock && poetry install --no-interaction --no-ansi --no-root --without dev

# Copy application files
COPY . .

# Set Python path to include the current directory
ENV PYTHONPATH="/app:${PYTHONPATH}"

# NOTE: protobufs/frames_pb2.py is committed to the repo (already generated), so
# no grpc_tools.protoc compile step is needed here.

# Environment variables
ENV PORT=7014

EXPOSE ${PORT}

CMD poetry run uvicorn app:app --host 0.0.0.0 --port ${PORT:-7014}

