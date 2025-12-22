"""
Flask Backend API for Document Quality Verification Pipeline
"""

import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from dotenv import load_dotenv
import logging
from flasgger import Swagger

from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.json_serializer import sanitize_for_json
from src.utils.document_downloader import DocumentDownloader

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_SIZE', 10485760))  # 10MB default
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = set(os.getenv('ALLOWED_EXTENSIONS', 'pdf,png,jpg,jpeg').split(','))

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.getenv('DOWNLOAD_FOLDER', 'downloads'), exist_ok=True)
os.makedirs('cache', exist_ok=True)
os.makedirs('logs', exist_ok=True)

# Setup logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize pipeline orchestrator
orchestrator = PipelineOrchestrator()

# Initialize document downloader
document_downloader = DocumentDownloader(
    download_folder=os.getenv('DOWNLOAD_FOLDER', 'downloads'),
    timeout=int(os.getenv('DOWNLOAD_TIMEOUT', 30)),
    max_size=int(os.getenv('MAX_UPLOAD_SIZE', 10485760))
)

# Initialize Swagger
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/api/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Document Quality Verification Pipeline API",
        "description": "API for verifying document quality using computer vision, OCR, and AI. Supports both manual file uploads and URL-based document processing.",
        "version": "1.0.0",
        "contact": {
            "name": "API Support"
        }
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "tags": [
        {
            "name": "Health",
            "description": "Health check endpoints"
        },
        {
            "name": "Manual Upload",
            "description": "Upload documents directly via multipart/form-data"
        },
        {
            "name": "URL Processing",
            "description": "Process documents from URLs (for RTS API integration)"
        },
        {
            "name": "Information",
            "description": "Get system information and pipeline details"
        }
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/')
def index():
    """Serve frontend index page."""
    return send_from_directory('frontend', 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.
    ---
    tags:
      - Health
    summary: Check API health status
    description: Returns the health status of the API service
    responses:
      200:
        description: API is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
            service:
              type: string
              example: Document Quality Verification Pipeline
            version:
              type: string
              example: 1.0.0
    """
    return jsonify({
        'status': 'healthy',
        'service': 'Document Quality Verification Pipeline',
        'version': '1.0.0'
    })


@app.route('/api/upload', methods=['POST'])
def upload_document():
    """
    Upload and process a single document.
    ---
    tags:
      - Manual Upload
    summary: Upload and process a document file
    description: Upload a document file (PDF or image) and get quality verification results
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: Document file to process (PDF, PNG, JPG, JPEG)
    responses:
      200:
        description: Document processed successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            status:
              type: string
              example: ACCEPTED
            final_quality_score:
              type: number
              example: 85.5
            message:
              type: string
              example: Document quality acceptable
            stage_results:
              type: array
              items:
                type: object
            processing_time_seconds:
              type: number
              example: 12.5
      400:
        description: Bad request (no file, invalid file type)
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: No file provided
      413:
        description: File too large
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: "File too large. Maximum size: 10MB"
      500:
        description: Processing error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: "Processing error: ..."
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # Check file extension
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': f'File type not allowed. Allowed types: {", ".join(app.config["ALLOWED_EXTENSIONS"])}'
            }), 400
        
        # Generate unique filename
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save file
        file.save(file_path)
        logger.info(f"File uploaded: {file.filename} -> {unique_filename}")
        
        # Process document through pipeline
        result = orchestrator.process_document(file_path, temp_dir='cache')
        
        # Add original filename to result
        result['original_filename'] = file.filename
        result['saved_filename'] = unique_filename
        
        # Sanitize result to convert any numpy types to Python native types
        result = sanitize_for_json(result)
        
        # Clean up uploaded file (optional - you may want to keep it)
        # os.remove(file_path)
        
        return jsonify(result)
    
    except RequestEntityTooLarge:
        return jsonify({
            'success': False,
            'error': f'File too large. Maximum size: {app.config["MAX_CONTENT_LENGTH"] / 1024 / 1024}MB'
        }), 413
    
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Processing error: {str(e)}'
        }), 500


