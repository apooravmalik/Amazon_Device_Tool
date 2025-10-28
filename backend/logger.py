import logging
import sys
from logging.handlers import RotatingFileHandler

class StreamToLogger:
    """
    A custom stream object that redirects 'write' calls to a logger.
    Used to capture stdout (like print statements) and stderr.
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''  # Buffer for incomplete lines

    def write(self, buf):
        """
        Handles the 'write' call from the stream (e.g., print).
        Buffers lines until a newline is received.
        """
        # Append buffer to our internal line buffer
        self.linebuf += buf
        
        # Check if there are newlines, indicating complete lines
        if '\n' in self.linebuf:
            lines = self.linebuf.split('\n')
            for line in lines[:-1]:  # Log all complete lines
                # Strip whitespace and log if the line is not empty
                message = line.strip()
                if message:
                    self.logger.log(self.log_level, message)
            
            # Keep the last, possibly incomplete, line in the buffer
            self.linebuf = lines[-1]

    def flush(self):
        """
        Handles the 'flush' call.
        Logs any remaining content in the buffer when flushed.
        """
        # When flush is called (e.g., at program exit),
        # log any remaining content in the buffer.
        message = self.linebuf.strip()
        if message:
            self.logger.log(self.log_level, message)
        self.linebuf = ''

def get_logger(name: str):
    """
    Configures and returns a logger that writes to app.log.
    """
    logger = logging.getLogger(name)
    
    # This check prevents adding handlers multiple times
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # Create a file handler to log to a file
        handler = RotatingFileHandler("app.log", maxBytes=1024 * 1024, backupCount=5)
        handler.setLevel(logging.DEBUG)
        
        # Create a formatter to define the structure of the log messages
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        
        # Add the configured handler to the logger
        logger.addHandler(handler)
        
    return logger

def redirect_prints_to_logging(logger):
    """
    Redirects sys.stdout and sys.stderr to the provided logger.
    
    Call this *once* in your main script after getting a logger.
    All subsequent 'print' statements and unhandled exceptions
    will be sent to the logger.
    """
    
    # Redirect stdout (for print statements)
    # Print statements will be logged at INFO level
    stdout_logger = StreamToLogger(logger, log_level=logging.INFO)
    sys.stdout = stdout_logger
    
    # Redirect stderr (for exceptions and errors)
    # Errors will be logged at ERROR level
    stderr_logger = StreamToLogger(logger, log_level=logging.ERROR)
    sys.stderr = stderr_logger
