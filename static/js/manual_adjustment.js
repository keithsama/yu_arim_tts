// Manual Adjustment JavaScript

let ttsData = null;
let originalShiftFactors = {};
let currentShiftFactors = {};
let referenceTemp = null;

// ページロード時の初期化
document.addEventListener('DOMContentLoaded', function() {
    loadCurrentData();
    setupEventListeners();
});

function loadCurrentData() {
    fetch('/get_current_data')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showMessage('No data available. Please run analysis first.', 'error');
                return;
            }
            
            ttsData = data;
            referenceTemp = data.reference_temperature;
            originalShiftFactors = JSON.parse(JSON.stringify(data.shift_factors));
            currentShiftFactors = JSON.parse(JSON.stringify(data.shift_factors));
            
            document.getElementById('refTempDisplay').textContent = referenceTemp + '°C';
            
            createSliders();
            updatePlots();
            updateTable();
        })
        .catch(error => {
            console.error('Error loading data:', error);
            showMessage('Error loading data', 'error');
        });
}

function createSliders() {
    const container = document.getElementById('sliderContainer');
    container.innerHTML = '';
    
    const temperatures = Object.keys(currentShiftFactors).map(t => parseFloat(t)).sort();
    
    temperatures.forEach(temp => {
        if (temp === referenceTemp) return; // Skip reference temperature
        
        const sliderId = `slider-${temp}`;
        const currentLogAT = currentShiftFactors[temp].log_aT;
        
        const sliderHTML = `
            <div class="slider-container">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="slider-label">${temp}°C</span>
                    <span class="slider-value" id="value-${temp}">${currentLogAT.toFixed(3)}</span>
                </div>
                <input type="range" 
                       class="form-range temperature-slider" 
                       id="${sliderId}"
                       min="-3" 
                       max="3" 
                       step="0.01" 
                       value="${currentLogAT}"
                       data-temperature="${temp}">
            </div>
        `;
        
        container.innerHTML += sliderHTML;
    });
    
    // スライダーイベントリスナー追加
    temperatures.forEach(temp => {
        if (temp === referenceTemp) return;
        
        const slider = document.getElementById(`slider-${temp}`);
        slider.addEventListener('input', function(e) {
            handleSliderChange(temp, parseFloat(e.target.value));
        });
    });
}

function handleSliderChange(temperature, logATValue) {
    // 値を更新
    currentShiftFactors[temperature] = {
        aT: Math.pow(10, logATValue),
        log_aT: logATValue
    };
    
    // 表示を更新
    document.getElementById(`value-${temperature}`).textContent = logATValue.toFixed(3);
    
    // プロットを更新
    updatePlots();
    updateTable();
    
    // サーバーに送信（デバウンス処理を追加する場合）
    updateServerData(temperature, logATValue);
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
    });
}

function updatePlots() {
    plotMasterCurve();
    plotOriginalData();
    plotShiftFactors();
}

function plotMasterCurve() {
    const traces = [];
    const colors = generateColors(Object.keys(ttsData.original_data).length);
    
    Object.keys(ttsData.original_data).forEach((temp, index) => {
        const tempFloat = parseFloat(temp);
        const data = ttsData.original_data[temp];
        const aT = currentShiftFactors[temp].aT;
        
        // シフトされたデータ
        const shiftedOmega = data.omega.map(w => w * aT);
        
        traces.push({
            x: shiftedOmega,
            y: data.modulus,
            mode: 'lines+markers',
            name: `${temp}°C`,
            line: { color: colors[index], width: 2 },
            marker: { size: 6 }
        });
    });
    
    const layout = {
        title: `Master Curve (T<sub>ref</sub> = ${referenceTemp}°C)`,
        xaxis: {
            title: 'ω·a<sub>T</sub> [rad/s]',
            type: 'log',
            gridcolor: '#e0e0e0'
        },
        yaxis: {
            title: "G' [Pa]",
            type: 'log',
            gridcolor: '#e0e0e0'
        },
        hovermode: 'closest',
        showlegend: true
    };
    
    Plotly.newPlot('masterCurvePlot', traces, layout);
}

