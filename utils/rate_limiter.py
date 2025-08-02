"""
Rate limiter for API protection
"""

import time
from typing import Dict
import structlog

logger = structlog.get_logger()

class RateLimiter:
    def __init__(self, redis_client=None, limit=100, window=60):
        self.redis_client = redis_client
        self.limit = limit
        self.window = window
        self.memory_store = {}  # Fallback

    def is_allowed(self, client_ip: str) -> bool:
        """Check if request is within rate limit"""
        try:
            current_time = int(time.time())
            
            if self.redis_client:
                key = f"rate_limit:{client_ip}"
                pipe = self.redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, current_time - self.window)
                pipe.zcard(key)
                pipe.zadd(key, {str(current_time): current_time})
                pipe.expire(key, self.window)
                results = pipe.execute()
                
                request_count = results[1]
                return request_count < self.limit
            else:
                # Memory fallback
                if client_ip not in self.memory_store:
                    self.memory_store[client_ip] = []
                
                # Clean old requests
                cutoff = current_time - self.window
                self.memory_store[client_ip] = [
                    req_time for req_time in self.memory_store[client_ip] 
                    if req_time > cutoff
                ]
                
                # Check limit
                if len(self.memory_store[client_ip]) >= self.limit:
                    return False
                
                self.memory_store[client_ip].append(current_time)
                return True
                
        except Exception as e:
            logger.warning(f"Rate limiter error: {e}")
            return True  # Allow on error
