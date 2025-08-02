"""
Conversation Manager for maintaining context across translation sessions
"""

import json
import time
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()

class ConversationManager:
    def __init__(self, redis_client=None, max_history=10):
        self.redis_client = redis_client
        self.max_history = max_history
        self.memory_store = {}  # Fallback when Redis unavailable

    def add_exchange(self, session_id: str, user_text: str, translation: str):
        """Add a new exchange to conversation history"""
        try:
            exchange = {
                'user_text': user_text,
                'translation': translation,
                'timestamp': time.time()
            }
            
            if self.redis_client:
                key = f"conversation:{session_id}"
                history = self._get_history(session_id)
                history.append(exchange)
                
                # Keep only recent exchanges
                if len(history) > self.max_history:
                    history = history[-self.max_history:]
                
                self.redis_client.setex(key, 3600, json.dumps(history))
            else:
                # Fallback to memory
                if session_id not in self.memory_store:
                    self.memory_store[session_id] = []
                
                self.memory_store[session_id].append(exchange)
                if len(self.memory_store[session_id]) > self.max_history:
                    self.memory_store[session_id] = self.memory_store[session_id][-self.max_history:]
                    
        except Exception as e:
            logger.warning(f"Failed to store conversation: {e}")

    def get_context(self, session_id: str) -> str:
        """Get conversation context for translation"""
        try:
            history = self._get_history(session_id)
            if not history:
                return ""
            
            # Build context from recent exchanges
            context_parts = []
            for exchange in history[-3:]:  # Last 3 exchanges
                context_parts.append(f"Previous: {exchange['user_text']} -> {exchange['translation']}")
            
            return " | ".join(context_parts)
            
        except Exception as e:
            logger.warning(f"Failed to get context: {e}")
            return ""

    def _get_history(self, session_id: str) -> List[Dict]:
        """Get conversation history for session"""
        try:
            if self.redis_client:
                key = f"conversation:{session_id}"
                data = self.redis_client.get(key)
                return json.loads(data) if data else []
            else:
                return self.memory_store.get(session_id, [])
        except:
            return []
