// ==================== GLOBAL VARIABLES ====================
let ttsData = null;
let originalShiftFactors = {};
let currentShiftFactors = {};
let referenceTemp = null;
let debugMode = false;

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Manual Adjustment Page Loaded');
    loadCurrentData();
    setupEventListeners();
});

// ==================== DATA LOADING ====================
function loadCurrentData() {
    console.log('📡 Fetching analysis data...');
    
    fetch('/get_current_data')
        .then(response => {
            console.log('Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('✅ Data received:', data);
            
            if (data.error) {
                showNoDataMessage();
                return;
            }
            
            // Validate and store data
            if (!data.shift_factors || Object.keys(data.shift_factors).length === 0) {
                console.error('❌ No shift factors in data');
                showMessage('No shift factors found in data', 'error');
                showNoDataMessage();
                return;
            }
            
            // Store data
            ttsData = data;
            referenceTemp = data.reference_temperature || 25;
            
            // Fix and store shift factors
            const fixedShiftFactors = fixShiftFactors(data.shift_factors);
            originalShiftFactors = JSON.parse(JSON.stringify(fixedShiftFactors));
            currentShiftFactors = JSON.parse(JSON.stringify(fixedShiftFactors));
            
            console.log('📊 Data processed successfully');
            console.log('Reference temp:', referenceTemp);
            console.log('Number of temperatures:', Object.keys(currentShiftFactors).length);
            
            // Initialize UI
            initializeUI();
        })
        .catch(error => {
            console.error('❌ Error loading data:', error);
            showErrorMessage(error);
        });
}

function fixShiftFactors(shiftFactors) {
    const fixed = {};
    Object.keys(shiftFactors).forEach(tempKey => {
        const sf = shiftFactors[tempKey];
        let logAT = sf.log_aT;
        
        // Calculate log_aT if missing
        if ((logAT === undefined || logAT === null) && sf.aT !== undefined && sf.aT > 0) {
            logAT = Math.log10(sf.aT);
        }
        
        fixed[tempKey] = {
            aT: sf.aT || 1,
            log_aT: logAT || 0
        };
    });
    return fixed;
}

function initializeUI() {
    // Update reference temperature display
    document.getElementById('refTempDisplay').textContent = referenceTemp.toFixed(1) + '°C';
    
    // Hide loading, show content
    document.getElementById('loadingDiv').style.display = 'none';
    document.getElementById('mainContent').style.display = 'block';
    
    // Create UI elements
    createSliders();
    updatePlots();
    updateTable();
    
    showMessage('Data loaded successfully', 'success');
}

function showNoDataMessage() {
    document.getElementById('loadingDiv').innerHTML = `
        <div class="alert alert-warning">
            <h4>No Analysis Data Found</h4>
            <p>Please run an analysis first before adjusting shift factors.</p>
            <a href="/" class="btn btn-primary">Go to Analysis</a>
        </div>
    `;
}

function showErrorMessage(error) {
    document.getElementById('loadingDiv').innerHTML = `
        <div class="alert alert-danger">
            <h4>Error Loading Data</h4>
            <p>${error.message}</p>
            <a href="/" class="btn btn-primary">Go to Analysis</a>
        </div>
    `;
}

// ==================== SLIDER CREATION ====================
function createSliders() {
    const container = document.getElementById('sliderContainer');
    container.innerHTML = '';
    
    const tempKeys = Object.keys(currentShiftFactors);
    const sortedTempKeys = tempKeys.sort((a, b) => parseFloat(a) - parseFloat(b));
    
    console.log('🎚️ Creating sliders for', sortedTempKeys.length, 'temperatures');
    
    sortedTempKeys.forEach(tempKey => {
        const temp = parseFloat(tempKey);
        
        // Skip reference temperature
        if (Math.abs(temp - referenceTemp) < 0.01) {
            return;
        }
        
        const shiftFactor = currentShiftFactors[tempKey];
        const currentLogAT = shiftFactor.log_aT || 0;
        
        const sliderId = `slider-${temp}`;
        
        const sliderHTML = `
            <div class="slider-container">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="slider-label">${temp.toFixed(1)}°C</span>
                    <span class="slider-value" id="value-${temp}">${currentLogAT.toFixed(3)}</span>
                </div>
                <input type="range" 
                       class="form-range temperature-slider" 
                       id="${sliderId}"
                       min="-3" 
                       max="3" 
                       step="0.01" 
                       value="${currentLogAT}"
                       data-temperature="${tempKey}">
                <div class="d-flex justify-content-between">
                    <small class="text-muted">-3</small>
                    <small class="text-muted">0</small>
                    <small class="text-muted">+3</small>
                </div>
            </div>
        `;
        
        container.innerHTML += sliderHTML;
    });
    
    // Add event listeners to sliders
    sortedTempKeys.forEach(tempKey => {
        const temp = parseFloat(tempKey);
        if (Math.abs(temp - referenceTemp) < 0.01) return;
        
        const slider = document.getElementById(`slider-${temp}`);
        if (slider) {
            slider.addEventListener('input', function(e) {
                handleSliderChange(tempKey, parseFloat(e.target.value));
            });
        }
    });
}

// ==================== SLIDER HANDLING ====================
function handleSliderChange(tempKey, logATValue) {
    const temp = parseFloat(tempKey);
    
    // Update values
    currentShiftFactors[tempKey] = {
        aT: Math.pow(10, logATValue),
        log_aT: logATValue
    };
    
    // Update display
    const valueElement = document.getElementById(`value-${temp}`);
    if (valueElement) {
        valueElement.textContent = logATValue.toFixed(3);
    }
    
    // Update plots and table
    updatePlots();
    updateTable();
    
    // Send to server
    updateServerData(temp, logATValue);
    
    // Update debug info if visible
    if (debugMode) {
        updateDebugInfo();
    }
}

function updateServerData(temperature, logATValue) {
    fetch('/update_shift_factor', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            temperature: temperature,
            log_aT: logATValue
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status !== 'success') {
            console.error('Failed to update server');
        }
    })
    .catch(error => {
        console.error('Server update error:', error);
    });
}

