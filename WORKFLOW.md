# Document Quality Verification Pipeline - Workflow Guide

## Overview

Automated quality control system for PMC documents (No Dues Certificates, NOC, Index II) that filters unreadable documents before expensive LLM processing.

**Benefits:** 50-60% cost reduction, 70-80% less manual review, 100% local processing

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│     DOCUMENT INPUT (Manual Upload OR URL Download)          │
│  • Manual: Upload PDF/PNG/JPG/JPEG via web/form             │
│  • URL: Download from RTS API or external source            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              FILE PREPROCESSING                             │
│  • PDF → Convert ALL pages to images                       │
│  • Image → Load and validate                               │
│  • Page Selection: 1-page=page1, 2-page=page2, 3+=best   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: BASIC QUALITY CHECKS (OpenCV - 50-100ms)         │
│  ✓ Resolution  ✓ Blur  ✓ Brightness  ✓ Contrast           │
│  ✓ White Space  ✓ Skew  ✓ Corruption                       │
│  Weight: 35%                                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                    ┌─────┴─────┐
                    │  PASS?    │
                    └─────┬─────┘
            ┌─────────────┴─────────────┐
            NO                          YES
            │                           │
            ▼                           ▼
    ┌───────────────┐    ┌──────────────────────────────────┐
    │   REJECTED    │    │  STAGE 2: OCR CONFIDENCE         │
    │  (Critical)   │    │  (Tesseract - 2-5 sec)           │
    └───────────────┘    │  ✓ Avg Confidence  ✓ High Words  │
                         │  ✓ Text Regions  ✓ Char Count    │
                         │  Weight: 40%                      │
                         └──────────┬───────────────────────┘
                                    │
                               ┌────┴────┐
                               │  PASS?  │
                               └────┬────┘
                        ┌───────────┴───────────┐
                        NO                      YES
                        │                       │
                        ▼                       ▼
                ┌───────────────┐    ┌──────────────────────────┐
                │   REJECTED    │    │  STAGE 3: HANDWRITING    │
                │  (Critical)   │    │  (CV - 0.5-2 sec)        │
                └───────────────┘    │  ✓ Stroke Width  ✓ Baseline│
                                     │  ✓ Spacing  ✓ Components   │
                                     │  Weight: 20%               │
                                     └──────────┬────────────────┘
                                                │
                                           ┌────┴────┐
                                           │  PASS?  │
                                           └────┬────┘
                                    ┌───────────┴───────────┐
                                    NO                      YES
                                    │                       │
                                    ▼                       ▼
                            ┌───────────────┐    ┌──────────────────────┐
                            │   REJECTED    │    │  STAGE 4: BRISQUE    │
                            │  (Critical)   │    │  (100-200ms)         │
                            └───────────────┘    │  Weight: 5%           │
                                                 └──────────┬───────────┘
                                                            │
                                                            ▼
                                            ┌───────────────────────────┐
                                            │  FINAL DECISION            │
                                            │  Score = S1×35% + S2×40%  │
                                            │         + S3×20% + S4×5%  │
                                            └───────────┬───────────────┘
                                                        │
                        ┌───────────────────────────────┼───────────────────────┐
                        │                               │                       │
                        ▼                               ▼                       ▼
                ┌───────────────┐              ┌──────────────┐      ┌──────────────┐
                │   ACCEPTED    │              │ FLAG REVIEW   │      │   REJECTED   │
                │  (Score ≥ 60) │              │ (Score 50-59)│      │ (Score < 50) │
                │  Send to LLM   │              │ Manual Review │      │ Do Not Send  │
                └───────────────┘              └──────────────┘      └──────────────┘
