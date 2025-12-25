# Document Quality Verification Pipeline

Automated quality verification system for government documents (NOC, No Dues, Index-II) before LLM processing. **100% local processing, zero ongoing costs.**

## Quick Start

```bash
cd /home/stark/Desktop/Doc_verifier_Qualification_Pipeline
chmod +x setup.sh && ./setup.sh
source venv/bin/activate
cp env.example .env
python app.py
```

Access: `http://localhost:5000` | API Docs: `http://localhost:5000/api/docs`

## What It Does

**Accepts:** Readable printed documents (OCR ≥ 50%), documents with signatures/stamps, slightly blurry but readable scans  
**Rejects:** Unreadable documents (OCR < 25%), handwritten documents, corrupted files

**Key Principle:** If OCR can read it (≥ 50%), accept even if image quality is imperfect.

## Features

- Single & bulk upload (up to 50 documents)
- Multi-page PDF processing (smart page selection)
- URL-based processing (RTS API integration)
- Index-II specialized processor (lenient validation)
- Swagger API documentation
- Simplified user messages (no technical jargon)

## System Architecture

4-stage cascading filter (3-8 seconds per document):

1. **Basic Quality** (50-100ms, 35% weight): Resolution, blur, brightness, contrast
2. **OCR Confidence** (2-5s, 40% weight): Text readability, confidence scores
3. **Handwriting Detection** (0.5-2s, 20% weight): Printed vs handwritten
4. **BRISQUE Quality** (100-200ms, 5% weight): Overall image quality

## Installation

### Prerequisites

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr poppler-utils

# macOS
brew install tesseract poppler
```

### Setup

```bash
./setup.sh
source venv/bin/activate
cp env.example .env
python app.py
```

## Configuration (.env)

### Key Thresholds

```env
# Quality Thresholds
OCR_CRITICAL_THRESHOLD=25          # Reject if < 25%
BLUR_CRITICAL_THRESHOLD=30        # Reject if < 30% AND OCR < 30%
BRIGHTNESS_CRITICAL_MAX=300       # Accept up to 300
HANDWRITING_CRITICAL_THRESHOLD=30 # Reject if ≥ 30%

# Scoring
SCORE_ACCEPT_THRESHOLD=70        # Accept if ≥ 70
SCORE_REVIEW_THRESHOLD=50        # Flag if 50-69

# Index-II Processor
INDEX2_PROCESSOR_ENABLED=true
INDEX2_MIN_OCR_CONFIDENCE=30     # Lenient for Index-II
INDEX2_MIN_ACCEPT_SCORE=50       # Lower threshold
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/upload` | POST | Single document upload |
| `/api/bulk-upload` | POST | Bulk upload (up to 50) |
| `/api/process-url` | POST | Process from URL |
| `/api/bulk-process-urls` | POST | Bulk process from URLs |
| `/api/docs` | GET | Swagger documentation |

## Quality Score

```
Final Score = (Stage1 × 35%) + (Stage2 × 40%) + (Stage3 × 20%) + (Stage4 × 5%)
```

**Acceptance:**
- Score ≥ 70 → ✅ ACCEPTED
- Score ≥ 60 + OCR ≥ 60% → ✅ ACCEPTED
- Score ≥ 55 + OCR ≥ 80% → ✅ ACCEPTED
- Score 50-69 → ⚠️ FLAG FOR REVIEW
- Score < 50 → ❌ REJECTED

**OCR-Based Override:**
- OCR ≥ 80% → Accept with score ≥ 55 (trust OCR over handwriting)
- OCR ≥ 60% → Accept with score ≥ 60
- OCR ≥ 50% → Filter blur/handwriting false positives

## Index-II Specialized Processor

**Detection:** Content-based (text markers, visual structure, negative signals)  
**Validation:** Lenient (OCR ≥ 30%, Score ≥ 50)  
**Bold Text:** OCR ≥ 70% trusted over handwriting detection  
**Routing:** Confidence ≥ 0.60 → Index-II pipeline, < 0.60 → General pipeline

**Negative Signals:** NOC, No Dues, Agreement, Will, Testament (prevent misrouting)

## Performance

- **Processing Time:** 3-8 seconds/document
- **Accuracy:** 85%+ correct decisions
- **Cost Savings:** 50-60% LLM cost reduction
- **Manual Review Reduction:** 70-80%
- **Acceptance Rate:** 50-55% reach LLM

## Recent Updates (v1.5.0)

- ✅ Simplified user messages (no technical details)
- ✅ Index-II bold text handling (OCR ≥ 70% trusted)
- ✅ Agreement/Will routing fixes (negative signals)
- ✅ Stricter Index-II detection (only exact markers)

---

**Version:** 1.5.0 | **Last Updated:** December 2025