// ==================== PLOTTING FUNCTIONS ====================
function updatePlots() {
    try {
        plotMasterCurve();
        plotOriginalData();
        plotShiftFactors();
    } catch (error) {
        console.error('Error updating plots:', error);
        showMessage('Error updating plots: ' + error.message, 'error');
    }
}

function plotMasterCurve() {
    if (!ttsData || !ttsData.original_data) return;
    
    const traces = [];
    const tempKeys = Object.keys(ttsData.original_data);
    const colors = generateColors(tempKeys.length);
    
    tempKeys.forEach((tempKey, index) => {
        const data = ttsData.original_data[tempKey];
        const shiftFactor = currentShiftFactors[tempKey];
        const aT = shiftFactor ? (shiftFactor.aT || 1) : 1;
        
        const shiftedOmega = data.omega.map(w => w * aT);
        
        traces.push({
            x: shiftedOmega,
            y: data.modulus,
            mode: 'lines+markers',
            name: `${parseFloat(tempKey).toFixed(1)}°C`,
            line: { color: colors[index], width: 2 },
            marker: { size: 6 },
            type: 'scatter'
        });
    });
    
    const layout = {
        title: `Master Curve (T<sub>ref</sub> = ${referenceTemp.toFixed(1)}°C)`,
        xaxis: {
            title: 'ω·a<sub>T</sub> [rad/s]',
            type: 'log',
            gridcolor: '#e0e0e0',
            showgrid: true
        },
        yaxis: {
            title: "G' [Pa]",
            type: 'log',
            gridcolor: '#e0e0e0',
            showgrid: true
        },
        hovermode: 'closest',
        showlegend: true,
        height: 420,
        margin: { t: 50, b: 50, l: 60, r: 20 }
    };
    
    Plotly.newPlot('masterCurvePlot', traces, layout, {responsive: true});
}

