import logging
import sys
from pythonjsonlogger import jsonlogger
from src.config.settings import settings

def setup_logging():
    """Configures structured JSON logging (Section 3.3)."""
    logger = logging.getLogger()
    
    # Set the log level from configuration
    try:
        logger.setLevel(settings.app.LOG_LEVEL)
    except ValueError:
        logger.setLevel(logging.INFO)
        
    # Remove default handlers
    if logger.handlers:
        logger.handlers = []

    # Create a stream handler for stdout
    handler = logging.StreamHandler(sys.stdout)

    # Use JSON formatter for structured logging
    # This is crucial for observability and audit trails (Section 2.3)
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
        rename_fields={'asctime': 'timestamp', 'levelname': 'level'}
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

# Configure logging globally upon import
setup_logging()
log = logging.getLogger(__name__)