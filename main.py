"""
Advanced Translation Engine
This module contains the core translation logic, including AI model handling,
caching with Redis, and integration with external services.
"""

import os
import json
import time
from typing import List, Dict, Optional, Any
import structlog
from transformers import pipeline
import torch
from redis import Redis, ConnectionError as RedisConnectionError

from .conversation_manager import ConversationManager
from ..config.settings import Config

logger = structlog.get_logger()

class AdvancedTranslationEngine:
    def __init__(self, config: Config, redis_client: Optional[Redis] = None):
        """
        Initializes the translation engine.
        
        Args:
            config (Config): The application configuration object.
            redis_client (Optional[Redis]): An optional Redis client for caching.
        """
        self.config = config
        self.redis_client = redis_client
        self.conversation_manager = ConversationManager(redis_client=self.redis_client)
        
        # Determine device for model inference (GPU or CPU)
        self.device = 0 if torch.cuda.is_available() and self.config.gpu_enabled else -1
        logger.info(f"Using device: {'GPU' if self.device == 0 else 'CPU'}")

        # Load the translation model from Hugging Face Transformers
        # The pipeline handles tokenization and model inference in one go.
        try:
            self.model_pipeline = pipeline(
                "translation",
                model=self.config.model_name,
                device=self.device,
                cache_dir=self.config.model_cache_dir,
                # Additional model parameters can be passed here
            )
            logger.info(f"Successfully loaded translation model: {self.config.model_name}")
        except Exception as e:
            logger.error(f"Failed to load translation model: {e}")
            self.model_pipeline = None

    def get_supported_languages(self) -> List[str]:
        """
        Returns a list of supported languages for translation.
        
        Note: For this example, we return a static list. In a real-world
        application, this would be dynamically fetched from the model.
        
        Returns:
            A list of language codes.
        """
        # This list should ideally be fetched from the model's tokenizer config
        # For simplicity, we use a predefined list.
        return ["en", "es", "fr", "de", "it", "ja", "ko", "zh", "ru", "ar"]

    def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        session_id: Optional[str] = None,
        use_context: bool = False,
        style: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Translates a single piece of text.
        
        Args:
            text (str): The text to translate.
            target_lang (str): The target language code.
            source_lang (Optional[str]): The source language code. Auto-detected if None.
            session_id (Optional[str]): A unique ID for conversation context.
            use_context (bool): Whether to use previous conversation for context.
            style (Optional[str]): Translation style (e.g., 'formal', 'casual').
            
        Returns:
            A dictionary containing the translation results and metadata.
        """
        start_time = time.time()
        
        # Check cache first
        cache_key = f"translation:{source_lang}:{target_lang}:{text}"
        if self.redis_client:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                result = json.loads(cached_data)
                result['cached'] = True
                result['translation_time'] = time.time() - start_time
                logger.info("Cache hit for translation")
                return result

        # Prepare prompt with context and style if enabled
        context = ""
        if use_context and session_id:
            context = self.conversation_manager.get_context(session_id)
            if context:
                context = f"Context: {context}. "
        
        # Add style guidance if provided
        style_prompt = ""
        if style:
            style_prompt = f"Translate in a {style} style. "

        full_text = f"{context}{style_prompt}{text}"

        translated_text = self._translate_text_with_ai(full_text, source_lang, target_lang)

        # Build the final response object
        translation_result = {
            "original_text": text,
            "translated_text": translated_text,
            "source_language": source_lang if source_lang else "auto-detected",
            "target_language": target_lang,
            "style": style,
            "confidence_score": 0.95, # Placeholder for a real model score
            "translation_time": time.time() - start_time,
            "cached": False
        }

        # Store in cache
        if self.redis_client and translation_result['translated_text']:
            self.redis_client.setex(cache_key, 3600, json.dumps(translation_result))
            logger.info("Translation result stored in cache")
        
        # Add to conversation history
        if session_id:
            self.conversation_manager.add_exchange(session_id, text, translated_text)

        return translation_result

    def batch_translate(self, texts: List[str], target_lang: str, source_lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Translates a list of texts in a single batch.
        
        Args:
            texts (List[str]): A list of texts to translate.
            target_lang (str): The target language code.
            source_lang (Optional[str]): The source language code.
        
        Returns:
            A list of dictionaries with the translation results.
        """
        if not self.model_pipeline:
            return [{"error": "Translation model not loaded"}]

        # Hugging Face pipelines can handle a list of inputs directly
        try:
            results = self.model_pipeline(texts, src_lang=source_lang, tgt_lang=target_lang)
            
            # Format the output to match the single translation response structure
            formatted_results = [
                {
                    "original_text": text,
                    "translated_text": res['translation_text'],
                    "source_language": source_lang,
                    "target_language": target_lang
                }
                for text, res in zip(texts, results)
            ]
            return formatted_results
        except Exception as e:
            logger.error(f"Batch translation failed: {e}")
            return [{"error": f"Batch translation failed: {e}"}]

    def _translate_text_with_ai(self, text: str, source_lang: Optional[str], target_lang: str) -> str:
        """
        Internal method to call the AI model for translation.
        
        Args:
            text (str): The text to translate.
            source_lang (Optional[str]): The source language code.
            target_lang (str): The target language code.
            
        Returns:
            The translated text.
        """
        if not self.model_pipeline:
            logger.error("Attempted to translate with no model loaded.")
            return "Error: Translation model not available."
            
        try:
            # Hugging Face pipeline expects `src_lang` and `tgt_lang` for translation
            result = self.model_pipeline(
                text,
                src_lang=source_lang,
                tgt_lang=target_lang
            )
            return result[0]['translation_text']
        except Exception as e:
            logger.error(f"AI translation failed: {e}")
            # Fallback to an external service if necessary
            # For this example, we return a simple error message
            return "Error: AI translation failed."
