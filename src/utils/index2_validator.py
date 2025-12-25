"""
Index-II Document Validator
Specialized validator for Maharashtra Index-II property registration documents.
Uses lenient acceptance criteria suitable for government document quality.
Focuses on authenticity markers rather than perfect image quality.
"""

import cv2
import numpy as np
from PIL import Image
import pytesseract
import logging
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)


class Index2Validator:
    """
    Specialized validator for Index-II documents.
    Focuses on authenticity markers rather than perfect image quality.
    """
    
    def __init__(self):
        """Initialize Index-II validator with lenient thresholds."""
        # Lenient OCR threshold for Index-II (government docs are often lower quality)
        self.min_ocr_confidence = float(os.getenv('INDEX2_MIN_OCR_CONFIDENCE', 30))
        
        # Minimum score to accept Index-II document
        self.min_accept_score = float(os.getenv('INDEX2_MIN_ACCEPT_SCORE', 50))
    
    def validate_index2(self, image_path: str) -> Dict:
        """
        Validate Index-II document based on structure and authenticity.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            dict: {
                'decision': 'ACCEPT' or 'REJECT',
                'score': float (0-100),
                'validation_details': dict,
                'rejection_reason': str or None
            }
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {
                    'decision': 'REJECT',
                    'score': 0,
                    'rejection_reason': 'Could not read image file',
                    'validation_details': {}
                }
            
            # Step 1: Check minimum readability (very lenient for Index-II)
            ocr_result = self._check_ocr_readability(image_path)
            if ocr_result['confidence'] < self.min_ocr_confidence:
                return {
                    'decision': 'REJECT',
                    'score': ocr_result['confidence'],
                    'rejection_reason': f'Text completely unreadable (OCR: {ocr_result["confidence"]:.1f}%) - document may be corrupted',
                    'validation_details': {'ocr': ocr_result}
                }
            
            # Step 2: Verify Index-II structural elements
            structural_check = self._verify_structure(image_path, img)
            
            # Step 3: Check if document is 100% handwritten (reject these)
            # Pass OCR confidence to help distinguish bold text from actual handwriting
            handwriting_check = self._check_if_fully_handwritten(image_path, ocr_result['confidence'])
            
            if handwriting_check['is_fully_handwritten']:
                return {
                    'decision': 'REJECT',
                    'score': 0,
                    'rejection_reason': 'Document is fully handwritten - not a valid Index-II',
                    'validation_details': {
                        'ocr': ocr_result,
                        'handwriting': handwriting_check
                    }
                }
            
            # Step 4: Calculate overall score
            overall_score = self._calculate_index2_score(
                ocr_result,
                structural_check,
                handwriting_check
            )
            
            # Decision: Accept if score >= minimum threshold (lenient)
            decision = 'ACCEPT' if overall_score >= self.min_accept_score else 'REJECT'
            
            return {
                'decision': decision,
                'score': round(overall_score, 2),
                'rejection_reason': None if decision == 'ACCEPT' else f'Quality below minimum threshold (score: {overall_score:.1f})',
                'validation_details': {
                    'ocr': ocr_result,
                    'structure': structural_check,
                    'handwriting': handwriting_check
                }
            }
            
        except Exception as e:
            logger.error(f"Index-II validation failed: {e}", exc_info=True)
            return {
                'decision': 'REJECT',
                'score': 0,
                'rejection_reason': f'Validation error: {str(e)}',
                'validation_details': {}
            }
    
    def _check_ocr_readability(self, image_path: str) -> Dict:
        """
        Check if text is readable - very lenient threshold for Index-II.
        """
        try:
            img = Image.open(image_path)
            
            # Try OCR with multiple languages
            try:
                ocr_data = pytesseract.image_to_data(
                    img,
                    lang='eng+hin+mar',
                    output_type=pytesseract.Output.DICT
                )
            except:
                try:
                    ocr_data = pytesseract.image_to_data(
                        img,
                        lang='eng+hin',
                        output_type=pytesseract.Output.DICT
                    )
                except:
                    ocr_data = pytesseract.image_to_data(
                        img,
                        lang='eng',
                        output_type=pytesseract.Output.DICT
                    )
            
            confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1' and conf != '']
            avg_confidence = np.mean(confidences) if confidences else 0
            
            # Extract text to check content
            try:
                text = pytesseract.image_to_string(img, lang='eng+hin+mar')
            except:
                try:
                    text = pytesseract.image_to_string(img, lang='eng+hin')
                except:
                    text = pytesseract.image_to_string(img, lang='eng')
            
            return {
                'confidence': round(avg_confidence, 2),
                'text_length': len(text.strip()),
                'has_content': len(text.strip()) > 50,
                'word_count': len(text.strip().split())
            }
            
        except Exception as e:
            logger.warning(f"OCR readability check failed: {e}")
            return {
                'confidence': 0,
                'text_length': 0,
                'has_content': False,
                'word_count': 0
            }
    
    def _verify_structure(self, image_path: str, img: np.ndarray) -> Dict:
        """
        Verify document has Index-II structural elements:
        - Barcode (top area)
        - Official seals/stamps
        - Table structure (payment details, property details)
        """
        try:
            height, width = img.shape[:2]
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            checks = {
                'has_barcode': False,
                'has_seal': False,
                'has_table_structure': False,
                'has_header': False
            }
            
            # Check for barcode in top 20% of document
            top_section = gray[0:int(height*0.2), :]
            edges = cv2.Canny(top_section, 50, 150)
            vertical_projection = np.sum(edges, axis=0)
            
            if len(vertical_projection) > 0:
                checks['has_barcode'] = (
                    np.std(vertical_projection) > 20 and 
                    np.max(vertical_projection) > height * 0.1
                )
            
            # Check for circular seals (Hough circles)
            try:
                circles = cv2.HoughCircles(
                    gray, cv2.HOUGH_GRADIENT, 1, 50,
                    param1=100, param2=30, minRadius=30, maxRadius=150
                )
                checks['has_seal'] = circles is not None and len(circles[0]) > 0
            except:
                pass
            
            # Check for table structure (horizontal lines)
            try:
                horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                detect_horizontal = cv2.morphologyEx(
                    thresh,
                    cv2.MORPH_OPEN,
                    horizontal_kernel,
                    iterations=2
                )
                checks['has_table_structure'] = np.sum(detect_horizontal) > width * height * 0.001
            except:
                pass
            
            # Check for header text (सूची क्र.2, Index-II)
            try:
                text = pytesseract.image_to_string(
                    Image.open(image_path),
                    lang='eng+hin+mar'
                )
                checks['has_header'] = any(
                    marker in text.lower() 
                    for marker in ['सूची', 'index', 'regn']
                )
            except:
                pass
            
            structure_score = sum(checks.values()) * 25  # 0-100 scale
            
            return {
                'checks': checks,
                'score': structure_score
            }
            
        except Exception as e:
            logger.warning(f"Structure verification failed: {e}")
            return {
                'checks': {},
                'score': 0
            }
    
    def _check_if_fully_handwritten(self, image_path: str, ocr_confidence: float = None) -> Dict:
        """
        Check if document is 100% handwritten (should reject these).
        Uses Florence-2 if available, otherwise uses OCR text analysis.
        
        For Index-II documents: If OCR confidence is high (>= 70%), trust OCR over handwriting detection.
        Bold text in Index-II documents can trigger false handwriting detection.
        """
        try:
            # CRITICAL: If OCR confidence is high (>= 70%), document is readable
            # Index-II documents with bold text often have high handwriting % but are still printed
            # Trust OCR over handwriting detection for high OCR confidence
            if ocr_confidence is not None and ocr_confidence >= 70:
                logger.info(f"High OCR confidence ({ocr_confidence:.1f}%) - trusting OCR, not fully handwritten (likely bold text)")
                return {
                    'is_fully_handwritten': False,
                    'confidence': 0.9,
                    'method': 'ocr_confidence_override'
                }
            
            # Try Florence-2 first (if available)
            try:
                from src.utils.florence_classifier import get_florence_instance
                
                florence = get_florence_instance()
                if florence and florence.enabled:
                    result = florence.classify_document(image_path)
                    
                    # If Florence says it's printed, trust it
                    if result.get('is_printed') and result.get('confidence', 0) > 0.6:
                        return {
                            'is_fully_handwritten': False,
                            'confidence': result.get('confidence', 0),
                            'method': 'florence'
                        }
                    
                    # If Florence says handwritten with high confidence, check OCR first
                    # High OCR (>= 60%) means text is readable, so it's likely bold text, not handwritten
                    if not result.get('is_printed') and result.get('confidence', 0) > 0.7:
                        if ocr_confidence is not None and ocr_confidence >= 60:
                            # OCR can read it - likely bold text, not handwritten
                            logger.info(f"Florence says handwritten but OCR is good ({ocr_confidence:.1f}%) - likely bold text, not fully handwritten")
                            return {
                                'is_fully_handwritten': False,
                                'confidence': 0.7,
                                'method': 'ocr_override_florence'
                            }
                        # OCR is low - likely actually handwritten
                        return {
                            'is_fully_handwritten': True,
                            'confidence': result.get('confidence', 0),
                            'method': 'florence'
                        }
            except:
                pass  # Florence not available
            
            # Fallback: Check for printed text patterns using OCR
            try:
                img = Image.open(image_path)
                try:
                    text = pytesseract.image_to_string(img, lang='eng+hin+mar')
                except:
                    try:
                        text = pytesseract.image_to_string(img, lang='eng+hin')
                    except:
                        text = pytesseract.image_to_string(img, lang='eng')
                
                # If we can extract significant printed text, it's not fully handwritten
                has_printed_keywords = any(
                    kw in text.lower() 
                    for kw in ['payment', 'details', 'registry', 'index', 'सूची', 'मोबदला', 'regn']
                )
                
                # Also check OCR confidence if available
                if ocr_confidence is not None and ocr_confidence >= 50:
                    # OCR can read it reasonably well - likely printed, not fully handwritten
                    logger.info(f"OCR confidence ({ocr_confidence:.1f}%) indicates readable text - not fully handwritten")
                    return {
                        'is_fully_handwritten': False,
                        'confidence': 0.8 if has_printed_keywords else 0.6,
                        'method': 'ocr_text_analysis'
                    }
                
                return {
                    'is_fully_handwritten': not has_printed_keywords,
                    'confidence': 0.8 if has_printed_keywords else 0.6,
                    'method': 'ocr_text_analysis'
                }
            except:
                pass
            
            # Default: assume not fully handwritten (conservative)
            return {
                'is_fully_handwritten': False,
                'confidence': 0.5,
                'method': 'default'
            }
            
        except Exception as e:
            logger.warning(f"Handwriting check failed: {e}")
            return {
                'is_fully_handwritten': False,
                'confidence': 0.5,
                'method': 'error'
            }
    
    def _calculate_index2_score(self, ocr_result: Dict, 
                               structural_check: Dict, 
                               handwriting_check: Dict) -> float:
        """
        Calculate overall Index-II validation score.
        
        Weights:
        - OCR readability: 40%
        - Structural elements: 40%
        - Not fully handwritten: 20%
        """
        # Boost OCR score (lenient for Index-II)
        ocr_score = min(100, ocr_result['confidence'] * 1.5)
        
        structure_score = structural_check.get('score', 0)
        
        # Handwriting score: 100 if not fully handwritten, 0 if fully handwritten
        handwriting_score = 100 if not handwriting_check.get('is_fully_handwritten', False) else 0
        
        overall = (
            ocr_score * 0.4 +
            structure_score * 0.4 +
            handwriting_score * 0.2
        )
        
        return round(overall, 2)
