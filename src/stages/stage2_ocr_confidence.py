"""
Stage 2: OCR Confidence Analysis
Uses Tesseract OCR to verify text readability.
Processing Time: 2-5 seconds per page
"""

import pytesseract
from PIL import Image
import cv2
import numpy as np
from typing import Dict, List
import os
from dotenv import load_dotenv

load_dotenv()


class OCRConfidenceAnalyzer:
    """Analyzes OCR confidence to determine text readability."""
    
    def __init__(self):
        """Initialize thresholds from environment variables."""
        # Critical threshold (immediate reject)
        self.ocr_critical_threshold = float(os.getenv('OCR_CRITICAL_THRESHOLD', 25))
        
        # Warning thresholds (partial credit)
        self.avg_confidence_threshold = float(os.getenv('OCR_AVG_CONFIDENCE_THRESHOLD', 45))
        self.high_confidence_words = int(os.getenv('OCR_HIGH_CONFIDENCE_WORDS', 5))
        self.high_confidence_score = float(os.getenv('OCR_HIGH_CONFIDENCE_SCORE', 70))
        self.min_text_regions = int(os.getenv('OCR_MIN_TEXT_REGIONS', 2))
        self.min_characters = int(os.getenv('OCR_MIN_CHARACTERS', 30))
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        Preprocess image for better OCR results.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Preprocessed image as numpy array
        """
        image = cv2.imread(image_path)
        if image is None:
            return None
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Apply thresholding
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return thresh
    
    def get_ocr_data(self, image_path: str) -> Dict:
        """
        Extract OCR data with confidence scores.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with OCR results and confidence data
        """
        # Preprocess image
        processed_image = self.preprocess_image(image_path)
        if processed_image is None:
            return None
        
        # Convert to PIL Image
        pil_image = Image.fromarray(processed_image)
        
        # Get OCR data with detailed information
        ocr_data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)
        
        return ocr_data
    
    def analyze_confidence(self, ocr_data: Dict) -> Dict:
        """
        Analyze OCR confidence scores.
        
        Args:
            ocr_data: OCR data dictionary from Tesseract
            
        Returns:
            Dictionary with confidence analysis results
        """
        confidences = []
        words = []
        text_regions = set()
        character_count = 0
        
        # Extract confidence scores and text
        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            conf = int(ocr_data['conf'][i]) if ocr_data['conf'][i] != '-1' else 0
            
            if text:  # Non-empty text
                confidences.append(conf)
                words.append({
                    'text': text,
                    'confidence': conf
                })
                character_count += len(text)
                
                # Track text regions (blocks)
                block_num = ocr_data['block_num'][i]
                if block_num > 0:
                    text_regions.add(block_num)
        
        if not confidences:
            return {
                'average_confidence': 0,
                'high_confidence_words_count': 0,
                'text_regions_count': 0,
                'character_count': 0,
                'total_words': 0,
                'words': []
            }
        
        avg_confidence = np.mean(confidences)
        high_confidence_words_list = [w for w in words if w['confidence'] >= self.high_confidence_score]
        
        return {
            'average_confidence': round(avg_confidence, 2),
            'high_confidence_words_count': len(high_confidence_words_list),
            'text_regions_count': len(text_regions),
            'character_count': character_count,
            'total_words': len(words),
            'words': words[:20]  # Return first 20 words for debugging
        }
    
    def process(self, image_path: str) -> Dict:
        """
        Run OCR confidence analysis on an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with overall result and detailed analysis
        """
        # Get OCR data
        ocr_data = self.get_ocr_data(image_path)
        if ocr_data is None:
            return {
                'stage': 'Stage 2: OCR Confidence Analysis',
                'passed': False,
                'error': 'Could not process image for OCR',
                'analysis': {}
            }
        
        # Analyze confidence
        analysis = self.analyze_confidence(ocr_data)
        
        # Check for critical failure (unreadable)
        critical_failures = []
        warnings = []
        
        avg_confidence = analysis['average_confidence']
        
        # CRITICAL: OCR confidence too low (unreadable)
        # This catches documents that cannot be read (bold images, corruption, etc.)
        if avg_confidence < self.ocr_critical_threshold:
            critical_failures.append(
                f"OCR confidence too low ({avg_confidence:.1f}%) - document unreadable. "
                f"Document may be too dark, overexposed, corrupted, or have broader lines that make text unreadable."
            )
            return {
                'stage': 'Stage 2: OCR Confidence Analysis',
                'passed': False,
                'stage_score': 0,
                'critical_failures': critical_failures,
                'warnings': [],
                'analysis': analysis,
                'checks': {},
                'rejection_reasons': critical_failures
            }
        
        # Check all criteria
        checks = {
            'average_confidence': bool(avg_confidence >= self.avg_confidence_threshold),
            'high_confidence_words': bool(analysis['high_confidence_words_count'] >= self.high_confidence_words),
            'text_regions': bool(analysis['text_regions_count'] >= self.min_text_regions),
            'character_count': bool(analysis['character_count'] >= self.min_characters)
        }
        
        all_passed = bool(all(checks.values()))
        
        # Classify failures as warnings
        if not checks['average_confidence']:
            warnings.append(f"Average OCR confidence ({avg_confidence:.1f}%) below recommended ({self.avg_confidence_threshold}%)")
        if not checks['high_confidence_words']:
            warnings.append(f"Only {analysis['high_confidence_words_count']} high-confidence words found (recommended: {self.high_confidence_words})")
        if not checks['text_regions']:
            warnings.append(f"Only {analysis['text_regions_count']} text regions detected (recommended: {self.min_text_regions})")
        if not checks['character_count']:
            warnings.append(f"Only {analysis['character_count']} characters found (recommended: {self.min_characters})")
        
        # Calculate stage score with partial credit for warnings
        # Weighted score based on confidence
        confidence_score = min(avg_confidence / 100, 1.0) * 40  # 40% weight
        passed_checks = sum([bool(v) for v in checks.values()])
        other_checks_score = (passed_checks / len(checks)) * 60  # 60% weight
        weighted_score = confidence_score + other_checks_score
        
        return {
            'stage': 'Stage 2: OCR Confidence Analysis',
            'passed': all_passed,
            'stage_score': round(weighted_score, 2),
            'critical_failures': critical_failures,
            'warnings': warnings,
            'analysis': analysis,
            'checks': checks,
            'rejection_reasons': warnings if not all_passed else []
        }