```

**Total Processing Time:** 3-8 seconds per document

---

## Acceptance & Rejection Criteria

### 🚫 Critical Failures (Immediate Rejection)

| Failure Type               | Detection                                    | Threshold                       | Notes                                           |
| -------------------------- | -------------------------------------------- | ------------------------------- | ----------------------------------------------- |
| **Handwritten**      | Handwriting % ≥ 30% OR spread > 50% regions | ≥ 30%                          | Filtered if blurry + OCR ≥ 50%                 |
| **Too Dark**         | Average brightness                           | < 20                            | Always critical                                 |
| **Overexposed**      | Average brightness                           | > 300                           | Always critical                                 |
| **Extremely Blurry** | Blur score (Laplacian variance)              | < 30                            | **Only if OCR < 30%** (readability check) |
| **Low Contrast**     | Contrast (std dev)                           | < 15                            | Always critical                                 |
| **Unreadable Text**  | OCR average confidence                       | < 25%                           | Always critical                                 |
| **Too Small**        | Resolution                                   | Width < 400px OR Height < 300px | Always critical                                 |
| **Corrupted**        | Thick lines, distortion, artifacts           | Thick line ratio > 25%          | Always critical                                 |

**Key Changes:**

- **Blur**: Only rejects if OCR < 30% (truly unreadable). If OCR ≥ 50%, blur becomes warning.
- **Handwriting**: False positives filtered for blurry scanned documents when OCR ≥ 50%.
- **Signatures/Stamps**: Accepted if concentrated (15-30%) and OCR ≥ 30% (reduced from 75%).

### ✅ Acceptance Criteria

Documents are **ACCEPTED** if:

- ✅ No critical failures (or blur/handwriting filtered when OCR indicates readability)
- ✅ **OCR-based acceptance** (prioritized):
  - OCR ≥ 80% → Accept if score ≥ 55
  - OCR ≥ 60% → Accept if score ≥ 60
  - OCR ≥ 50% → Blur/handwriting false positives filtered
- ✅ **Standard acceptance**: Final quality score ≥ 60 (or ≥ 70)
- ✅ OCR confidence ≥ 25% (critical threshold)
- ✅ Handwriting < 30% (or concentrated 15-30% with OCR ≥ 30%)
- ✅ Brightness 15-300, Contrast ≥ 15

**Key Principle**: If OCR can read it (≥ 50%), document is accepted even if blur score is low or handwriting detection has false positives.

### 📊 Quality Score Thresholds

| Score | OCR Confidence | Status                        | Action                                  |
| ----- | -------------- | ----------------------------- | --------------------------------------- |
| ≥ 70 | Any            | ✅**ACCEPTED**          | Send to LLM                             |
| ≥ 60 | ≥ 60%         | ✅**ACCEPTED**          | Send to LLM (lenient)                   |
| ≥ 55 | ≥ 80%         | ✅**ACCEPTED**          | Send to LLM (very lenient for high OCR) |
| 50-69 | < 60%          | ⚠️**FLAG FOR REVIEW** | Manual review                           |
| < 50  | Any            | ❌**REJECTED**          | Do not process                          |

**Leniency Rules:**

- **OCR ≥ 80%**: Accept with score ≥ 55 (very readable documents)
- **OCR ≥ 60%**: Accept with score ≥ 60 (readable documents)
- **Standard**: Score ≥ 70 (or ≥ 60 with no critical failures)
- **Blur/Handwriting**: Filtered when OCR ≥ 50% (readable despite image quality issues)

---

## How It Works

### Stage 1: Basic Quality Checks (35% weight, 50-100ms)

- **Resolution**: Min 400×300px (critical), 800×600px (recommended)
- **Blur**: Laplacian variance < 30 = critical failure **only if OCR < 30%** (readability check)
  - If OCR ≥ 50%, blur becomes warning, not rejection
- **Brightness**: < 15 (too dark) or > 300 (overexposed) = critical failure
  - Documents with brightness up to 300 are accepted (increased from 250)
- **Contrast**: < 15 = critical failure
- **White Space**: > 80% = warning (does not cause stage failure)
- **Skew**: > 15° = warning (does not cause stage failure)
- **Corruption**: Detects broader lines, distortion, visual mess
- **Status Logic**: Stage passes if no critical failures (warnings are acceptable and don't cause failure)

### Stage 2: OCR Confidence (40% weight, 2-5 sec)

- **Average Confidence**: < 25% = critical failure
- **High Confidence Words**: Count words with ≥ 70% confidence
- **Text Regions**: Number of separate text areas
- **Character Count**: Total characters detected

### Stage 3: Handwriting Detection (20% weight, 0.5-2 sec)

- **Handwriting %**: ≥ 30% = critical failure (filtered if blurry + OCR ≥ 50%)
- **Distribution Analysis**:
  - Concentrated (15-30%, < 25% regions) = Signatures/stamps → ✅ Accept if OCR ≥ 30%
  - Spread out (> 50% regions) = Handwritten doc → ❌ Reject
- **False Positive Filtering**: For blurry scanned documents (blur < 30), handwriting false positives are filtered when OCR ≥ 50%
- **Bold Text Handling**: High OCR (≥ 80%) trusted over handwriting detection for bold text cases
- **Florence-2 Verification**: Optional AI-powered check when handwriting detected but OCR is high (≥ 50%)
- Uses: Stroke width variance, baseline variance, character spacing, connected components

### Stage 4: BRISQUE Quality (5% weight, 100-200ms)

- Overall image quality assessment (informational)

### Final Decision

```
Final Score = (Stage1 × 35%) + (Stage2 × 40%) + (Stage3 × 20%) + (Stage4 × 5%)
```

**Decision Logic (Priority Order):**

1. **Critical Failures** → ❌ REJECTED (unless filtered by OCR readability)
2. **OCR-Based Acceptance** (prioritized):
   - OCR ≥ 80% + Score ≥ 55 → ✅ ACCEPTED (trust OCR over handwriting for bold text)
   - OCR ≥ 60% + Score ≥ 60 → ✅ ACCEPTED
   - OCR ≥ 50% → Filter blur/handwriting false positives
3. **Florence-2 Verification** (if enabled):
   - Handwriting ≥ 20% + OCR ≥ 50% → Check Florence
   - Florence says "printed" → ✅ ACCEPTED (override handwriting false positive)
   - Florence says "handwritten" → ❌ REJECTED (safeguard)
4. **Standard Scoring**:
   - Score ≥ 70 → ✅ ACCEPTED
   - Score ≥ 60 (with leniency) → ✅ ACCEPTED
   - Score 50-59 → ⚠️ FLAG FOR REVIEW
   - Score < 50 → ❌ REJECTED

**Key Improvements**: 
- Readability (OCR) is prioritized over image quality metrics
- Bold text false positives reduced by trusting high OCR
- Florence-2 provides additional verification layer
- Multiple safeguards prevent accepting handwritten documents

---

## Installation & Setup

### Prerequisites

- Python 3.8+
- Tesseract OCR: `sudo apt-get install tesseract-ocr` (Ubuntu) or `brew install tesseract` (macOS)
- Poppler: `sudo apt-get install poppler-utils` (Ubuntu) or `brew install poppler` (macOS)

### Quick Setup

```bash
cd /home/stark/Desktop/Doc_verifier_Qualification_Pipeline
chmod +x setup.sh && ./setup.sh
source venv/bin/activate
cp env.example .env
pip install requests flasgger  # For URL processing and Swagger docs
python app.py
```

Access at: **http://localhost:5000**
- Web Interface: `http://localhost:5000`
- Swagger API Docs: `http://localhost:5000/api/docs`

