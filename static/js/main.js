// Main JavaScript for TTS Web App

let uploadedTemperatures = [];
let currentTTS = null;

document.addEventListener('DOMContentLoaded', function() {
    // イベントリスナーの設定
    document.getElementById('uploadBtn').addEventListener('click', uploadFiles);
    document.getElementById('analyzeBtn').addEventListener('click', runAnalysis);
    document.getElementById('method').addEventListener('change', toggleMethodParams);
});

function uploadFiles() {
    const fileInput = document.getElementById('fileInput');
    const files = fileInput.files;
    
    if (files.length === 0) {
        alert('Please select files to upload');
        return;
    }
    
    const formData = new FormData();
    for (let file of files) {
        formData.append('files', file);
    }
    
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            uploadedTemperatures = data.temperatures;
            updateReferenceTemperatureSelect();
            document.getElementById('uploadStatus').innerHTML = 
                `<div class="alert alert-success">
                    Uploaded ${data.files.length} files. 
                    Temperatures: ${data.temperatures.join(', ')}°C
                </div>`;
        } else {
            throw new Error(data.error);
        }
    })
    .catch(error => {
        document.getElementById('uploadStatus').innerHTML = 
            `<div class="alert alert-danger">Error: ${error.message}</div>`;
    });
}

function updateReferenceTemperatureSelect() {
    const select = document.getElementById('refTemp');
    select.innerHTML = '';
    
    uploadedTemperatures.forEach(temp => {
        const option = document.createElement('option');
        option.value = temp;
        option.textContent = temp + '°C';
        select.appendChild(option);
    });
    
    // デフォルトで中間の温度を選択
    if (uploadedTemperatures.length > 0) {
        const midIndex = Math.floor(uploadedTemperatures.length / 2);
        select.selectedIndex = midIndex;
    }
}

function toggleMethodParams() {
    const method = document.getElementById('method').value;
    const wlfParams = document.getElementById('wlfParams');
    const arrheniusParams = document.getElementById('arrheniusParams');
    
    if (method === 'WLF') {
        wlfParams.style.display = 'block';
        arrheniusParams.style.display = 'none';
    } else {
        wlfParams.style.display = 'none';
        arrheniusParams.style.display = 'block';
    }
}

function runAnalysis() {
    const refTemp = document.getElementById('refTemp').value;
    const method = document.getElementById('method').value;
    
    if (!refTemp) {
        alert('Please select a reference temperature');
        return;
    }
    
    let params = {
        reference_temperature: parseFloat(refTemp),
        method: method
    };
    
    if (method === 'WLF') {
        params.C1 = parseFloat(document.getElementById('C1').value);
        params.C2 = parseFloat(document.getElementById('C2').value);
        params.fit_constants = document.getElementById('fitWLF').checked;
    } else {
        params.Ea = parseFloat(document.getElementById('Ea').value) * 1000; // kJ to J
        params.fit_Ea = document.getElementById('fitEa').checked;
    }
    
    // Show loading
    showLoading(true);
    
    fetch('/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(params)
    })
    .then(response => response.json())
    .then(data => {
        showLoading(false);
        if (data.status === 'success') {
            displayResults(data);
        } else {
            throw new Error(data.error);
        }
    })
    .catch(error => {
        showLoading(false);
        alert('Analysis error: ' + error.message);
    });
}

function displayResults(data) {
    const resultsDiv = document.getElementById('results');
    const plotContainer = document.getElementById('plotContainer');
    const shiftFactorsDiv = document.getElementById('shiftFactors');
    
    // Display plot
    if (data.plots && data.plots.master_curve) {
        plotContainer.innerHTML = `
            <img src="data:image/png;base64,${data.plots.master_curve}" 
                 alt="Master Curve" class="img-fluid">
        `;
    }
    
    // Display shift factors table
    let tableHTML = `
        <h4>Shift Factors</h4>
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Temperature (°C)</th>
                    <th>aT</th>
                    <th>log(aT)</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    for (let temp in data.shift_factors) {
        const sf = data.shift_factors[temp];
        tableHTML += `
            <tr>
                <td>${temp}</td>
                <td>${sf.aT.toExponential(3)}</td>
                <td>${sf.log_aT.toFixed(3)}</td>
            </tr>
        `;
    }
    
    tableHTML += '</tbody></table>';
    
    // Add parameters info
    if (data.method === 'WLF' && data.WLF_C1) {
        tableHTML += `
            <div class="alert alert-info">
                <strong>WLF Parameters:</strong><br>
                C₁ = ${data.WLF_C1.toFixed(2)}, C₂ = ${data.WLF_C2.toFixed(2)}
            </div>
        `;
    } else if (data.method === 'Arrhenius' && data.Ea_kJ) {
        tableHTML += `
            <div class="alert alert-info">
                <strong>Arrhenius Parameters:</strong><br>
                Ea = ${data.Ea_kJ.toFixed(1)} kJ/mol
            </div>
        `;
    }
    
    shiftFactorsDiv.innerHTML = tableHTML;
    resultsDiv.style.display = 'block';
    
    // Store current TTS data for download
    currentTTS = data;
}

function showLoading(show) {
    if (show) {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'loadingOverlay';
        loadingDiv.className = 'loading-overlay';
        loadingDiv.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div class="text-white mt-3">Analyzing...</div>
            </div>
        `;
        document.body.appendChild(loadingDiv);
    } else {
        const loadingDiv = document.getElementById('loadingOverlay');
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }
}// JavaScript Document