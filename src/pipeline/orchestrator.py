"""
Pipeline Orchestrator
Coordinates all stages of the document quality verification pipeline.
"""

import os
import time
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv

from src.stages.stage1_basic_quality import BasicQualityChecker
from src.stages.stage2_ocr_confidence import OCRConfidenceAnalyzer
from src.stages.stage3_handwriting_detection import HandwritingDetector
from src.stages.stage4_brisque_quality import BRISQUEQualityScorer
from src.utils.pdf_converter import PDFConverter
from src.utils.image_processor import ImageProcessor

# Optional Florence-2 integration (modular component)
try:
    from src.utils.florence_classifier import get_florence_instance
    FLORENCE_AVAILABLE = True
except ImportError:
    FLORENCE_AVAILABLE = False
    logger.warning("Florence-2 classifier not available (install torch and transformers to enable)")

load_dotenv()

# Set up logger
logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the complete document quality verification pipeline."""
    
    def __init__(self):
        """Initialize all pipeline stages."""
        self.stage1 = BasicQualityChecker()
        # Initialize Florence classifier if available (lazy loaded)
        self.florence_classifier = None
        if FLORENCE_AVAILABLE:
            try:
                self.florence_classifier = get_florence_instance()
                logger.info("Florence-2 classifier available (will load on first use)")
            except Exception as e:
                logger.warning(f"Florence-2 classifier initialization failed: {e}")
        self.stage2 = OCRConfidenceAnalyzer()
        self.stage3 = HandwritingDetector()
        self.stage4 = BRISQUEQualityScorer()
        self.pdf_converter = PDFConverter()
        self.image_processor = ImageProcessor()
    
    def calculate_final_quality_score(self, stage_results: List[Dict]) -> float:
        """
        Calculate final composite quality score.
        
        Formula:
        Quality Score = (Resolution × 0.10) +
                       (Blur × 0.15) +
                       (Brightness × 0.10) +
                       (OCR Confidence × 0.40) +
                       (Handwriting × 0.20) +
                       (BRISQUE × 0.05)
        
        Args:
            stage_results: List of stage result dictionaries
            
        Returns:
            Final quality score (0-100)
        """
        # Extract stage scores
        stage1_score = next((r.get('stage_score', 0) for r in stage_results if r.get('stage') == 'Stage 1: Basic Quality Checks'), 0)
        stage2_score = next((r.get('stage_score', 0) for r in stage_results if r.get('stage') == 'Stage 2: OCR Confidence Analysis'), 0)
        stage3_score = next((r.get('stage_score', 0) for r in stage_results if r.get('stage') == 'Stage 3: Handwriting Detection'), 0)
        stage4_score = next((r.get('stage_score', 0) for r in stage_results if r.get('stage') == 'Stage 4: Overall Quality Score (BRISQUE)'), 0)
        
        # Weighted average
        final_score = (
            stage1_score * 0.35 +  # Combined basic checks
            stage2_score * 0.40 +  # OCR confidence (most important)
            stage3_score * 0.20 +  # Handwriting detection
            stage4_score * 0.05    # BRISQUE quality
        )
        
        return round(final_score, 2)
    
    def make_consensus_decision(
        self,
        ocr_confidence: Optional[float],
        handwriting_pct: Optional[float],
        handwriting_dist: Optional[Dict],
        blur_score: Optional[float],
        resolution: Optional[tuple],
        stage1_critical: List[str],
        stage2_critical: List[str],
        stage3_critical: List[str],
        image_path: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Make consensus-based decision using all signals together.
        Handles blurry scanned documents by trusting OCR over handwriting detection.
        
        Returns:
            Status dict if consensus decision made, None if should use scoring
        """
        # Extract distribution info
        is_concentrated = handwriting_dist.get('is_concentrated', False) if handwriting_dist else False
        is_spread_out = handwriting_dist.get('is_spread_out', False) if handwriting_dist else False
        
        # ========================================
        # TRUST HIGH OCR OVER HANDWRITING DETECTION
        # ========================================
        # If OCR is very high (>= 80%), it can reliably read printed text
        # Bold text, formatting, and scanning artifacts can cause false handwriting detection
        # Trust OCR as the primary signal when it's very high
        # BUT: Always check Florence to ensure we don't accept handwritten documents
        if ocr_confidence is not None and ocr_confidence >= 80:
            # Very high OCR confidence - document is clearly readable printed text
            # Even if handwriting detection flags it (e.g., from bold text), trust OCR
            # BUT: Must verify with Florence to ensure it's not handwritten
            if handwriting_pct is not None and handwriting_pct >= 40:
                # High handwriting detection but very high OCR - likely false positive (bold text, formatting)
                # ALWAYS check Florence first - if it says handwritten, reject regardless of OCR
                florence_override = self._check_florence_override(
                    image_path, ocr_confidence, handwriting_pct
                )
                
                # SAFEGUARD: If Florence says handwritten, REJECT even if OCR is high
                # Handwritten documents can sometimes have decent OCR if very clear
                if florence_override and not florence_override.get('is_printed', True):
                    # Florence confirmed it's handwritten - reject
                    logger.warning(
                        f"High OCR ({ocr_confidence:.1f}%) but Florence confirmed HANDWRITTEN - "
                        f"rejecting document (handwriting: {handwriting_pct:.1f}%)"
                    )
                    return {
                        'status': 'REJECTED',
                        'priority': 'N/A',
                        'message': f'Document is handwritten - Florence-2 confirmed handwritten text despite high OCR confidence ({ocr_confidence:.1f}%). Only printed documents are accepted.'
                    }
                
                if florence_override and florence_override.get('is_printed'):
                    # Florence confirms printed - accept
                    logger.info(
                        f"High OCR ({ocr_confidence:.1f}%) + Florence confirmed printed - "
                        f"overriding handwriting false positive ({handwriting_pct:.1f}%)"
                    )
                    return {
                        'status': 'ACCEPTED',
                        'priority': 'Normal',
                        'message': f'Document accepted - Very high OCR confidence ({ocr_confidence:.1f}%) and Florence-2 confirmed printed text. Handwriting detection ({handwriting_pct:.1f}%) was false positive (likely bold text or formatting).',
                        'florence_override': {
                            'applied': True,
                            'is_printed': True,
                            'confidence': florence_override.get('confidence', 0),
                            'explanation': florence_override.get('explanation', '')[:200]
                        }
                    }
                else:
                    # Florence did not confirm or was not available
                    # For extremely high OCR (>= 85%), trust OCR for bold text cases
                    # BUT: Only if handwriting is not extremely high (>= 50% is suspicious)
                    if ocr_confidence >= 85 and handwriting_pct < 50:
                        logger.info(
                            f"Extremely high OCR ({ocr_confidence:.1f}%) with moderate handwriting "
                            f"({handwriting_pct:.1f}%) - trusting OCR (likely bold text false positive)"
                        )
                        return {
                            'status': 'ACCEPTED',
                            'priority': 'Normal',
                            'message': f'Document accepted - Extremely high OCR confidence ({ocr_confidence:.1f}%) indicates readable printed text. Handwriting detection ({handwriting_pct:.1f}%) is likely false positive from bold text or formatting.'
                        }
                    elif handwriting_pct >= 50:
                        # Very high handwriting (>= 50%) - even with high OCR, require Florence confirmation
                        # This is a safeguard against accepting handwritten documents
                        logger.warning(
                            f"Very high handwriting ({handwriting_pct:.1f}%) with high OCR ({ocr_confidence:.1f}%) - "
                            f"Florence did not confirm printed, rejecting to avoid false positive"
                        )
                        return {
                            'status': 'REJECTED',
                            'priority': 'N/A',
                            'message': f'Document appears handwritten ({handwriting_pct:.1f}% handwriting). Florence-2 verification required but not available or did not confirm printed text. Only printed documents are accepted.'
                        }
        
        # ========================================
        # HANDLE BLURRY SCANNED DOCUMENTS
        # ========================================
        # When document is blurry, handwriting detection is unreliable
        # Trust OCR confidence as primary signal for blurry documents
        is_blurry = blur_score is not None and blur_score < 60  # Below warning threshold
        is_very_blurry = blur_score is not None and blur_score < 30  # Critical blur
        
        # If very blurry, handwriting detection is unreliable - discount it heavily
        # Use OCR confidence as primary signal
        if is_very_blurry and ocr_confidence is not None:
            # If OCR can read it reasonably well (>= 50%), it's likely printed text
            # Blur artifacts make printed text look irregular, causing false handwriting detection
            if ocr_confidence >= 50:
                # Trust OCR - this is likely a blurry scanned printed document
                # Reject for blur, but don't reject for handwriting
                # The blur rejection will happen in stage1_critical check
                pass  # Let blur rejection happen, but ignore handwriting false positive
            elif ocr_confidence >= 30:
                # Moderate OCR confidence with blur - could be printed or handwritten
                # Don't trust handwriting detection when blur is high
                handwriting_pct = None  # Ignore handwriting detection for blurry docs
        
        # ========================================
        # CRITICAL FAILURES (No Override Allowed)
        # ========================================
        
        # Truly unreadable - OCR cannot read text
        if ocr_confidence is not None and ocr_confidence < 20:
            return {
                'status': 'REJECTED',
                'priority': 'N/A',
                'message': 'Text completely unreadable - OCR confidence too low'
            }
        
        # Clearly handwritten (high percentage) - but only if not blurry
        # Blurry documents can have false positives, so require higher threshold or good OCR
        if handwriting_pct is not None and handwriting_pct >= 40:
            # Handwriting >= 40% - likely actually handwritten
            # But if OCR is high (>= 70%), check Florence to verify (might be false positive from bold text)
            if ocr_confidence is not None and ocr_confidence >= 70:
                # Good OCR - might be false positive (bold text, formatting), check Florence
                florence_override = self._check_florence_override(
                    image_path, ocr_confidence, handwriting_pct
                )
                
                # SAFEGUARD: Check if Florence said handwritten
                if florence_override and not florence_override.get('is_printed', True):
                    # Florence confirmed handwritten - reject
                    logger.warning(
                        f"Florence confirmed HANDWRITTEN for handwriting {handwriting_pct:.1f}% - "
                        f"rejecting despite OCR: {ocr_confidence:.1f}%"
                    )
                    return {
                        'status': 'REJECTED',
                        'priority': 'N/A',
                        'message': f'Document is handwritten - Florence-2 confirmed handwritten text. Only printed documents are accepted.'
                    }
                
                if florence_override and florence_override.get('is_printed'):
                    # Florence confirms it's printed - override
                    logger.info(
                        f"Florence override: Document classified as printed "
                        f"(confidence: {florence_override.get('confidence', 0):.2f})"
                    )
                    return {
                        'status': 'ACCEPTED',
                        'priority': 'Normal',
                        'message': f'Document accepted - Florence-2 confirmed printed text (confidence: {florence_override.get("confidence", 0):.1%}). Handwriting detection was false positive (likely bold text or formatting).',
                        'florence_override': {
                            'applied': True,
                            'is_printed': True,
                            'confidence': florence_override.get('confidence', 0),
                            'explanation': florence_override.get('explanation', '')[:200]
                        }
                    }
                elif ocr_confidence >= 75:
                    # OCR is very high (>= 75%) but Florence didn't confirm
                    # Still trust OCR for bold text cases - likely false positive
                    logger.info(
                        f"Very high OCR ({ocr_confidence:.1f}%) but Florence did not confirm - "
                        f"trusting OCR over handwriting detection ({handwriting_pct:.1f}%) - likely bold text"
                    )
                    return {
                        'status': 'ACCEPTED',
                        'priority': 'Normal',
                        'message': f'Document accepted - Very high OCR confidence ({ocr_confidence:.1f}%) indicates readable printed text. Handwriting detection ({handwriting_pct:.1f}%) is likely false positive from bold text or formatting.'
                    }
                else:
                    # Florence did not confirm and OCR not high enough - reject
                    return {
                        'status': 'REJECTED',
                        'priority': 'N/A',
                        'message': f'Document is significantly handwritten ({handwriting_pct:.1f}% handwriting) - only printed documents are accepted'
                    }
            else:
                # OCR not high enough - reject without checking Florence
                return {
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Document is significantly handwritten ({handwriting_pct:.1f}% handwriting) - only printed documents are accepted'
                }
        
        # Handwriting 30-39% - check Florence if OCR is good
        if handwriting_pct is not None and handwriting_pct >= 30 and handwriting_pct < 40:
            if ocr_confidence is not None and ocr_confidence >= 60:
                # Good OCR - check Florence for false positive
                florence_override = self._check_florence_override(
                    image_path, ocr_confidence, handwriting_pct
                )
                if florence_override and florence_override.get('is_printed'):
                    # Florence confirms printed - accept
                    logger.info(
                        f"Florence override: Document classified as printed "
                        f"(confidence: {florence_override.get('confidence', 0):.2f})"
                    )
                    return {
                        'status': 'ACCEPTED',
                        'priority': 'Normal',
                        'message': f'Document accepted - Florence-2 confirmed printed text (confidence: {florence_override.get("confidence", 0):.1%}). Handwriting detection was false positive.',
                        'florence_override': {
                            'applied': True,
                            'is_printed': True,
                            'confidence': florence_override.get('confidence', 0),
                            'explanation': florence_override.get('explanation', '')[:200]
                        }
                    }
                # If Florence doesn't confirm, continue to other checks (don't reject immediately)
        
        # Handwritten + spread out (even if lower percentage) - but discount if blurry
        if (handwriting_pct is not None and handwriting_pct >= 25 and is_spread_out):
            # Spread-out handwriting is a strong indicator of actually handwritten documents
            # But if OCR is high, it might be a false positive from blur/scanning artifacts
            if handwriting_pct >= 40:
                # Very high handwriting percentage spread out - likely actually handwritten
                # Only check Florence if OCR is very high (>= 80%)
                if ocr_confidence is not None and ocr_confidence >= 80:
                    florence_override = self._check_florence_override(
                        image_path, ocr_confidence, handwriting_pct
                    )
                    if florence_override and florence_override.get('is_printed'):
                        logger.info(
                            f"Florence override: Spread handwriting is false positive "
                            f"(confidence: {florence_override.get('confidence', 0):.2f})"
                        )
                        return {
                            'status': 'ACCEPTED',
                            'priority': 'Normal',
                            'message': f'Document accepted - Florence-2 confirmed printed text (confidence: {florence_override.get("confidence", 0):.1%}). Spread handwriting detection was false positive.',
                            'florence_override': {
                                'applied': True,
                                'is_printed': True,
                                'confidence': florence_override.get('confidence', 0),
                                'explanation': florence_override.get('explanation', '')[:200]
                            }
                        }
                    else:
                        return {
                            'status': 'REJECTED',
                            'priority': 'N/A',
                            'message': f'Handwritten text throughout document ({handwriting_pct:.1f}% handwriting spread across document)'
                        }
                else:
                    return {
                        'status': 'REJECTED',
                        'priority': 'N/A',
                        'message': f'Handwritten text throughout document ({handwriting_pct:.1f}% handwriting spread across document)'
                    }
            elif ocr_confidence is not None and ocr_confidence >= 60:
                # Medium-high handwriting spread out - check Florence if OCR is good
                florence_override = self._check_florence_override(
                    image_path, ocr_confidence, handwriting_pct
                )
                if florence_override and florence_override.get('is_printed'):
                    logger.info(
                        f"Florence override: Spread handwriting is false positive "
                        f"(confidence: {florence_override.get('confidence', 0):.2f})"
                    )
                    return {
                        'status': 'ACCEPTED',
                        'priority': 'Normal',
                        'message': f'Document accepted - Florence-2 confirmed printed text (confidence: {florence_override.get("confidence", 0):.1%}). Spread handwriting detection was false positive.',
                        'florence_override': {
                            'applied': True,
                            'is_printed': True,
                            'confidence': florence_override.get('confidence', 0),
                            'explanation': florence_override.get('explanation', '')[:200]
                        }
                    }
                else:
                    return {
                        'status': 'REJECTED',
                        'priority': 'N/A',
                        'message': f'Handwritten text throughout document ({handwriting_pct:.1f}% handwriting spread across document)'
                    }
            else:
                # OCR not high enough - reject spread-out handwriting
                return {
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Handwritten text throughout document ({handwriting_pct:.1f}% handwriting spread across document)'
                }
        
        # Physically unusable - resolution or blur too poor
        if resolution is not None:
            width, height = resolution
            if width < 400 or height < 300:
                return {
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Image resolution too low ({width}x{height}) - minimum 400x300 required'
                }
        
        # Only reject for blur if OCR also confirms it's unreadable
        # If OCR can read it well, blur is acceptable (scanned documents often have lower blur scores)
        blur_extreme_threshold = float(os.getenv('BLUR_EXTREME_THRESHOLD', 15))
        
        if blur_score is not None and blur_score < 30:
            # EXTREME BLUR: Very low blur scores (< 15 by default) are always rejected
            # Even if OCR can partially read it, extreme blur makes document unreadable
            if blur_score < blur_extreme_threshold:
                return {
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Document extremely blurry (blur score: {blur_score:.1f}) - unreadable. Please rescan clearly.'
                }
            
            # MODERATE BLUR (15-30): Check OCR confidence
            # Check OCR confidence - if OCR can read it well, don't reject for blur
            if ocr_confidence is not None and ocr_confidence >= 50:
                # Document is readable despite moderate blur - accept it
                # Blur is just a warning, not a critical failure
                pass
            elif ocr_confidence is not None and ocr_confidence >= 30:
                # Moderate OCR confidence with moderate blur - may need rescanning
                # Flag for review rather than reject (user can decide)
                return {
                    'status': 'FLAG_FOR_REVIEW',
                    'priority': 'Low',
                    'message': f'Document is blurry (blur score: {blur_score:.1f}) but OCR can partially read it ({ocr_confidence:.1f}% confidence) - may need rescanning'
                }
            else:
                # Low OCR confidence + blur = truly unreadable
                return {
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Document too blurry (blur score: {blur_score:.1f}) and unreadable (OCR confidence: {ocr_confidence:.1f}%)'
                }
        
        # Any critical failures from stages (after filtering readable documents)
        all_critical = stage1_critical + stage2_critical + stage3_critical
        if len(all_critical) > 0:
            # If document is readable (OCR >= 50%), don't reject for blur/handwriting
            # BUT: Extreme blur (< 15 by default) is always rejected regardless of OCR
            blur_extreme_threshold = float(os.getenv('BLUR_EXTREME_THRESHOLD', 15))
            is_readable = ocr_confidence is not None and ocr_confidence >= 50
            is_extreme_blur = blur_score is not None and blur_score < blur_extreme_threshold
            
            if is_readable and not is_extreme_blur:
                # Check Florence for handwriting false positives BEFORE filtering
                # If Florence confirms printed, we can safely filter handwriting failures
                handwriting_critical = [f for f in all_critical if 'handwriting' in f.lower()]
                if handwriting_critical and image_path:
                    # Check Florence to verify if handwriting is false positive
                    florence_override = self._check_florence_override(
                        image_path, ocr_confidence, handwriting_pct
                    )
                    if florence_override and florence_override.get('is_printed'):
                        # Florence confirms printed - filter out handwriting failures
                        logger.info(
                            f"Florence confirmed printed (confidence: {florence_override.get('confidence', 0):.2f}) - "
                            f"filtering handwriting false positive"
                        )
                        all_critical = [
                            f for f in all_critical 
                            if 'handwriting' not in f.lower()
                        ]
                
                # Filter out blur and handwriting issues for readable documents (but not extreme blur)
                filtered_critical = [
                    f for f in all_critical 
                    if 'blur' not in f.lower() and 'blurry' not in f.lower() and 'handwriting' not in f.lower()
                ]
                if len(filtered_critical) == 0:
                    # No real critical issues - document is readable
                    return None  # Use scoring system instead
                all_critical = filtered_critical
            
            return {
                'status': 'REJECTED',
                'priority': 'N/A',
                'message': all_critical[0] if all_critical else 'Document has critical quality issues - cannot process'
            }
        
        # ========================================
        # CLEAR ACCEPTANCE (All Signals Agree)
        # ========================================
        
        # Strong printed document signals - all metrics agree
        if (ocr_confidence is not None and ocr_confidence > 80 and
            handwriting_pct is not None and handwriting_pct < 15 and
            blur_score is not None and blur_score > 100 and
            resolution is not None and resolution[0] > 800):
            return {
                'status': 'ACCEPTED',
                'priority': 'High',
                'message': 'High quality printed document - all quality checks passed'
            }
        
        # ========================================
        # SIGNATURE HANDLING (Concentrated Handwriting)
        # ========================================
        
        if (handwriting_pct is not None and handwriting_pct > 15 and 
            handwriting_pct < 30 and is_concentrated):
            
            # Concentrated handwriting = likely signatures/stamps
            # If OCR can read it (>= 30%), accept it - signatures don't affect OCR readability
            if ocr_confidence is not None and ocr_confidence >= 30:
                return {
                    'status': 'ACCEPTED',
                    'priority': 'Normal',
                    'message': f'Printed document with signatures/stamps ({handwriting_pct:.1f}% handwriting in isolated areas, OCR: {ocr_confidence:.1f}%)'
                }
            else:
                # OCR too low - might be unreadable
                return {
                    'status': 'FLAG_FOR_REVIEW',
                    'priority': 'Low',
                    'message': f'Signatures/stamps detected ({handwriting_pct:.1f}% handwriting) but OCR confidence low ({ocr_confidence:.1f}%) - needs review'
                }
        
        # ========================================
        # DISAGREEMENT ZONES (Flag for Human Review)
        # ========================================
        
        # OCR says good, handwriting detector says significant
        # BUT: If handwriting is concentrated (signatures/stamps), trust OCR and accept
        if (ocr_confidence is not None and ocr_confidence > 75 and
            handwriting_pct is not None and handwriting_pct > 25 and handwriting_pct < 40):
            # Check if handwriting is concentrated (signatures/stamps) or spread out
            if is_concentrated:
                # High OCR + concentrated handwriting = printed document with signatures/stamps
                # Trust OCR - it can read the printed text, signatures don't matter
                return {
                    'status': 'ACCEPTED',
                    'priority': 'Normal',
                    'message': f'Printed document with signatures/stamps ({handwriting_pct:.1f}% handwriting in isolated areas). High OCR confidence ({ocr_confidence:.1f}%) confirms readable printed text.'
                }
            elif is_spread_out:
                # Spread out handwriting + high OCR = conflicting signals, needs review
                return {
                    'status': 'FLAG_FOR_REVIEW',
                    'priority': 'Medium',
                    'message': f'OCR and handwriting detection disagree (OCR: {ocr_confidence:.1f}%, Handwriting: {handwriting_pct:.1f}% spread out) - needs human review'
                }
            else:
                # Distribution unclear - flag for review
                return {
                    'status': 'FLAG_FOR_REVIEW',
                    'priority': 'Medium',
                    'message': f'OCR and handwriting detection disagree (OCR: {ocr_confidence:.1f}%, Handwriting: {handwriting_pct:.1f}%) - needs human review'
                }
        
        # OCR says bad, but other quality metrics good (unusual font?)
        if (ocr_confidence is not None and ocr_confidence < 50 and
            blur_score is not None and blur_score > 150 and
            resolution is not None and resolution[0] > 1000):
            return {
                'status': 'FLAG_FOR_REVIEW',
                'priority': 'Low',
                'message': f'Low OCR confidence ({ocr_confidence:.1f}%) despite good image quality - unusual font or layout?'
            }
        
        # Handwriting detected but OCR is high (could be false positive from blur or clean handwritten)
        if (handwriting_pct is not None and handwriting_pct > 20 and
            ocr_confidence is not None and ocr_confidence > 70):
            # If document is blurry, trust OCR - blur causes false handwriting detection
            if is_blurry:
                # Blurry scanned document with high OCR = printed text, handwriting detection is wrong
                return {
                    'status': 'ACCEPTED',
                    'priority': 'Normal',
                    'message': f'Blurry scanned document - OCR confidence ({ocr_confidence:.1f}%) indicates printed text. Handwriting detection unreliable due to blur artifacts.'
                }
            # Check distribution
            if is_concentrated:
                # Concentrated handwriting + high OCR = printed document with signatures/stamps
                # Trust OCR - it can read the printed text
                return {
                    'status': 'ACCEPTED',
                    'priority': 'Normal',
                    'message': f'Printed document with signatures/stamps ({handwriting_pct:.1f}% handwriting in isolated areas). High OCR confidence ({ocr_confidence:.1f}%) confirms readable printed text.'
                }
            elif is_spread_out:
                # Spread out + high OCR = likely clean handwritten document
                return {
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Handwritten document detected ({handwriting_pct:.1f}% handwriting spread across document) despite high OCR confidence'
                }
            else:
                # Distribution unclear - but high OCR suggests printed text, accept it
                return {
                    'status': 'ACCEPTED',
                    'priority': 'Normal',
                    'message': f'High OCR confidence ({ocr_confidence:.1f}%) indicates readable printed text. Handwriting detection ({handwriting_pct:.1f}%) may be false positive.'
                }
        
        # No consensus decision - use scoring system
        return None
    
    def _check_florence_override(
        self, 
        image_path: Optional[str], 
        ocr_confidence: Optional[float], 
        handwriting_pct: Optional[float]
    ) -> Optional[Dict]:
        """
        Check if Florence-2 should override handwriting detection.
        Only called when handwriting is detected AND OCR confidence is good.
        Uses conservative thresholds to avoid false positives.
        
        Args:
            image_path: Path to image file
            ocr_confidence: OCR confidence percentage
            handwriting_pct: Handwriting percentage detected
            
        Returns:
            Florence classification result dict or None
        """
        # Only use Florence if:
        # 1. Florence is available and enabled
        # 2. Image path is provided
        # 3. OCR confidence is >= 50% (readable - lower threshold to catch more cases)
        # 4. Handwriting is detected (>= 20%)
        # 5. For higher handwriting, require higher OCR
        if (not FLORENCE_AVAILABLE or 
            not self.florence_classifier or 
            not image_path or 
            ocr_confidence is None or 
            ocr_confidence < 50 or  # Require readable OCR (50%)
            handwriting_pct is None or
            handwriting_pct < 20):
            return None
        
        # For higher handwriting percentages, require higher OCR
        # BUT: Lower thresholds to catch more false positives (bold text cases)
        if handwriting_pct >= 40:
            # Very high handwriting - check if OCR is good (>= 70% - lowered from 80%)
            # Bold text can cause high handwriting detection, so be more lenient
            if ocr_confidence < 70:
                return None
        elif handwriting_pct >= 35:
            # High handwriting - require OCR >= 65% (lowered from 70%)
            if ocr_confidence < 65:
                return None
        elif handwriting_pct >= 30:
            # Medium-high handwriting - require OCR >= 60%
            if ocr_confidence < 60:
                return None
        
        try:
            logger.info(
                f"Checking Florence override: OCR={ocr_confidence:.1f}%, "
                f"Handwriting={handwriting_pct:.1f}%"
            )
            result = self.florence_classifier.classify_document(image_path)
            
            if result.get('error'):
                logger.warning(f"Florence classification error: {result.get('error')}")
                return None
            
            # VERY CONSERVATIVE OVERRIDE: Only override if Florence is EXTREMELY confident it's printed
            # Require very high confidence (>= 0.85) to override rejection
            # Also validate OCR - handwritten documents typically have lower OCR even if readable
            florence_confidence = result.get('confidence', 0)
            is_printed = result.get('is_printed', False)
            
            if not is_printed:
                # Florence says it's handwritten - don't override, REJECT
                # This is a critical safeguard - even if OCR is high, handwritten is handwritten
                logger.warning(
                    f"Florence confirmed HANDWRITTEN (confidence: {florence_confidence:.2f}) - "
                    f"REJECTING document despite OCR: {ocr_confidence:.1f}%, Handwriting: {handwriting_pct:.1f}%"
                )
                return {
                    'is_printed': False,
                    'confidence': florence_confidence,
                    'explanation': result.get('explanation', ''),
                    'reject_reason': 'Florence-2 confirmed document is handwritten'
                }
            
            # Adjust confidence threshold based on handwriting percentage and OCR
            # Higher handwriting OR lower OCR requires higher Florence confidence
            if handwriting_pct >= 40:
                required_confidence = 0.75  # Lowered from 0.80 - be more lenient for bold text cases
            elif handwriting_pct >= 35:
                required_confidence = 0.70  # Lowered from 0.75
            elif handwriting_pct >= 30:
                required_confidence = 0.65  # Lowered from 0.70
            else:
                required_confidence = 0.60  # Lowered from 0.65
            
            # If OCR is very high (>= 80%), we can be more lenient with Florence confidence
            # This helps catch bold text false positives
            if ocr_confidence >= 80:
                required_confidence = max(0.60, required_confidence - 0.10)  # Reduce by 0.10 if OCR very high
            elif ocr_confidence >= 75:
                required_confidence = max(0.60, required_confidence - 0.05)  # Reduce by 0.05 if OCR high
            
            if florence_confidence < required_confidence:
                # Florence says printed but confidence too low - don't override
                logger.info(
                    f"Florence says printed but confidence too low ({florence_confidence:.2f} < {required_confidence:.2f}) - "
                    f"not overriding rejection"
                )
                return None
            
            # All checks passed - safe to override
            logger.info(
                f"Florence override approved: Printed (confidence: {florence_confidence:.2f}), "
                f"OCR: {ocr_confidence:.1f}%, Handwriting: {handwriting_pct:.1f}%"
            )
            return result
            
        except Exception as e:
            logger.error(f"Florence override check failed: {e}", exc_info=True)
            return None
    
    def determine_status(self, final_score: float, has_critical_failures: bool, ocr_confidence: Optional[float] = None, stage_results: Optional[List[Dict]] = None) -> Dict:
        """
        Determine document status based on final score and critical failures.
        
        Args:
            final_score: Final quality score (0-100)
            has_critical_failures: Whether any critical failures were detected
            ocr_confidence: OCR confidence percentage (optional, for leniency)
            stage_results: Stage results (optional, for extracting OCR if not provided)
            
        Returns:
            Status dictionary
        """
        # Extract OCR confidence from stage results if not provided
        if ocr_confidence is None and stage_results is not None:
            for stage_result in stage_results:
                if 'OCR Confidence Analysis' in stage_result.get('stage', ''):
                    if 'analysis' in stage_result:
                        ocr_confidence = stage_result['analysis'].get('average_confidence')
                        break
        # Reject if critical failures detected (regardless of score)
        if has_critical_failures:
            return {
                'status': 'REJECTED',
                'priority': 'N/A',
                'message': 'Document has critical quality issues - cannot process'
            }
        
        # Use scoring thresholds for decision
        score_accept = float(os.getenv('SCORE_ACCEPT_THRESHOLD', 70))
        score_review = float(os.getenv('SCORE_REVIEW_THRESHOLD', 50))
        
        # Be more lenient for clear, readable documents:
        # 1. If OCR confidence is high (>= 80%), accept even with lower scores (>= 55)
        # 2. If OCR confidence is good (>= 60%), accept with score >= 60
        # 3. Standard leniency: score within 10 points of threshold (>= 60) with no critical failures
        # This helps clear documents that might have minor scoring issues
        
        # High OCR confidence = very readable document, be lenient
        if ocr_confidence is not None and ocr_confidence >= 80:
            # Very high OCR - document is clearly readable
            if final_score >= 55 and not has_critical_failures:
                return {
                    'status': 'ACCEPTED',
                    'priority': 'High' if final_score >= 75 else 'Normal',
                    'message': f'High quality readable document (OCR: {ocr_confidence:.1f}%) - send to LLM for processing'
                }
        elif ocr_confidence is not None and ocr_confidence >= 60:
            # Good OCR - document is readable
            if final_score >= 60 and not has_critical_failures:
                return {
                    'status': 'ACCEPTED',
                    'priority': 'High' if final_score >= 85 else 'Normal',
                    'message': f'Readable document (OCR: {ocr_confidence:.1f}%) - send to LLM for processing'
                }
        
        # Standard acceptance logic
        if final_score >= score_accept or (final_score >= score_accept - 10 and not has_critical_failures):
            return {
                'status': 'ACCEPTED',
                'priority': 'High' if final_score >= 85 else 'Normal',
                'message': 'Quality acceptable - send to LLM for processing'
            }
        elif final_score >= score_review:
            return {
                'status': 'FLAG_FOR_REVIEW',
                'priority': 'Low',
                'message': 'Marginal quality - flag for manual review before processing'
            }
        else:
            return {
                'status': 'REJECTED',
                'priority': 'N/A',
                'message': 'Quality too low - do not process'
            }
    
    def process_document(self, file_path: str, temp_dir: Optional[str] = None) -> Dict:
        """
        Process a document through all pipeline stages.
        
        Args:
            file_path: Path to document (PDF or image)
            temp_dir: Temporary directory for intermediate files
            
        Returns:
            Complete pipeline result dictionary
        """
        start_time = time.time()
        stage_results = []
        all_critical_failures = []
        all_warnings = []
        
        # Determine if PDF or image
        is_pdf = self.pdf_converter.is_pdf(file_path)
        image_paths = []
        
        if is_pdf:
            # Convert PDF to images (all pages)
            if temp_dir is None:
                temp_dir = os.path.join(os.path.dirname(file_path), 'temp_images')
            
            try:
                image_paths = self.pdf_converter.convert_pdf_to_images(file_path, temp_dir)
                if not image_paths:
                    return {
                        'success': False,
                        'error': 'Failed to convert PDF to images',
                        'file_path': file_path
                    }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'PDF conversion error: {str(e)}',
                    'file_path': file_path
                }
        elif self.image_processor.is_image_file(file_path):
            image_paths = [file_path]  # Single image, treat as list for consistency
        else:
            return {
                'success': False,
                'error': 'Unsupported file format',
                'file_path': file_path
            }
        
        # Process all pages/images
        page_results = []
        best_page_result = None
        best_page_score = -1
        best_page_index = 0
        
        for page_idx, image_path in enumerate(image_paths):
            page_num = page_idx + 1
            logger.info(f"Processing page {page_num}/{len(image_paths)} of {file_path}")
            
            try:
                page_stage_results = []
                page_critical_failures = []
                page_warnings = []
                
                # Run ALL stages for this page
                # Stage 1: Basic Quality Checks
                try:
                    stage1_result = self.stage1.process(image_path)
                    page_stage_results.append(stage1_result)
                    page_critical_failures.extend(stage1_result.get('critical_failures', []))
                    page_warnings.extend(stage1_result.get('warnings', []))
                except Exception as e:
                    page_stage_results.append({
                        'stage': 'Stage 1: Basic Quality Checks',
                        'passed': False,
                        'error': str(e),
                        'critical_failures': [],
                        'warnings': []
                    })
                
                # Stage 2: OCR Confidence Analysis
                try:
                    stage2_result = self.stage2.process(image_path)
                    page_stage_results.append(stage2_result)
                    page_critical_failures.extend(stage2_result.get('critical_failures', []))
                    page_warnings.extend(stage2_result.get('warnings', []))
                except Exception as e:
                    page_stage_results.append({
                        'stage': 'Stage 2: OCR Confidence Analysis',
                        'passed': False,
                        'error': str(e),
                        'critical_failures': [],
                        'warnings': []
                    })
                
                # Stage 3: Handwriting Detection
                try:
                    stage3_result = self.stage3.process(image_path)
                    page_stage_results.append(stage3_result)
                    page_critical_failures.extend(stage3_result.get('critical_failures', []))
                    page_warnings.extend(stage3_result.get('warnings', []))
                except Exception as e:
                    page_stage_results.append({
                        'stage': 'Stage 3: Handwriting Detection',
                        'passed': False,
                        'error': str(e),
                        'critical_failures': [],
                        'warnings': []
                    })
                
                # Stage 4: BRISQUE Quality Score
                try:
                    stage4_result = self.stage4.process(image_path)
                    page_stage_results.append(stage4_result)
                    page_critical_failures.extend(stage4_result.get('critical_failures', []))
                    page_warnings.extend(stage4_result.get('warnings', []))
                except Exception as e:
                    page_stage_results.append({
                        'stage': 'Stage 4: Overall Quality Score (BRISQUE)',
                        'passed': False,
                        'error': str(e),
                        'critical_failures': [],
                        'warnings': []
                    })
                
                # Extract metrics for this page
                page_stage1_result = next((r for r in page_stage_results if 'Basic Quality Checks' in r.get('stage', '')), None)
                page_stage2_result = next((r for r in page_stage_results if 'OCR Confidence Analysis' in r.get('stage', '')), None)
                page_stage3_result = next((r for r in page_stage_results if 'Handwriting Detection' in r.get('stage', '')), None)
                page_stage4_result = next((r for r in page_stage_results if 'BRISQUE' in r.get('stage', '')), None)
                
                page_ocr_confidence = None
                page_handwriting_pct = None
                page_handwriting_dist = None
                page_blur_score = None
                page_resolution = None
                
                if page_stage2_result and 'analysis' in page_stage2_result:
                    page_ocr_confidence = page_stage2_result['analysis'].get('average_confidence')
                
                if page_stage3_result and 'analysis' in page_stage3_result:
                    page_handwriting_analysis = page_stage3_result['analysis']
                    page_handwriting_pct = page_handwriting_analysis.get('handwriting_percentage')
                    page_handwriting_dist = page_handwriting_analysis.get('distribution', {})
                
                if page_stage1_result and 'checks' in page_stage1_result:
                    checks = page_stage1_result['checks']
                    if 'blur_details' in checks:
                        page_blur_score = checks['blur_details'].get('blur_score')
                    if 'resolution_details' in checks:
                        res_details = checks['resolution_details']
                        page_resolution = (res_details.get('width', 0), res_details.get('height', 0))
                
                # Filter blur and handwriting false positives for this page
                page_is_very_blurry = page_blur_score is not None and page_blur_score < 30
                page_blur_extreme_threshold = float(os.getenv('BLUR_EXTREME_THRESHOLD', 15))
                page_is_extreme_blur = page_blur_score is not None and page_blur_score < page_blur_extreme_threshold
                page_is_readable = page_ocr_confidence is not None and page_ocr_confidence >= 50
                
                if page_is_readable and not page_is_extreme_blur:
                    # Document is readable and not extremely blurry - remove blur critical failures
                    blur_critical_failures = [
                        f for f in page_stage1_result.get('critical_failures', []) 
                        if 'blur' in f.lower() or 'blurry' in f.lower()
                    ]
                    if blur_critical_failures:
                        page_critical_failures = [
                            f for f in page_critical_failures 
                            if f not in blur_critical_failures
                        ]
                        if page_stage1_result:
                            page_stage1_result['critical_failures'] = [
                                f for f in page_stage1_result.get('critical_failures', [])
                                if f not in blur_critical_failures
                            ]
                            if 'warnings' not in page_stage1_result:
                                page_stage1_result['warnings'] = []
                            warning_msg = f'Document is slightly blurry (blur score: {page_blur_score:.1f}) but readable (OCR: {page_ocr_confidence:.1f}%)'
                            page_stage1_result['warnings'].append(warning_msg)
                            page_warnings.append(warning_msg)
                    
                    # Also remove handwriting false positives when document is readable
                    if page_is_very_blurry:
                        handwriting_critical_failures = [
                            f for f in page_stage3_result.get('critical_failures', []) 
                            if 'handwriting' in f.lower()
                        ]
                        if handwriting_critical_failures:
                            page_critical_failures = [
                                f for f in page_critical_failures 
                                if f not in handwriting_critical_failures
                            ]
                            if page_stage3_result:
                                page_stage3_result['critical_failures'] = [
                                    f for f in page_stage3_result.get('critical_failures', [])
                                    if f not in handwriting_critical_failures
                                ]
                                if 'warnings' not in page_stage3_result:
                                    page_stage3_result['warnings'] = []
                                warning_msg = f'Handwriting detection unreliable due to blur (blur score: {page_blur_score:.1f}). OCR confidence ({page_ocr_confidence:.1f}%) confirms printed text.'
                                page_stage3_result['warnings'].append(warning_msg)
                                page_warnings.append(warning_msg)
                
                # CONSENSUS-BASED DECISION LOGIC for this page
                consensus_status = self.make_consensus_decision(
                    ocr_confidence=page_ocr_confidence,
                    handwriting_pct=page_handwriting_pct,
                    handwriting_dist=page_handwriting_dist,
                    blur_score=page_blur_score,
                    resolution=page_resolution,
                    stage1_critical=page_stage1_result.get('critical_failures', []) if page_stage1_result else [],
                    stage2_critical=page_stage2_result.get('critical_failures', []) if page_stage2_result else [],
                    stage3_critical=page_stage3_result.get('critical_failures', []) if page_stage3_result else [],
                    image_path=image_path  # Pass image path for Florence override
                )
                
                # Extract Florence override info if present
                florence_info = None
                if consensus_status:
                    florence_info = consensus_status.get('florence_override')
                
                # Calculate final quality score for this page
                page_final_score = self.calculate_final_quality_score(page_stage_results)
                page_has_critical_failures = len(page_critical_failures) > 0
                
                # If consensus logic didn't make a decision, use scoring system
                if consensus_status is None:
                    page_status_info = self.determine_status(page_final_score, page_has_critical_failures, page_ocr_confidence, page_stage_results)
                else:
                    page_status_info = consensus_status.copy()
                    if page_status_info['status'] == 'REJECTED':
                        page_has_critical_failures = True
                
                # Store page result
                page_result = {
                    'page_number': page_num,
                    'total_pages': len(image_paths),
                    'final_quality_score': page_final_score,
                    'has_critical_failures': page_has_critical_failures,
                    'critical_failures': page_critical_failures,
                    'warnings': page_warnings,
                    'status': page_status_info['status'],
                    'priority': page_status_info['priority'],
                    'message': page_status_info['message'],
                    'ocr_confidence': page_ocr_confidence,
                    'handwriting_percentage': page_handwriting_pct,
                    'stage_results': page_stage_results
                }
                
                # Add Florence override info if available
                if florence_info:
                    page_result['florence_override'] = florence_info
                
                page_results.append(page_result)
                
                # Track best page with special rules:
                # - 1-page document: Use page 1
                # - 2-page document: Always use page 2 (content is typically on page 2)
                # - 3+ page document: Use best page (highest score, no critical failures preferred)
                
                # Special handling for 2-page documents: prioritize page 2
                if len(image_paths) == 2:
                    if page_num == 2:
                        # For 2-page documents, always use page 2 as the primary page
                        best_page_score = page_final_score
                        best_page_result = page_result
                        best_page_index = page_idx
                    # For page 1 of 2-page document, skip (page 2 will be used)
                elif len(image_paths) == 1:
                    # For 1-page documents, use page 1
                    if page_num == 1:
                        best_page_score = page_final_score
                        best_page_result = page_result
                        best_page_index = page_idx
                else:
                    # For 3+ page documents, use best page logic
                    if not page_has_critical_failures:
                        # This page has no critical failures
                        if best_page_result is None or best_page_result['has_critical_failures']:
                            # First page without failures, or previous best had failures
                            best_page_score = page_final_score
                            best_page_result = page_result
                            best_page_index = page_idx
                        elif page_final_score > best_page_score:
                            # Both have no failures, use higher score
                            best_page_score = page_final_score
                            best_page_result = page_result
                            best_page_index = page_idx
                    else:
                        # This page has critical failures
                        if best_page_result is None:
                            # First page processed, use it as best for now
                            best_page_score = page_final_score
                            best_page_result = page_result
                            best_page_index = page_idx
                        elif best_page_result['has_critical_failures'] and page_final_score > best_page_score:
                            # Both have failures, use higher score
                            best_page_score = page_final_score
                            best_page_result = page_result
                            best_page_index = page_idx
            except Exception as e:
                # If a page fails to process, log error and continue with other pages
                logger.error(f"Error processing page {page_num} of {file_path}: {str(e)}", exc_info=True)
                page_results.append({
                    'page_number': page_num,
                    'total_pages': len(image_paths),
                    'final_quality_score': 0,
                    'has_critical_failures': True,
                    'critical_failures': [f'Error processing page {page_num}: {str(e)}'],
                    'warnings': [],
                    'status': 'REJECTED',
                    'priority': 'N/A',
                    'message': f'Failed to process page {page_num}',
                    'ocr_confidence': None,
                    'handwriting_percentage': None,
                    'stage_results': []
                })
        
        # Ensure we have a best page result
        if best_page_result is None and page_results:
            # Fallback: use page with highest score
            best_page_result = max(page_results, key=lambda x: x['final_quality_score'])
            best_page_index = page_results.index(best_page_result)
        
        # Aggregate results from all pages
        all_critical_failures = []
        all_warnings = []
        stage_results = []
        
        # Use best page's stage results for main display
        if best_page_result:
            stage_results = best_page_result['stage_results']
            all_critical_failures = best_page_result['critical_failures']
            all_warnings = best_page_result['warnings']
        
        # Extract metrics from best page
        stage1_result = next((r for r in stage_results if 'Basic Quality Checks' in r.get('stage', '')), None)
        stage2_result = next((r for r in stage_results if 'OCR Confidence Analysis' in r.get('stage', '')), None)
        stage3_result = next((r for r in stage_results if 'Handwriting Detection' in r.get('stage', '')), None)
        stage4_result = next((r for r in stage_results if 'BRISQUE' in r.get('stage', '')), None)
        
        ocr_confidence = None
        handwriting_pct = None
        handwriting_dist = None
        blur_score = None
        resolution = None
        
        if stage2_result and 'analysis' in stage2_result:
            ocr_confidence = stage2_result['analysis'].get('average_confidence')
        
        if stage3_result and 'analysis' in stage3_result:
            handwriting_analysis = stage3_result['analysis']
            handwriting_pct = handwriting_analysis.get('handwriting_percentage')
            handwriting_dist = handwriting_analysis.get('distribution', {})
        
        if stage1_result and 'checks' in stage1_result:
            checks = stage1_result['checks']
            if 'blur_details' in checks:
                blur_score = checks['blur_details'].get('blur_score')
            if 'resolution_details' in checks:
                res_details = checks['resolution_details']
                resolution = (res_details.get('width', 0), res_details.get('height', 0))
        
        # Final decision based on best page
        final_score = best_page_result['final_quality_score'] if best_page_result else 0
        has_critical_failures = best_page_result['has_critical_failures'] if best_page_result else True
        status_info = {
            'status': best_page_result['status'] if best_page_result else 'REJECTED',
            'priority': best_page_result['priority'] if best_page_result else 'N/A',
            'message': best_page_result['message'] if best_page_result else 'All pages failed quality checks'
        }
        
        # If multiple pages, update message to indicate which page was used
        if len(image_paths) == 2:
            # For 2-page documents, always check page 2 (content page)
            if best_page_result and best_page_result['page_number'] == 2:
                if status_info['status'] == 'ACCEPTED':
                    status_info['message'] = f"Document accepted based on page 2 (content page). {status_info['message']}"
                else:
                    status_info['message'] = f"Document evaluated based on page 2 (content page). {status_info['message']}"
            else:
                # Fallback if page 2 wasn't processed
                status_info['message'] = f"Document evaluated based on page {best_page_result['page_number'] if best_page_result else 1}. {status_info['message']}"
        elif len(image_paths) > 2:
            # For 3+ page documents, use best page logic
            if status_info['status'] == 'ACCEPTED':
                status_info['message'] = f"Document accepted based on page {best_page_result['page_number']} (best quality). {status_info['message']}"
            else:
                # Check if any page passed
                passed_pages = [p for p in page_results if p['status'] == 'ACCEPTED']
                if passed_pages:
                    status_info['status'] = 'ACCEPTED'
                    status_info['priority'] = 'Normal'
                    status_info['message'] = f"Document accepted - {len(passed_pages)} page(s) passed quality checks (out of {len(image_paths)} total)"
                else:
                    status_info['message'] = f"All {len(image_paths)} pages failed quality checks. Best page: {best_page_result['page_number']}"
        
        processing_time = round(time.time() - start_time, 2)
        
        # Check if any page had Florence override
        florence_override_used = False
        florence_override_info = None
        for page_result in page_results:
            if page_result.get('florence_override'):
                florence_override_used = True
                florence_override_info = page_result.get('florence_override')
                break  # Use first override found
        
        result = {
            'success': True,
            'file_path': file_path,
            'file_type': 'PDF' if is_pdf else 'Image',
            'total_pages': len(image_paths),
            'processing_time_seconds': processing_time,
            'final_quality_score': final_score,
            'has_critical_failures': has_critical_failures,
            'critical_failures': all_critical_failures,
            'warnings': all_warnings,
            'status': status_info['status'],
            'priority': status_info['priority'],
            'message': status_info['message'],
            'rejection_reasons': all_critical_failures + all_warnings if status_info['status'] != 'ACCEPTED' else [],
            'stage_results': stage_results,
            'page_results': page_results,  # Results for each page
            'best_page': best_page_result['page_number'] if best_page_result else 1
        }
        
        # Add Florence override info if used
        if florence_override_used and florence_override_info:
            result['florence_override'] = florence_override_info
        
        return result

