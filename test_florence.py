#!/usr/bin/env python3
"""
Test script for Florence-2 document classifier.
Tests Florence on sample documents to verify integration.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.florence_classifier import get_florence_instance

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_florence_on_samples():
    """Test Florence on sample documents"""
    
    # Initialize Florence classifier
    florence = get_florence_instance()
    
    if not florence.enabled:
        logger.warning("Florence classifier is disabled. Set FLORENCE_ENABLED=true to enable.")
        return
    
    # Test documents (adjust paths as needed)
    test_cases = [
        {
            'path': 'Documents/invoice.pdf',
            'expected': 'printed',
            'description': 'Invoice document (should be printed)'
        },
        {
            'path': 'Documents/Society NOC3.pdf',
            'expected': 'printed',
            'description': 'NOC document (should be printed)'
        },
        # Add more test cases as needed
    ]
    
    print("\n" + "="*70)
    print("Florence-2 Document Classification Test")
    print("="*70)
    
    for i, test_case in enumerate(test_cases, 1):
        doc_path = test_case['path']
        expected = test_case['expected']
        description = test_case['description']
        
        if not os.path.exists(doc_path):
            logger.warning(f"Test file not found: {doc_path} - skipping")
            continue
        
        print(f"\n[{i}/{len(test_cases)}] Testing: {description}")
        print(f"File: {doc_path}")
        print("-" * 70)
        
        try:
            result = florence.classify_document(doc_path)
            
            if result.get('error'):
                print(f"❌ Error: {result.get('error')}")
                continue
            
            is_printed = result.get('is_printed', False)
            confidence = result.get('confidence', 0)
            explanation = result.get('explanation', '')
            raw_scores = result.get('raw_scores', {})
            
            classification = "PRINTED" if is_printed else "HANDWRITTEN"
            match = (is_printed and expected == 'printed') or (not is_printed and expected == 'handwritten')
            
            status = "✅ PASS" if match else "❌ FAIL"
            
            print(f"Classification: {classification}")
            print(f"Confidence: {confidence:.1%}")
            print(f"Expected: {expected.upper()}")
            print(f"Result: {status}")
            print(f"Keyword Scores: {raw_scores}")
            print(f"Explanation (first 200 chars): {explanation[:200]}...")
            
        except Exception as e:
            logger.error(f"Test failed for {doc_path}: {e}", exc_info=True)
            print(f"❌ Exception: {str(e)}")
    
    print("\n" + "="*70)
    print("Test completed!")
    print("="*70)


def test_florence_quick_check():
    """Quick test to verify Florence is working"""
    
    print("\n" + "="*70)
    print("Quick Florence Availability Check")
    print("="*70)
    
    try:
        florence = get_florence_instance()
        
        print(f"Florence enabled: {florence.enabled}")
        print(f"Device: {florence.device}")
        print(f"Model loaded: {florence._model_loaded}")
        
        if florence.enabled:
            print("\n✅ Florence classifier is available and enabled")
            print("   Model will load on first classification call")
        else:
            print("\n⚠️  Florence classifier is disabled")
            print("   Set FLORENCE_ENABLED=true in .env to enable")
            
    except Exception as e:
        print(f"\n❌ Error initializing Florence: {e}")
        logger.error(f"Florence initialization error: {e}", exc_info=True)


if __name__ == "__main__":
    # Quick check first
    test_florence_quick_check()
    
    # Run full tests if documents are available
    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        test_florence_on_samples()
    else:
        print("\n💡 Tip: Run with --full flag to test on sample documents")
        print("   python test_florence.py --full")