@app.route('/api/bulk-upload', methods=['POST'])
def bulk_upload_documents():
    """
    Upload and process multiple documents in bulk.
    ---
    tags:
      - Manual Upload
    summary: Upload and process multiple documents
    description: Upload multiple document files and get quality verification results for each
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: files[]
        type: array
        items:
          type: file
        required: true
        description: Multiple document files to process (PDF, PNG, JPG, JPEG). Maximum 50 files.
    responses:
      200:
        description: Documents processed successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            summary:
              type: object
              properties:
                total_files:
                  type: integer
                  example: 5
                successful:
                  type: integer
                  example: 5
                failed:
                  type: integer
                  example: 0
                accepted:
                  type: integer
                  example: 3
                rejected:
                  type: integer
                  example: 2
                flagged_for_review:
                  type: integer
                  example: 0
            results:
              type: array
              items:
                type: object
                properties:
                  filename:
                    type: string
                  status:
                    type: string
                  score:
                    type: number
                  reason:
                    type: string
            errors:
              type: array
              items:
                type: object
      400:
        description: Bad request
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
      413:
        description: Total file size too large
      500:
        description: Processing error
    """
    try:
        # Check if files are present
        if 'files[]' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No files provided'
            }), 400
        
        files = request.files.getlist('files[]')
        
        if len(files) == 0:
            return jsonify({
                'success': False,
                'error': 'No files selected'
            }), 400
        
        # Limit number of files (configurable)
        max_files = int(os.getenv('MAX_BULK_FILES', 50))
        if len(files) > max_files:
            return jsonify({
                'success': False,
                'error': f'Too many files. Maximum {max_files} files allowed per bulk upload.'
            }), 400
        
        results = []
        errors = []
        
        # Process each file
        for idx, file in enumerate(files):
            file_result = {
                'filename': file.filename,
                'index': idx + 1,
                'success': False,
                'status': None,
                'score': None,
                'reason': None,
                'error': None
            }
            
            try:
                # Check file extension
                if not allowed_file(file.filename):
                    file_result['error'] = f'Invalid file type. Allowed: {", ".join(app.config["ALLOWED_EXTENSIONS"])}'
                    errors.append(file_result)
                    continue
                
                # Generate unique filename
                file_extension = file.filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{uuid.uuid4()}.{file_extension}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                # Save file
                file.save(file_path)
                logger.info(f"Bulk upload - File {idx+1}/{len(files)}: {file.filename} -> {unique_filename}")
                
                # Process document through pipeline
                result = orchestrator.process_document(file_path, temp_dir='cache')
                
                # Extract key information
                file_result['success'] = result.get('success', False)
                file_result['status'] = result.get('status', 'UNKNOWN')
                file_result['score'] = result.get('final_quality_score', 0)
                
                # Handle multi-page PDFs
                if result.get('total_pages') and result['total_pages'] > 1:
                    # Multi-page PDF - check if any page passed
                    if result.get('page_results'):
                        passed_pages = [p for p in result['page_results'] if p['status'] == 'ACCEPTED']
                        if passed_pages:
                            file_result['status'] = 'ACCEPTED'
                            file_result['reason'] = f"{len(passed_pages)} of {result['total_pages']} page(s) passed quality checks"
                            # Use best page's OCR confidence
                            best_page = result.get('best_page', 1)
                            best_page_result = next((p for p in result['page_results'] if p['page_number'] == best_page), None)
                            if best_page_result:
                                file_result['ocr_confidence'] = best_page_result.get('ocr_confidence')
                        else:
                            # All pages failed
                            file_result['status'] = 'REJECTED'
                            file_result['reason'] = f"All {result['total_pages']} pages failed quality checks"
                            # Use best page's OCR confidence
                            best_page = result.get('best_page', 1)
                            best_page_result = next((p for p in result['page_results'] if p['page_number'] == best_page), None)
                            if best_page_result:
                                file_result['ocr_confidence'] = best_page_result.get('ocr_confidence')
                    else:
                        # Fallback to main result
                        file_result['status'] = result.get('status', 'UNKNOWN')
                        file_result['reason'] = result.get('message', 'Multi-page document processed')
                else:
                    # Single page or image
                    # Get one-line reason
                    if result.get('critical_failures') and len(result['critical_failures']) > 0:
                        file_result['reason'] = result['critical_failures'][0]
                    elif result.get('message'):
                        file_result['reason'] = result['message']
                    elif result.get('status') == 'ACCEPTED':
                        file_result['reason'] = 'Document quality acceptable'
                    elif result.get('status') == 'REJECTED':
                        file_result['reason'] = 'Document quality too low'
                    else:
                        file_result['reason'] = 'Needs review'
                
                # Add OCR confidence if not already set
                if 'ocr_confidence' not in file_result:
                    if result.get('stage_results'):
                        for stage in result['stage_results']:
                            if 'OCR Confidence Analysis' in stage.get('stage', ''):
                                if stage.get('analysis') and 'average_confidence' in stage['analysis']:
                                    file_result['ocr_confidence'] = stage['analysis']['average_confidence']
                                    break
                
                file_result['processing_time'] = result.get('processing_time_seconds', 0)
                file_result['total_pages'] = result.get('total_pages', 1)
                file_result['original_filename'] = file.filename
                file_result['saved_filename'] = unique_filename
                
                results.append(file_result)
                
            except Exception as e:
                logger.error(f"Error processing file {file.filename} in bulk upload: {str(e)}", exc_info=True)
                file_result['error'] = f'Processing error: {str(e)}'
                errors.append(file_result)
        
        # Calculate summary statistics
        total_files = len(files)
        successful = len([r for r in results if r['success']])
        accepted = len([r for r in results if r['status'] == 'ACCEPTED'])
        rejected = len([r for r in results if r['status'] == 'REJECTED'])
        flagged = len([r for r in results if r['status'] == 'FLAG_FOR_REVIEW'])
        
        return jsonify({
            'success': True,
            'summary': {
                'total_files': total_files,
                'successful': successful,
                'failed': len(errors),
                'accepted': accepted,
                'rejected': rejected,
                'flagged_for_review': flagged
            },
            'results': results,
            'errors': errors
        })
    
    except RequestEntityTooLarge:
        return jsonify({
            'success': False,
            'error': f'Total file size too large. Maximum size: {app.config["MAX_CONTENT_LENGTH"] / 1024 / 1024}MB'
        }), 413
    
    except Exception as e:
        logger.error(f"Error in bulk upload: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Bulk upload error: {str(e)}'
        }), 500


