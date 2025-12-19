// Document Quality Verification Pipeline - Frontend JavaScript

const API_BASE_URL = '/api';

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const processBtn = document.getElementById('processBtn');
const clearBtn = document.getElementById('clearBtn');
const resultsSection = document.getElementById('resultsSection');
const loadingOverlay = document.getElementById('loadingOverlay');
const overallStatus = document.getElementById('overallStatus');
const stageResults = document.getElementById('stageResults');
const qualityScore = document.getElementById('qualityScore');

// Bulk Upload Elements
const bulkUploadArea = document.getElementById('bulkUploadArea');
const bulkFileInput = document.getElementById('bulkFileInput');
const bulkFileInfo = document.getElementById('bulkFileInfo');
const fileCount = document.getElementById('fileCount');
const fileList = document.getElementById('fileList');
const processBulkBtn = document.getElementById('processBulkBtn');
const clearBulkBtn = document.getElementById('clearBulkBtn');
const bulkResultsSection = document.getElementById('bulkResultsSection');
const bulkSummary = document.getElementById('bulkSummary');
const bulkResultsTable = document.getElementById('bulkResultsTable');

let selectedFile = null;
let selectedFiles = [];

// Event Listeners
uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', handleDragOver);
uploadArea.addEventListener('dragleave', handleDragLeave);
uploadArea.addEventListener('drop', handleDrop);
fileInput.addEventListener('change', handleFileSelect);
processBtn.addEventListener('click', processDocument);
clearBtn.addEventListener('click', clearSelection);

// Bulk Upload Event Listeners
bulkUploadArea.addEventListener('click', () => bulkFileInput.click());
bulkUploadArea.addEventListener('dragover', handleBulkDragOver);
bulkUploadArea.addEventListener('dragleave', handleBulkDragLeave);
bulkUploadArea.addEventListener('drop', handleBulkDrop);
bulkFileInput.addEventListener('change', handleBulkFileSelect);
processBulkBtn.addEventListener('click', processBulkDocuments);
clearBulkBtn.addEventListener('click', clearBulkSelection);

function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

function handleFileSelect(e) {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
}

function handleFile(file) {
    // Validate file type
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
    if (!allowedTypes.includes(file.type) && !file.name.match(/\.(pdf|png|jpg|jpeg)$/i)) {
        alert('Invalid file type. Please upload a PDF or image file (PNG, JPG, JPEG).');
        return;
    }
    
    // Validate file size (10MB)
    if (file.size > 10 * 1024 * 1024) {
        alert('File size exceeds 10MB limit.');
        return;
    }
    
    selectedFile = file;
    fileName.textContent = file.name;
    fileInfo.style.display = 'block';
    resultsSection.style.display = 'none';
}

function clearSelection() {
    selectedFile = null;
    fileInput.value = '';
    fileInfo.style.display = 'none';
    resultsSection.style.display = 'none';
}

async function processDocument() {
    if (!selectedFile) {
        alert('Please select a file first.');
        return;
    }
    
    // Show loading overlay
    loadingOverlay.style.display = 'flex';
    resetLoadingStages();
    
    // Create form data
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    try {
        // Simulate stage progression
        simulateStageProgression();
        
        // Send request to API
        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        // Hide loading overlay
        loadingOverlay.style.display = 'none';
        
        if (result.success) {
            displayResults(result);
        } else {
            alert(`Error: ${result.error || 'Unknown error occurred'}`);
        }
    } catch (error) {
        loadingOverlay.style.display = 'none';
        console.error('Error:', error);
        alert('An error occurred while processing the document. Please try again.');
    }
}

function simulateStageProgression() {
    const stages = ['stage1Loading', 'stage2Loading', 'stage3Loading', 'stage4Loading'];
    let currentStage = 0;
    
    const interval = setInterval(() => {
        if (currentStage > 0) {
            document.getElementById(stages[currentStage - 1]).classList.remove('active');
            document.getElementById(stages[currentStage - 1]).classList.add('completed');
        }
        
        if (currentStage < stages.length) {
            document.getElementById(stages[currentStage]).classList.add('active');
            currentStage++;
        } else {
            clearInterval(interval);
        }
    }, 1000);
}

function resetLoadingStages() {
    const stages = ['stage1Loading', 'stage2Loading', 'stage3Loading', 'stage4Loading'];
    stages.forEach(stageId => {
        const element = document.getElementById(stageId);
        element.classList.remove('active', 'completed');
    });
}

