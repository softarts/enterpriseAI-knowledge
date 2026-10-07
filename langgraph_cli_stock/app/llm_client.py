"""LLM client module with HTTP request/response logging."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import httpx

from .config import get_llm_config
from .trace import sanitize_for_json
from .utils.redaction import redact_headers, redact_json_payload


class LLMClient:
    """OpenAI-compatible LLM client with full HTTP logging."""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """Initialize LLM client with configuration."""
        config = get_llm_config()
        self.api_key = api_key or config["api_key"]
        self.base_url = base_url or config["base_url"]
        self.model = model or config["model"]
        self._trace_id = None
        self._logger = None
    
    def set_trace_context(self, trace_id: str, logger: logging.Logger):
        """Set trace context for logging."""
        self._trace_id = trace_id
        self._logger = logger
    
    def _log_request(self, method: str, url: str, headers: Dict, json_data: Dict):
        """Log HTTP request details."""
        if not self._logger:
            return
        
        # Redact sensitive data
        safe_headers = redact_headers(dict(headers))
        safe_json = redact_json_payload(json_data)
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self._trace_id,
            "event_type": "llm_http_request",
            "component": "llm_client",
            "payload": {
                "method": method,
                "url": url,
                "headers": safe_headers,
                "json": safe_json,
                "request_start_time": datetime.now(timezone.utc).isoformat()
            }
        }
        
        # Use the logger to write the entry
        extra = {
            "trace_id": self._trace_id,
            "event_type": "llm_http_request",
            "component": "llm_client",
            "payload": log_entry["payload"]
        }
        
        # Log the request
        self._logger.info(f"LLM HTTP Request: {method} {url}", extra=extra)
    
    def _log_response(self, method: str, url: str, status_code: int, 
                      headers: Dict, response_data: Any, duration_ms: float):
        """Log HTTP response details."""
        if not self._logger:
            return
        
        # Redact sensitive data
        safe_headers = redact_headers(dict(headers))
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self._trace_id,
            "event_type": "llm_http_response",
            "component": "llm_client",
            "payload": {
                "method": method,
                "url": url,
                "status_code": status_code,
                "headers": safe_headers,
                "response": sanitize_for_json(response_data),
                "duration_ms": duration_ms,
                "success": status_code < 400
            }
        }
        
        extra = {
            "trace_id": self._trace_id,
            "event_type": "llm_http_response", 
            "component": "llm_client",
            "payload": log_entry["payload"]
        }
        
        self._logger.info(
            f"LLM HTTP Response: {status_code} ({duration_ms:.0f}ms)", 
            extra=extra
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send a chat completion request and return the response."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }
        
        if tools:
            payload["tools"] = tools
        
        # Log the request
        self._log_request("POST", url, headers, payload)
        
        # Make the HTTP request
        start_time = time.time()
        
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, headers=headers, json=payload)
                duration_ms = (time.time() - start_time) * 1000
                
                # Parse response
                try:
                    response_data = response.json()
                except json.JSONDecodeError:
                    response_data = {"text": response.text}
                
                # Log the response
                self._log_response(
                    "POST", 
                    url, 
                    response.status_code, 
                    dict(response.headers), 
                    response_data, 
                    duration_ms
                )
                
                # Raise for error status codes
                response.raise_for_status()
                
                return response_data
                
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            error_data = {"error": str(e), "status_code": e.response.status_code}
            self._log_response("POST", url, e.response.status_code, 
                             dict(e.response.headers), error_data, duration_ms)
            raise
            
        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            error_data = {"error": str(e), "type": "request_error"}
            self._logger.error(
                f"LLM request failed: {e}",
                extra={
                    "trace_id": self._trace_id,
                    "event_type": "error",
                    "component": "llm_client",
                    "payload": error_data
                }
            )
            raise


def get_llm_client() -> LLMClient:
    """Get a configured LLM client instance."""
    return LLMClient()