@app.route('/api/process-url', methods=['POST'])
def process_document_from_url():
    """
    Download and process a document from URL.
    ---
    tags:
      - URL Processing
    summary: Process a document from URL
    description: Download a document from a URL and get quality verification results. Useful for RTS API integration.
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - url
          properties:
            url:
              type: string
              format: uri
              example: https://example.com/document.pdf
              description: URL of the document to download and process
            filename:
              type: string
              example: my_document
              description: Optional custom filename (without extension)
    responses:
      200:
        description: Document processed successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            status:
              type: string
              example: ACCEPTED
            final_quality_score:
              type: number
              example: 85.5
            source:
              type: string
              example: url
            source_url:
              type: string
              example: https://example.com/document.pdf
            downloaded_filename:
              type: string
              example: my_document.pdf
            stage_results:
              type: array
              items:
                type: object
      400:
        description: Bad request (invalid URL, download failed)
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: "Download failed: Invalid URL format"
      500:
        description: Processing error
    """
    try:
        # Check if request is JSON
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON with Content-Type: application/json'
            }), 400
        
        data = request.get_json()
        
        # Check if URL is provided
        if 'url' not in data or not data['url']:
            return jsonify({
                'success': False,
                'error': 'URL is required'
            }), 400
        
        url = data['url']
        custom_filename = data.get('filename', None)
        
        logger.info(f"Processing document from URL: {url}")
        
        # Download document
        file_path, error = document_downloader.download_document(url, custom_filename)
        
        if error:
            return jsonify({
                'success': False,
                'error': f'Download failed: {error}'
            }), 400
        
        if not file_path:
            return jsonify({
                'success': False,
                'error': 'Download failed: Unknown error'
            }), 500
        
        try:
            # Process document through pipeline
            result = orchestrator.process_document(file_path, temp_dir='cache')
            
            # Add metadata
            result['source'] = 'url'
            result['source_url'] = url
            result['downloaded_filename'] = os.path.basename(file_path)
            
            # Sanitize result
            result = sanitize_for_json(result)
            
            # Clean up downloaded file (optional - you may want to keep it)
            # document_downloader.cleanup_file(file_path)
            
            
            return jsonify(result)
        
        except Exception as e:
            # Clean up file on processing error
            document_downloader.cleanup_file(file_path)
            raise
    
    except Exception as e:
        logger.error(f"Error processing document from URL: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Processing error: {str(e)}'
        }), 500


