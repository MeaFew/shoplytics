FROM python:3.12-slim

LABEL org.opencontainers.image.title="E-commerce User Behavior Analytics"
LABEL org.opencontainers.image.description="Full-stack analytics pipeline on 29M user behavior records"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: root dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2: dashboard dependencies
COPY dashboard/requirements.txt dashboard/
RUN pip install --no-cache-dir -r dashboard/requirements.txt

# Layer 3: project code (excludes data via .dockerignore)
COPY . .

EXPOSE 8501
CMD ["sh", "-c", "python python/scripts/run_analysis_pipeline.py && cd dashboard && streamlit run app.py --server.address 0.0.0.0 --server.port 8501"]
