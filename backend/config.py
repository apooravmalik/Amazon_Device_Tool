import os
import logging
import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("config")

# Build DB connection string
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_SERVER = os.getenv("DB_SERVER", "10.192.0.173")
DB_NAME = os.getenv("DB_NAME", "vtasdata_amazon")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "m00se_1234")
DB_TRUST_CERT = os.getenv("DB_TRUST_CERT", "yes")

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8000))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- ProServer Configuration ---
PROSERVER_IP = os.getenv("PROSERVER_IP", "10.192.0.173")
PROSERVER_PORT = int(os.getenv("PROSERVER_PORT", "7777"))

# --- SQLAlchemy Connection String ---
def create_connection_string():
    """Create a properly formatted connection string for MS SQL Server using SQLAlchemy"""
    # Build the ODBC connection string without quotes around the driver
    odbc_str = (
        f"DRIVER={DB_DRIVER};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        f"TrustServerCertificate={'yes' if DB_TRUST_CERT.lower() == 'yes' else 'no'};"
        f"Timeout=60;"
    )
    # URL-encode the entire connection string
    params = urllib.parse.quote_plus(odbc_str)
    return f"mssql+pyodbc:///?odbc_connect={params}"

CONNECTION_STRING = create_connection_string()
logger.debug(f"Connection string created successfully")

# Create SQLAlchemy engine
try:
    engine = create_engine(
        CONNECTION_STRING,
        echo=False,  # Set to True for debugging SQL queries
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
    )
    logger.info("SQLAlchemy engine created successfully")
except Exception as e:
    logger.error(f"Error creating engine: {e}")
    raise

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

def health_check():
    """Verifies database connection by executing a simple query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful for health check")
        return True
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

@contextmanager
def get_db_connection():
    """
    Provide a transactional scope around a series of operations.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def fetch_one(query: str, params: dict = None):
    """Fetch a single row."""
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        row = result.fetchone()
        return dict(row._mapping) if row else None

def fetch_all(query: str, params: dict = None):
    """Fetch all rows."""
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

def execute_query(query: str, params: dict = None):
    """Execute insert/update/delete query and return affected row count."""
    with engine.begin() as conn:  # begin ensures commit/rollback
        result = conn.execute(text(query), params or {})
        return result.rowcount