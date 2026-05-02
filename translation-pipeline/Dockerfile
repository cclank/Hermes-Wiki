FROM python:3.11-slim

WORKDIR /app

# Install git for repository cloning
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app_enhanced.py app.py
COPY terminology_map.json .
COPY .env* ./

# Create translations directory
RUN mkdir -p /app/translations

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Expose port
EXPOSE 8080

# Run the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 3600 app:app