function plotOriginalData() {
    if (!ttsData || !ttsData.original_data) return;
    
    const traces = [];
    const tempKeys = Object.keys(ttsData.original_data);
    const colors = generateColors(tempKeys.length);
    
    tempKeys.forEach((tempKey, index) => {
        const data = ttsData.original_data[tempKey];
        
        traces.push({
            x: data.omega,
            y: data.modulus,
            mode: 'lines+markers',
            name: `${parseFloat(tempKey).toFixed(1)}°C`,
            line: { color: colors[index], width: 2 },
            marker: { size: 5 },
            type: 'scatter'
        });
    });
    
    const layout = {
        title: 'Original Data',
        xaxis: {
            title: 'ω [rad/s]',
            type: 'log',
            gridcolor: '#e0e0e0',
            showgrid: true
        },
        yaxis: {
            title: "G' [Pa]",
            type: 'log',
            gridcolor: '#e0e0e0',
            showgrid: true
        },
        hovermode: 'closest',
        showlegend: true,
        height: 350,
        margin: { t: 40, b: 50, l: 60, r: 20 }
    };
    
    Plotly.newPlot('originalDataPlot', traces, layout, {responsive: true});
}

function plotShiftFactors() {
    const tempKeys = Object.keys(currentShiftFactors);
    const sortedTempKeys = tempKeys.sort((a, b) => parseFloat(a) - parseFloat(b));
    
    const temperatures = [];
    const currentLogATs = [];
    const originalLogATs = [];
    
    sortedTempKeys.forEach(tempKey => {
        const temp = parseFloat(tempKey);
        temperatures.push(temp);
        
        const currentSF = currentShiftFactors[tempKey];
        const originalSF = originalShiftFactors[tempKey];
        
        currentLogATs.push(currentSF.log_aT || 0);
        originalLogATs.push(originalSF.log_aT || 0);
    });
    
    const traces = [
        {
            x: temperatures,
            y: currentLogATs,
            mode: 'lines+markers',
            name: 'Current (Manual)',
            line: { color: '#0066cc', width: 3 },
            marker: { size: 10, color: '#0066cc' },
            type: 'scatter'
        },
        {
            x: temperatures,
            y: originalLogATs,
            mode: 'lines+markers',
            name: 'Original (Auto)',
            line: { color: '#ff6600', width: 2, dash: 'dash' },
            marker: { 
                size: 8,
                color: '#ff6600',
                symbol: 'circle-open',
                line: { width: 2 }
            },
            type: 'scatter'
        }
    ];
    
    const layout = {
        title: 'Shift Factors Comparison',
        xaxis: {
            title: 'Temperature [°C]',
            gridcolor: '#e0e0e0',
            showgrid: true
        },
        yaxis: {
            title: 'log(a<sub>T</sub>)',
            gridcolor: '#e0e0e0',
            showgrid: true,
            zeroline: true,
            zerolinecolor: '#000000',
            zerolinewidth: 1
        },
        shapes: [
            {
                type: 'line',
                x0: referenceTemp,
                y0: -3,
                x1: referenceTemp,
                y1: 3,
                line: {
                    color: 'green',
                    width: 2,
                    dash: 'dash'
                }
            }
        ],
        annotations: [
            {
                x: referenceTemp,
                y: 2.5,
                text: `T<sub>ref</sub>`,
                showarrow: false,
                bgcolor: 'rgba(255, 255, 255, 0.9)',
                bordercolor: 'green',
                borderwidth: 1
            }
        ],
        hovermode: 'x unified',
        showlegend: true,
        height: 350,
        margin: { t: 40, b: 50, l: 60, r: 20 }
    };
    
    Plotly.newPlot('shiftFactorPlot', traces, layout, {responsive: true});
}

// ==================== TABLE UPDATE ====================
function updateTable() {
    const tbody = document.getElementById('shiftFactorTable');
    tbody.innerHTML = '';
    
    const tempKeys = Object.keys(currentShiftFactors);
    const sortedTempKeys = tempKeys.sort((a, b) => parseFloat(a) - parseFloat(b));
    
    sortedTempKeys.forEach(tempKey => {
        const temp = parseFloat(tempKey);
        const sf = currentShiftFactors[tempKey];
        
        if (!sf) return;
        
        const isRef = Math.abs(temp - referenceTemp) < 0.01;
        
        const row = document.createElement('tr');
        if (isRef) {
            row.className = 'ref-temp-row';
        }
        
        row.innerHTML = `
            <td>${temp.toFixed(1)}</td>
            <td>${sf.aT ? sf.aT.toExponential(2) : '1.00e+0'}</td>
            <td>${sf.log_aT !== undefined ? sf.log_aT.toFixed(3) : '0.000'}</td>
        `;
        tbody.appendChild(row);
    });
}

