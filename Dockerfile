# Use the official Microsoft Playwright image as it has all browser system dependencies installed
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set shell and environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Copy dependency specifications first to leverage caching
COPY requirements.txt /app/

# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Pre-fetch the Camoufox browser binary during image build
# This avoids downloading it at runtime
RUN python -m camoufox fetch

# Copy the rest of the application code
COPY src /app/src
COPY config.yaml /app/

# Create folders for screenshots and database storage
RUN mkdir -p /app/screenshots /app/data

# Run the page watcher daemon by default
CMD ["python", "-m", "src.main", "--config", "/app/config.yaml", "--db", "/app/data/watcher.db"]
