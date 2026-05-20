# Base image: Python 3.12
FROM python:3.12-slim

LABEL org.opencontainers.image.title="E-commerce User Behavior Analytics"
LABEL org.opencontainers.image.description="Full-stack analytics pipeline on 29M user behavior records"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt dashboard/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r dashboard/requirements.txt

# Copy project code
COPY . .

# Default: run the full analysis pipeline then start dashboard
EXPOSE 8501
CMD ["sh", "-c", "python python/scripts/run_analysis_pipeline.py && cd dashboard && streamlit run app.py --server.address 0.0.0.0 --server.port 8501"]
