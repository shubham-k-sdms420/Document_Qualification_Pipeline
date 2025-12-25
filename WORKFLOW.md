# Document Quality Verification Pipeline - Workflow

Automated quality control for government documents (NOC, No Dues, Index-II) before LLM processing.

**Benefits:** 50-60% cost reduction, 70-80% less manual review, 100% local processing

---

## System Architecture

```
DOCUMENT INPUT (Upload/URL)
    ↓
INDEX-II DETECTION
    ├─ Text markers (सूची क्र.2, regn:63m)
    ├─ Visual structure (barcode, seals, tables)
    ├─ Negative signals (NOC/No Dues/Agreement/Will)
    └─ Confidence ≥ 0.60 → Index-II pipeline
       Confidence < 0.60 → General pipeline
    ↓
4-STAGE QUALITY CHECKS
    ├─ Stage 1: Basic Quality (35%) - Resolution, blur, brightness
    ├─ Stage 2: OCR Confidence (40%) - Text readability
    ├─ Stage 3: Handwriting (20%) - Printed vs handwritten
    └─ Stage 4: BRISQUE (5%) - Overall quality
    ↓
FINAL DECISION
    ├─ Score ≥ 70 → ✅ ACCEPTED
    ├─ Score ≥ 60 + OCR ≥ 60% → ✅ ACCEPTED
    ├─ Score 50-69 → ⚠️ FLAG FOR REVIEW
    └─ Score < 50 → ❌ REJECTED
```

**Processing Time:** 3-8 seconds per document

---

## Acceptance & Rejection Criteria

### Critical Failures (Immediate Rejection)

| Failure | Threshold | Notes |
|---------|-----------|-------|
| Handwritten | ≥ 30% | Filtered if OCR ≥ 50% |
| Too Dark | < 20 | Always critical |
| Overexposed | > 300 | Always critical |
| Extremely Blurry | < 30 | Only if OCR < 30% |
| Low Contrast | < 15 | Always critical |
| Unreadable Text | OCR < 25% | Always critical |
| Too Small | < 400×300px | Always critical |

### Acceptance Rules

**Standard:**
- No critical failures
- Score ≥ 60-70
- OCR ≥ 25%

**OCR-Based (Prioritized):**
- OCR ≥ 80% → Accept if score ≥ 55
- OCR ≥ 60% → Accept if score ≥ 60
- OCR ≥ 50% → Filter blur/handwriting false positives

**Index-II (Lenient):**
- OCR ≥ 30%
- Score ≥ 50
- Not fully handwritten
- OCR ≥ 70% → Trust OCR over handwriting (bold text)

---

## Stage Details

### Stage 1: Basic Quality (35% weight, 50-100ms)
- Resolution: Min 400×300px
- Blur: < 30 only if OCR < 30%
- Brightness: 15-300
- Contrast: ≥ 15
- Status: Passes if no critical failures (warnings OK)

### Stage 2: OCR Confidence (40% weight, 2-5s)
- Average confidence: < 25% = critical failure
- High confidence words: Count words ≥ 70%
- Text regions: Number of separate areas
- Character count: Total characters

### Stage 3: Handwriting Detection (20% weight, 0.5-2s)
- Handwriting %: ≥ 30% = critical (filtered if OCR ≥ 50%)
- Distribution:
  - Concentrated (15-30%) = Signatures/stamps → Accept if OCR ≥ 30%
  - Spread out (> 50% regions) = Handwritten → Reject
- Bold text: OCR ≥ 80% trusted over handwriting
- Florence-2: Optional verification (20s timeout)

### Stage 4: BRISQUE (5% weight, 100-200ms)
- Overall image quality assessment

---

## Index-II Processor

**Detection:**
- Content-based (not filename)
- Text markers: "सूची क्र.2", "regn:63m", "गावाचे नाव"
- Visual: Barcode, seals, table structure
- Negative signals: NOC, No Dues, Agreement, Will, Testament
- Only full unambiguous markers override negative signals

**Validation (Lenient):**
- OCR ≥ 30% (vs. 50% for general)
- Score ≥ 50 (vs. 60-70 for general)
- OCR ≥ 70% → Trust OCR over handwriting (bold text handling)

**Routing:**
- Confidence ≥ 0.60 → Index-II pipeline
- Confidence < 0.60 → General pipeline

---

## OCR Thresholds Summary

| OCR Range | Status | Action |
|-----------|--------|--------|
| < 20% | ❌ REJECTED | Unreadable |
| 20-24% | ❌ REJECTED | Critical failure |
| 25-29% | ⚠️ WARNING | Below recommended |
| 30-49% | ⚠️ REVIEW | Marginal |
| 50-59% | ✅ ACCEPTED | Readable |
| 60-79% | ✅ ACCEPTED | Good |
| ≥ 80% | ✅ ACCEPTED | Excellent (lenient scoring) |

**Key Rules:**
- OCR ≥ 50% → Filter blur/handwriting false positives
- OCR ≥ 60% → Accept with score ≥ 60
- OCR ≥ 80% → Accept with score ≥ 55

---

## Configuration

### Critical Thresholds

```env
OCR_CRITICAL_THRESHOLD=25
BLUR_CRITICAL_THRESHOLD=30
BRIGHTNESS_CRITICAL_MAX=300
HANDWRITING_CRITICAL_THRESHOLD=30
SCORE_ACCEPT_THRESHOLD=70
SCORE_REVIEW_THRESHOLD=50
```

### Index-II

```env
INDEX2_PROCESSOR_ENABLED=true
INDEX2_MIN_OCR_CONFIDENCE=30
INDEX2_MIN_ACCEPT_SCORE=50
```

---

## Recent Updates (v1.5.0)

- ✅ Simplified user messages (no technical details)
- ✅ Index-II bold text handling (OCR ≥ 70% trusted)
- ✅ Agreement/Will routing fixes
- ✅ Stricter Index-II detection (exact markers only)

---

**Version:** 1.5.0 | **Last Updated:** December 2025
