FROM python:3.12-slim

LABEL org.opencontainers.image.title="E-commerce User Behavior Analytics"
LABEL org.opencontainers.image.description="Full-stack analytics platform on 29M real user behavior records"

# System dependencies (gcc for XGBoost, others minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Layer 1: root Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Layer 2: dashboard dependencies ----
COPY dashboard/requirements.txt dashboard/requirements.txt
RUN pip install --no-cache-dir -r dashboard/requirements.txt

# ---- Layer 3: project source (data excluded via .dockerignore) ----
COPY . .

# Volumes for data persistence
VOLUME ["/app/data", "/app/images", "/app/reports"]

EXPOSE 8501 8888

# Default entrypoint: Streamlit dashboard (aligned with exposed port 8501)
# Override via docker-compose for analytics (pipeline) or jupyter (notebook) services
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
