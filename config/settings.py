"""
Configuration management
"""

import os
from typing import Dict

class Config:
    def __init__(self):
        self.debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        self.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.model_cache_dir = os.getenv('MODEL_CACHE_DIR', './models')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')

    def get_flask_config(self) -> Dict:
        return {
            'DEBUG': self.debug,
            'SECRET_KEY': self.secret_key,
            'JSON_SORT_KEYS': False
        }