@app.route('/api/bulk-process-urls', methods=['POST'])
def bulk_process_documents_from_urls():
    """
    Download and process multiple documents from URLs.
    ---
    tags:
      - URL Processing
    summary: Process multiple documents from URLs
    description: Download multiple documents from URLs and get quality verification results for each. Useful for bulk processing from RTS API.
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - urls
          properties:
            urls:
              type: array
              items:
                type: string
                format: uri
              example: ["https://example.com/doc1.pdf", "https://example.com/doc2.pdf"]
              description: Array of document URLs to download and process
            filenames:
              type: array
              items:
                type: string
              example: ["doc1", "doc2"]
              description: Optional array of custom filenames (must match urls array length)
    responses:
      200:
        description: Documents processed successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            summary:
              type: object
              properties:
                total_urls:
                  type: integer
                  example: 5
                successful:
                  type: integer
                  example: 5
                failed:
                  type: integer
                  example: 0
                accepted:
                  type: integer
                  example: 3
                rejected:
                  type: integer
                  example: 2
            results:
              type: array
              items:
                type: object
                properties:
                  url:
                    type: string
                  status:
                    type: string
                  score:
                    type: number
                  reason:
                    type: string
            errors:
              type: array
              items:
                type: object
      400:
        description: Bad request (invalid URLs, download failed)
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
      500:
        description: Processing error
    """
    try:
        # Check if request is JSON
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON with Content-Type: application/json'
            }), 400
        
        data = request.get_json()
        
        # Check if URLs are provided
        if 'urls' not in data or not isinstance(data['urls'], list):
            return jsonify({
                'success': False,
                'error': 'URLs array is required'
            }), 400
        
        urls = data['urls']
        custom_filenames = data.get('filenames', [None] * len(urls))
        
        if len(urls) == 0:
            return jsonify({
                'success': False,
                'error': 'No URLs provided'
            }), 400
        
        # Validate filenames array length
        if len(custom_filenames) != len(urls):
            return jsonify({
                'success': False,
                'error': 'filenames array length must match urls array length'
            }), 400
        
        # Limit number of URLs (configurable)
        max_urls = int(os.getenv('MAX_BULK_FILES', 50))
        if len(urls) > max_urls:
            return jsonify({
                'success': False,
                'error': f'Too many URLs. Maximum {max_urls} URLs allowed per bulk request.'
            }), 400
        
        results = []
        errors = []
        downloaded_files = []  # Track downloaded files for cleanup
        
        # Process each URL
        for idx, url in enumerate(urls):
            file_result = {
                'url': url,
                'index': idx + 1,
                'success': False,
                'status': None,
                'score': None,
                'reason': None,
                'error': None
            }
            
            try:
                custom_filename = custom_filenames[idx] if custom_filenames[idx] else None
                
                logger.info(f"Bulk processing - URL {idx+1}/{len(urls)}: {url}")
                
                # Download document
                file_path, download_error = document_downloader.download_document(url, custom_filename)
                
                if download_error:
                    file_result['error'] = f'Download failed: {download_error}'
                    errors.append(file_result)
                    continue
                
                if not file_path:
                    file_result['error'] = 'Download failed: Unknown error'
                    errors.append(file_result)
                    continue
                
                downloaded_files.append(file_path)
                
                try:
                    # Process document through pipeline
                    result = orchestrator.process_document(file_path, temp_dir='cache')
                    
                    # Extract key information (same logic as bulk upload)
                    file_result['success'] = result.get('success', False)
                    file_result['status'] = result.get('status', 'UNKNOWN')
                    file_result['score'] = result.get('final_quality_score', 0)
                    
                    # Handle multi-page PDFs
                    if result.get('total_pages') and result['total_pages'] > 1:
                        if result.get('page_results'):
                            passed_pages = [p for p in result['page_results'] if p['status'] == 'ACCEPTED']
                            if passed_pages:
                                file_result['status'] = 'ACCEPTED'
                                file_result['reason'] = f"{len(passed_pages)} of {result['total_pages']} page(s) passed quality checks"
                                best_page = result.get('best_page', 1)
                                best_page_result = next((p for p in result['page_results'] if p['page_number'] == best_page), None)
                                if best_page_result:
                                    file_result['ocr_confidence'] = best_page_result.get('ocr_confidence')
                            else:
                                file_result['status'] = 'REJECTED'
                                file_result['reason'] = f"All {result['total_pages']} pages failed quality checks"
                                best_page = result.get('best_page', 1)
                                best_page_result = next((p for p in result['page_results'] if p['page_number'] == best_page), None)
                                if best_page_result:
                                    file_result['ocr_confidence'] = best_page_result.get('ocr_confidence')
                        else:
                            file_result['status'] = result.get('status', 'UNKNOWN')
                            file_result['reason'] = result.get('message', 'Multi-page document processed')
                    else:
                        # Single page or image
                        if result.get('critical_failures') and len(result['critical_failures']) > 0:
                            file_result['reason'] = result['critical_failures'][0]
                        elif result.get('message'):
                            file_result['reason'] = result['message']
                        elif result.get('status') == 'ACCEPTED':
                            file_result['reason'] = 'Document quality acceptable'
                        elif result.get('status') == 'REJECTED':
                            file_result['reason'] = 'Document quality too low'
                        else:
                            file_result['reason'] = 'Needs review'
                    
                    # Add OCR confidence if not already set
                    if 'ocr_confidence' not in file_result:
                        if result.get('stage_results'):
                            for stage in result['stage_results']:
                                if 'OCR Confidence Analysis' in stage.get('stage', ''):
                                    if stage.get('analysis') and 'average_confidence' in stage['analysis']:
                                        file_result['ocr_confidence'] = stage['analysis']['average_confidence']
                                        break
                    
                    file_result['processing_time'] = result.get('processing_time_seconds', 0)
                    file_result['total_pages'] = result.get('total_pages', 1)
                    file_result['downloaded_filename'] = os.path.basename(file_path)
                    file_result['source'] = 'url'
                    file_result['source_url'] = url
                    
                    results.append(file_result)
                
                except Exception as e:
                    logger.error(f"Error processing file from URL {url}: {str(e)}", exc_info=True)
                    file_result['error'] = f'Processing error: {str(e)}'
                    errors.append(file_result)
                    # Clean up file on processing error
                    document_downloader.cleanup_file(file_path)
                    downloaded_files.remove(file_path)
            
            except Exception as e:
                logger.error(f"Error downloading/processing URL {url}: {str(e)}", exc_info=True)
                file_result['error'] = f'Error: {str(e)}'
                errors.append(file_result)
        
        # Clean up all downloaded files (optional - you may want to keep them)
        # for file_path in downloaded_files:
        #     document_downloader.cleanup_file(file_path)
        
        # Calculate summary statistics
        total_urls = len(urls)
        successful = len([r for r in results if r['success']])
        accepted = len([r for r in results if r['status'] == 'ACCEPTED'])
        rejected = len([r for r in results if r['status'] == 'REJECTED'])
        flagged = len([r for r in results if r['status'] == 'FLAG_FOR_REVIEW'])
        
        return jsonify({
            'success': True,
            'summary': {
                'total_urls': total_urls,
                'successful': successful,
                'failed': len(errors),
                'accepted': accepted,
                'rejected': rejected,
                'flagged_for_review': flagged
            },
            'results': results,
            'errors': errors
        })
    
    except Exception as e:
        logger.error(f"Error in bulk URL processing: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Bulk processing error: {str(e)}'
        }), 500