---

## Usage

### Web Interface

1. Open `http://localhost:5000`
2. Upload PDF/image (drag & drop or click)
3. Click "Process Document"
4. View results (3-8 seconds)

### API Endpoints

**Health Check:**

```bash
GET /api/health
```

**Upload & Process (Manual Upload):**

```bash
POST /api/upload
Content-Type: multipart/form-data
Form data: file=(PDF or image)
```

**Bulk Upload:**

```bash
POST /api/bulk-upload
Content-Type: multipart/form-data
Form data: files[]=(Multiple PDF or image files)
```

**Process from URL (RTS API Integration):**

```bash
POST /api/process-url
Content-Type: application/json

{
  "url": "https://rts-website.com/api/document/123/download",
  "filename": "doc123"  // optional
}
```

**Bulk Process from URLs:**

```bash
POST /api/bulk-process-urls
Content-Type: application/json

{
  "urls": [
    "https://rts-website.com/api/document/123/download",
    "https://rts-website.com/api/document/124/download"
  ],
  "filenames": ["doc123", "doc124"]  // optional
}
```

**Swagger API Documentation:**

```bash
GET /api/docs
```

Interactive Swagger UI for testing all endpoints.

**Response Format:**

```json
{
  "success": true,
  "final_quality_score": 85.5,
  "status": "ACCEPTED",
  "priority": "High",
  "message": "Quality acceptable - send to LLM for processing",
  "source": "url",  // or "upload"
  "source_url": "https://...",  // if from URL
  "stage_results": [...]
}
```