function plotOriginalData() {
    const traces = [];
    const colors = generateColors(Object.keys(ttsData.original_data).length);
    
    Object.keys(ttsData.original_data).forEach((temp, index) => {
        const data = ttsData.original_data[temp];
        
        traces.push({
            x: data.omega,
            y: data.modulus,
            mode: 'lines+markers',
            name: `${temp}°C`,
            line: { color: colors[index], width: 2 },
            marker: { size: 5 }
        });
    });
    
    const layout = {
        title: 'Original Data',
        xaxis: {
            title: 'ω [rad/s]',
            type: 'log',
            gridcolor: '#e0e0e0'
        },
        yaxis: {
            title: "G' [Pa]",
            type: 'log',
            gridcolor: '#e0e0e0'
        },
        hovermode: 'closest',
        showlegend: true,
        legend: {
            x: 0.02,
            y: 0.98
        }
    };
    
    Plotly.newPlot('originalDataPlot', traces, layout);
}

function plotShiftFactors() {
    const temperatures = Object.keys(currentShiftFactors).map(t => parseFloat(t)).sort();
    const logATs = temperatures.map(t => currentShiftFactors[t].log_aT);
    const originalLogATs = temperatures.map(t => originalShiftFactors[t].log_aT);
    
    const traces = [
        {
            x: temperatures,
            y: logATs,
            mode: 'lines+markers',
            name: 'Current',
            line: { color: 'blue', width: 2 },
            marker: { size: 10 }
        },
        {
            x: temperatures,
            y: originalLogATs,
            mode: 'markers',
            name: 'Original',
            marker: { 
                color: 'red', 
                size: 8,
                symbol: 'circle-open'
            }
        }
    ];
    
    const layout = {
        title: 'Shift Factors',
        xaxis: {
            title: 'Temperature [°C]',
            gridcolor: '#e0e0e0'
        },
        yaxis: {
            title: 'log(a<sub>T</sub>)',
            gridcolor: '#e0e0e0',
            zeroline: true,
            zerolinecolor: '#ff0000',
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
                    color: 'red',
                    width: 1,
                    dash: 'dash'
                }
            }
        ],
        hovermode: 'closest'
    };
    
    Plotly.newPlot('shiftFactorPlot', traces, layout);
}

function updateTable() {
    const tbody = document.getElementById('shiftFactorTable');
    tbody.innerHTML = '';
    
    const temperatures = Object.keys(currentShiftFactors).map(t => parseFloat(t)).sort();
    
    temperatures.forEach(temp => {
        const sf = currentShiftFactors[temp];
        const row = `
            <tr class="${temp === referenceTemp ? 'table-primary' : ''}">
                <td>${temp}</td>
                <td>${sf.aT.toExponential(2)}</td>
                <td>${sf.log_aT.toFixed(3)}</td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

function setupEventListeners() {
    // リセットボタン
    document.getElementById('resetBtn').addEventListener('click', function() {
        currentShiftFactors = JSON.parse(JSON.stringify(originalShiftFactors));
        
        // スライダーをリセット
        Object.keys(currentShiftFactors).forEach(temp => {
            if (parseFloat(temp) === referenceTemp) return;
            
            const slider = document.getElementById(`slider-${temp}`);
            if (slider) {
                slider.value = currentShiftFactors[temp].log_aT;
                document.getElementById(`value-${temp}`).textContent = 
                    currentShiftFactors[temp].log_aT.toFixed(3);
            }
        });
        
        updatePlots();
        updateTable();
        showMessage('Reset to original values', 'success');
    });
    
    // 保存ボタン
    document.getElementById('saveBtn').addEventListener('click', function() {
        const saveData = {
            reference_temperature: referenceTemp,
            shift_factors: currentShiftFactors,
            timestamp: new Date().toISOString()
        };
        
        // ローカルストレージに保存
        localStorage.setItem('tts_manual_adjustment', JSON.stringify(saveData));
        showMessage('Settings saved locally', 'success');
    });
    
    // エクスポートボタン
    document.getElementById('exportBtn').addEventListener('click', function() {
        fetch('/save_manual_adjustment', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                reference_temperature: referenceTemp,
                original_data: ttsData.original_data,
                shift_factors: currentShiftFactors
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // ダウンロードリンクを作成
                const link = document.createElement('a');
                link.href = data.download_url;
                link.download = data.filename;
                link.click();
                
                showMessage('Excel file exported successfully', 'success');
            }
        })
        .catch(error => {
            showMessage('Export failed: ' + error, 'error');
        });
    });
}

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
    const alertClass = type === 'error' ? 'alert-danger' : 'alert-success';
    
    messageDiv.innerHTML = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // 3秒後に自動的に消す
    setTimeout(() => {
        messageDiv.innerHTML = '';
    }, 3000);
}// JavaScript Document