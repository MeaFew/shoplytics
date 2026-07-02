import os

# Superset configuration for DuckDB integration
# SECRET_KEY 必须显式提供，不设默认值，避免已知的弱密钥被部署到任何环境。
# 本地开发请在 docker-compose.superset.yml 同级创建 .env 文件：
#     echo "SUPERSET_SECRET_KEY=$(openssl rand -base64 42)" > .env
_secret = os.environ.get("SUPERSET_SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "SUPERSET_SECRET_KEY 未设置。请通过环境变量提供一个随机密钥，"
        "例如: export SUPERSET_SECRET_KEY=$(openssl rand -base64 42)"
    )
SECRET_KEY = _secret

# Allow connecting to DuckDB
PREVENT_UNSAFE_DB_CONNECTIONS = False

# Database configuration (SQLite for metadata)
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"

# Enable CORS for local development
ENABLE_CORS = True
CORS_OPTIONS = {"supports_credentials": True}

# Disable Talisman for local development
TALISMAN_ENABLED = False

# Disable CSRF for easier local setup
WTF_CSRF_ENABLED = False

# DuckDB engine configuration
# Users can add DuckDB as a database with connection string:
# duckdb:///app/data/analytics.duckdb
