#!/usr/bin/env python3
"""
Lightweight Translation Engine for GitHub Codespaces
Optimized for 3-4GB memory limit with essential languages only
"""
import sys
import os
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from flask import Flask, request, jsonify, g, render_template_string
from werkzeug.middleware.proxy_fix import ProxyFix
import structlog
from prometheus_client import Counter, Histogram, generate_latest
from flask_cors import CORS

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

class LightweightTranslationEngine:
    """Lightweight translation engine optimized for Codespaces"""
    
    def __init__(self):
        # Only 4 essential languages: English (input), Spanish, Arabic, Chinese
        self.supported_languages = ["en", "es", "ar", "zh"]
        
        # Comprehensive translation dictionaries for essential languages
        self.translations = {
            "en": {
                "hello": "hello",
                "world": "world",
                "thank you": "thank you",
                "good morning": "good morning",
                "welcome": "welcome",
                "login": "login",
                "register": "register",
                "checkout": "checkout",
                "add to cart": "add to cart",
                "your order": "your order",
                "has been processed": "has been processed",
                "successfully": "successfully",
                "premium subscription": "premium subscription",
                "activated": "activated",
                "welcome to our store": "welcome to our store",
                "checkout now": "checkout now",
                "your trial has expired": "your trial has expired",
                "hello, world!": "hello, world!",
                "what is your name?": "what is your name?",
                "how are you?": "how are you?",
                "good bye": "good bye",
                "see you later": "see you later",
                "have a nice day": "have a nice day",
                "please": "please",
                "excuse me": "excuse me",
                "i'm sorry": "i'm sorry",
                "yes": "yes",
                "no": "no"
            },
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
                "hello, world!": "¡hola, mundo!",
                "what is your name?": "¿cómo te llamas?",
                "how are you?": "¿cómo estás?",
                "good bye": "adiós",
                "see you later": "hasta luego",
                "have a nice day": "que tengas un buen día",
                "please": "por favor",
                "excuse me": "disculpe",
                "i'm sorry": "lo siento",
                "yes": "sí",
                "no": "no"
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
                "add to cart": "أضف إلى السلة",
                "your order": "طلبك",
                "has been processed": "تم معالجته",
                "successfully": "بنجاح",
                "premium subscription": "الاشتراك المميز",
                "activated": "مفعل",
                "welcome to our store": "مرحبا بك في متجرنا",
                "checkout now": "ادفع الآن",
                "your trial has expired": "انتهت فترة التجربة",
                "hello, world!": "مرحبا، العالم!",
                "what is your name?": "ما اسمك؟",
                "how are you?": "كيف حالك؟",
                "good bye": "وداعا",
                "see you later": "أراك لاحقا",
                "have a nice day": "أتمنى لك يوما سعيدا",
                "please": "من فضلك",
                "excuse me": "المعذرة",
                "i'm sorry": "آسف",
                "yes": "نعم",
                "no": "لا"
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
                "add to cart": "添加到购物车",
                "your order": "您的订单",
                "has been processed": "已处理",
                "successfully": "成功",
                "premium subscription": "高级订阅",
                "activated": "已激活",
                "welcome to our store": "欢迎来到我们的商店",
                "checkout now": "立即结账",
                "your trial has expired": "您的试用期已到期",
                "hello, world!": "你好，世界！",
                "what is your name?": "你叫什么名字？",
                "how are you?": "你好吗？",
                "good bye": "再见",
                "see you later": "回头见",
                "have a nice day": "祝你今天愉快",
                "please": "请",
                "excuse me": "打扰一下",
                "i'm sorry": "对不起",
                "yes": "是",
                "no": "不"
            }
        }
        
        # Load FAANG-level AI models for essential languages
        self.ai_models = {}
        self._load_faang_ai_models()
    
    def _load_faang_ai_models(self):
        """Load AI models for FAANG-level performance"""
        try:
            from transformers import pipeline
            
            # Load AI models for Spanish, Arabic, and Chinese (FAANG quality)
            models_to_load = {
                "es": "Helsinki-NLP/opus-mt-en-es",
                "ar": "Helsinki-NLP/opus-mt-en-ar", 
                "zh": "Helsinki-NLP/opus-mt-en-zh"
            }
            
            for lang, model_name in models_to_load.items():
                try:
                    self.ai_models[lang] = pipeline(
                        "translation",
                        model=model_name,
                        device=-1,  # CPU optimized for Codespaces
                        model_kwargs={
                            "low_cpu_mem_usage": True,
                            "torch_dtype": "float32"
                        }
                    )
                    logger.info(f"✅ FAANG-level AI model loaded for {lang}: {model_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to load AI model for {lang}: {e}")
                    
        except ImportError:
            logger.error("❌ Transformers not available - install with: pip install transformers torch")
        except Exception as e:
            logger.error(f"❌ Failed to initialize AI models: {e}")
    
    def get_supported_languages(self) -> List[str]:
        return self.supported_languages
    
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en", 
                  style: str = "general", context: str = "") -> Dict[str, Any]:
        """
        Lightweight translation with dictionary-first approach
        """
        start_time = time.time()
        try:
            # Prioritize AI models for FAANG-level quality
            if target_lang in self.ai_models and source_lang in ["auto", "en"]:
                try:
                    result = self.ai_models[target_lang](text)
                    translated_text = result[0]['translation_text']
                    translation_time = time.time() - start_time
                    logger.info(f"🚀 FAANG-level AI translation used for {target_lang}", translation_time=translation_time)
                    return {
                        'translated_text': translated_text,
                        'detected_language': "en",
                        'confidence': 0.95,
                        'translation_time': translation_time,
                        'method': 'ai_model_faang'
                    }
                except Exception as e:
                    logger.warning(f"AI model failed for {target_lang}: {e}")
            
            # Fallback to dictionary if AI model unavailable
            dictionary_translation = self._dictionary_translate(text, target_lang)
            if dictionary_translation is not None:
                translation_time = time.time() - start_time
                logger.info("Used dictionary fallback", translation_time=translation_time)
                return {
                    'translated_text': dictionary_translation,
                    'detected_language': "en",
                    'confidence': 0.8,
                    'translation_time': translation_time,
                    'method': 'dictionary_fallback'
                }
            
            # Fallback to AI model only for Spanish and if available
            if target_lang == "es" and target_lang in self.ai_models and source_lang in ["auto", "en"]:
                try:
                    result = self.ai_models[target_lang](text)
                    translated_text = result[0]['translation_text']
                    translation_time = time.time() - start_time
                    logger.info("Used AI model translation", translation_time=translation_time)
                    return {
                        'translated_text': translated_text,
                        'detected_language': "en",
                        'confidence': 0.95,
                        'translation_time': translation_time,
                        'method': 'ai_model'
                    }
                except Exception as e:
                    logger.warning(f"AI model failed: {e}")

            # Final fallback
            translation_time = time.time() - start_time
            translated_text = f"[{target_lang.upper()}] {text}"
            logger.warning("Using fallback translation", translation_time=translation_time)
            
            return {
                'translated_text': translated_text,
                'detected_language': "en",
                'confidence': 0.1,
                'translation_time': translation_time,
                'method': 'fallback'
            }
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return {
                'translated_text': f"Translation Error: {text}",
                'detected_language': "en",
                'confidence': 0.0,
                'translation_time': time.time() - start_time,
                'method': 'error'
            }
    
    def _dictionary_translate(self, text: str, target_lang: str) -> Optional[str]:
        """Fast dictionary lookup translation"""
        if target_lang not in self.translations:
            return None
        
        text_lower = text.lower().strip()
        lang_dict = self.translations[target_lang]
        
        # Direct phrase match
        if text_lower in lang_dict:
            return lang_dict[text_lower]
        
        return None

