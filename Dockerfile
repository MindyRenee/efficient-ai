FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[proxy]"

# Expose port
EXPOSE 8000

# Set environment variables for x402
ENV EFFICIENT_NETWORK=eip155:8453
ENV EFFICIENT_FACILITATOR_URL=https://x402.org/facilitator

# Run the server
CMD ["efficient", "serve", "--host", "0.0.0.0", "--port", "8000"]
