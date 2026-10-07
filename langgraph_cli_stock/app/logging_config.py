"""Logging configuration for JSON Lines format."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_log_dir


class JsonLinesHandler(logging.Handler):
    """Custom logging handler that writes JSON Lines format."""
    
    def __init__(self, log_file: Path):
        super().__init__()
        self.log_file = log_file
        self.sequence = 0
        
    def emit(self, record: logging.LogRecord):
        """Emit a JSON Lines log record."""
        try:
            # Get extra fields from record.__dict__ (logging merges extra into __dict__)
            trace_id = getattr(record, 'trace_id', "")
            event_type = getattr(record, 'event_type', record.name)
            component = getattr(record, 'component', record.name)
            payload = getattr(record, 'payload', {})
            
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trace_id": trace_id,
                "event_type": event_type,
                "component": component,
                "sequence": self.sequence,
                "payload": payload
            }
            
            self.sequence += 1
            
            # Write as JSON Line
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            # Last resort error handling
            print(f"Failed to write log: {e}", file=sys.stderr)


def setup_logging(trace_id: str) -> logging.Logger:
    """Set up logging for a specific trace."""
    # Create log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = get_log_dir() / f"trace_{timestamp}.jsonl"
    
    # Create logger
    logger = logging.getLogger(f"trace_{trace_id}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    # Add JSON Lines handler
    handler = JsonLinesHandler(log_file)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    
    # Store trace_id in logger context
    logger.trace_id = trace_id
    
    return logger


def get_logger(name: str, trace_id: str = None) -> logging.Logger:
    """Get a logger with the given name and trace context."""
    logger = logging.getLogger(name)
    
    if trace_id:
        logger.trace_id = trace_id
    
    return logger