"""
Image Processing Utilities
Handles image loading and preprocessing.
"""

import cv2
import numpy as np
from PIL import Image
import os
from typing import Optional, Tuple


class ImageProcessor:
    """Handles image loading and basic processing."""
    
    @staticmethod
    def load_image(image_path: str) -> Optional[np.ndarray]:
        """
        Load image from file path.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Image as numpy array or None if failed
        """
        if not os.path.exists(image_path):
            return None
        
        image = cv2.imread(image_path)
        return image
    
    @staticmethod
    def is_image_file(file_path: str) -> bool:
        """
        Check if file is an image.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if image, False otherwise
        """
        valid_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif']
        return any(file_path.lower().endswith(ext) for ext in valid_extensions)
    
    @staticmethod
    def get_image_info(image_path: str) -> dict:
        """
        Get basic image information.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary with image information
        """
        try:
            image = Image.open(image_path)
            return {
                'width': image.width,
                'height': image.height,
                'format': image.format,
                'mode': image.mode,
                'size_bytes': os.path.getsize(image_path)
            }
        except Exception as e:
            return {
                'error': str(e)
            }

