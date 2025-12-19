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

from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.json_serializer import sanitize_for_json

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
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'Document Quality Verification Pipeline',
        'version': '1.0.0'
    })


@app.route('/api/upload', methods=['POST'])
def upload_document():
    """
    Upload and process a document.
    
    Expected: multipart/form-data with 'file' field
    Returns: JSON with processing results
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
    
    Expected: multipart/form-data with 'files[]' field (multiple files)
    Returns: JSON with processing results for each document
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


@app.route('/api/stages', methods=['GET'])
def get_stages_info():
    """Get information about pipeline stages."""
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

