"""
Stage 3: Handwriting Detection
Detects handwritten vs printed text using computer vision techniques.
Processing Time: 0.5-2 seconds per page
"""

import cv2
import numpy as np
from typing import Dict, Tuple
import os
from dotenv import load_dotenv

load_dotenv()


class HandwritingDetector:
    """Detects handwriting in documents using traditional CV methods."""
    
    def __init__(self):
        """Initialize thresholds from environment variables."""
        # Critical threshold (immediate reject) - for spread-out handwriting
        # Default to 20% for spread-out handwriting (handwritten documents)
        self.handwriting_critical_threshold = float(os.getenv('HANDWRITING_CRITICAL_THRESHOLD', 20))
        
        # Warning threshold (for minor handwriting like signatures)
        self.handwriting_threshold = float(os.getenv('HANDWRITING_THRESHOLD', 15))
    
    def analyze_stroke_width(self, image: np.ndarray) -> float:
        """
        Analyze stroke width variance (handwriting has more variance).
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Variance score (higher = more handwriting-like)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Apply edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Calculate stroke width using distance transform
        dist_transform = cv2.distanceTransform(edges, cv2.DIST_L2, 5)
        
        # Get stroke widths (non-zero values)
        stroke_widths = dist_transform[dist_transform > 0]
        
        if len(stroke_widths) == 0:
            return 0.0
        
        # Calculate coefficient of variation (std/mean)
        if np.mean(stroke_widths) > 0:
            cv_score = (np.std(stroke_widths) / np.mean(stroke_widths)) * 100
        else:
            cv_score = 0.0
        
        return cv_score
    
    def analyze_baseline_variance(self, image: np.ndarray) -> float:
        """
        Analyze baseline variance (handwriting has wavy baselines).
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Baseline variance score
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Apply horizontal projection to find text lines
        horizontal_projection = np.sum(gray < 128, axis=1)
        
        # Find peaks (text lines)
        threshold = np.max(horizontal_projection) * 0.3
        peaks = np.where(horizontal_projection > threshold)[0]
        
        if len(peaks) < 2:
            return 0.0
        
        # Calculate variance in peak positions
        # For printed text, peaks should be evenly spaced
        if len(peaks) > 1:
            spacing = np.diff(peaks)
            spacing_variance = np.var(spacing) if len(spacing) > 0 else 0
            mean_spacing = np.mean(spacing) if len(spacing) > 0 else 1
            
            # Use coefficient of variation instead of raw variance
            # This is more robust and less sensitive to document size
            if mean_spacing > 0:
                cv_score = (np.std(spacing) / mean_spacing) * 100
            else:
                cv_score = 0.0
            
            # Cap the score more reasonably - printed text can have CV up to 30-40%
            # Only very irregular spacing (CV > 50%) suggests handwriting
            variance_score = min(cv_score * 1.5, 60)  # Cap at 60 instead of 100
        else:
            variance_score = 0.0
        
        return variance_score
    
    def analyze_character_spacing(self, image: np.ndarray) -> float:
        """
        Analyze character spacing regularity.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Spacing irregularity score
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Apply vertical projection to find character boundaries
        vertical_projection = np.sum(gray < 128, axis=0)
        
        # Find valleys (spaces between characters)
        threshold = np.max(vertical_projection) * 0.1
        valleys = np.where(vertical_projection < threshold)[0]
        
        if len(valleys) < 2:
            return 0.0
        
        # Calculate spacing between valleys
        spacing = np.diff(valleys)
        spacing = spacing[spacing > 5]  # Filter out very small gaps
        
        if len(spacing) == 0:
            return 0.0
        
        # Calculate coefficient of variation
        if np.mean(spacing) > 0:
            cv_score = (np.std(spacing) / np.mean(spacing)) * 100
        else:
            cv_score = 0.0
        
        return min(cv_score, 100)
    
    def analyze_connected_components(self, image: np.ndarray) -> float:
        """
        Analyze connected component characteristics.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Handwriting likelihood score
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Threshold
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Find connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        
        if num_labels < 2:
            return 0.0
        
        # Analyze component sizes and shapes
        component_areas = stats[1:, cv2.CC_STAT_AREA]  # Skip background
        component_widths = stats[1:, cv2.CC_STAT_WIDTH]
        component_heights = stats[1:, cv2.CC_STAT_HEIGHT]
        
        # Calculate aspect ratios
        aspect_ratios = component_widths / (component_heights + 1e-5)
        
        # Handwriting tends to have more variable aspect ratios
        aspect_ratio_variance = np.var(aspect_ratios) if len(aspect_ratios) > 0 else 0
        
        # Normalize score
        score = min(aspect_ratio_variance * 10, 100)
        
        return score
    
    def analyze_handwriting_distribution(self, image: np.ndarray) -> Dict:
        """
        Analyze if handwriting is concentrated (signatures/stamps) or spread throughout.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Dictionary with distribution analysis
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        height, width = gray.shape
        
        # Divide image into grid regions
        grid_rows, grid_cols = 4, 4
        region_height = height // grid_rows
        region_width = width // grid_cols
        
        # Analyze each region for handwriting characteristics
        region_scores = []
        handwriting_regions = 0
        
        for row in range(grid_rows):
            for col in range(grid_cols):
                y_start = row * region_height
                y_end = (row + 1) * region_height if row < grid_rows - 1 else height
                x_start = col * region_width
                x_end = (col + 1) * region_width if col < grid_cols - 1 else width
                
                region = gray[y_start:y_end, x_start:x_end]
                
                # Quick handwriting check for this region
                # Use stroke width variance as indicator
                edges = cv2.Canny(region, 50, 150)
                if np.sum(edges) > 0:
                    dist_transform = cv2.distanceTransform(edges, cv2.DIST_L2, 3)
                    stroke_widths = dist_transform[dist_transform > 0]
                    if len(stroke_widths) > 10:
                        cv_score = (np.std(stroke_widths) / (np.mean(stroke_widths) + 1e-5)) * 100
                        region_scores.append(cv_score)
                        # If region has high handwriting score, count it
                        if cv_score > 20:  # Threshold for handwriting in region
                            handwriting_regions += 1
        
        total_regions = grid_rows * grid_cols
        handwriting_region_percentage = (handwriting_regions / total_regions) * 100 if total_regions > 0 else 0
        
        # If handwriting is in < 25% of regions, it's likely signatures/stamps (concentrated)
        # If handwriting is in > 50% of regions, it's likely a handwritten document (spread out)
        is_concentrated = handwriting_region_percentage < 25
        is_spread_out = handwriting_region_percentage > 50
        
        return {
            'handwriting_regions': handwriting_regions,
            'total_regions': total_regions,
            'handwriting_region_percentage': round(handwriting_region_percentage, 2),
            'is_concentrated': is_concentrated,
            'is_spread_out': is_spread_out,
            'average_region_score': round(np.mean(region_scores) if region_scores else 0, 2)
        }
    
    def calculate_handwriting_percentage(self, image: np.ndarray) -> Dict:
        """
        Calculate overall handwriting percentage with distribution analysis.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Dictionary with handwriting analysis results
        """
        # Get individual scores
        stroke_score = self.analyze_stroke_width(image)
        baseline_score = self.analyze_baseline_variance(image)
        spacing_score = self.analyze_character_spacing(image)
        component_score = self.analyze_connected_components(image)
        
        # Weighted average - reduced baseline weight since it's more prone to false positives
        handwriting_percentage = (
            stroke_score * 0.35 +
            baseline_score * 0.15 +  # Reduced from 0.25 to 0.15
            spacing_score * 0.30 +   # Increased from 0.25 to 0.30
            component_score * 0.20
        )
        
        # Analyze distribution
        distribution = self.analyze_handwriting_distribution(image)
        
        return {
            'handwriting_percentage': round(handwriting_percentage, 2),
            'stroke_width_score': round(stroke_score, 2),
            'baseline_variance_score': round(baseline_score, 2),
            'spacing_irregularity_score': round(spacing_score, 2),
            'component_variance_score': round(component_score, 2),
            'distribution': distribution
        }
    
    def process(self, image_path: str) -> Dict:
        """
        Run handwriting detection on an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with overall result and detailed analysis
        """
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            return {
                'stage': 'Stage 3: Handwriting Detection',
                'passed': False,
                'error': 'Could not load image',
                'analysis': {}
            }
        
        # Calculate handwriting percentage with distribution analysis
        analysis = self.calculate_handwriting_percentage(image)
        
        handwriting_pct = analysis['handwriting_percentage']
        distribution = analysis.get('distribution', {})
        is_concentrated = distribution.get('is_concentrated', False)
        is_spread_out = distribution.get('is_spread_out', False)
        handwriting_regions_pct = distribution.get('handwriting_region_percentage', 0)
        
        critical_failures = []
        warnings = []
        
        # OCR confidence is ONE signal, not ground truth
        # We use it for cross-validation in orchestrator, not to override handwriting detection
        # Handwriting percentage is a physical property that cannot be "overridden"
        
        # CRITICAL: Very high handwriting percentage - definitely handwritten document
        if handwriting_pct >= 40:
            passed = False
            action = 'REJECT'
            critical_failures.append(
                f'Document is significantly handwritten ({handwriting_pct:.1f}% handwriting) - only printed documents are accepted'
            )
            stage_score = 0
        
        # CRITICAL: Handwriting spread throughout document (>50% of regions) = handwritten document
        elif is_spread_out and handwriting_pct >= 25:
            # Handwriting is spread throughout - this is a handwritten document
            passed = False
            action = 'REJECT'
            critical_failures.append(
                f'Handwritten text throughout document: {handwriting_pct:.1f}% handwriting spread across {handwriting_regions_pct:.1f}% of document regions'
            )
            stage_score = 0
        
        # ACCEPT: Handwriting is concentrated AND percentage is reasonable (signatures/stamps)
        elif is_concentrated and handwriting_pct < 30:
            # Handwriting is in isolated areas - likely signatures/stamps/symbols
            passed = True
            action = 'ACCEPT'
            if handwriting_pct >= 15:
                warnings.append(f'Handwriting detected ({handwriting_pct:.1f}%) in isolated areas - likely signatures/stamps, acceptable')
            else:
                warnings.append(f'Minor handwriting detected ({handwriting_pct:.1f}%) - likely signatures/stamps, acceptable')
            # Full or near-full credit for signatures/stamps
            stage_score = max(80, 100 - handwriting_pct * 0.5)
        
        # WARNING: Moderate handwriting, unclear distribution - needs review
        elif handwriting_pct >= 20 and handwriting_pct < 30:
            # Moderate handwriting - could be signatures or handwritten content
            passed = True  # Don't reject, but flag for review
            action = 'WARNING'
            warnings.append(f'Moderate handwriting detected ({handwriting_pct:.1f}%) - distribution unclear, may need review')
            # Reduced score
            stage_score = max(60, 100 - handwriting_pct * 1.5)
        
        # ACCEPT: Low handwriting (likely just signatures/stamps)
        elif handwriting_pct >= 10:
            passed = True
            action = 'ACCEPT'
            warnings.append(f'Minor handwriting detected ({handwriting_pct:.1f}%) - likely signatures/stamps, acceptable')
            stage_score = max(85, 100 - handwriting_pct * 1.5)
        
        # ACCEPT: Very low or no handwriting
        else:
            passed = True
            action = 'ACCEPT'
            stage_score = 100
        
        return {
            'stage': 'Stage 3: Handwriting Detection',
            'passed': passed,
            'action': action,
            'stage_score': round(stage_score, 2),
            'critical_failures': critical_failures,
            'warnings': warnings,
            'analysis': analysis,
            'rejection_reasons': critical_failures + warnings
        }

