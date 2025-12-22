"""
Florence-2 Document Classifier
Modular component for detecting false positive handwriting classifications.
Only loads model when first used (lazy loading).
"""

import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM
import logging
import os
from typing import Dict, Union, Optional

logger = logging.getLogger(__name__)


class FlorenceHandwritingClassifier:
    """
    Florence-2 based document classifier for handwriting detection.
    Only initializes model when first used (lazy loading).
    
    This is a modular component that can be enabled/disabled via configuration.
    """
    
    def __init__(self, model_name: str = "microsoft/Florence-2-base", enabled: bool = True):
        """
        Initialize Florence classifier.
        
        Args:
            model_name: HuggingFace model name
            enabled: Whether Florence classification is enabled
        """
        self.model = None
        self.processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = model_name
        self.enabled = enabled
        self._model_loaded = False
        
    def _load_model(self):
        """Lazy load model on first use"""
        if not self.enabled:
            logger.warning("Florence classifier is disabled")
            return False
            
        if self.model is None and not self._model_loaded:
            logger.info(f"Loading Florence-2 model ({self.model_name}) - first time only...")
            try:
                # Check for required dependencies first
                missing = []
                try:
                    import einops
                except ImportError:
                    missing.append("einops")
                
                try:
                    import timm
                except ImportError:
                    missing.append("timm")
                
                if missing:
                    error_msg = (
                        f"Missing required dependencies for Florence-2: {', '.join(missing)}. "
                        f"Install with: pip install {' '.join(missing)}"
                    )
                    logger.error(error_msg)
                    raise ImportError(error_msg)
                
                # Dependencies available, proceed with model loading
                # Set environment variable to avoid SDPA compatibility issues
                import os as os_module
                original_attn = os_module.environ.get('TRANSFORMERS_ATTENTION_IMPLEMENTATION', None)
                os_module.environ['TRANSFORMERS_ATTENTION_IMPLEMENTATION'] = 'eager'
                
                try:
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_name,
                        trust_remote_code=True,
                        attn_implementation="eager"  # Use eager attention to avoid SDPA issues
                    ).to(self.device)
                    
                    self.processor = AutoProcessor.from_pretrained(
                        self.model_name,
                        trust_remote_code=True
                    )
                    self._model_loaded = True
                    logger.info(f"Florence model loaded successfully on {self.device}")
                    return True
                finally:
                    # Restore original environment variable
                    if original_attn is not None:
                        os_module.environ['TRANSFORMERS_ATTENTION_IMPLEMENTATION'] = original_attn
                    elif 'TRANSFORMERS_ATTENTION_IMPLEMENTATION' in os_module.environ:
                        del os_module.environ['TRANSFORMERS_ATTENTION_IMPLEMENTATION']
            except ImportError as e:
                # Missing dependencies - don't log as error, just warn
                logger.warning(f"Florence-2 dependencies missing: {e}")
                logger.warning("Florence classifier will be disabled. Install missing packages to enable.")
                self._model_loaded = False
                self.enabled = False  # Disable to prevent repeated attempts
                return False
            except Exception as e:
                logger.error(f"Failed to load Florence model: {e}", exc_info=True)
                self._model_loaded = False
                return False
        return self._model_loaded
    
    def classify_document(self, image_path_or_pil: Union[str, Image.Image], 
                         prompt: Optional[str] = None) -> Dict:
        """
        Classify if document is handwritten or printed.
        
        Args:
            image_path_or_pil: Path to image or PIL Image object
            prompt: Custom prompt (optional, uses default if None)
            
        Returns:
            dict with keys:
                - is_printed: bool
                - confidence: float (0-1)
                - explanation: str
                - raw_scores: dict with keyword scores
                - error: str (if classification failed)
        """
        if not self.enabled:
            return {
                'is_printed': None,
                'confidence': 0.0,
                'explanation': 'Florence classifier is disabled',
                'error': 'Classifier disabled'
            }
        
        if not self._load_model():
            return {
                'is_printed': None,
                'confidence': 0.0,
                'explanation': 'Failed to load Florence model',
                'error': 'Model loading failed'
            }
        
        try:
            # Load image
            if isinstance(image_path_or_pil, str):
                if not os.path.exists(image_path_or_pil):
                    raise FileNotFoundError(f"Image not found: {image_path_or_pil}")
                image = Image.open(image_path_or_pil).convert('RGB')
            else:
                image = image_path_or_pil.convert('RGB')
            
            # Default prompt optimized for document classification
            if prompt is None:
                prompt = "<MORE_DETAILED_CAPTION>"
            
            # Run inference
            inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                # Fix for Florence-2 past_key_values issue: explicitly set use_cache=False
                # or provide empty past_key_values
                try:
                    generated_ids = self.model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=512,
                        num_beams=1,
                        do_sample=False,
                        use_cache=False,  # Disable cache to avoid past_key_values issues
                        pad_token_id=self.processor.tokenizer.pad_token_id or self.processor.tokenizer.eos_token_id
                    )
                except AttributeError as e:
                    # Fallback: try with minimal parameters
                    logger.warning(f"Generation with cache failed, trying without: {e}")
                    generated_ids = self.model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=256,
                        do_sample=False
                    )
            
            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
            
            # Parse the explanation from generated text
            try:
                explanation = self.processor.post_process_generation(
                    generated_text,
                    task=prompt,
                    image_size=(image.width, image.height)
                )
            except Exception as e:
                # Fallback: use raw generated text if post-processing fails
                logger.warning(f"Post-processing failed, using raw text: {e}")
                explanation = generated_text
            
            # Parse result
            result = self._parse_classification(explanation)
            result['explanation'] = str(explanation)
            
            return result
            
        except Exception as e:
            logger.error(f"Florence classification failed: {e}", exc_info=True)
            return {
                'is_printed': None,
                'confidence': 0.0,
                'explanation': f'Classification error: {str(e)}',
                'error': str(e)
            }
    
    def _parse_classification(self, explanation: str) -> Dict:
        """
        Parse Florence output to determine if document is printed or handwritten.
        Uses conservative logic to avoid false positives (accepting handwritten as printed).
        
        Args:
            explanation: Raw Florence output text
            
        Returns:
            dict with classification results
        """
        text = str(explanation).lower()
        
        # Keywords indicating printed documents (strong signals)
        printed_keywords_strong = [
            'printed', 'typed', 'computer-generated', 'digital',
            'system-generated', 'form', 'official document',
            'certificate', 'template', 'scanned document'
        ]
        
        printed_keywords_weak = [
            'document', 'pdf', 'text', 'stamp', 'seal'
        ]
        
        # Keywords indicating handwritten (strong signals)
        handwritten_keywords_strong = [
            'handwritten', 'handwriting', 'written by hand',
            'manuscript', 'cursive', 'script', 'hand-drawn',
            'written manually', 'hand written'
        ]
        
        handwritten_keywords_weak = [
            'pen', 'pencil', 'ink', 'written'
        ]
        
        # Count strong and weak signals separately
        printed_strong = sum(1 for kw in printed_keywords_strong if kw in text)
        printed_weak = sum(1 for kw in printed_keywords_weak if kw in text)
        handwritten_strong = sum(1 for kw in handwritten_keywords_strong if kw in text)
        handwritten_weak = sum(1 for kw in handwritten_keywords_weak if kw in text)
        
        # Weighted scores (strong signals count more)
        printed_score = (printed_strong * 3) + printed_weak
        handwritten_score = (handwritten_strong * 3) + handwritten_weak
        
        # Special handling for mixed documents (signatures/stamps)
        has_signature = any(word in text for word in ['signature', 'signed', 'stamp', 'seal'])
        has_printed_text = any(word in text for word in ['text', 'printed', 'typed', 'form', 'document'])
        
        # CONSERVATIVE DECISION LOGIC (avoid false positives)
        # Only classify as printed if we have strong evidence
        
        if handwritten_strong > 0:
            # Strong handwritten signals - classify as handwritten
            is_printed = False
            confidence = min(0.95, 0.7 + (handwritten_strong * 0.1))
        elif printed_strong >= 2 and handwritten_score == 0:
            # Strong printed signals, no handwritten signals
            is_printed = True
            confidence = min(0.95, 0.75 + (printed_strong * 0.05))
        elif has_signature and has_printed_text and printed_strong >= 1:
            # Printed document with signatures/stamps (common case)
            # But require at least one strong printed signal
            is_printed = True
            confidence = 0.8
        elif printed_score > handwritten_score * 3 and printed_strong >= 1:
            # Much more printed, with at least one strong signal
            is_printed = True
            confidence = min(0.9, 0.65 + (printed_strong * 0.05))
        elif handwritten_score > printed_score:
            # More handwritten signals
            is_printed = False
            confidence = min(0.9, 0.6 + (handwritten_score * 0.05))
        elif printed_score > handwritten_score * 2 and printed_strong >= 1:
            # Significantly more printed with strong signal
            is_printed = True
            confidence = 0.7
        else:
            # Ambiguous - default to HANDWRITTEN (safer - avoid false positives)
            # This is more conservative than before - when in doubt, reject
            is_printed = False
            confidence = 0.5
            logger.debug("Florence classification ambiguous - defaulting to handwritten (conservative)")
        
        return {
            'is_printed': is_printed,
            'confidence': round(confidence, 3),
            'raw_scores': {
                'printed_keywords': printed_score,
                'handwritten_keywords': handwritten_score,
                'has_signature': has_signature
            }
        }
    
    def is_false_positive_handwriting(self, image_path_or_pil: Union[str, Image.Image], 
                                      threshold: float = 0.6) -> bool:
        """
        Quick check: Is this a false positive handwriting detection?
        
        Args:
            image_path_or_pil: Path to image or PIL Image
            threshold: Minimum confidence to consider it printed
            
        Returns:
            bool: True if document is actually printed (false positive)
        """
        if not self.enabled:
            return False
        
        result = self.classify_document(image_path_or_pil)
        
        if result.get('error'):
            return False
        
        return result.get('is_printed', False) and result.get('confidence', 0) >= threshold


# Global instance (lazy loaded, can be configured via environment)
def get_florence_classifier() -> FlorenceHandwritingClassifier:
    """
    Get or create global Florence classifier instance.
    Can be configured via FLORENCE_ENABLED environment variable.
    """
    enabled = os.getenv('FLORENCE_ENABLED', 'false').lower() == 'true'
    return FlorenceHandwritingClassifier(enabled=enabled)


# Global instance (will be created on first use)
_florence_instance = None

def get_florence_instance() -> FlorenceHandwritingClassifier:
    """Get singleton Florence instance"""
    global _florence_instance
    if _florence_instance is None:
        _florence_instance = get_florence_classifier()
    return _florence_instance