// ==================== EVENT LISTENERS ====================
function setupEventListeners() {
    // Reset button
    document.getElementById('resetBtn').addEventListener('click', handleReset);
    
    // Export button
    document.getElementById('exportBtn').addEventListener('click', handleExport);
    
    // Debug button (if exists)
    const debugBtn = document.getElementById('debugBtn');
    if (debugBtn) {
        debugBtn.addEventListener('click', toggleDebug);
    }
}

function handleReset() {
    console.log('🔄 Resetting to original values');
    
    currentShiftFactors = JSON.parse(JSON.stringify(originalShiftFactors));
    
    // Reset sliders
    Object.keys(currentShiftFactors).forEach(tempKey => {
        const temp = parseFloat(tempKey);
        if (Math.abs(temp - referenceTemp) < 0.01) return;
        
        const slider = document.getElementById(`slider-${temp}`);
        const sf = currentShiftFactors[tempKey];
        
        if (slider && sf) {
            slider.value = sf.log_aT || 0;
            document.getElementById(`value-${temp}`).textContent = 
                (sf.log_aT || 0).toFixed(3);
        }
    });
    
    updatePlots();
    updateTable();
    showMessage('Reset to original values', 'success');
}

function handleExport() {
    console.log('📥 Exporting to Excel');
    
    showMessage('Preparing Excel file...', 'info');
    
    const exportData = {
        reference_temperature: referenceTemp,
        original_data: ttsData.original_data,
        shift_factors: currentShiftFactors
    };
    
    console.log('Export data:', exportData);
    
    fetch('/save_manual_adjustment', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(exportData)
    })
    .then(response => {
        console.log('Export response status:', response.status);
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`Server error (${response.status}): ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Export response data:', data);
        
        if (data.status === 'success') {
            // Download the file
            console.log('Downloading from:', data.download_url);
            window.location.href = data.download_url;
            
            showMessage(`Excel file downloaded: ${data.filename}`, 'success');
        } else {
            throw new Error(data.error || 'Export failed');
        }
    })
    .catch(error => {
        console.error('Export error:', error);
        showMessage('Export failed: ' + error.message, 'error');
    });
}

// ==================== UTILITY FUNCTIONS ====================
function generateColors(count) {
    const colors = [];
    for (let i = 0; i < count; i++) {
        const hue = (i * 360 / count) % 360;
        colors.push(`hsl(${hue}, 70%, 50%)`);
    }
    return colors;
}

function showMessage(message, type) {
    const messageDiv = document.getElementById('statusMessage');
    const alertClass = type === 'error' ? 'alert-danger' : 
                      type === 'info' ? 'alert-info' : 'alert-success';
    
    const alertHTML = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    messageDiv.innerHTML = alertHTML;
    
    // Auto dismiss after 5 seconds (except errors)
    if (type !== 'error') {
        setTimeout(() => {
            const alert = messageDiv.querySelector('.alert');
            if (alert) {
                alert.classList.remove('show');
                setTimeout(() => {
                    if (messageDiv.innerHTML === alertHTML) {
                        messageDiv.innerHTML = '';
                    }
                }, 150);
            }
        }, 5000);
    }
}

// ==================== DEBUG FUNCTIONS ====================
function toggleDebug() {
    debugMode = !debugMode;
    const panel = document.getElementById('debugPanel');
    
    if (debugMode) {
        panel.classList.add('show');
        updateDebugInfo();
    } else {
        panel.classList.remove('show');
    }
}

function updateDebugInfo() {
    const debugContent = document.getElementById('debugContent');
    const tempCount = Object.keys(currentShiftFactors).length;
    const dataPoints = ttsData && ttsData.original_data ? 
        Object.values(ttsData.original_data).reduce((sum, d) => sum + d.omega.length, 0) : 0;
    
    debugContent.innerHTML = `
        <div class="mt-2">
            <small>
                <strong>Temperatures:</strong> ${tempCount}<br>
                <strong>Reference:</strong> ${referenceTemp?.toFixed(1)}°C<br>
                <strong>Data points:</strong> ${dataPoints}<br>
                <strong>Session:</strong> ${ttsData ? 'Active' : 'None'}
            </small>
        </div>
    `;
}