function displayResults(result) {
    resultsSection.style.display = 'block';
    
    // Display overall status
    let statusClass = 'rejected';
    if (result.status === 'ACCEPTED') {
        statusClass = 'accepted';
    } else if (result.status === 'FLAG_FOR_REVIEW') {
        statusClass = 'review'; // Will need to add CSS for this
    }
    
    overallStatus.className = `status-card ${statusClass}`;
    
    let statusHTML = `<h3>${result.status.replace('_', ' ')}</h3>`;
    
    // Show page information if multi-page PDF
    if (result.total_pages && result.total_pages > 1) {
        statusHTML += `<p><strong>Total Pages:</strong> ${result.total_pages}</p>`;
        if (result.best_page) {
            statusHTML += `<p><strong>Best Quality Page:</strong> Page ${result.best_page}</p>`;
        }
    }
    
    statusHTML += `<p><strong>Priority:</strong> ${result.priority || 'N/A'}</p>`;
    statusHTML += `<p>${result.message}</p>`;
    statusHTML += `<p><strong>Processing Time:</strong> ${result.processing_time_seconds}s</p>`;
    
    // Show page results if multi-page
    if (result.page_results && result.page_results.length > 1) {
        statusHTML += `<div style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.05); border-radius: 5px;">`;
        statusHTML += `<strong>Page Results:</strong><ul style="margin-top: 5px;">`;
        result.page_results.forEach(page => {
            const pageStatusIcon = page.status === 'ACCEPTED' ? '✅' : 
                                 page.status === 'REJECTED' ? '❌' : '⚠️';
            statusHTML += `<li>Page ${page.page_number}: ${pageStatusIcon} ${page.status} (Score: ${page.final_quality_score.toFixed(2)}, OCR: ${page.ocr_confidence ? page.ocr_confidence.toFixed(1) + '%' : 'N/A'})</li>`;
        });
        statusHTML += `</ul></div>`;
    }
    
    // Show critical failures if any
    if (result.critical_failures && result.critical_failures.length > 0) {
        statusHTML += `<div style="margin-top: 15px; padding: 10px; background: rgba(220, 53, 69, 0.1); border-radius: 5px;">`;
        statusHTML += `<strong style="color: #dc3545;">Critical Issues:</strong><ul style="margin-top: 5px;">`;
        result.critical_failures.forEach(failure => {
            statusHTML += `<li style="color: #721c24;">${failure}</li>`;
        });
        statusHTML += `</ul></div>`;
    }
    
    // Show warnings if any
    if (result.warnings && result.warnings.length > 0) {
        statusHTML += `<div style="margin-top: 10px; padding: 10px; background: rgba(255, 193, 7, 0.1); border-radius: 5px;">`;
        statusHTML += `<strong style="color: #856404;">Warnings:</strong><ul style="margin-top: 5px;">`;
        result.warnings.forEach(warning => {
            statusHTML += `<li style="color: #856404;">${warning}</li>`;
        });
        statusHTML += `</ul></div>`;
    }
    
    overallStatus.innerHTML = statusHTML;
    
    // Display stage results
    stageResults.innerHTML = '';
    if (result.stage_results && result.stage_results.length > 0) {
        result.stage_results.forEach((stage, index) => {
            const stageDiv = document.createElement('div');
            stageDiv.className = `stage-result-item ${stage.passed ? 'passed' : 'failed'}`;
            
            let stageContent = `
                <h4>${stage.stage}</h4>
                <div class="stage-score">Score: ${stage.stage_score || 0}/100</div>
                <p><strong>Status:</strong> ${stage.passed ? '✓ Passed' : '✗ Failed'}</p>
            `;
            
            if (stage.error) {
                stageContent += `<p style="color: #dc3545;"><strong>Error:</strong> ${stage.error}</p>`;
            }
            
            // Show critical failures
            if (stage.critical_failures && stage.critical_failures.length > 0) {
                stageContent += `
                    <div class="rejection-reasons" style="background: #f8d7da; border-left: 4px solid #dc3545;">
                        <strong style="color: #721c24;">Critical Issues:</strong>
                        <ul>
                            ${stage.critical_failures.map(failure => `<li style="color: #721c24;">${failure}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }
            
            // Show warnings
            if (stage.warnings && stage.warnings.length > 0) {
                stageContent += `
                    <div class="rejection-reasons" style="background: #fff3cd; border-left: 4px solid #ffc107; margin-top: 10px;">
                        <strong style="color: #856404;">Warnings:</strong>
                        <ul>
                            ${stage.warnings.map(warning => `<li style="color: #856404;">${warning}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }
            
            // Show rejection reasons (for backward compatibility)
            if (stage.rejection_reasons && stage.rejection_reasons.length > 0 && 
                (!stage.critical_failures || stage.critical_failures.length === 0) &&
                (!stage.warnings || stage.warnings.length === 0)) {
                stageContent += `
                    <div class="rejection-reasons">
                        <strong>Issues:</strong>
                        <ul>
                            ${stage.rejection_reasons.filter(r => r).map(reason => `<li>${reason}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }
            
            // Add stage-specific details
            if (stage.checks) {
                stageContent += '<div style="margin-top: 10px;"><strong>Checks:</strong><ul>';
                Object.keys(stage.checks).forEach(key => {
                    if (typeof stage.checks[key] === 'boolean') {
                        stageContent += `<li>${key}: ${stage.checks[key] ? '✓' : '✗'}</li>`;
                    }
                });
                stageContent += '</ul></div>';
            }
            
            if (stage.analysis) {
                stageContent += '<div style="margin-top: 10px;"><strong>Analysis Details:</strong><ul>';
                Object.keys(stage.analysis).forEach(key => {
                    if (typeof stage.analysis[key] !== 'object' || stage.analysis[key] === null) {
                        stageContent += `<li>${key}: ${stage.analysis[key]}</li>`;
                    }
                });
                stageContent += '</ul></div>';
            }
            
            stageDiv.innerHTML = stageContent;
            stageResults.appendChild(stageDiv);
        });
    }
    
    // Display quality score
    let scoreHTML = `
        <h3>Final Quality Score</h3>
        <div class="quality-score-value">${result.final_quality_score || 0}</div>
        <p>Out of 100</p>
    `;
    
    // Show score interpretation
    if (result.final_quality_score >= 70) {
        scoreHTML += `<p style="margin-top: 10px; font-size: 1.1em;">✓ Quality Acceptable</p>`;
    } else if (result.final_quality_score >= 50) {
        scoreHTML += `<p style="margin-top: 10px; font-size: 1.1em;">⚠ Flagged for Review</p>`;
    } else {
        scoreHTML += `<p style="margin-top: 10px; font-size: 1.1em;">✗ Quality Too Low</p>`;
    }
    
    qualityScore.innerHTML = scoreHTML;
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Tab Switching
function switchTab(tab) {
    const singleTab = document.getElementById('singleTab');
    const bulkTab = document.getElementById('bulkTab');
    const singleCard = document.getElementById('singleUploadCard');
    const bulkCard = document.getElementById('bulkUploadCard');
    const singleResults = document.getElementById('resultsSection');
    const bulkResults = document.getElementById('bulkResultsSection');
    
    if (tab === 'single') {
        singleTab.classList.add('active');
        bulkTab.classList.remove('active');
        singleCard.style.display = 'block';
        bulkCard.style.display = 'none';
        bulkResults.style.display = 'none';
    } else {
        bulkTab.classList.add('active');
        singleTab.classList.remove('active');
        bulkCard.style.display = 'block';
        singleCard.style.display = 'none';
        singleResults.style.display = 'none';
    }
}

// Bulk Upload Handlers
function handleBulkDragOver(e) {
    e.preventDefault();
    bulkUploadArea.classList.add('dragover');
}

function handleBulkDragLeave(e) {
    e.preventDefault();
    bulkUploadArea.classList.remove('dragover');
}

function handleBulkDrop(e) {
    e.preventDefault();
    bulkUploadArea.classList.remove('dragover');
    
    const files = Array.from(e.dataTransfer.files);
    handleBulkFiles(files);
}

function handleBulkFileSelect(e) {
    if (e.target.files.length > 0) {
        handleBulkFiles(Array.from(e.target.files));
    }
}

function handleBulkFiles(files) {
    // Filter valid files
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
    const validFiles = files.filter(file => {
        return allowedTypes.includes(file.type) || file.name.match(/\.(pdf|png|jpg|jpeg)$/i);
    });
    
    if (validFiles.length === 0) {
        alert('No valid files selected. Please upload PDF or image files (PNG, JPG, JPEG).');
        return;
    }
    
    // Check file sizes
    const oversizedFiles = validFiles.filter(file => file.size > 10 * 1024 * 1024);
    if (oversizedFiles.length > 0) {
        alert(`${oversizedFiles.length} file(s) exceed 10MB limit and will be skipped.`);
    }
    
    // Filter out oversized files
    const sizeValidFiles = validFiles.filter(file => file.size <= 10 * 1024 * 1024);
    
    if (sizeValidFiles.length > 50) {
        alert('Too many files. Maximum 50 files allowed. Only first 50 will be processed.');
        selectedFiles = sizeValidFiles.slice(0, 50);
    } else {
        selectedFiles = sizeValidFiles;
    }
    
    updateBulkFileInfo();
    bulkResultsSection.style.display = 'none';
}

function updateBulkFileInfo() {
    if (selectedFiles.length === 0) {
        bulkFileInfo.style.display = 'none';
        return;
    }
    
    fileCount.textContent = selectedFiles.length;
    fileList.innerHTML = '';
    
    selectedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span>${index + 1}. ${file.name}</span>
            <span class="file-size">(${(file.size / 1024 / 1024).toFixed(2)} MB)</span>
        `;
        fileList.appendChild(fileItem);
    });
    
    bulkFileInfo.style.display = 'block';
}

function clearBulkSelection() {
    selectedFiles = [];
    bulkFileInput.value = '';
    bulkFileInfo.style.display = 'none';
    bulkResultsSection.style.display = 'none';
}

async function processBulkDocuments() {
    if (selectedFiles.length === 0) {
        alert('Please select files first.');
        return;
    }
    
    // Show loading overlay
    loadingOverlay.style.display = 'flex';
    resetLoadingStages();
    
    // Create form data
    const formData = new FormData();
    selectedFiles.forEach(file => {
        formData.append('files[]', file);
    });
    
    try {
        // Simulate stage progression
        simulateStageProgression();
        
        // Send request to API
        const response = await fetch(`${API_BASE_URL}/bulk-upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        // Hide loading overlay
        loadingOverlay.style.display = 'none';
        
        if (result.success) {
            displayBulkResults(result);
        } else {
            alert(`Error: ${result.error || 'Unknown error occurred'}`);
        }
    } catch (error) {
        loadingOverlay.style.display = 'none';
        console.error('Error:', error);
        alert('An error occurred while processing documents. Please try again.');
    }
}

