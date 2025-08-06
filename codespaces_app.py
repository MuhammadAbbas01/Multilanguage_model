#!/usr/bin/env python3
"""
Reduced Translation Engine for Codespaces Demo (Arabic, Chinese, Spanish)
"""

import os
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from flask import Flask, request, jsonify, g
from werkzeug.middleware.proxy_fix import ProxyFix
import structlog
from prometheus_client import Counter, Histogram, generate_latest
# Add imports for Hugging Face transformers pipeline
from transformers import pipeline

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Prometheus metrics
REQUEST_COUNT = Counter('translation_requests_total', 'Total translation requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('translation_request_duration_seconds', 'Translation request latency')

class SimpleRateLimiter:
    """Simple in-memory rate limiter"""
    def __init__(self):
        self.requests = {}
        self.limit = 100  # requests per minute
        
    def is_allowed(self, client_ip: str) -> bool:
        current_time = time.time()
        minute_key = int(current_time // 60)
        
        if client_ip not in self.requests:
            self.requests[client_ip] = {}
        
        # Clean old entries
        self.requests[client_ip] = {
            k: v for k, v in self.requests[client_ip].items() 
            if k >= minute_key - 1
        }
        
        current_count = self.requests[client_ip].get(minute_key, 0)
        if current_count >= self.limit:
            return False
            
        self.requests[client_ip][minute_key] = current_count + 1
        return True

class EnhancedTranslationEngine:
    """Reduced translation engine for Codespaces with specific language support"""
    
    def __init__(self):
        # Only support Spanish, Chinese, and Arabic for this demo
        self.supported_languages = ["es", "zh", "ar"]
        
        # Reduced translation dictionaries for the supported languages
        self.translations = {
            "es": {
                "hello": "hola",
                "world": "mundo",
                "thank you": "gracias",
                "good morning": "buenos días",
                "welcome": "bienvenido",
                "login": "iniciar sesión",
                "register": "registrarse",
                "checkout": "finalizar compra",
                "add to cart": "añadir al carrito",
                "your order": "su pedido",
                "has been processed": "ha sido procesado",
                "successfully": "con éxito",
                "premium subscription": "suscripción premium",
                "activated": "activada",
                "welcome to our store": "bienvenido a nuestra tienda",
                "checkout now": "finalizar compra ahora",
                "your trial has expired": "su período de prueba ha expirado",
                "how are you?": "¿cómo estás?", # Added
                "please help me": "por favor, ayúdame" # Added
            },
            "zh": {
                "hello": "你好",
                "world": "世界",
                "thank you": "谢谢",
                "good morning": "早上好",
                "welcome": "欢迎",
                "login": "登录",
                "register": "注册",
                "checkout": "结帐",
                "hello, world!": "你好，世界！",
                "how are you?": "你好吗？", # Added
                "what is your name?": "你叫什么名字？" # Added
            },
            "ar": {
                "hello": "مرحبا",
                "world": "عالم",
                "thank you": "شكرا",
                "good morning": "صباح الخير",
                "welcome": "أهلا بك",
                "login": "تسجيل الدخول",
                "register": "تسجيل",
                "checkout": "الدفع",
                "hello, world!": "مرحبا، العالم!",
                "how are you?": "كيف حالك؟", # Added
                "goodbye": "مع السلامة" # Added
            }
        }
        
        # Try to load transformers models only for the supported languages
        self.ai_models = {}
        try:
            import torch
            device = 0 if torch.cuda.is_available() else -1
            
            # AI models for English to Spanish, Chinese, and Arabic
            try:
                self.ai_models["es"] = pipeline("translation_en_to_es", model="Helsinki-NLP/opus-mt-en-es", device=device)
                logger.info("AI translation model for Spanish loaded.")
            except Exception as e:
                logger.warning(f"Could not load AI model for Spanish: {e}.")

            try:
                self.ai_models["ar"] = pipeline("translation_en_to_ar", model="Helsinki-NLP/opus-mt-en-ar", device=device)
                logger.info("AI translation model for Arabic loaded.")
            except Exception as e:
                logger.warning(f"Could not load AI model for Arabic: {e}.")
            
            try:
                self.ai_models["zh"] = pipeline("translation_en_to_zh", model="Helsinki-NLP/opus-mt-en-zh", device=device)
                logger.info("AI translation model for Chinese loaded.")
            except Exception as e:
                logger.warning(f"Could not load AI model for Chinese: {e}.")

        except Exception as e:
            logger.warning(f"Could not load any AI models: {e}. Using enhanced rule-based translation only.")
            self.ai_models = {}
    
    def get_supported_languages(self) -> List[str]:
        return self.supported_languages
    
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en", 
                  style: str = "general", context: str = "") -> Dict[str, Any]:
        """
        Enhanced translation with a clear fallback strategy.
        1. Try to find an exact match in the hard-coded dictionary.
        2. If that fails, fall back to the AI model if available.
        3. If both fail, return a default non-translated result.
        """
        start_time = time.time()
        
        try:
            # First, try a fast dictionary lookup
            dictionary_translation = self._enhanced_translate(text, target_lang)

            if dictionary_translation is not None:
                # If a dictionary translation was found, use it immediately
                translated_text = dictionary_translation
                translation_time = time.time() - start_time
                logger.info("Used dictionary translation", translation_time=translation_time)
                return {
                    'translated_text': translated_text,
                    'detected_language': "en", # Assuming dictionary is from English
                    'confidence': 1.0,  # High confidence for a hard-coded match
                    'translation_time': translation_time
                }
            
            # If no dictionary translation was found, fall back to the AI model
            # This check is what ensures only valid models are used.
            if target_lang in self.ai_models and source_lang in ["auto", "en"]:
                result = self.ai_models[target_lang](text)
                translated_text = result[0]['translation_text']
                translation_time = time.time() - start_time
                logger.info("Used AI model translation", translation_time=translation_time)
                return {
                    'translated_text': translated_text,
                    'detected_language': "en", # Model translates from English
                    'confidence': 0.95,
                    'translation_time': translation_time
                }

            # If both dictionary and AI model are not available, return a default response
            translation_time = time.time() - start_time
            translated_text = f"[{target_lang.upper()}] {text}"
            logger.warning("No translation found, returning original text with placeholder", translation_time=translation_time)
            
            return {
                'translated_text': translated_text,
                'detected_language': "en",
                'confidence': 0.0,
                'translation_time': translation_time
            }
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return {
                'translated_text': f"Translation Error: {text}",
                'detected_language': "en",
                'confidence': 0.0,
                'translation_time': time.time() - start_time
            }
    
    def _enhanced_translate(self, text: str, target_lang: str) -> Optional[str]:
        """
        Performs a simple, exact-match dictionary lookup.
        Returns the translated string if a match is found, otherwise returns None.
        """
        if target_lang not in self.translations:
            return None
        
        text_lower = text.lower().strip()
        lang_dict = self.translations[target_lang]
        
        # Only perform a direct phrase match, as this is fast and accurate
        if text_lower in lang_dict:
            return lang_dict[text_lower]
        
        # If no match is found, return None to indicate failure
        return None

class TranslationAPI:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        
        # Initialize components
        self._setup_components()
        self._setup_routes()
        self._setup_middleware()

    def _setup_components(self):
        """Initialize core components with error handling"""
        try:
            self.translator = EnhancedTranslationEngine()
            self.rate_limiter = SimpleRateLimiter()
            self.cache = {}  # Simple in-memory cache
            logger.info("All components initialized successfully")
        except Exception as e:
            logger.error(f"Component initialization failed: {e}")
            raise

    def _setup_middleware(self):
        """Setup request middleware"""
        @self.app.before_request
        def before_request():
            g.start_time = time.time()
            REQUEST_COUNT.labels(method=request.method, endpoint=request.endpoint or 'unknown').inc()

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
                'service': 'lingua-translate-reduced', # Changed service name for clarity
                'version': '2.1.0-reduced', # Changed version for clarity
                'timestamp': datetime.utcnow().isoformat()
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
        """Handle single translation request with proper security"""
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

            # Extract parameters with defaults
            text = data['text']
            source_lang = data.get('source_lang', 'auto')
            target_lang = data.get('target_lang', 'en')
            style = data.get('style', 'general')

            # Check cache
            cache_key = f"translate:{source_lang}:{target_lang}:{style}:{hash(text)}"
            if cache_key in self.cache:
                logger.info("Cache hit", cache_key=cache_key)
                response_data = self.cache[cache_key].copy()
                response_data['cached'] = True
                return jsonify(response_data)

            # Perform translation
            start_time = time.time()
            translation_result = self.translator.translate(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                style=style
            )
            translation_time = time.time() - start_time

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
            try:
                self.cache[cache_key] = response_data.copy()
            except Exception as e:
                logger.warning(f"Failed to cache result: {e}")

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
        if not data or not isinstance(data, dict):
            return 'Invalid JSON data'
            
        if not data.get('text'):
            return 'Missing required field: text'
        
        if not isinstance(data['text'], str):
            return 'Text must be a string'
        
        if len(data['text']) > 5000:
            return 'Text too long (max 5000 characters)'
        
        target_lang = data.get('target_lang')
        if target_lang and target_lang not in self.translator.get_supported_languages():
            return f'Unsupported target language: {target_lang}'
        
        return None

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask application"""
        logger.info(f"Starting Lingua Translate API (Reduced) on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

def create_app():
    """Application factory"""
    api = TranslationAPI()
    return api.app

if __name__ == '__main__':
    # For development
    api = TranslationAPI()
    api.run(debug=True)
