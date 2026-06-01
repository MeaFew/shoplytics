import os

# Superset configuration for DuckDB integration
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "dev-key-change-in-production")

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
