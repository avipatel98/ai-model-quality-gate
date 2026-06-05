FROM python:3.10-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and pre-trained model artefacts
COPY src/ ./src/

# Expose API port
EXPOSE 8000

# 4 workers for the optimised serving tier
CMD ["python", "-m", "uvicorn", "src.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
