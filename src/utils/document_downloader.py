"""
Document Downloader Utility
Downloads documents from URLs for processing.
"""

import os
import uuid
import requests
from typing import Optional, Tuple
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


class DocumentDownloader:
    """Downloads documents from URLs."""
    
    def __init__(self, download_folder: str = 'downloads', timeout: int = 30, max_size: int = 10485760):
        """
        Initialize document downloader.
        
        Args:
            download_folder: Directory to save downloaded files
            timeout: Request timeout in seconds (default: 30)
            max_size: Maximum file size in bytes (default: 10MB)
        """
        self.download_folder = download_folder
        self.timeout = timeout
        self.max_size = max_size
        
        # Create download folder if it doesn't exist
        os.makedirs(self.download_folder, exist_ok=True)
    
    def get_file_extension_from_url(self, url: str) -> Optional[str]:
        """
        Extract file extension from URL.
        
        Args:
            url: Document URL
            
        Returns:
            File extension (without dot) or None
        """
        try:
            parsed = urlparse(url)
            path = parsed.path
            
            # Try to get extension from path
            if '.' in path:
                ext = path.rsplit('.', 1)[1].lower()
                # Remove query parameters if any
                if '?' in ext:
                    ext = ext.split('?')[0]
                # Common document extensions
                if ext in ['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif']:
                    return ext
            
            # Try to get from Content-Type header (will be checked in download)
            return None
        except Exception as e:
            logger.warning(f"Error extracting extension from URL {url}: {e}")
            return None
    
    def get_file_extension_from_content_type(self, content_type: str) -> Optional[str]:
        """
        Extract file extension from Content-Type header.
        
        Args:
            content_type: HTTP Content-Type header value
            
        Returns:
            File extension (without dot) or None
        """
        content_type_map = {
            'application/pdf': 'pdf',
            'image/png': 'png',
            'image/jpeg': 'jpg',
            'image/jpg': 'jpg',
            'image/bmp': 'bmp',
            'image/tiff': 'tiff',
            'image/tif': 'tif'
        }
        
        # Remove charset and other parameters
        content_type = content_type.split(';')[0].strip().lower()
        return content_type_map.get(content_type)
    
    def download_document(self, url: str, filename: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Download document from URL.
        
        Args:
            url: Document URL
            filename: Optional custom filename (without extension)
            
        Returns:
            Tuple of (file_path, error_message)
            file_path: Path to downloaded file if successful, None otherwise
            error_message: Error message if failed, None otherwise
        """
        try:
            logger.info(f"Downloading document from URL: {url}")
            
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return None, "Invalid URL format"
            
            # Make request with streaming to handle large files
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                stream=True,
                allow_redirects=True
            )
            
            # Check status code
            response.raise_for_status()
            
            # Check Content-Length if available
            content_length = response.headers.get('Content-Length')
            if content_length:
                size = int(content_length)
                if size > self.max_size:
                    return None, f"File too large ({size / 1024 / 1024:.2f}MB). Maximum size: {self.max_size / 1024 / 1024:.2f}MB"
            
            # Determine file extension
            file_extension = None
            
            # Try to get from URL first
            file_extension = self.get_file_extension_from_url(url)
            
            # If not found, try Content-Type header
            if not file_extension:
                content_type = response.headers.get('Content-Type', '')
                file_extension = self.get_file_extension_from_content_type(content_type)
            
            # Default to pdf if still not found
            if not file_extension:
                file_extension = 'pdf'
                logger.warning(f"Could not determine file type from URL or headers, defaulting to PDF")
            
            # Generate filename
            if filename:
                unique_filename = f"{filename}.{file_extension}"
            else:
                unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            file_path = os.path.join(self.download_folder, unique_filename)
            
            # Download file in chunks to handle large files and check size
            downloaded_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # Check size during download
                        if downloaded_size > self.max_size:
                            os.remove(file_path)
                            return None, f"File too large ({downloaded_size / 1024 / 1024:.2f}MB). Maximum size: {self.max_size / 1024 / 1024:.2f}MB"
            
            logger.info(f"Successfully downloaded document: {url} -> {file_path} ({downloaded_size / 1024:.2f}KB)")
            
            return file_path, None
            
        except requests.exceptions.Timeout:
            return None, f"Request timeout after {self.timeout} seconds"
        except requests.exceptions.ConnectionError:
            return None, "Connection error - could not reach the server"
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP error: {e.response.status_code} - {e.response.reason}"
        except requests.exceptions.RequestException as e:
            return None, f"Request error: {str(e)}"
        except Exception as e:
            logger.error(f"Error downloading document from {url}: {str(e)}", exc_info=True)
            return None, f"Download error: {str(e)}"
    
    def cleanup_file(self, file_path: str):
        """
        Delete downloaded file.
        
        Args:
            file_path: Path to file to delete
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up downloaded file: {file_path}")
        except Exception as e:
            logger.warning(f"Error cleaning up file {file_path}: {e}")
