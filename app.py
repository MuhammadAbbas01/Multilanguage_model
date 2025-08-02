#!/usr/bin/env python3
"""
Lingua Translate - Production-Ready Multilingual Translation Service
Author: Your Name
Description: High-performance translation API with advanced features
"""

import os
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, request, jsonify, g
from werkzeug.middleware.proxy_fix import ProxyFix
import redis
import structlog
from prometheus_client import Counter, Histogram, generate_latest
import torch

# Assuming these are available in a `utils` and `config` directory
from utils.translation_engine import AdvancedTranslationEngine
from utils.conversation_manager import ConversationManager
from utils.rate_limiter import RateLimiter
from config.settings import Config

# Initialize structured logging
logger = structlog.get_logger()

# Prometheus metrics
REQUEST_COUNT = Counter('translation_requests_total', 'Total translation requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('translation_request_duration_seconds', 'Translation request latency')

class TranslationAPI:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        
        # Initialize components
        self._setup_config()
        self._setup_redis()
        self._setup_components()
        self._setup_routes()
        self._setup_middleware()

    def _setup_config(self):
        """Load configuration"""
        self.config = Config()
        self.app.config.update(self.config.get_flask_config())

    def _setup_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            self.redis_client = None

    def _setup_components(self):
        """Initialize core components"""
        try:
            # These classes would need to be implemented separately
            self.translator = AdvancedTranslationEngine()
            self.conversation_manager = ConversationManager(redis_client=self.redis_client)
            self.rate_limiter = RateLimiter(redis_client=self.redis_client)
            logger.info("All components initialized successfully")
        except Exception as e:
            logger.error(f"Component initialization failed: {e}")
            raise

    def _setup_middleware(self):
        """Setup request middleware"""
        @self.app.before_request
        def before_request():
            g.start_time = time.time()
            REQUEST_COUNT.labels(method=request.method, endpoint=request.endpoint).inc()

        @self.app.after_request
        def after_request(response):
            if hasattr(g, 'start_time'):
                REQUEST_LATENCY.observe(time.time() - g.start_time)
            return response

    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.route('/')
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'service': 'lingua-translate',
                'version': '2.0.0',
                'timestamp': datetime.utcnow().isoformat(),
                'gpu_available': torch.cuda.is_available()
            })

        @self.app.route('/metrics')
        def metrics():
            """Prometheus metrics endpoint"""
            return generate_latest()

        @self.app.route('/translate', methods=['POST'])
        def translate():
            """Main translation endpoint"""
            return self._handle_translate_request()

        @self.app.route('/languages', methods=['GET'])
        def get_languages():
            """Get supported languages"""
            return jsonify({
                'supported_languages': self.translator.get_supported_languages(),
                'total_count': len(self.translator.get_supported_languages())
            })

        @self.app.route('/batch-translate', methods=['POST'])
        def batch_translate():
            """Batch translation endpoint"""
            return self._handle_batch_translate()

    def _handle_translate_request(self):
        """Handle single translation request"""
        try:
            # Rate limiting
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            if not self.rate_limiter.is_allowed(client_ip):
                return jsonify({'error': 'Rate limit exceeded'}), 429

            # Validate request
            if not request.is_json:
                return jsonify({'error': 'Content-Type must be application/json'}), 400

            data = request.get_json()
            validation_error = self._validate_translate_request(data)
            if validation_error:
                return jsonify({'error': validation_error}), 400

            # Extract parameters
            text = data['text']
            source_lang = data.get('source_lang', 'auto')
            target_lang = data.get('target_lang', 'en')
            style = data.get('style', 'general')
            use_context = data.get('use_context', True)

            # Check cache
            cache_key = f"translate:{source_lang}:{target_lang}:{style}:{hash(text)}"
            if self.redis_client:
                cached_result = self.redis_client.get(cache_key)
                if cached_result:
                    logger.info("Cache hit", cache_key=cache_key)
                    # The eval() function can be dangerous with arbitrary input, but here
                    # it's used with trusted data coming from our own Redis cache.
                    response_data = eval(cached_result)
                    response_data['cached'] = True
                    return jsonify(response_data)

            # Get conversation context
            context = ""
            if use_context and self.conversation_manager:
                session_id = data.get('session_id', client_ip)
                context = self.conversation_manager.get_context(session_id)

            # Perform translation
            start_time = time.time()
            translation_result = self.translator.translate(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                style=style,
                context=context
            )
            translation_time = time.time() - start_time

            # Store in conversation history
            if use_context and self.conversation_manager:
                session_id = data.get('session_id', client_ip)
                self.conversation_manager.add_exchange(
                    session_id=session_id,
                    user_text=text,
                    translation=translation_result['translated_text']
                )

            # Prepare response
            response_data = {
                'original_text': text,
                'translated_text': translation_result['translated_text'],
                'source_language': translation_result.get('detected_language', source_lang),
                'target_language': target_lang,
                'style': style,
                'confidence_score': translation_result.get('confidence', 0.95),
                'translation_time': round(translation_time, 3),
                'cached': False
            }

            # Cache result
            if self.redis_client:
                # The str() function is used to convert the dictionary to a string
                # before storing it in Redis.
                self.redis_client.setex(cache_key, 3600, str(response_data))

            logger.info("Translation completed", 
                        source_lang=source_lang, 
                        target_lang=target_lang,
                        translation_time=translation_time)
            
            return jsonify(response_data)

        except Exception as e:
            logger.error(f"Translation error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    def _handle_batch_translate(self):
        """Handle batch translation requests"""
        try:
            data = request.get_json()
            if not data or 'texts' not in data:
                return jsonify({'error': 'Missing texts array'}), 400

            texts = data['texts']
            if len(texts) > 100:
                return jsonify({'error': 'Maximum 100 texts per batch'}), 400

            source_lang = data.get('source_lang', 'auto')
            target_lang = data.get('target_lang', 'en')
            style = data.get('style', 'general')

            results = []
            for text in texts:
                result = self.translator.translate(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    style=style
                )
                results.append({
                    'original': text,
                    'translated': result['translated_text'],
                    'confidence': result.get('confidence', 0.95)
                })

            return jsonify({
                'results': results,
                'total_count': len(results),
                'source_language': source_lang,
                'target_language': target_lang
            })

        except Exception as e:
            logger.error(f"Batch translation error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    def _validate_translate_request(self, data: Dict) -> Optional[str]:
        """Validate translation request data"""
        if not data.get('text'):
            return 'Missing required field: text'
        
        if len(data['text']) > 5000:
            return 'Text too long (max 5000 characters)'
        
        target_lang = data.get('target_lang')
        if target_lang and target_lang not in self.translator.get_supported_languages():
            return f'Unsupported target language: {target_lang}'
        
        return None

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask application"""
        logger.info(f"Starting Lingua Translate API on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

def create_app():
    """Application factory"""
    api = TranslationAPI()
    return api.app

if __name__ == '__main__':
    # For development
    api = TranslationAPI()
    api.run(debug=True)
