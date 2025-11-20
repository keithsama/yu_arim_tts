"""
Time-Temperature Superposition Web Application
Flask-based TTS analysis tool
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import io
import base64
import json
from werkzeug.utils import secure_filename
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # バックエンドを設定
import matplotlib.pyplot as plt
from datetime import datetime
import tempfile
from pathlib import Path

# TTSクラスをインポート（既存のコードを別ファイルとして保存）
from tts_core import TTS

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}

# アップロードフォルダの作成
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/results', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    """メインページ"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    """ファイルアップロード処理"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    temperatures = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filepath)
            
            # ファイル名から温度を抽出
            import re
            numbers = re.findall(r'-?\d+\.?\d*', filename)
            if numbers:
                temperatures.append(float(numbers[0]))
    
    if not uploaded_files:
        return jsonify({'error': 'No valid files uploaded'}), 400
    
    return jsonify({
        'status': 'success',
        'files': uploaded_files,
        'temperatures': sorted(list(set(temperatures)))
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    """TTS解析の実行"""
    try:
        data = request.json
        
        # パラメータの取得
        ref_temp = float(data.get('reference_temperature', 25))
        method = data.get('method', 'WLF')  # WLF or Arrhenius
        
        # TTSインスタンスの作成
        tts = TTS(T_ref=ref_temp)
        
        # データの読み込み
        tts.load_excel(folder_path=app.config['UPLOAD_FOLDER'])
        
        # シフト計算
        if method == 'WLF':
            C1 = float(data.get('C1', 8.86))
            C2 = float(data.get('C2', 101.6))
            fit = data.get('fit_constants', False)
            tts.shift_WLF(C1=C1, C2=C2, fit_constants=fit)
        else:  # Arrhenius
            Ea = float(data.get('Ea', 80000))
            fit = data.get('fit_Ea', False)
            tts.shift_Arrhenius(Ea=Ea, fit_Ea=fit)
        
        # プロット生成
        plot_data = generate_plots(tts)
        
        # シフトファクターの取得
        shift_factors = {}
        for T in tts.shift_factors:
            shift_factors[str(T)] = {
                'aT': tts.shift_factors[T],
                'log_aT': np.log10(tts.shift_factors[T])
            }
        
        # 結果の準備
        result = {
            'status': 'success',
            'reference_temperature': ref_temp,
            'method': method,
            'shift_factors': shift_factors,
            'plots': plot_data
        }
        
        if method == 'WLF' and tts.WLF_C1:
            result['WLF_C1'] = tts.WLF_C1
            result['WLF_C2'] = tts.WLF_C2
        elif method == 'Arrhenius' and tts.Ea:
            result['Ea_kJ'] = tts.Ea / 1000
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_plots(tts):
    """プロットを生成してBase64エンコード"""
    plots = {}
    
    # マスターカーブプロット
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    temps = sorted(tts.data.keys())
    colors = plt.cm.coolwarm(np.linspace(0, 1, len(temps)))
    
    # 元データ
    ax = axes[0, 0]
    for i, T in enumerate(temps):
        ax.loglog(tts.data[T]['omega'], tts.data[T]['modulus'], 
                 'o-', color=colors[i], label=f'{T}°C', 
                 markersize=5, alpha=0.7)
    ax.set_xlabel('ω [rad/s]')
    ax.set_ylabel("G' [Pa]")
    ax.set_title('Original Data')
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    
    # マスターカーブ
    ax = axes[0, 1]
    for i, T in enumerate(temps):
        omega_shifted = tts.data[T]['omega'] * tts.shift_factors[T]
        ax.loglog(omega_shifted, tts.data[T]['modulus'], 
                 'o-', color=colors[i], label=f'{T}°C',
                 markersize=5, alpha=0.7)
    ax.set_xlabel('ω·aT [rad/s]')
    ax.set_ylabel("G' [Pa]")
    ax.set_title(f'Master Curve (Tref = {tts.T_ref}°C)')
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    
    # シフトファクター
    ax = axes[1, 0]
    temps_arr = np.array(sorted(tts.shift_factors.keys()))
    log_aT = [np.log10(tts.shift_factors[T]) for T in temps_arr]
    ax.plot(temps_arr, log_aT, 'bo-', markersize=10, linewidth=2)
    ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
    ax.axvline(x=tts.T_ref, color='r', linestyle='--', alpha=0.5)
    ax.set_xlabel('Temperature [°C]')
    ax.set_ylabel('log(aT)')
    ax.set_title('Shift Factors')
    ax.grid(True, alpha=0.3)
    
    # WLF/Arrheniusプロット
    ax = axes[1, 1]
    if tts.shift_method == 'WLF':
        plot_wlf(ax, tts)
    else:
        plot_arrhenius(ax, tts)
    
    plt.tight_layout()
    
    # Base64エンコード
    img = io.BytesIO()
    plt.savefig(img, format='png', dpi=100)
    img.seek(0)
    plots['master_curve'] = base64.b64encode(img.getvalue()).decode()
    plt.close()
    
    return plots

def plot_wlf(ax, tts):
    """WLFプロット"""
    temps_arr = np.array(sorted(tts.shift_factors.keys()))
    T_diff = temps_arr[temps_arr != tts.T_ref] - tts.T_ref
    log_aT_nonref = [np.log10(tts.shift_factors[T]) for T in temps_arr if T != tts.T_ref]
    
    if len(T_diff) > 0:
        x_data = 1 / T_diff
        y_data = -np.array(log_aT_nonref) / T_diff
        ax.plot(x_data, y_data, 'ro', markersize=10)
        
        if tts.WLF_C1 and tts.WLF_C2:
            x_range = np.linspace(min(x_data)*1.1, max(x_data)*1.1, 100)
            y_theory = tts.WLF_C1 / (tts.WLF_C2 * x_range + 1)
            ax.plot(x_range, y_theory, 'b-', linewidth=2, alpha=0.7)
        
        ax.set_xlabel('1/(T-Tref) [1/°C]')
        ax.set_ylabel('-log(aT)/(T-Tref)')
        ax.set_title(f'WLF Plot (C₁={tts.WLF_C1:.2f}, C₂={tts.WLF_C2:.2f})')
        ax.grid(True, alpha=0.3)

def plot_arrhenius(ax, tts):
    """Arrheniusプロット"""
    temps_arr = np.array(sorted(tts.shift_factors.keys()))
    T_K = temps_arr + 273.15
    log_aT_all = [np.log10(tts.shift_factors[T]) for T in temps_arr]
    ax.plot(1000/T_K, log_aT_all, 'ro', markersize=10)
    
    if tts.Ea:
        T_range = np.linspace(min(temps_arr)-20, max(temps_arr)+20, 100) + 273.15
        T_ref_K = tts.T_ref + 273.15
        R = 8.314
        log_aT_theory = (tts.Ea/R) * (1/T_range - 1/T_ref_K) / np.log(10)
        ax.plot(1000/T_range, log_aT_theory, 'b-', linewidth=2, alpha=0.7)
    
    ax.set_xlabel('1000/T [1/K]')
    ax.set_ylabel('log(aT)')
    ax.set_title(f'Arrhenius Plot (Ea={tts.Ea/1000:.1f} kJ/mol)')
    ax.grid(True, alpha=0.3)

@app.route('/download/<filename>')
def download_file(filename):
    """結果ファイルのダウンロード"""
    try:
        path = os.path.join('static/results', filename)
        return send_file(path, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/clear', methods=['POST'])
def clear_uploads():
    """アップロードフォルダのクリア"""
    try:
        for file in os.listdir(app.config['UPLOAD_FOLDER']):
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file))
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)