class TranslationAPI:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        
        # Initialize components
        self._setup_components()
        self._setup_routes()
        self._setup_middleware()

    def _setup_components(self):
        """Initialize core components with error handling"""
        try:
            self.translator = LightweightTranslationEngine()
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
        def serve_web_app():
            """Serve the web application HTML"""
            return jsonify({
                'status': 'healthy',
                'service': 'lingua-translate-faang-level',
                'version': '1.0.0-codespaces',
                'timestamp': datetime.utcnow().isoformat(),
                'supported_languages': self.translator.get_supported_languages(),
                'memory_optimized': True
            })

        @self.app.route('/health')
        def health_check():
            """Health check endpoint"""
            import psutil
            memory_info = psutil.virtual_memory()
            return jsonify({
                'status': 'healthy',
                'service': 'lingua-translate-faang-level',
                'version': '1.0.0-codespaces',
                'timestamp': datetime.utcnow().isoformat(),
                'memory_usage': {
                    'available_gb': round(memory_info.available / (1024**3), 2),
                    'percent_used': memory_info.percent
                },
                'ai_models_loaded': list(self.translator.ai_models.keys())
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
                'total_count': len(self.translator.get_supported_languages()),
                'optimized_for': 'codespaces'
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
                return jsonify({'error': 'Content-Type must be JSON'}), 400

            data = request.get_json()
            validation_error = self._validate_translate_request(data)
            if validation_error:
                return jsonify({'error': validation_error}), 400

            # Extract parameters
            text = data['text']
            source_lang = data.get('source_lang', 'auto')
            target_lang = data.get('target_lang', 'es')
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
                'cached': False,
                'method': translation_result.get('method', 'unknown'),
                'optimized_for': 'codespaces'
            }

            # Cache result (limit cache size for memory)
            if len(self.cache) < 100:  # Limit cache size
                self.cache[cache_key] = response_data.copy()

            logger.info("Translation completed", 
                       source_lang=source_lang, 
                       target_lang=target_lang,
                       translation_time=translation_time)
            
            return jsonify(response_data)

        except Exception as e:
            logger.error(f"Translation error: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    def _handle_batch_translate(self):
        """Handle batch translation requests (limited for memory)"""
        try:
            data = request.get_json()
            if not data or 'texts' not in data:
                return jsonify({'error': 'Missing texts array'}), 400

            texts = data['texts']
            if len(texts) > 20:  # Reduced for Codespaces
                return jsonify({'error': 'Maximum 20 texts per batch for Codespaces'}), 400

            source_lang = data.get('source_lang', 'auto')
            target_lang = data.get('target_lang', 'es')
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
                    'confidence': result.get('confidence', 0.95),
                    'method': result.get('method', 'unknown')
                })

            return jsonify({
                'results': results,
                'total_count': len(results),
                'source_language': source_lang,
                'target_language': target_lang,
                'optimized_for': 'codespaces'
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
        
        if len(data['text']) > 1000:  # Reduced for Codespaces
            return 'Text too long (max 1000 characters for Codespaces)'
        
        target_lang = data.get('target_lang')
        if target_lang and target_lang not in self.translator.get_supported_languages():
            return f'Unsupported target language: {target_lang}. Supported: {self.translator.get_supported_languages()}'
        
        return None

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask application"""
        logger.info(f"Starting FAANG-Level Lingua Translate API on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug, threaded=True)

def create_app():
    """Application factory"""
    api = TranslationAPI()
    return api.app

if __name__ == '__main__':
    print("Starting FAANG-Level Lingua Translate API for GitHub Codespaces...")
    print(f"Python version: {sys.version}")
    
    try:
        api = TranslationAPI()
        print("✅ FAANG-Level TranslationAPI initialized successfully")
        print(f"✅ Supported languages: {api.translator.get_supported_languages()}")
        print(f"🚀 FAANG-level AI models loaded: {list(api.translator.ai_models.keys())}")
        print("🎯 Optimized for GitHub Codespaces with FAANG-quality AI models")
        
        # Check memory
        try:
            import psutil
            memory_info = psutil.virtual_memory()
            print(f"Available memory: {memory_info.available / (1024**3):.1f}GB")
            print(f"Memory usage: {memory_info.percent}%")
        except ImportError:
            print("psutil not available, cannot check memory")
        
        api.run(host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        print(f"Failed to start application: {e}")
        import traceback
        traceback.print_exc()