function displayBulkResults(result) {
    bulkResultsSection.style.display = 'block';
    
    // Display summary
    const summary = result.summary;
    let summaryHTML = `
        <div class="summary-stats">
            <div class="stat-item">
                <div class="stat-value">${summary.total_files}</div>
                <div class="stat-label">Total Files</div>
            </div>
            <div class="stat-item">
                <div class="stat-value accepted">${summary.accepted}</div>
                <div class="stat-label">Accepted</div>
            </div>
            <div class="stat-item">
                <div class="stat-value rejected">${summary.rejected}</div>
                <div class="stat-label">Rejected</div>
            </div>
            <div class="stat-item">
                <div class="stat-value review">${summary.flagged_for_review}</div>
                <div class="stat-label">Flagged for Review</div>
            </div>
            <div class="stat-item">
                <div class="stat-value error">${summary.failed}</div>
                <div class="stat-label">Failed</div>
            </div>
        </div>
    `;
    bulkSummary.innerHTML = summaryHTML;
    
    // Display results table
    let tableHTML = `
        <table class="results-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Filename</th>
                    <th>Pages</th>
                    <th>Status</th>
                    <th>Score</th>
                    <th>OCR %</th>
                    <th>Reason</th>
                    <th>Time (s)</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    result.results.forEach((item, index) => {
        const statusClass = item.status === 'ACCEPTED' ? 'accepted' : 
                           item.status === 'REJECTED' ? 'rejected' : 'review';
        const statusIcon = item.status === 'ACCEPTED' ? '✅' : 
                         item.status === 'REJECTED' ? '❌' : '⚠️';
        
        tableHTML += `
            <tr class="${statusClass}">
                <td>${index + 1}</td>
                <td class="filename">${item.filename}</td>
                <td>${item.total_pages || 1}</td>
                <td><span class="status-badge ${statusClass}">${statusIcon} ${item.status}</span></td>
                <td>${item.score !== null ? item.score.toFixed(2) : 'N/A'}</td>
                <td>${item.ocr_confidence ? item.ocr_confidence.toFixed(1) + '%' : 'N/A'}</td>
                <td class="reason">${item.reason || 'N/A'}</td>
                <td>${item.processing_time ? item.processing_time.toFixed(2) : 'N/A'}</td>
            </tr>
        `;
    });
    
    // Add error rows if any
    if (result.errors && result.errors.length > 0) {
        result.errors.forEach((item, index) => {
            tableHTML += `
                <tr class="error">
                    <td>${result.results.length + index + 1}</td>
                    <td class="filename">${item.filename}</td>
                    <td><span class="status-badge error">❌ ERROR</span></td>
                    <td>N/A</td>
                    <td>N/A</td>
                    <td class="reason">${item.error || 'Processing failed'}</td>
                    <td>N/A</td>
                </tr>
            `;
        });
    }
    
    tableHTML += `
            </tbody>
        </table>
    `;
    
    bulkResultsTable.innerHTML = tableHTML;
    
    // Scroll to results
    bulkResultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Check API health on load
window.addEventListener('load', async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        const data = await response.json();
        console.log('API Status:', data);
    } catch (error) {
        console.error('API Health Check Failed:', error);
    }
});

