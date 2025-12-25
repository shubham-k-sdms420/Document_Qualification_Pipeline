"""
Index-II Document Detector
Detects Maharashtra Index-II property registration documents by analyzing content.
Does NOT rely on filenames - uses OCR text, visual structure, and barcode detection.
"""

import pytesseract
from PIL import Image
import cv2
import numpy as np
import logging
from typing import Dict, List, Optional
import os

logger = logging.getLogger(__name__)

# Import PDF converter for handling PDF files
try:
    from src.utils.pdf_converter import PDFConverter
    PDF_CONVERTER_AVAILABLE = True
except ImportError:
    PDF_CONVERTER_AVAILABLE = False

# Check if pyzbar is available for barcode decoding
try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False


class Index2Detector:
    """
    Detects if a document is an Index-II property registration document.
    Uses content-based detection (text markers, visual structure, AI analysis).
    """
    
    def __init__(self):
        """Initialize Index-II detector."""
        self.use_barcode_lib = PYZBAR_AVAILABLE
        if not PYZBAR_AVAILABLE:
            logger.warning("pyzbar not installed - barcode decoding disabled. Install with: pip install pyzbar")
        
        self.current_image_path = None  # Store for negative signal check
        
        # Initialize PDF converter for handling PDF files
        self.pdf_converter = None
        if PDF_CONVERTER_AVAILABLE:
            self.pdf_converter = PDFConverter()
        
        # CRITICAL MARKERS - UNIQUE to Index-II documents only
        # These should ONLY appear in Index-II documents
        self.critical_markers = {
            'सूची क्र.2': 'Index-II header (Marathi)',
            'सूची क्र.२': 'Index-II header variant',
            'index-ii': 'Index-II header (English)',
            'index ii': 'Index-II header variant',
            'regn:63m': 'Registration type 63m',
            'regn.63m': 'Registration type variant',
            'regn:63': 'Registration type partial',
            'दुय्यम निबंधक': 'Sub-Registrar (Marathi)',
            'गावाचे नाव': 'Village name field (Index-II specific)',
            'विलेखाचा प्रकार': 'Deed type field (Index-II specific)',
            'बाजारभाव': 'Market value field (Index-II specific)',
        }
        
        # STRONG MARKERS - Common in property documents but not unique
        self.strong_markers = {
            'sub-registrar class': 'Sub-Registrar with class designation',
            'joint sub-registrar': 'Joint Sub-Registrar',
            'मोबदला': 'Consideration amount',
            'भू-मापन': 'Land measurement',
            'पालिकेचे नाव': 'Municipal corporation name',
            'हवेली': 'Haveli (with context)',  # Only if with sub-registrar
        }
        
        # SUPPORTING MARKERS - help but not decisive
        # REMOVED generic markers like "पुणे", "pune", "maharashtra" 
        # These appear in ALL government documents!
        self.supporting_markers = {
            'stamp duty': 'Stamp duty',
            'registration fee': 'Registration fee',
            'echallan': 'E-challan payment',
        }
        
        # NEGATIVE MARKERS - indicate it's NOT Index-II
        self.negative_markers = {
            # NOC/No Dues markers
            'no objection': 'NOC certificate',
            'no objection certificate': 'NOC certificate full',
            'noc': 'NOC abbreviation',
            'no dues': 'No Dues certificate',
            'no dues certificate': 'No Dues certificate full',
            'clearance certificate': 'Clearance certificate',
            'non encumbrance': 'Non-encumbrance certificate',
            'bonafide certificate': 'Bonafide certificate',
            'property tax': 'Property tax receipt (not Index-II)',
            'tax receipt': 'Tax receipt (not Index-II)',
            # NEW: Agreement/Will/Testament markers
            'deed of assignment': 'Assignment deed',
            'assignment': 'Assignment document',
            'deed of transfer': 'Transfer deed',
            'agreement': 'Agreement document',
            'sale agreement': 'Sale agreement',
            'purchase agreement': 'Purchase agreement',
            'agreement to sell': 'Sale agreement',
            'will': 'Testament/Will',
            'testament': 'Testament document',
            'testator': 'Will document',
            'executor': 'Will document',
            'bequeath': 'Will document',
            'bequeathed': 'Will document',
            'vendor': 'Sale deed',
            'purchaser': 'Purchase deed',
            'assignor': 'Assignment deed',
            'assignee': 'Assignment deed',
            'transferor': 'Transfer deed',
            'transferee': 'Transfer deed',
            'power of attorney': 'Power of attorney (not Index-II)',
            'poa': 'Power of attorney',
        }
    
    def _convert_pdf_to_image(self, pdf_path: str) -> Optional[str]:
        """
        Convert PDF to image (first page only for detection).
        Returns path to converted image or None if conversion fails.
        """
        try:
            if not self.pdf_converter:
                return None
            
            # Create temp directory for converted image
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix='index2_detection_')
            
            # Convert first page only (for speed)
            image_paths = self.pdf_converter.convert_pdf_to_images(pdf_path, temp_dir, first_page_only=True)
            
            if image_paths and len(image_paths) > 0:
                return image_paths[0]
            return None
            
        except Exception as e:
            logger.warning(f"PDF conversion failed: {e}")
            return None
    
    def is_index2_document(self, image_path: str) -> Dict:
        """
        Check if document is Index-II based on content analysis.
        Uses multi-layered detection: text markers, visual structure, barcodes.
        Handles both PDF and image files.
        
        Args:
            image_path: Path to the image or PDF file
            
        Returns:
            dict: {
                'is_index2': bool,
                'confidence': float (0-1),
                'indicators_found': list,
                'detection_method': str
            }
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Detecting Index-II for: {os.path.basename(image_path)}")
            logger.info(f"{'='*60}")
            
            # CRITICAL: Initialize filename_negative_signals FIRST before any conditional checks
            # Python treats variables assigned anywhere in function as local, so must initialize early
            filename_negative_signals = []
            try:
                filename_negative_signals = self._check_filename_negative_signals(image_path)
                if filename_negative_signals:
                    logger.warning(f"⚠ Filename indicates NOC/No Dues document - checking content to confirm")
            except Exception as e:
                logger.debug(f"Filename negative signal check failed: {e}")
                filename_negative_signals = []  # Ensure it's still a list even on error
            
            # Check if file is PDF and convert to image if needed
            actual_image_path = image_path
            is_pdf = image_path.lower().endswith('.pdf')
            temp_image_path = None
            
            if is_pdf:
                logger.info("File is PDF - converting first page to image for detection")
                temp_image_path = self._convert_pdf_to_image(image_path)
                if temp_image_path:
                    actual_image_path = temp_image_path
                    logger.info(f"PDF converted to image: {actual_image_path}")
                else:
                    logger.warning("Failed to convert PDF to image - detection may fail")
                    # Continue with PDF path, but it will likely fail
            
            # Store image path for negative signal check (needed in confidence calculation)
            self.current_image_path = actual_image_path
            
            # Method 1: Text content markers (most reliable)
            text_indicators = self._check_text_content(actual_image_path)
            
            # Method 2: Visual structure (barcode, seals, layout)
            visual_indicators = self._check_visual_structure(actual_image_path)
            
            # CRITICAL CHECK: Early handwriting detection - extract text FIRST
            # Index-II documents are ALWAYS printed, so if OCR extracts very little, it's NOT Index-II
            extracted_text = self._extract_text_robust(actual_image_path)
            text_length = len(extracted_text.strip())
            
            # NEW: Early handwriting detection - reject immediately if very little text
            if text_length < 100:
                # Very little text - likely handwritten
                logger.warning(f"⚠ Very little text extracted ({text_length} chars) - likely handwritten document")
                logger.warning("⚠ Index-II documents are always printed - rejecting early based on insufficient text")
                return {
                    'is_index2': False,
                    'confidence': 0.0,
                    'indicators_found': [],
                    'detection_method': 'early_handwriting_detection',
                    'text_indicators_count': 0,
                    'visual_indicators_count': 0,
                    'reason': 'Very little text extracted - likely handwritten document. Index-II documents are always printed.'
                }
            
            has_readable_text = text_length >= 50  # At least 50 characters for further processing
            
            # Log what we found
            logger.info(f"Detection results:")
            logger.info(f"  Text indicators: {len(text_indicators)}")
            logger.info(f"  Extracted text length: {len(extracted_text.strip())} characters")
            if text_indicators:
                for ind in text_indicators[:5]:  # Show first 5
                    logger.info(f"    - {ind['marker']} ({ind['type']})")
            logger.info(f"  Visual indicators: {len(visual_indicators)}")
            if visual_indicators:
                for ind in visual_indicators[:5]:  # Show first 5
                    logger.info(f"    - {ind['marker']} ({ind.get('type', 'VISUAL')})")
            
            # Calculate confidence (no Florence for speed)
            # Pass filename negative signals to confidence calculation (as fallback only)
            # filename_negative_signals is already initialized as empty list, so it's always defined
            confidence = self._calculate_confidence(text_indicators, visual_indicators, filename_negative_signals)
            
            # THRESHOLD: 0.60 (must have strong evidence, not just barcode/seal)
            is_index2 = confidence >= 0.60
            
            # Determine primary detection method
            detection_method = self._determine_method(text_indicators, visual_indicators)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"RESULT: is_index2={is_index2}, confidence={confidence:.2f}")
            logger.info(f"Method: {detection_method}")
            logger.info(f"Text markers: {len(text_indicators)}, Visual markers: {len(visual_indicators)}")
            logger.info(f"{'='*60}\n")
            
            result = {
                'is_index2': is_index2,
                'confidence': round(confidence, 3),
                'indicators_found': text_indicators + visual_indicators,
                'detection_method': detection_method,
                'text_indicators_count': len(text_indicators),
                'visual_indicators_count': len(visual_indicators)
            }
            
            # Clean up temporary image file if PDF was converted
            if 'temp_image_path' in locals() and temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                    # Also remove temp directory if empty
                    temp_dir = os.path.dirname(temp_image_path)
                    if os.path.exists(temp_dir):
                        try:
                            os.rmdir(temp_dir)
                        except:
                            pass  # Directory not empty, leave it
                except:
                    pass  # Cleanup failed, continue
            
            return result
            
        except Exception as e:
            logger.error(f"Index-II detection failed: {e}", exc_info=True)
            
            # Clean up temporary image file if PDF was converted
            if 'temp_image_path' in locals() and temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                    temp_dir = os.path.dirname(temp_image_path)
                    if os.path.exists(temp_dir):
                        try:
                            os.rmdir(temp_dir)
                        except:
                            pass
                except:
                    pass
            
            return {
                'is_index2': False,
                'confidence': 0.0,
                'indicators_found': [],
                'detection_method': 'error',
                'text_indicators_count': 0,
                'visual_indicators_count': 0,
                'error': str(e)
            }
    
    def _extract_text_robust(self, image_path: str) -> str:
        """
        Enhanced OCR with multiple attempts for better Marathi extraction.
        """
        texts = []
        
        try:
            img = Image.open(image_path)
            
            # Method 1: Direct OCR with all languages
            try:
                text1 = pytesseract.image_to_string(
                    img, 
                    lang='eng+hin+mar',
                    config='--psm 6'  # Assume uniform block of text
                )
                if text1.strip():
                    texts.append(text1)
            except Exception as e:
                logger.debug(f"OCR method 1 failed: {e}")
            
            # Method 2: Preprocess for better contrast, then OCR
            try:
                cv_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
                if cv_img is not None:
                    # Increase contrast
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                    enhanced = clahe.apply(cv_img)
                    # Threshold
                    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    
                    pil_enhanced = Image.fromarray(thresh)
                    text2 = pytesseract.image_to_string(
                        pil_enhanced,
                        lang='eng+hin+mar',
                        config='--psm 3'  # Fully automatic page segmentation
                    )
                    if text2.strip():
                        texts.append(text2)
            except Exception as e:
                logger.debug(f"OCR method 2 failed: {e}")
            
            # Method 3: REMOVED - redundant with header extraction in _extract_critical_markers_from_header
            # Header extraction already covers top section, so this is unnecessary
            
            # Fallback: Try with fewer languages
            if not texts:
                try:
                    text_fallback = pytesseract.image_to_string(img, lang='eng+hin')
                    if text_fallback.strip():
                        texts.append(text_fallback)
                except:
                    try:
                        text_fallback = pytesseract.image_to_string(img, lang='eng')
                        if text_fallback.strip():
                            texts.append(text_fallback)
                    except:
                        pass
            
            # Combine all extracted texts
            combined_text = '\n'.join(texts)
            
            # Log extracted text for debugging (first 500 chars)
            if combined_text:
                logger.debug(f"Extracted text (first 500 chars): {combined_text[:500]}")
            else:
                logger.warning("No text extracted from document - OCR may have failed")
            
            return combined_text
            
        except Exception as e:
            logger.warning(f"Robust text extraction failed: {e}")
            return ""
    
    def _extract_critical_markers_from_header(self, image_path: str) -> List[Dict]:
        """
        NEW: Targeted extraction of Index-II markers from header region.
        Uses aggressive preprocessing to extract "सूची क्र.2", "regn:63m", etc.
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return []
            
            height, width = img.shape[:2]
            
            # Focus on top 25% of document (where Index-II markers appear)
            header_region = img[0:int(height*0.25), :]
            
            # Aggressive preprocessing for Marathi text
            gray = cv2.cvtColor(header_region, cv2.COLOR_BGR2GRAY)
            
            # Multiple preprocessing attempts
            preprocessed_images = []
            
            # Method 1: High contrast
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            preprocessed_images.append(enhanced)
            
            # Method 2: Binary threshold
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            preprocessed_images.append(binary)
            
            # Method 3: Inverted binary
            _, inv_binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            preprocessed_images.append(inv_binary)
            
            # Method 4: Adaptive threshold
            adaptive = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            preprocessed_images.append(adaptive)
            
            # Try OCR on each preprocessed version
            found_markers = []
            # FULL Index-II markers only - no partial/ambiguous matches
            # REMOVED: 'सूची', 'क्र', 'निबंधक' - too generic (appear in agreements/wills)
            critical_patterns = [
                'सूची क्र.2', 'सूची क्र.२',  # Full Index-II header
                'index-ii', 'index ii', 'index-2',  # English Index-II
                'regn:63m', 'regn.63m', 'regn 63m', 'regn:63',  # Registration type
                'दुय्यम निबंधक',  # Sub-Registrar (full phrase)
                'गावाचे नाव', 'विलेखाचा प्रकार', 'बाजारभाव',  # Index-II specific fields
                'सब रजिस्ट्रार', 'उप निबंधक'  # Alternative registrar terms
            ]
            
            for idx, preprocessed in enumerate(preprocessed_images):
                try:
                    pil_img = Image.fromarray(preprocessed)
                    
                    # Try with reduced PSM modes for speed (optimized from [6,7,8,11] to [6,7])
                    for psm in [6, 7]:  # Reduced PSM modes for faster processing
                        text = pytesseract.image_to_string(
                            pil_img,
                            lang='eng+hin+mar',
                            config=f'--psm {psm}'
                        )
                        
                        text_lower = text.lower()
                        
                        # Check for critical patterns
                        for pattern in critical_patterns:
                            pattern_lower = pattern.lower()
                            if pattern_lower in text_lower or pattern in text:
                                # Avoid duplicates
                                if not any(m['marker'] == pattern for m in found_markers):
                                    found_markers.append({
                                        'marker': pattern,
                                        'type': 'CRITICAL',
                                        'description': f'Index-II marker (header extraction method {idx}, PSM {psm})',
                                        'weight': 2.0
                                    })
                                    logger.info(f"✓ Found CRITICAL marker in header: {pattern} (method {idx}, PSM {psm})")
                
                except Exception as e:
                    logger.debug(f"Header OCR method {idx} failed: {e}")
                    continue
            
            return found_markers
            
        except Exception as e:
            logger.warning(f"Header extraction failed: {e}")
            return []
    
    def _check_text_content(self, image_path: str) -> List[Dict]:
        """
        Extract text and look for Index-II specific markers.
        Enhanced with robust OCR for better Marathi extraction.
        Now includes targeted header extraction when standard OCR fails.
        """
        try:
            # Use robust text extraction
            text = self._extract_text_robust(image_path)
            text_lower = text.lower()
            
            indicators_found = []
            
            # Check CRITICAL markers - UNIQUE to Index-II only
            for marker, description in self.critical_markers.items():
                # Check both original and lowercase
                # Also check if marker appears as part of a word (for OCR errors)
                marker_lower = marker.lower()
                if (marker in text or marker_lower in text_lower or 
                    any(marker_lower in word.lower() for word in text.split() if len(word) > 3)):
                    indicators_found.append({
                        'marker': marker,
                        'type': 'CRITICAL',
                        'description': description,
                        'weight': 2.0  # Very strong - definitive proof
                    })
                    logger.info(f"✓ Found CRITICAL marker: {marker}")
            
            # Also check for partial matches (OCR might miss some characters)
            # Check for "सूची" and "क्र" separately (OCR might split them)
            if 'सूची' in text or 'सूची' in text_lower:
                if 'क्र' in text or 'क्र' in text_lower or '2' in text or 'ii' in text_lower:
                    # Found both parts - likely Index-II
                    indicators_found.append({
                        'marker': 'सूची + क्र.2 (partial match)',
                        'type': 'CRITICAL',
                        'description': 'Index-II header (partial OCR match)',
                        'weight': 1.8  # Slightly lower but still strong
                    })
                    logger.info(f"✓ Found CRITICAL marker (partial): सूची + क्र.2")
            
            # Check for "regn" variations (OCR might miss colon or have spacing)
            if 'regn' in text_lower:
                # Check if followed by numbers (63, 63m, etc.)
                import re
                regn_pattern = r'regn[:\s\.]*63[mM]?'
                if re.search(regn_pattern, text_lower):
                    indicators_found.append({
                        'marker': 'regn:63m (pattern match)',
                        'type': 'CRITICAL',
                        'description': 'Registration type (pattern match)',
                        'weight': 1.8
                    })
                    logger.info(f"✓ Found CRITICAL marker (pattern): regn:63m")
            
            # If no critical markers found, try targeted header extraction
            if not any(ind['type'] == 'CRITICAL' for ind in indicators_found):
                logger.info("No critical markers in standard OCR - trying targeted header extraction...")
                header_markers = self._extract_critical_markers_from_header(image_path)
                indicators_found.extend(header_markers)
            
            # Check STRONG markers
            for marker, description in self.strong_markers.items():
                if marker in text or marker.lower() in text_lower:
                    indicators_found.append({
                        'marker': marker,
                        'type': 'STRONG',
                        'description': description,
                        'weight': 0.6
                    })
                    logger.info(f"✓ Found STRONG marker: {marker}")
            
            # Check SUPPORTING markers
            for marker, description in self.supporting_markers.items():
                if marker.lower() in text_lower:
                    indicators_found.append({
                        'marker': marker,
                        'type': 'SUPPORTING',
                        'description': description,
                        'weight': 0.3
                    })
                    logger.debug(f"✓ Found SUPPORTING marker: {marker}")
            
            return indicators_found
            
        except Exception as e:
            logger.warning(f"Text content check failed: {e}")
            return []
    
    def _check_visual_structure(self, image_path: str) -> List[Dict]:
        """
        IMPROVED visual detection - should work even if OCR fails.
        Checks for barcodes, seals, table structure, and stamps.
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return []
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape
            indicators_found = []
            
            # 1. BARCODE DETECTION - but only in TOP section
            top_section = gray[0:int(height*0.15), :]  # Only top 15%
            
            # Method A: Edge detection for vertical lines
            edges = cv2.Canny(top_section, 30, 100)
            vertical_projection = np.sum(edges, axis=0)
            
            if len(vertical_projection) > 0:
                # Barcode has distinct peaks
                mean_proj = np.mean(vertical_projection)
                std_proj = np.std(vertical_projection)
                peaks = vertical_projection > (mean_proj + 2 * std_proj)
                peak_count = np.sum(peaks)
                
                # BARCODE must have many peaks in TOP section specifically
                # Added upper limit to avoid noise
                if 20 < peak_count < 200:  # Reasonable range
                    indicators_found.append({
                        'marker': f'barcode_top_section',
                        'type': 'VISUAL_SUPPORTING',  # DOWNGRADED from CRITICAL
                        'description': 'Barcode in header area',
                        'weight': 0.5  # Lowered weight
                    })
                    logger.info(f"✓ Found barcode pattern with {peak_count} peaks")
            
            # Method B: Detect actual barcode using pyzbar (more reliable)
            if self.use_barcode_lib:
                try:
                    pil_img = Image.open(image_path)
                    # Only check top portion
                    width_pil, height_pil = pil_img.size
                    top_crop = pil_img.crop((0, 0, width_pil, int(height_pil * 0.15)))
                    barcodes = pyzbar.decode(top_crop)
                    
                    if len(barcodes) > 0:
                        # Check barcode data for Index-II patterns
                        barcode_data = barcodes[0].data.decode('utf-8', errors='ignore')
                        
                        # Index-II barcodes often contain date patterns or specific formats
                        if any(char.isdigit() for char in barcode_data) and len(barcode_data) > 8:
                            indicators_found.append({
                                'marker': f'barcode_decoded',
                                'type': 'VISUAL_SUPPORTING',
                                'description': 'Valid barcode in header',
                                'weight': 0.6
                            })
                            logger.info(f"✓ Decoded barcode: {barcode_data[:20]}")
                except Exception as e:
                    logger.debug(f"Barcode decode error: {e}")
            
            # 2. CIRCULAR SEAL DETECTION - MUCH MORE CONSERVATIVE
            # Blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (9, 9), 2)
            
            try:
                circles = cv2.HoughCircles(
                    blurred,
                    cv2.HOUGH_GRADIENT,
                    dp=1,
                    minDist=100,  # INCREASED - seals should be far apart
                    param1=100,   # INCREASED - more strict
                    param2=35,     # INCREASED - more strict
                    minRadius=40, # INCREASED - seals are reasonably large
                    maxRadius=150 # DECREASED - not too large
                )
                
                if circles is not None:
                    seal_count = len(circles[0])
                    
                    # Index-II typically has 1-4 official seals, not 728!
                    if 1 <= seal_count <= 5:  # Reasonable range
                        indicators_found.append({
                            'marker': f'{seal_count}_official_seals',
                            'type': 'VISUAL_SUPPORTING',  # DOWNGRADED
                            'description': f'{seal_count} circular seals',
                            'weight': 0.4 + (seal_count * 0.1)
                        })
                        logger.info(f"✓ Found {seal_count} circular seal(s)")
                    else:
                        logger.warning(f"Found {seal_count} circles - likely noise, ignoring")
            except Exception as e:
                logger.debug(f"Seal detection failed: {e}")
            
            # 3. TABLE STRUCTURE DETECTION (Payment details table)
            try:
                horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
                
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                
                h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
                v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
                
                h_count = np.sum(h_lines) / 255
                v_count = np.sum(v_lines) / 255
                
                # Index-II has DENSE grid structure (payment details table)
                # NOC/No Dues have simpler tables
                if h_count > width * 3 and v_count > height * 2:  # More strict thresholds
                    indicators_found.append({
                        'marker': 'dense_table_grid',
                        'type': 'VISUAL_SUPPORTING',  # DOWNGRADED
                        'description': 'Dense table structure',
                        'weight': 0.5
                    })
                    logger.info(f"✓ Found table structure (H:{h_count:.0f}, V:{v_count:.0f})")
            except Exception as e:
                logger.debug(f"Table detection failed: {e}")
            
            # 4. SKIP colored stamp detection - too generic
            # NOC/No Dues also have stamps, so this is not a good indicator
            
            return indicators_found
            
        except Exception as e:
            logger.warning(f"Visual structure check failed: {e}")
            return []
    
    def _check_negative_signals(self, image_path: str) -> List[Dict]:
        """
        Check for signals that indicate it's NOT Index-II.
        Enhanced to work even with partial OCR extraction.
        """
        try:
            text = self._extract_text_robust(image_path)
            text_lower = text.lower()
            
            # If text is very short (< 50 chars), likely handwritten or unreadable
            # Index-II documents are always printed and have substantial text
            if len(text.strip()) < 50:
                logger.warning(f"⚠ Very little text extracted ({len(text.strip())} chars) - likely handwritten/unreadable")
                logger.warning(f"⚠ Index-II documents must have substantial printed text - this is likely NOT Index-II")
                negative_signals = [{
                    'marker': 'insufficient_text',
                    'description': 'Very little text extracted - likely handwritten or unreadable',
                    'penalty': 0.8  # VERY high penalty - Index-II must have substantial printed text
                }]
                return negative_signals
            
            negative_signals = []
            
            # NOC/Certificate/Agreement/Will markers (case-insensitive, partial matches)
            noc_markers = {
                # NOC/No Dues
                'no objection certificate': 'NOC certificate',
                'no objection': 'NOC',
                'noc': 'NOC abbreviation',
                'no dues certificate': 'No Dues certificate',
                'no dues': 'No Dues',
                'clearance certificate': 'Clearance',
                'non encumbrance': 'Non-encumbrance',
                'bonafide certificate': 'Bonafide',
                'society': 'Housing society document',
                'co-op': 'Cooperative society',
                'co-operative': 'Cooperative society',
                'cooperative': 'Cooperative society',
                'housing society': 'Housing society',
                'to whomsoever': 'Certificate phrase',
                'to whom': 'Certificate phrase',
                'this is to certify': 'Certificate phrase',
                'property tax': 'Tax receipt',
                'tax receipt': 'Tax receipt',
                # NEW: Agreement/Will/Testament markers
                'deed of assignment': 'Assignment deed',
                'assignment': 'Assignment document',
                'deed of transfer': 'Transfer deed',
                'agreement': 'Agreement document',
                'sale agreement': 'Sale agreement',
                'purchase agreement': 'Purchase agreement',
                'agreement to sell': 'Sale agreement',
                'will': 'Testament/Will',
                'testament': 'Testament document',
                'testator': 'Will document',
                'executor': 'Will document',
                'bequeath': 'Will document',
                'bequeathed': 'Will document',
                'vendor': 'Sale deed',
                'purchaser': 'Purchase deed',
                'assignor': 'Assignment deed',
                'assignee': 'Assignment deed',
                'transferor': 'Transfer deed',
                'transferee': 'Transfer deed',
                'power of attorney': 'Power of attorney (not Index-II)',
                'poa': 'Power of attorney',
            }
            
            # Check for markers (including partial word matches for OCR errors)
            for marker, description in noc_markers.items():
                # Check exact match
                if marker in text_lower:
                    negative_signals.append({
                        'marker': marker,
                        'description': description,
                        'penalty': 0.4
                    })
                    logger.warning(f"⚠ Found negative signal: {marker}")
                # Also check if marker appears as part of a word (for OCR errors)
                # e.g., "society" might be extracted as "societ" or "societv"
                elif len(marker) > 4:  # Only for longer markers to avoid false positives
                    marker_chars = set(marker.lower())
                    # Check if most characters of marker appear in text
                    for word in text_lower.split():
                        if len(word) >= len(marker) * 0.7:  # At least 70% of marker length
                            word_chars = set(word)
                            overlap = len(marker_chars & word_chars) / len(marker_chars)
                            if overlap >= 0.8:  # 80% character overlap
                                negative_signals.append({
                                    'marker': f'{marker}_partial_match',
                                    'description': f'{description} (partial OCR match)',
                                    'penalty': 0.3  # Lower penalty for partial match
                                })
                                logger.warning(f"⚠ Found negative signal (partial): {marker} in word '{word}'")
                                break
            
            return negative_signals
            
        except Exception as e:
            logger.warning(f"Negative signal check failed: {e}")
            return []
    
    def _calculate_confidence(self, text_indicators: List[Dict], 
                             visual_indicators: List[Dict],
                             filename_negative_signals: List[Dict] = None) -> float:
        """
        FIXED: Stricter rules, negative signals, require CRITICAL markers.
        Visual markers alone (barcode/seal) are NOT enough.
        """
        # Ensure filename_negative_signals is a list (default to empty list)
        if filename_negative_signals is None:
            filename_negative_signals = []
        
        # Check for negative signals from content
        negative_signals = []
        if self.current_image_path:
            negative_signals = self._check_negative_signals(self.current_image_path)
        
        # Add filename negative signals (fallback when OCR fails)
        if filename_negative_signals:
            negative_signals.extend(filename_negative_signals)
            logger.info(f"  Added {len(filename_negative_signals)} negative signals from filename")
        
        # Separate marker types
        text_critical = [ind for ind in text_indicators if ind['type'] == 'CRITICAL']
        text_strong = [ind for ind in text_indicators if ind['type'] == 'STRONG']
        text_supporting = [ind for ind in text_indicators if ind['type'] == 'SUPPORTING']
        visual_critical = [ind for ind in visual_indicators if ind.get('type') == 'VISUAL_CRITICAL']
        
        text_score = sum(ind['weight'] for ind in text_indicators)
        visual_score = sum(ind['weight'] for ind in visual_indicators)
        
        logger.info(f"\nScoring breakdown:")
        logger.info(f"  Text score: {text_score:.2f} (Critical:{len(text_critical)}, Strong:{len(text_strong)})")
        logger.info(f"  Visual score: {visual_score:.2f}")
        logger.info(f"  Negative signals: {len(negative_signals)}")
        if negative_signals:
            logger.info(f"  Negative signal details: {[s['marker'] for s in negative_signals]}")
        
        # RULE 0: STRICT - Negative signals ALWAYS take priority unless we have FULL unambiguous markers
        if len(negative_signals) > 0:
            # Check negative signal types - expanded to include agreement/will/testament
            strong_negative_markers = [
                # NOC/No Dues
                'no objection certificate', 'no objection', 'noc',
                'no dues certificate', 'no dues',
                'clearance certificate', 'society',
                # Agreement/Will/Testament
                'deed of assignment', 'assignment', 'agreement',
                'sale agreement', 'purchase agreement', 'agreement to sell',
                'will', 'testament', 'testator', 'bequeath', 'bequeathed',
                'vendor', 'purchaser', 'assignor', 'assignee',
                'transferor', 'transferee', 'power of attorney', 'poa'
            ]
            
            found_strong_negative = any(
                any(sn in sig['marker'].lower() for sn in strong_negative_markers)
                for sig in negative_signals
            )
            
            if found_strong_negative:
                # Check if we have FULL, UNAMBIGUOUS Index-II markers (NOT partial matches)
                # Only ignore negative signals if we have COMPLETE, EXACT Index-II markers
                # Partial matches like "सूची + क्र.2 (partial match)" are NOT sufficient
                full_unambiguous_markers = [
                    'सूची क्र.2', 'सूची क्र.२',  # Full exact match only
                    'index-ii', 'index ii',  # Full exact match
                    'regn:63m', 'regn.63m',  # Full exact match
                    'दुय्यम निबंधक'  # Full exact match
                    # REMOVED: 'सूची + क्र.2 (partial match)' - partial matches should NOT override negative signals
                ]
                
                has_full_marker = any(
                    ind['marker'] in full_unambiguous_markers
                    for ind in text_critical
                )
                
                if has_full_marker:
                    # Has FULL, EXACT Index-II marker - negative signal is false positive
                    logger.info(f"  → FULL Index-II marker found ({[ind['marker'] for ind in text_critical if ind['marker'] in full_unambiguous_markers][0]}) - ignoring negative signals")
                    # Continue to RULE 1
                else:
                    # Only partial/generic markers (like "गावाचे नाव" or "सूची + क्र.2 (partial match)") - trust negative signals
                    penalty = sum(sig['penalty'] for sig in negative_signals)
                    confidence = max(0.0, 0.20 - penalty)  # Lower base (0.20 instead of 0.25)
                    partial_markers = [ind['marker'] for ind in text_critical if ind['marker'] not in full_unambiguous_markers]
                    logger.info(f"  → RULE 0: STRONG negative signals (agreement/will/NOC) + only partial markers ({partial_markers}) = NOT Index-II, confidence={confidence:.2f}")
                    return confidence
        
        # Check for insufficient text (handwritten documents)
        if any(sig.get('marker') == 'insufficient_text' for sig in negative_signals):
            penalty = sum(sig['penalty'] for sig in negative_signals)
            confidence = max(0.0, 0.2 - penalty)
            logger.info(f"  → RULE 0B: Insufficient text = likely handwritten, confidence={confidence:.2f}")
            return confidence
        
        # RULE 1: CRITICAL text marker (DEFINITIVE markers only - partial/weak markers handled in RULE 0)
        # Only definitive markers like "सूची क्र.2", "index-ii", "regn:63m", "दुय्यम निबंधक"
        # Weak markers like "गावाचे नाव" alone are NOT enough if negative signals present
        definitive_markers = [
            'सूची क्र.2', 'सूची क्र.२',
            'index-ii', 'index ii',
            'regn:63m', 'regn.63m',
            'दुय्यम निबंधक'
        ]
        
        definitive_critical = [ind for ind in text_critical if ind['marker'] in definitive_markers]
        
        if len(definitive_critical) >= 1:
            confidence = 0.85 + min(0.1, visual_score * 0.02)
            logger.info(f"  → RULE 1: DEFINITIVE CRITICAL text marker found ({definitive_critical[0]['marker']}), confidence={confidence:.2f}")
            return confidence
        
        # If we have weak critical markers (like "गावाचे नाव") but negative signals, reject
        if len(text_critical) >= 1 and len(negative_signals) > 0:
            weak_markers = [ind['marker'] for ind in text_critical if ind['marker'] not in definitive_markers]
            if weak_markers:
                penalty = sum(sig['penalty'] for sig in negative_signals)
                confidence = max(0.0, 0.25 - penalty)
                logger.info(f"  → RULE 1B: Weak critical markers ({weak_markers}) + negative signals = NOT Index-II, confidence={confidence:.2f}")
                return confidence
        
        # RULE 2: Multiple strong markers + visual
        if len(text_strong) >= 3 and visual_score > 1.0:
            confidence = 0.65 + (text_score * 0.05)
            logger.info(f"  → RULE 2: Multiple strong markers, confidence={confidence:.2f}")
            return confidence
        
        # RULE 3: Circumstantial evidence (barcode+table+payment terms, NO negatives)
        # STRICT: Agreement/Will docs also have payment tables but are NOT Index-II
        has_barcode = any('barcode' in ind['marker'].lower() for ind in visual_indicators)
        has_table = any('table' in ind['marker'].lower() for ind in visual_indicators)
        payment_markers = ['stamp duty', 'registration fee', 'echallan']
        found_payment_terms = [ind for ind in text_indicators 
                              if any(pm in ind['marker'].lower() for pm in payment_markers)]
        
        # CRITICAL: Must have NO negative signals AND sufficient text indicators
        # Agreement/Will docs have payment tables but are NOT Index-II
        if has_barcode and has_table and len(found_payment_terms) >= 2:
            if len(negative_signals) == 0 and len(text_indicators) >= 2:
                confidence = 0.70
                logger.info(f"  → RULE 3: CIRCUMSTANTIAL (barcode+table+{len(found_payment_terms)} payments, no negatives), confidence={confidence:.2f}")
                return confidence
            else:
                logger.info(f"  → RULE 3: Pattern matches BUT negative signals present ({len(negative_signals)}) or insufficient text ({len(text_indicators)}) - NOT Index-II")
                # Don't return, continue to lower confidence rules
        
        # RULE 4: Default - low confidence (below threshold)
        combined = (text_score * 0.7 + visual_score * 0.3) / 3.0
        confidence = min(0.55, combined)  # Lowered max to 0.55 (below 0.60 threshold)
        logger.info(f"  → RULE 4: Default low confidence={confidence:.2f}")
        return confidence
    
    def _determine_method(self, text_indicators: List[Dict],
                          visual_indicators: List[Dict]) -> str:
        """Determine primary detection method"""
        has_critical_text = any(ind['type'] == 'CRITICAL' for ind in text_indicators)
        has_critical_visual = any(ind.get('type') == 'VISUAL_CRITICAL' for ind in visual_indicators)
        
        if has_critical_text:
            return "Text markers (CRITICAL found)"
        elif has_critical_visual:
            return "Visual markers (barcode/seal found)"
        elif len(text_indicators) > len(visual_indicators):
            return "Text markers"
        else:
            return "Visual structure"
