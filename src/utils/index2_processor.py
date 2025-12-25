"""
Index-II Document Processor
Main component that routes documents to Index-II specialized pipeline or general pipeline.
"""

import logging
from typing import Dict, Optional
import os

from src.utils.index2_detector import Index2Detector
from src.utils.index2_validator import Index2Validator

logger = logging.getLogger(__name__)


class Index2Processor:
    """
    Main processor for Index-II documents.
    Routes documents to specialized Index-II validation or general pipeline.
    """
    
    def __init__(self):
        """Initialize Index-II processor."""
        self.detector = Index2Detector()
        self.validator = Index2Validator()
        self.enabled = os.getenv('INDEX2_PROCESSOR_ENABLED', 'true').lower() == 'true'
    
    def process_document(self, image_path: str, 
                        use_general_pipeline: bool = True,
                        general_pipeline_func: Optional[callable] = None) -> Dict:
        """
        Process document - route to Index-II pipeline if detected, otherwise use general pipeline.
        
        Args:
            image_path: Path to the image file
            use_general_pipeline: Whether to fall back to general pipeline if not Index-II
            general_pipeline_func: Function to call for general document processing
            
        Returns:
            dict with validation results
        """
        if not self.enabled:
            logger.info("Index-II processor is disabled, using general pipeline")
            if use_general_pipeline and general_pipeline_func:
                return general_pipeline_func(image_path)
            return {
                'decision': 'REJECT',
                'score': 0,
                'rejection_reason': 'Index-II processor disabled',
                'document_type': 'UNKNOWN'
            }
        
        try:
            # Step 1: Detect if document is Index-II
            detection = self.detector.is_index2_document(image_path)
            
            logger.info(
                f"Index-II detection: is_index2={detection['is_index2']}, "
                f"confidence={detection['confidence']:.2f}, "
                f"method={detection.get('detection_method', 'unknown')}"
            )
            
            if detection['is_index2'] and detection['confidence'] >= 0.6:
                # Use specialized Index-II pipeline
                logger.info("Routing to Index-II specialized pipeline")
                result = self.validator.validate_index2(image_path)
                
                # Convert decision format to match general pipeline
                status = 'ACCEPTED' if result['decision'] == 'ACCEPT' else 'REJECTED'
                
                # Check if rejection reason indicates it's NOT actually Index-II
                # (e.g., handwritten documents shouldn't be classified as Index-II)
                rejection_reason = result.get('rejection_reason', '')
                is_actually_index2 = True
                if status == 'REJECTED':
                    # If rejected for being handwritten, it's probably NOT Index-II
                    # Index-II documents are always printed
                    if 'handwritten' in rejection_reason.lower():
                        logger.warning("Document rejected for being handwritten - likely NOT Index-II, may be misclassified")
                        is_actually_index2 = False
                
                return {
                    'status': status,
                    'final_quality_score': result['score'],
                    'decision': result['decision'],
                    'document_type': 'INDEX-II' if is_actually_index2 else 'GENERAL',
                    'detection_confidence': detection['confidence'],
                    'detection_method': detection.get('detection_method', 'unknown'),
                    'indicators_found': detection.get('indicators_found', []),
                    'message': self._format_message(result, detection, is_actually_index2),
                    'rejection_reason': rejection_reason,
                    'validation_details': result.get('validation_details', {}),
                    'index2_processing': True,
                    'is_actually_index2': is_actually_index2
                }
            else:
                # Not Index-II - use general pipeline
                logger.info(
                    f"Document is not Index-II (confidence: {detection['confidence']:.2f}), "
                    f"routing to general pipeline"
                )
                
                if use_general_pipeline and general_pipeline_func:
                    general_result = general_pipeline_func(image_path)
                    general_result['document_type'] = 'GENERAL'
                    general_result['index2_detection_confidence'] = detection['confidence']
                    return general_result
                else:
                    return {
                        'status': 'REJECTED',
                        'final_quality_score': 0,
                        'decision': 'REJECT',
                        'document_type': 'GENERAL',
                        'message': 'Document is not Index-II and general pipeline not available',
                        'rejection_reason': 'Not Index-II document',
                        'index2_processing': False
                    }
                    
        except Exception as e:
            logger.error(f"Index-II processing failed: {e}", exc_info=True)
            
            # Fallback to general pipeline on error
            if use_general_pipeline and general_pipeline_func:
                logger.warning("Falling back to general pipeline due to error")
                return general_pipeline_func(image_path)
            
            return {
                'status': 'REJECTED',
                'final_quality_score': 0,
                'decision': 'REJECT',
                'document_type': 'UNKNOWN',
                'message': f'Index-II processing error: {str(e)}',
                'rejection_reason': 'Processing error',
                'index2_processing': False,
                'error': str(e)
            }
    
    def _format_message(self, result: Dict, detection: Dict, is_actually_index2: bool = True) -> str:
        """Format user-friendly message for Index-II processing."""
        if result['decision'] == 'ACCEPT':
            # Generic message without document type name
            return (
                f"Document accepted (score: {result['score']:.1f}/100). "
                f"Document structure verified with {len(detection.get('indicators_found', []))} authenticity markers."
            )
        else:
            reason = result.get('rejection_reason', 'Quality below threshold')
            # Generic rejection message without mentioning document type
            return (
                f"Document rejected: {reason}. "
                f"Score: {result['score']:.1f}/100"
            )
