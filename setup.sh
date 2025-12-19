#!/bin/bash

# Document Quality Verification Pipeline Setup Script

echo "========================================="
echo "Document Quality Pipeline Setup"
echo "========================================="

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Create necessary directories
echo "Creating directories..."
mkdir -p uploads
mkdir -p cache
mkdir -p logs

# Check for Tesseract OCR
echo "Checking for Tesseract OCR..."
if ! command -v tesseract &> /dev/null; then
    echo "WARNING: Tesseract OCR not found. Please install it:"
    echo "  Ubuntu/Debian: sudo apt-get install tesseract-ocr"
    echo "  macOS: brew install tesseract"
    echo "  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
fi

# Check for Poppler (for PDF processing)
echo "Checking for Poppler..."
if ! command -v pdftoppm &> /dev/null; then
    echo "WARNING: Poppler not found. Please install it:"
    echo "  Ubuntu/Debian: sudo apt-get install poppler-utils"
    echo "  macOS: brew install poppler"
    echo "  Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases"
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To start the server, run:"
echo "  python app.py"
echo ""

