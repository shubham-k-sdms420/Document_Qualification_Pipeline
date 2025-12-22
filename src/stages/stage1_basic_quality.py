"""
Stage 1: Basic Quality Checks
Uses OpenCV to perform fast quality checks on documents.
Processing Time: 50-100ms per page
"""

import cv2
import numpy as np
from typing import Dict, Tuple, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class BasicQualityChecker:
    """Performs basic quality checks using OpenCV."""
    
    def __init__(self):
        """Initialize thresholds from environment variables."""
        # Critical thresholds (immediate reject)
        self.resolution_critical_width = int(os.getenv('RESOLUTION_MIN_WIDTH', 400))
        self.resolution_critical_height = int(os.getenv('RESOLUTION_MIN_HEIGHT', 300))
        self.blur_critical_threshold = float(os.getenv('BLUR_CRITICAL_THRESHOLD', 30))
        
        # Warning thresholds (partial credit)
        self.resolution_min_width = int(os.getenv('RESOLUTION_MIN_WIDTH', 800))
        self.resolution_min_height = int(os.getenv('RESOLUTION_MIN_HEIGHT', 600))
        self.blur_threshold = float(os.getenv('BLUR_THRESHOLD', 60))
        self.brightness_min = int(os.getenv('BRIGHTNESS_MIN', 35))
        self.brightness_max = int(os.getenv('BRIGHTNESS_MAX', 220))
        self.contrast_threshold = float(os.getenv('CONTRAST_THRESHOLD', 22))
        self.white_space_max = float(os.getenv('WHITE_SPACE_MAX', 80))
        self.skew_threshold = float(os.getenv('SKEW_THRESHOLD', 15))
        
        # Critical thresholds for unreadable documents
        self.brightness_critical_min = int(os.getenv('BRIGHTNESS_CRITICAL_MIN', 15))  # Too dark
        self.brightness_critical_max = int(os.getenv('BRIGHTNESS_CRITICAL_MAX', 300))  # Too bright/overexposed
        self.contrast_critical_threshold = float(os.getenv('CONTRAST_CRITICAL_THRESHOLD', 15))  # Too low contrast
    
    def check_resolution(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Check if image resolution meets minimum requirements.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, failure_type, details_dict)
            failure_type: 'critical', 'warning', or 'pass'
        """
        height, width = image.shape[:2]
        
        # Critical failure (too small)
        if width < self.resolution_critical_width or height < self.resolution_critical_height:
            return False, 'critical', {
                'width': int(width),
                'height': int(height),
                'min_width_required': self.resolution_min_width,
                'min_height_required': self.resolution_min_height,
                'message': 'Resolution too low - document too small to process'
            }
        
        # Warning (below recommended but above critical)
        if width < self.resolution_min_width or height < self.resolution_min_height:
            return False, 'warning', {
                'width': int(width),
                'height': int(height),
                'min_width_required': self.resolution_min_width,
                'min_height_required': self.resolution_min_height,
                'message': 'Resolution below recommended - may affect quality'
            }
        
        # Pass
        return True, 'pass', {
            'width': int(width),
            'height': int(height),
            'min_width_required': self.resolution_min_width,
            'min_height_required': self.resolution_min_height,
            'message': 'Resolution acceptable'
        }
    
    def check_blur(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Detect blur using Laplacian variance.
        Detects documents with broader lines, mess, or extreme blur that are unreadable.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, failure_type, details_dict)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # CRITICAL: Extremely blurry - document has broader lines, mess, or is unreadable
        if laplacian_var < self.blur_critical_threshold:
            return False, 'critical', {
                'blur_score': round(laplacian_var, 2),
                'threshold': self.blur_threshold,
                'message': f'Document extremely blurry (blur score: {laplacian_var:.1f}) - has broader lines, distortion, or is unreadable. Please rescan clearly.'
            }
        
        # Warning (slightly blurry)
        if laplacian_var < self.blur_threshold:
            return False, 'warning', {
                'blur_score': round(laplacian_var, 2),
                'threshold': self.blur_threshold,
                'message': 'Document slightly blurry - may affect readability'
            }
        
        # Pass
        return True, 'pass', {
            'blur_score': round(laplacian_var, 2),
            'threshold': self.blur_threshold,
            'message': 'Image sharpness acceptable'
        }
    
    def check_brightness(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Check average brightness levels.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, details_dict)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        avg_brightness = float(np.mean(gray))
        
        # CRITICAL: Too dark - image is unreadable (bold/dark images that can't be read by naked eyes)
        if avg_brightness < self.brightness_critical_min:
            return False, 'critical', {
                'brightness': round(avg_brightness, 2),
                'min_threshold': self.brightness_min,
                'max_threshold': self.brightness_max,
                'status': 'too_dark',
                'message': f'Document too dark (brightness: {avg_brightness:.1f}) - cannot be read by naked eyes. Please rescan with proper lighting.'
            }
        
        # CRITICAL: Too bright/overexposed - image is washed out and unreadable
        # Only reject if extremely overexposed (> 250) - very bright but readable documents should pass
        if avg_brightness > self.brightness_critical_max:
            return False, 'critical', {
                'brightness': round(avg_brightness, 2),
                'min_threshold': self.brightness_min,
                'max_threshold': self.brightness_max,
                'status': 'too_bright',
                'message': f'Document severely overexposed/washed out (brightness: {avg_brightness:.1f}) - cannot be read. Please rescan with proper lighting.'
            }
        
        # Warning (slightly out of range)
        if avg_brightness < self.brightness_min or avg_brightness > self.brightness_max:
            status = 'too_dark' if avg_brightness < self.brightness_min else 'too_bright'
            message = 'Lighting slightly suboptimal - may affect quality'
            return False, 'warning', {
                'brightness': round(avg_brightness, 2),
                'min_threshold': self.brightness_min,
                'max_threshold': self.brightness_max,
                'status': status,
                'message': message
            }
        
        # Pass
        return True, 'pass', {
            'brightness': round(avg_brightness, 2),
            'min_threshold': self.brightness_min,
            'max_threshold': self.brightness_max,
            'status': 'acceptable',
            'message': 'Lighting acceptable'
        }
    
    def check_contrast(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Check contrast using standard deviation of pixel values.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, details_dict)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        contrast = float(np.std(gray))
        
        # CRITICAL: Extremely low contrast - text is not distinguishable (unreadable)
        # This catches documents with mess, corruption, or broader lines that make text unreadable
        if contrast < self.contrast_critical_threshold:
            return False, 'critical', {
                'contrast_score': round(contrast, 2),
                'threshold': self.contrast_threshold,
                'message': f'Extremely low contrast ({contrast:.1f}) - text not distinguishable. Document may be corrupted, have broader lines, or be unreadable.'
            }
        
        # Warning (low contrast)
        if contrast < self.contrast_threshold:
            return False, 'warning', {
                'contrast_score': round(contrast, 2),
                'threshold': self.contrast_threshold,
                'message': 'Low contrast - may affect text readability'
            }
        
        # Pass
        return True, 'pass', {
            'contrast_score': round(contrast, 2),
            'threshold': self.contrast_threshold,
            'message': 'Contrast acceptable'
        }
    
    def check_white_space(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Check percentage of white space (blank document detection).
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, details_dict)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        # Consider pixels with value > 240 as white space
        white_pixels = int(np.sum(gray > 240))
        total_pixels = gray.size
        white_space_percent = (white_pixels / total_pixels) * 100
        
        # Warning (high white space)
        if white_space_percent >= self.white_space_max:
            return False, 'warning', {
                'white_space_percent': round(white_space_percent, 2),
                'threshold': self.white_space_max,
                'message': 'High white space detected - may be mostly blank'
            }
        
        # Pass
        return True, 'pass', {
            'white_space_percent': round(white_space_percent, 2),
            'threshold': self.white_space_max,
            'message': 'Document has sufficient content'
        }
    
    def check_document_corruption(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Check for document corruption, distortion, broader lines, or mess.
        Detects documents that are corrupted or have visual artifacts.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, failure_type, details_dict)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Check for compression artifacts or distortion
        # Use edge detection to find irregular patterns
        edges = cv2.Canny(gray, 50, 150)
        
        # Calculate edge density (too high = mess/corruption)
        edge_density = np.sum(edges > 0) / edges.size * 100
        
        # Check for very thick lines (broader lines)
        # Use morphological operations to detect thick strokes
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        thick_line_ratio = np.sum(dilated > 0) / edges.size * 100
        
        # Check for irregular patterns (mess/distortion)
        # Calculate variance in edge distribution
        h_projection = np.sum(edges, axis=1)
        v_projection = np.sum(edges, axis=0)
        h_variance = np.var(h_projection)
        v_variance = np.var(v_projection)
        
        # High variance in edge distribution indicates irregular patterns (mess)
        irregularity_score = (h_variance + v_variance) / 1000000  # Normalize
        
        # CRITICAL: Document has severe broader lines or mess (corruption/distortion)
        # Very high thick line ratio indicates broader lines or severe distortion
        if thick_line_ratio > 25 or (irregularity_score > 100 and thick_line_ratio > 15):
            return False, 'critical', {
                'edge_density': round(edge_density, 2),
                'thick_line_ratio': round(thick_line_ratio, 2),
                'irregularity_score': round(irregularity_score, 2),
                'message': f'Document appears corrupted or distorted - has broader lines ({thick_line_ratio:.1f}%) or visual mess. Document may be unreadable.'
            }
        
        # Warning: Some distortion detected (moderate broader lines)
        if thick_line_ratio > 18 or irregularity_score > 80:
            return False, 'warning', {
                'edge_density': round(edge_density, 2),
                'thick_line_ratio': round(thick_line_ratio, 2),
                'irregularity_score': round(irregularity_score, 2),
                'message': 'Some distortion or broader lines detected - may affect readability'
            }
        
        # Pass
        return True, 'pass', {
            'edge_density': round(edge_density, 2),
            'thick_line_ratio': round(thick_line_ratio, 2),
            'irregularity_score': round(irregularity_score, 2),
            'message': 'Document structure acceptable'
        }
    
    def check_skew(self, image: np.ndarray) -> Tuple[bool, str, Dict]:
        """
        Detect document rotation/skew angle.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Tuple of (pass_status, details_dict)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Hough line transform to detect lines
        lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
        
        if lines is None or len(lines) == 0:
            # No lines detected, assume no significant skew
            return True, 'pass', {
                'skew_angle': 0.0,
                'threshold': self.skew_threshold,
                'message': 'Document alignment acceptable'
            }
        
        # Calculate average angle
        angles = []
        for line in lines[:20]:  # Use first 20 lines
            rho, theta = line[0]
            angle = (theta * 180 / np.pi) - 90
            angles.append(angle)
        
        avg_angle = float(np.mean(angles))
        # Normalize angle to -45 to 45 range
        if avg_angle > 45:
            avg_angle -= 90
        elif avg_angle < -45:
            avg_angle += 90
        
        abs_angle = abs(avg_angle)
        
        # Warning (slight skew)
        if abs_angle >= self.skew_threshold:
            return False, 'warning', {
                'skew_angle': round(avg_angle, 2),
                'threshold': self.skew_threshold,
                'message': 'Document slightly tilted - may affect processing'
            }
        
        # Pass
        return True, 'pass', {
            'skew_angle': round(avg_angle, 2),
            'threshold': self.skew_threshold,
            'message': 'Document alignment acceptable'
        }
    
    def process(self, image_path: str) -> Dict:
        """
        Run all basic quality checks on an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with overall result and detailed checks
        """
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            return {
                'stage': 'Stage 1: Basic Quality Checks',
                'passed': False,
                'error': 'Could not load image',
                'checks': {}
            }
        
        checks = {}
        critical_failures = []
        warnings = []
        all_passed = True  # Stage passes if no critical failures (warnings are acceptable)
        
        # Run all checks with failure classification
        checks['resolution'], failure_type, result = self.check_resolution(image)
        checks['resolution_details'] = result
        checks['resolution_failure_type'] = failure_type
        if not checks['resolution']:
            # Only mark as failed if it's a critical failure, not a warning
            if failure_type == 'critical':
                all_passed = False
                critical_failures.append(result['message'])
            else:
                warnings.append(result['message'])
        
        checks['blur'], failure_type, result = self.check_blur(image)
        checks['blur_details'] = result
        checks['blur_failure_type'] = failure_type
        
        # Blur is a physical property - cannot be overridden by OCR
        # OCR confidence is just one signal, not ground truth
        if not checks['blur']:
            # Only mark as failed if it's a critical failure, not a warning
            if failure_type == 'critical':
                all_passed = False
                critical_failures.append(result['message'])
            else:
                warnings.append(result['message'])
        
        checks['brightness'], failure_type, result = self.check_brightness(image)
        checks['brightness_details'] = result
        checks['brightness_failure_type'] = failure_type
        if not checks['brightness']:
            # Only mark as failed if it's a critical failure, not a warning
            if failure_type == 'critical':
                all_passed = False
                critical_failures.append(result['message'])
            else:
                warnings.append(result['message'])
        
        checks['contrast'], failure_type, result = self.check_contrast(image)
        checks['contrast_details'] = result
        checks['contrast_failure_type'] = failure_type
        if not checks['contrast']:
            # Only mark as failed if it's a critical failure, not a warning
            if failure_type == 'critical':
                all_passed = False
                critical_failures.append(result['message'])
            else:
                warnings.append(result['message'])
        
        checks['white_space'], failure_type, result = self.check_white_space(image)
        checks['white_space_details'] = result
        checks['white_space_failure_type'] = failure_type
        if not checks['white_space']:
            # White space is always a warning, never critical - don't mark as failed
                warnings.append(result['message'])
        
        checks['skew'], failure_type, result = self.check_skew(image)
        checks['skew_details'] = result
        checks['skew_failure_type'] = failure_type
        if not checks['skew']:
            # Skew is always a warning, never critical - don't mark as failed
                warnings.append(result['message'])
        
        # Check for document corruption/distortion (broader lines, mess)
        checks['corruption'], failure_type, result = self.check_document_corruption(image)
        checks['corruption_details'] = result
        checks['corruption_failure_type'] = failure_type
        if not checks['corruption']:
            # Only mark as failed if it's a critical failure, not a warning
            if failure_type == 'critical':
                all_passed = False
                critical_failures.append(result['message'])
            else:
                warnings.append(result['message'])
        
        # Calculate stage score with partial credit for warnings
        # Pass = 100%, Warning = 50%, Critical = 0%
        score_weights = {
            'resolution': 1/7,
            'blur': 1/7,
            'brightness': 1/7,
            'contrast': 1/7,
            'white_space': 1/7,
            'skew': 1/7,
            'corruption': 1/7
        }
        
        stage_score = 0
        for check_name in score_weights.keys():
            if checks.get(check_name, True):  # Default to True if check not run
                stage_score += score_weights[check_name] * 100
            elif checks.get(f'{check_name}_failure_type') == 'warning':
                stage_score += score_weights[check_name] * 50  # Partial credit
            # Critical failures get 0 points
        
        return {
            'stage': 'Stage 1: Basic Quality Checks',
            'passed': all_passed,
            'stage_score': round(stage_score, 2),
            'critical_failures': critical_failures,
            'warnings': warnings,
            'checks': checks,
            'rejection_reasons': critical_failures + warnings
        }

