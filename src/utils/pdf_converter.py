"""
PDF to Image Converter Utility
Converts PDF files to images for processing.
"""

from pdf2image import convert_from_path
from PIL import Image
import os
from typing import List, Optional


class PDFConverter:
    """Converts PDF files to images."""
    
    def __init__(self, dpi: int = 300):
        """
        Initialize PDF converter.
        
        Args:
            dpi: DPI for PDF conversion (default: 300)
        """
        self.dpi = dpi
    
    def convert_pdf_to_images(self, pdf_path: str, output_dir: Optional[str] = None, first_page_only: bool = False) -> List[str]:
        """
        Convert PDF to list of image file paths.
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save images (optional)
            first_page_only: If True, only convert first page (for quick detection)
            
        Returns:
            List of image file paths
        """
        try:
            # Convert PDF to images
            if first_page_only:
                # Only convert first page
                images = convert_from_path(pdf_path, dpi=self.dpi, first_page=1, last_page=1)
            else:
                images = convert_from_path(pdf_path, dpi=self.dpi)
            
            image_paths = []
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            
            if output_dir is None:
                output_dir = os.path.dirname(pdf_path)
            
            os.makedirs(output_dir, exist_ok=True)
            
            # Save each page as image
            for i, image in enumerate(images):
                image_filename = f"{base_name}_page_{i+1}.png"
                image_path = os.path.join(output_dir, image_filename)
                image.save(image_path, 'PNG')
                image_paths.append(image_path)
            
            return image_paths
        
        except Exception as e:
            raise Exception(f"Error converting PDF to images: {str(e)}")
    
    def is_pdf(self, file_path: str) -> bool:
        """
        Check if file is a PDF.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if PDF, False otherwise
        """
        return file_path.lower().endswith('.pdf')

