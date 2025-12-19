"""
Stage 4: Overall Quality Score (BRISQUE)
Uses BRISQUE algorithm for blind image quality assessment.
Processing Time: 100-200ms
"""

import cv2
import numpy as np
from typing import Dict
import os
from dotenv import load_dotenv

load_dotenv()


class BRISQUEQualityScorer:
    """Calculates BRISQUE quality score for images."""
    
    def __init__(self):
        """Initialize threshold from environment variables."""
        self.brisque_threshold = float(os.getenv('BRISQUE_THRESHOLD', 55))
    
    def calculate_brisque_score(self, image: np.ndarray) -> float:
        """
        Calculate BRISQUE (Blind/Referenceless Image Spatial Quality Evaluator) score.
        
        Note: OpenCV's quality module requires contrib package.
        If not available, we use a simplified version.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            BRISQUE score (lower is better, 0-100 scale)
        """
        try:
            # Try to use OpenCV's quality module
            quality = cv2.quality.QualityBRISQUE_compute(image, "brisque_model.yml", "brisque_range.yml")
            if quality is not None and len(quality) > 0:
                return float(quality[0])
        except:
            pass
        
        # Fallback: Simplified BRISQUE-like calculation
        # Convert to grayscale if needed
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Normalize to 0-1 range
        gray_norm = gray.astype(np.float32) / 255.0
        
        # Calculate natural scene statistics
        # Mean subtracted contrast normalized (MSCN) coefficients
        mu = cv2.GaussianBlur(gray_norm, (7, 7), 7/6)
        mu_sq = mu * mu
        sigma_sq = cv2.GaussianBlur(gray_norm * gray_norm, (7, 7), 7/6)
        sigma = np.sqrt(np.abs(sigma_sq - mu_sq) + 1e-10)
        struct = (gray_norm - mu) / sigma
        
        # Calculate horizontal and vertical pairwise products
        h_pair = struct[:, :-1] * struct[:, 1:]
        v_pair = struct[:-1, :] * struct[1:, :]
        
        # Calculate statistics (these should be small values for natural images)
        h_mean = np.mean(h_pair)
        h_std = np.std(h_pair)
        v_mean = np.mean(v_pair)
        v_std = np.std(v_pair)
        
        # Simplified BRISQUE score (higher = worse quality)
        # For natural images, these statistics are typically small
        # Large deviations indicate poor quality
        # Normalize the values properly
        deviation = abs(h_mean) + abs(v_mean) + h_std + v_std
        
        # Scale to 0-100 range (typical good images have deviation < 2)
        # Poor quality images have higher deviation
        score = min(deviation * 20, 100)  # Adjusted scaling factor
        
        return score
    
    def process(self, image_path: str) -> Dict:
        """
        Run BRISQUE quality assessment on an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with overall result and quality score
        """
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            return {
                'stage': 'Stage 4: Overall Quality Score (BRISQUE)',
                'passed': False,
                'error': 'Could not load image',
                'score': 0
            }
        
        # Calculate BRISQUE score
        brisque_score = self.calculate_brisque_score(image)
        
        # Convert to quality score (0-100, higher = better)
        # Inverse of BRISQUE score
        quality_score = max(0, 100 - brisque_score)
        
        # Decision logic (lower BRISQUE = better quality)
        # BRISQUE is only 5% weight, so don't fail the stage - just provide warning
        # This prevents BRISQUE from causing false rejections
        warnings = []
        passed = True  # Always pass - BRISQUE is just informational
        
        if brisque_score >= self.brisque_threshold:
            quality_level = 'Poor'
            warnings.append(f'Overall quality low (BRISQUE: {brisque_score:.1f})')
        elif brisque_score >= 50:
            quality_level = 'Acceptable'
            warnings.append(f'Quality acceptable but not optimal (BRISQUE: {brisque_score:.1f})')
        elif brisque_score >= 30:
            quality_level = 'Good'
        else:
            quality_level = 'Excellent'
        
        return {
            'stage': 'Stage 4: Overall Quality Score (BRISQUE)',
            'passed': passed,
            'brisque_score': round(brisque_score, 2),
            'quality_level': quality_level,
            'stage_score': round(quality_score, 2),
            'critical_failures': [],
            'warnings': warnings,
            'rejection_reasons': warnings if not passed else []
        }