@app.route('/api/stages', methods=['GET'])
def get_stages_info():
    """
    Get information about pipeline stages.
    ---
    tags:
      - Information
    summary: Get pipeline stage information
    description: Returns detailed information about all quality verification stages
    responses:
      200:
        description: Pipeline stages information
        schema:
          type: object
          properties:
            stages:
              type: array
              items:
                type: object
                properties:
                  stage:
                    type: integer
                    example: 1
                  name:
                    type: string
                    example: Basic Quality Checks
                  technology:
                    type: string
                    example: OpenCV
                  processing_time:
                    type: string
                    example: 50-100ms
                  checks:
                    type: array
                    items:
                      type: string
    """
    return jsonify({
        'stages': [
            {
                'stage': 1,
                'name': 'Basic Quality Checks',
                'technology': 'OpenCV',
                'processing_time': '50-100ms',
                'checks': [
                    'Resolution',
                    'Blur Detection',
                    'Brightness',
                    'Contrast',
                    'White Space',
                    'Skew Detection'
                ]
            },
            {
                'stage': 2,
                'name': 'OCR Confidence Analysis',
                'technology': 'Tesseract OCR',
                'processing_time': '2-5 seconds',
                'checks': [
                    'Average Confidence',
                    'High Confidence Words',
                    'Text Regions',
                    'Character Count'
                ]
            },
            {
                'stage': 3,
                'name': 'Handwriting Detection',
                'technology': 'Computer Vision',
                'processing_time': '0.5-2 seconds',
                'checks': [
                    'Stroke Width Variance',
                    'Baseline Variance',
                    'Character Spacing',
                    'Connected Components'
                ]
            },
            {
                'stage': 4,
                'name': 'Overall Quality Score',
                'technology': 'BRISQUE',
                'processing_time': '100-200ms',
                'checks': [
                    'Blind Image Quality Assessment'
                ]
            }
        ]
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {str(error)}", exc_info=True)
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    logger.info(f"Starting Document Quality Verification Pipeline on {host}:{port}")
    app.run(host=host, port=port, debug=debug)