---

## Configuration (.env)

### Critical Thresholds

```env
RESOLUTION_MIN_WIDTH=400
RESOLUTION_MIN_HEIGHT=300
BLUR_CRITICAL_THRESHOLD=30
BRIGHTNESS_CRITICAL_MIN=15
BRIGHTNESS_CRITICAL_MAX=300
CONTRAST_CRITICAL_THRESHOLD=15
OCR_CRITICAL_THRESHOLD=25
HANDWRITING_CRITICAL_THRESHOLD=30
```

### Scoring Thresholds

```env
SCORE_ACCEPT_THRESHOLD=70
SCORE_REVIEW_THRESHOLD=50
```

### Server Configuration

```env
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
MAX_UPLOAD_SIZE=10485760
DOWNLOAD_FOLDER=downloads
DOWNLOAD_TIMEOUT=30
```

### Florence-2 Configuration (Optional)

```env
FLORENCE_ENABLED=true  # Enable Florence-2 for handwriting verification
```

**Installation:**
```bash
pip install torch transformers einops timm
```

**When Used:**
- Handwriting detected (≥ 20%) AND OCR confidence ≥ 50%
- Helps reduce false positives (e.g., bold text misclassified as handwriting)
- First document: ~8-10 seconds (model loading), subsequent: ~1-2 seconds

---

## Project Structure

```
Doc_verifier_Qualification_Pipeline/
├── app.py                      # Flask backend with Swagger
├── src/
│   ├── stages/                 # 4 pipeline stages
│   │   ├── stage1_basic_quality.py
│   │   ├── stage2_ocr_confidence.py
│   │   ├── stage3_handwriting_detection.py
│   │   └── stage4_brisque_quality.py
│   ├── utils/                  # Utilities
│   │   ├── document_downloader.py  # URL-based downloader
│   │   ├── florence_classifier.py  # Florence-2 AI (optional)
│   │   ├── pdf_converter.py
│   │   └── image_processor.py
│   └── pipeline/
│       └── orchestrator.py     # Main coordinator
├── frontend/                   # Web interface
├── uploads/                     # Manual uploads
├── downloads/                   # URL downloads
└── .env                        # Configuration
```

**Technologies:** Flask, OpenCV, Tesseract OCR, Poppler, BRISQUE, Florence-2 (optional), Swagger

---

## Performance Metrics

- **Processing Time**: 3-8 seconds/document
- **Accuracy**: 85%+ correct decisions
- **Cost Savings**: 50-60% LLM cost reduction
- **Manual Review Reduction**: 70-80%
- **Acceptance Rate**: 50-55% reach LLM (improved with OCR-based filtering)
- **False Positive Rate**: < 5% (good docs rejected)
- **False Negative Rate**: < 5% (bad docs accepted)

---

## Troubleshooting

| Issue                | Solution                                                              |
| -------------------- | --------------------------------------------------------------------- |
| Module not found     | `source venv/bin/activate` then `pip install -r requirements.txt` |
| Tesseract not found  | Install:`sudo apt-get install tesseract-ocr`                        |
| Poppler not found    | Install:`sudo apt-get install poppler-utils`                        |
| Port in use          | Change `FLASK_PORT` in `.env`                                     |
| Incorrect rejections | Check stage results, adjust thresholds in `.env`                    |

