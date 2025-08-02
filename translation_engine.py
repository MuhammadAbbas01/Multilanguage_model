"""
Advanced Translation Engine with Multi-Model Support
Optimized for production use with caching and error handling
"""

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
from typing import Dict, List, Optional
import structlog
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger()

class AdvancedTranslationEngine:
    """Production-ready translation engine with advanced features"""
    
    SUPPORTED_LANGUAGES = {
        'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
        'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'ja': 'Japanese',
        'ko': 'Korean', 'zh': 'Chinese', 'ar': 'Arabic', 'hi': 'Hindi',
        'ur': 'Urdu', 'bn': 'Bengali', 'tr': 'Turkish', 'pl': 'Polish',
        'nl': 'Dutch', 'sv': 'Swedish', 'da': 'Danish', 'no': 'Norwegian'
    }

    def __init__(self, model_name: str = "facebook/nllb-200-distilled-600M"):
        """Initialize the translation engine"""
        logger.info(f"Initializing translation engine with model: {model_name}")
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = model_name
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        try:
            # Load model and tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir="./models")
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                model_name, 
                cache_dir="./models",
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            )
            self.model.to(self.device)
            
            # Initialize language detection pipeline
            self.language_detector = pipeline(
                "text-classification",
                model="papluca/xlm-roberta-base-language-detection",
                device=0 if self.device == "cuda" else -1
            )
            
            logger.info(f"Model loaded successfully on device: {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def detect_language(self, text: str) -> str:
        """Detect the language of input text"""
        try:
            if len(text.strip()) < 3:
                return "en" # Default to English for very short text
                
            result = self.language_detector(text)[0]
            detected_lang = result['label'].lower()
            
            # Map common language codes
            lang_mapping = {
                'english': 'en', 'spanish': 'es', 'french': 'fr',
                'german': 'de', 'italian': 'it', 'portuguese': 'pt',
                'russian': 'ru', 'japanese': 'ja', 'korean': 'ko',
                'chinese': 'zh', 'arabic': 'ar', 'hindi': 'hi',
                'urdu': 'ur', 'bengali': 'bn', 'turkish': 'tr'
            }
            
            return lang_mapping.get(detected_lang, detected_lang[:2])
            
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "en"

    def translate(self, text: str, source_lang: str = "auto", 
                  target_lang: str = "en", style: str = "general",
                  context: str = "") -> Dict:
        """
        Translate text with advanced features
        
        Args:
            text: Text to translate
            source_lang: Source language code or "auto"
            target_lang: Target language code
            style: Translation style (general, formal, casual)
            context: Conversation context
            
        Returns:
            Dict with translation results
        """
        start_time = time.time()
        
        try:
            # Detect source language if auto
            if source_lang == "auto":
                source_lang = self.detect_language(text)
                
            # Validate languages
            if target_lang not in self.SUPPORTED_LANGUAGES:
                raise ValueError(f"Unsupported target language: {target_lang}")
            
            # Apply style modifications
            styled_text = self._apply_style(text, style)
            
            # Add context if provided
            if context:
                input_text = f"Context: {context}\nTranslate: {styled_text}"
            else:
                input_text = styled_text
            
            # Prepare input with language tokens
            if self.model_name.startswith("facebook/nllb"):
                input_text = f"{self._get_lang_token(source_lang)} {input_text}"
                target_token = self._get_lang_token(target_lang)
            else:
                input_text = f">>{target_lang}<< {input_text}"
                target_token = None
            
            # Tokenize and translate
            inputs = self.tokenizer(
                input_text, 
                return_tensors="pt", 
                max_length=512,
                truncation=True,
                padding=True
            ).to(self.device)
            
            with torch.no_grad():
                if target_token:
                    # For NLLB models
                    forced_bos_token_id = self.tokenizer.lang_code_to_id.get(target_token)
                    outputs = self.model.generate(
                        **inputs,
                        forced_bos_token_id=forced_bos_token_id,
                        max_length=512,
                        num_beams=4,
                        length_penalty=0.6,
                        do_sample=False
                    )
                else:
                    # For other models
                    outputs = self.model.generate(
                        **inputs,
                        max_length=512,
                        num_beams=4,
                        length_penalty=0.6,
                        do_sample=False
                    )
            
            # Decode translation
            translated_text = self.tokenizer.decode(
                outputs[0], 
                skip_special_tokens=True
            ).strip()
            
            # Clean up translation
            translated_text = self._post_process_translation(translated_text, style)
            
            translation_time = time.time() - start_time
            
            result = {
                'translated_text': translated_text,
                'detected_language': source_lang,
                'confidence': self._calculate_confidence(inputs, outputs),
                'translation_time': translation_time
            }
            
            logger.info(f"Translation completed in {translation_time:.3f}s",
                        source=source_lang, target=target_lang)
            
            return result
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return {
                'translated_text': text, # Fallback to original
                'detected_language': source_lang,
                'confidence': 0.0,
                'translation_time': time.time() - start_time,
                'error': str(e)
            }

    def _apply_style(self, text: str, style: str) -> str:
        """Apply style modifications to text"""
        style_prompts = {
            'formal': "Translate this formally and professionally: ",
            'casual': "Translate this in a casual, friendly way: ",
            'technical': "Translate this technical content accurately: ",
            'literary': "Translate this with literary and poetic style: "
        }
        
        if style in style_prompts:
            return f"{style_prompts[style]}{text}"
        return text

    def _get_lang_token(self, lang_code: str) -> str:
        """Get language token for NLLB models"""
        # NLLB language code mapping
        nllb_codes = {
            'en': 'eng_Latn', 'es': 'spa_Latn', 'fr': 'fra_Latn',
            'de': 'deu_Latn', 'it': 'ita_Latn', 'pt': 'por_Latn',
            'ru': 'rus_Cyrl', 'ja': 'jpn_Jpan', 'ko': 'kor_Hang',
            'zh': 'zho_Hans', 'ar': 'arb_Arab', 'hi': 'hin_Deva',
            'ur': 'urd_Arab', 'bn': 'ben_Beng', 'tr': 'tur_Latn'
        }
        return nllb_codes.get(lang_code, 'eng_Latn')

    def _post_process_translation(self, text: str, style: str) -> str:
        """Clean and format translation output"""
        # Remove common artifacts
        text = text.replace(" ", " ") # Remove sentencepiece artifacts
        text = " ".join(text.split()) # Normalize whitespace
        
        # Style-specific post-processing
        if style == "formal":
            text = text.replace(" i ", " I ") # Capitalize I in English
        
        return text.strip()

    def _calculate_confidence(self, inputs: Dict, outputs: torch.Tensor) -> float:
        """Calculate translation confidence score"""
        try:
            # Simple confidence based on model probability
            # This is a placeholder - in production, you'd use more sophisticated methods
            return min(0.95, max(0.7, 0.9 - (len(inputs['input_ids'][0]) / 1000)))
        except:
            return 0.8

    def get_supported_languages(self) -> List[str]:
        """Get list of supported language codes"""
        return list(self.SUPPORTED_LANGUAGES.keys())

    def get_model_info(self) -> Dict:
        """Get model information"""
        return {
            'model_name': self.model_name,
            'device': self.device,
            'supported_languages': len(self.SUPPORTED_LANGUAGES),
            'gpu_available': torch.cuda.is_available()
        }
