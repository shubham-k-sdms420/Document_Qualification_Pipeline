# Document Quality Verification Pipeline

Automated quality verification system for government documents (NOC, No Dues, Index-II) before LLM processing. **100% local processing, zero ongoing costs.**

## About the Project

This pipeline filters out low-quality documents before they reach expensive LLM processing, reducing costs by 50-60% and manual review by 70-80%. It uses a 4-stage cascading quality check system that evaluates documents based on image quality, OCR readability, handwriting detection, and overall quality metrics.

**Problem Solved:** Prevents wasted LLM API calls on unreadable, handwritten, or corrupted documents by catching quality issues early.

## Tech Stack

- **Backend:** Python 3.11, Flask 3.0.0
- **Image Processing:** OpenCV 4.8.1, Pillow 10.1.0
- **OCR:** Tesseract (English, Hindi, Marathi)
- **PDF Processing:** pdf2image, poppler-utils
- **Quality Assessment:** scikit-image (BRISQUE)
- **ML/AI:** PyTorch, Transformers (Florence-2 for handwriting detection)
- **API Documentation:** Flasgger (Swagger/OpenAPI)
- **Production Server:** Gunicorn (4 workers)
- **Containerization:** Docker, Docker Compose

## Quick Start

### Docker (Recommended)

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Access:** `http://localhost:5000` | **API Docs:** `http://localhost:5000/api/docs`

### Linux Setup (Local Installation)

```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    tesseract-ocr-mar \
    poppler-utils \
    python3-pip \
    python3-venv

# 2. Clone repository
git clone https://github.com/shubham-k-sdms420/Document_Qualification_Pipeline.git
cd Document_Qualification_Pipeline

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 5. Configure environment
cp env.example .env
# Edit .env file with your settings (optional)

# 6. Create necessary directories
mkdir -p uploads downloads cache logs

# 7. Run the application
python app.py
```

The application will start on `http://localhost:5000`

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Document Upload/URL                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  PDF Converter │ (if PDF)
                    └────────┬───────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │      Index-II Detection (Optional)      │
        │  ┌──────────────────────────────────┐  │
        │  │ Content-based detection           │  │
        │  │ - Text markers (Marathi/English) │  │
        │  │ - Visual structure (barcode/seal)│  │
        │  │ - Negative signals (NOC/Agreement)│  │
        │  └──────────────────────────────────┘  │
        └────────────┬─────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                        │
        ▼                        ▼
┌───────────────┐      ┌──────────────────┐
│ Index-II     │      │ General Pipeline  │
│ Pipeline     │      │                   │
│ (Lenient)    │      │                   │
└──────┬───────┘      └─────────┬─────────┘
       │                        │
       └────────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │   Stage 1: Basic     │
        │   Quality Check      │
        │   (35% weight)       │
        │ - Resolution         │
        │ - Blur detection     │
        │ - Brightness/Contrast│
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │   Stage 2: OCR       │
        │   Confidence         │
        │   (40% weight)       │
        │ - Text extraction    │
        │ - Confidence scores  │
        │ - Readability check  │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │   Stage 3: Handwriting│
        │   Detection          │
        │   (20% weight)       │
        │ - Printed vs written │
        │ - Florence-2 override│
        │ - Bold text handling │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │   Stage 4: BRISQUE    │
        │   Quality Score       │
        │   (5% weight)         │
        │ - Overall quality     │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │   Consensus Decision │
        │   - Weighted scoring  │
        │   - OCR overrides     │
        │   - Final verdict     │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │   ACCEPT / REJECT    │
        │   / FLAG FOR REVIEW  │
        └───────────────────────┘
```

## Directory Structure

```
Document_Qualification_Pipeline/
│
├── app.py                      # Flask application entry point
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker container configuration
├── docker-compose.yml          # Docker Compose configuration
├── gunicorn_config.py          # Gunicorn server configuration
├── env.example                 # Environment variables template
├── setup.sh                    # Setup script for local installation
│
├── src/                        # Source code
│   ├── __init__.py
│   │
│   ├── pipeline/              # Pipeline orchestration
│   │   ├── __init__.py
│   │   └── orchestrator.py    # Main pipeline coordinator
│   │
│   ├── stages/                 # Quality check stages
│   │   ├── __init__.py
│   │   ├── stage1_basic_quality.py      # Basic quality checks
│   │   ├── stage2_ocr_confidence.py    # OCR analysis
│   │   ├── stage3_handwriting_detection.py  # Handwriting detection
│   │   └── stage4_brisque_quality.py   # BRISQUE scoring
│   │
│   └── utils/                  # Utility modules
│       ├── __init__.py
│       ├── pdf_converter.py           # PDF to image conversion
│       ├── image_processor.py         # Image preprocessing
│       ├── json_serializer.py         # JSON serialization helpers
│       ├── document_downloader.py     # URL-based document download
│       ├── florence_classifier.py     # Florence-2 ML classifier
│       ├── index2_detector.py         # Index-II document detection
│       ├── index2_processor.py       # Index-II specialized processor
│       └── index2_validator.py       # Index-II validation logic
│
├── frontend/                   # Web interface
│   ├── index.html
│   ├── script.js
│   └── styles.css
│
├── uploads/                    # Uploaded documents (created at runtime)
├── downloads/                  # Downloaded documents (created at runtime)
├── cache/                      # Processing cache (created at runtime)
├── logs/                       # Application logs (created at runtime)
│
└── Documents/                  # Test documents (optional)
```

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

## Index-II Specialized Processor

**Detection:** Content-based (text markers, visual structure, negative signals)  
**Validation:** Lenient (OCR ≥ 30%, Score ≥ 50)  
**Bold Text:** OCR ≥ 70% trusted over handwriting detection  
**Routing:** Confidence ≥ 0.60 → Index-II pipeline, < 0.60 → General pipeline

## Performance

- **Processing Time:** 3-8 seconds/document
- **Accuracy:** 85%+ correct decisions
- **Cost Savings:** 50-60% LLM cost reduction
- **Manual Review Reduction:** 70-80%

## Configuration

Key environment variables (see `env.example`):

```env
# Quality Thresholds
OCR_CRITICAL_THRESHOLD=25
BLUR_CRITICAL_THRESHOLD=30
BRIGHTNESS_CRITICAL_MAX=300
HANDWRITING_CRITICAL_THRESHOLD=30

# Scoring
SCORE_ACCEPT_THRESHOLD=70
SCORE_REVIEW_THRESHOLD=50

# Index-II Processor
INDEX2_PROCESSOR_ENABLED=true
INDEX2_MIN_OCR_CONFIDENCE=30
INDEX2_MIN_ACCEPT_SCORE=50

# Gunicorn (Docker)
GUNICORN_WORKERS=4
```

## Recent Updates (v1.5.0)

- ✅ Docker support with Gunicorn (4 workers)
- ✅ Simplified user messages (no technical details)
- ✅ Index-II bold text handling (OCR ≥ 70% trusted)
- ✅ Agreement/Will routing fixes (negative signals)
- ✅ Stricter Index-II detection (only exact markers)

---

**Version:** 1.5.0 | **Last Updated:** December 2025