---

---

## Flag for Review Criteria

Documents are **FLAGGED FOR REVIEW** when there's ambiguity or conflicting signals:

| Condition                                                          | Reason                                                                     |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| **Score 50-59** (with OCR < 60%)                             | Marginal quality, needs human judgment                                     |
| **Blur < 30 + OCR 30-49%**                                   | Blurry but partially readable - may need rescanning                        |
| **Handwriting 15-30% (concentrated) + OCR < 30%**            | Unclear if signatures or handwritten content                               |
| **OCR > 75% + Handwriting 25-40%**                           | Conflicting signals - OCR says good, handwriting detector says significant |
| **OCR < 50% + Good image quality**                           | Low OCR despite good image - unusual font/layout?                          |
| **Handwriting > 20% + OCR > 70% (concentrated, not blurry)** | Needs human verification                                                   |

**Priority Levels:**

- **Low**: Minor ambiguity, likely acceptable
- **Medium**: Significant ambiguity, needs careful review

---

## Recent Improvements (v1.1.0 - December 2025)

### OCR Confidence as Primary Signal

- **Blur Rejection**: Only rejects for blur if OCR < 30% (truly unreadable). If OCR ≥ 50%, blur becomes warning.
- **Readability First**: System prioritizes OCR readability over perfect image quality.

### Handwriting Detection Improvements

- **Blurry Documents**: Handwriting false positives filtered when blurry but OCR ≥ 50%.
- **Signatures/Stamps**: Accepts concentrated handwriting (15-30%) with OCR ≥ 30% (reduced from 75%).
- **Bold Text Handling**: Fixed false positives where bold text was misclassified as handwriting. High OCR (≥ 80%) trusted over handwriting detection.
- **Florence-2 Integration**: Optional AI-powered verification reduces handwriting false positives. Only called when handwriting detected but OCR is high (≥ 50%).

### Lenient Acceptance

- **OCR ≥ 80%**: Accept with score ≥ 55, trust OCR over handwriting detection
- **OCR ≥ 60%**: Accept with score ≥ 60
- **OCR ≥ 50%**: Filter blur/handwriting false positives

### Multi-Page PDF Processing

- **All Pages Processed**: System processes every page of multi-page PDFs
- **Page Selection Logic**:
  - **1-page documents**: Evaluated based on page 1
  - **2-page documents**: Evaluated based on page 2 (content page, page 1 typically cover/blank)
  - **3+ page documents**: Evaluated based on best quality page (highest score, no critical failures preferred)
- **Acceptance Rule**: Document is accepted if at least one page passes quality checks
- **Results**: Returns results for all pages, with best page highlighted

### Brightness Threshold Update

- **Increased Threshold**: Brightness critical maximum increased from 250 to 300
- **Rationale**: Documents with higher brightness (up to 300) can still be readable if OCR confidence is good
- **Configuration**: Set via `BRIGHTNESS_CRITICAL_MAX=300` in `.env`

### Stage 1 Status Logic Improvement

- **Previous Behavior**: Stage failed if any check failed (including warnings)
- **Current Behavior**: Stage only fails on critical failures; warnings don't cause stage failure
- **Result**: More accurate status reporting - documents with only warnings show Stage 1 as "Passed"

### New Features

- **URL-Based Processing**: Download and process documents from URLs via `/api/process-url` and `/api/bulk-process-urls`
- **RTS API Integration**: Support for processing documents from external APIs
- **Swagger Documentation**: Interactive API docs at `/api/docs` for testing all endpoints
- **Enhanced Safeguards**: Multiple layers to prevent accepting handwritten documents even with high OCR

**Result**: Better handling of readable scanned documents, reduced false rejections, accurate evaluation of multi-page documents, improved brightness tolerance, support for URL-based processing, and comprehensive API documentation.

---

**Version:** 1.2.0 | **Last Updated:** December 2025 |
