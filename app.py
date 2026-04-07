"""
YU-ARIM Time-Temperature Superposition Web Application
Flask-based TTS analysis tool - Complete Version
"""
"""
app.py - TTS Analysis Tool Web Application
修正版: セッション問題解消、シフトファクター重複解消、構造整理
"""

import os
import io
import re
import base64
import json
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask import (Flask, render_template, request, jsonify,
                   send_file, session)
from werkzeug.utils import secure_filename

from tts_core import TTS

# =============================================================
# App Configuration
# =============================================================
app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER='uploads',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,   # 16 MB
    ALLOWED_EXTENSIONS={'xlsx', 'xls', 'csv'},
    SECRET_KEY=os.environ.get('SECRET_KEY',
                              uuid.uuid4().hex),
)

# ★ セッションの代わりにサーバーサイドストレージを使用
#    （Flaskのcookieセッションは4KB制限があるため）
_server_store = {}

# Create directories
for d in ['uploads', 'static/results', 'static/css',
          'static/js', 'templates']:
    os.makedirs(d, exist_ok=True)


def allowed_file(filename):
    """Check if file extension is allowed"""
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower()
            in app.config['ALLOWED_EXTENSIONS'])


def get_session_id():
    """セッションIDを取得または作成"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def save_to_store(data):
    """サーバーサイドストアにデータ保存"""
    sid = get_session_id()
    _server_store[sid] = data


def load_from_store():
    """サーバーサイドストアからデータ取得"""
    sid = get_session_id()
    return _server_store.get(sid)


def clear_store():
    """サーバーサイドストアをクリア"""
    sid = session.get('session_id')
    if sid and sid in _server_store:
        del _server_store[sid]


# =============================================================
# Routes
# =============================================================
@app.route('/')
def index():
    """Main page"""
    template_path = os.path.join('templates', 'index.html')
    if os.path.exists(template_path):
        return render_template('index.html')

    return jsonify({
        'application': 'TTS Analysis Tool',
        'status': 'running',
        'version': '2.0.0',
        'message': 'Welcome to TTS Analysis Tool',
        'endpoints': {
            'upload':       '/upload       [POST]',
            'analyze':      '/analyze      [POST]',
            'manual':       '/manual_adjustment [GET]',
            'get_data':     '/get_current_data  [GET]',
            'update_shift': '/update_shift_factor [POST]',
            'save_manual':  '/save_manual_adjustment [POST]',
            'download':     '/download/<filename> [GET]',
            'clear':        '/clear        [POST]',
            'health':       '/health       [GET]',
        }
    })


@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# =============================================================
# File Upload
# =============================================================
@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file upload"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('files')
    uploaded_files = []
    temperatures = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filepath)

            # Extract temperature from filename
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


# =============================================================
# Analysis
# =============================================================
@app.route('/analyze', methods=['POST'])
def analyze():
    """Run TTS analysis"""
    try:
        data = request.json
        ref_temp = float(data.get('reference_temperature', 25))
        method = data.get('method', 'WLF')

        # Create TTS instance
        tts = TTS(T_ref=ref_temp)
        tts.load_excel(folder_path=app.config['UPLOAD_FOLDER'])

        # Perform shift
        if method == 'WLF':
            C1 = float(data.get('C1', 8.86))
            C2 = float(data.get('C2', 101.6))
            fit = data.get('fit_constants', False)
            tts.shift_WLF(C1=C1, C2=C2, fit_constants=fit)
        else:
            Ea = float(data.get('Ea', 80000))
            fit = data.get('fit_Ea', False)
            tts.shift_Arrhenius(Ea=Ea, fit_Ea=fit)

        # ★ サーバーサイドストアに保存（Cookie制限回避）
        store_data = {
            'reference_temperature': ref_temp,
            'method': method,
            'original_data': {},
            'shift_factors': {},
        }

        for T in tts.data:
            store_data['original_data'][str(T)] = {
                'omega': tts.data[T]['omega'].tolist(),
                'modulus': tts.data[T]['modulus'].tolist()
            }

        # ★ シフトファクター: 温度ごとに1つだけ
        store_data['shift_factors'] = tts.get_shift_factors_summary()

        save_to_store(store_data)

        # Generate plots
        plot_data = generate_plots(tts)

        # Response
        result = {
            'status': 'success',
            'reference_temperature': ref_temp,
            'method': method,
            'shift_factors': store_data['shift_factors'],
            'num_shift_factors': len(store_data['shift_factors']),
            'num_temperatures': len(tts.data),
            'plots': plot_data,
        }

        if method == 'WLF' and tts.WLF_C1:
            result['WLF_C1'] = float(tts.WLF_C1)
            result['WLF_C2'] = float(tts.WLF_C2)
        elif method == 'Arrhenius' and tts.Ea:
            result['Ea_kJ'] = float(tts.Ea / 1000)

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Analysis error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# =============================================================
# Manual Adjustment
# =============================================================
@app.route('/manual_adjustment')
def manual_adjustment_page():
    """Manual adjustment page"""
    template_path = os.path.join('templates', 'manual_adjustment.html')
    if os.path.exists(template_path):
        return render_template('manual_adjustment.html')
    return jsonify({
        'message': 'Manual adjustment page',
        'note': 'Create templates/manual_adjustment.html'
    })


@app.route('/get_current_data', methods=['GET'])
def get_current_data():
    """Get current analysis data"""
    data = load_from_store()
    if data:
        # ★ シフトファクター数を明示
        data['num_shift_factors'] = len(data.get('shift_factors', {}))
        return jsonify(data)
    return jsonify({'error': 'No data available. '
                    'Please run analysis first.'}), 404


@app.route('/update_shift_factor', methods=['POST'])
def update_shift_factor():
    """Update a single shift factor (manual adjustment)"""
    try:
        req = request.json
        temperature = str(float(req['temperature']))
        log_aT = float(req['log_aT'])

        data = load_from_store()
        if not data:
            return jsonify({'error': 'No data in session'}), 400

        # ★ 温度ごとに1つだけ更新
        data['shift_factors'][temperature] = {
            'aT': float(10 ** log_aT),
            'log_aT': log_aT
        }
        save_to_store(data)

        return jsonify({
            'status': 'success',
            'temperature': temperature,
            'aT': float(10 ** log_aT),
            'log_aT': log_aT,
            'total_shift_factors': len(data['shift_factors'])
        })

    except Exception as e:
        app.logger.error(f"Update shift factor error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/save_manual_adjustment', methods=['POST'])
def save_manual_adjustment():
    """Save manual adjustment results to Excel"""
    try:
        # リクエストデータまたはストアから取得
        req_data = request.json
        store_data = load_from_store()

        # マージ: リクエストデータ優先、なければストアから
        if req_data and 'original_data' in req_data:
            data = req_data
        elif store_data:
            data = store_data
            # リクエストでシフトファクターが更新されていれば上書き
            if req_data and 'shift_factors' in req_data:
                data['shift_factors'] = req_data['shift_factors']
        else:
            return jsonify({'error': 'No data available'}), 400

        # ファイル生成
        results_dir = os.path.join('static', 'results')
        os.makedirs(results_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'manual_adjustment_{timestamp}.xlsx'
        filepath = os.path.join(results_dir, filename)

        export_manual_results(data, filepath)

        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            return jsonify({
                'status': 'success',
                'filename': filename,
                'download_url': f'/download/{filename}',
                'file_size': file_size,
                'num_shift_factors': len(
                    data.get('shift_factors', {}))
            })
        else:
            raise Exception("File was not created")

    except Exception as e:
        app.logger.error(f"Save error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def export_manual_results(data, filepath):
    """
    Export manual adjustment results to Excel
    ★ シフトファクターは温度ごとに1行のみ
    """
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:

        # ── Sheet 1: Master Curve Data ──
        rows = []
        for temp_str, temp_data in data.get('original_data', {}).items():
            try:
                T = float(temp_str)
                sf = data.get('shift_factors', {}).get(temp_str, {})
                aT = sf.get('aT', 1.0)

                omega_list = temp_data.get('omega', [])
                modulus_list = temp_data.get('modulus', [])

                for i in range(len(omega_list)):
                    rows.append({
                        'Temperature [°C]': T,
                        'omega [rad/s]': omega_list[i],
                        "G' [Pa]": modulus_list[i],
                        'omega*aT [rad/s]': omega_list[i] * aT,
                    })
            except Exception as e:
                app.logger.error(
                    f"Error processing temp {temp_str}: {e}")

        if rows:
            pd.DataFrame(rows).to_excel(
                writer, sheet_name='Master Curve Data', index=False)
            app.logger.info(
                f"Master Curve Data: {len(rows)} rows")

        # ── Sheet 2: Shift Factors（★ 温度ごとに1行のみ！）──
        sf_rows = []
        for temp_str, sf in sorted(
                data.get('shift_factors', {}).items(),
                key=lambda x: float(x[0])):
            try:
                sf_rows.append({
                    'Temperature [°C]': float(temp_str),
                    'aT': sf.get('aT', 1.0),
                    'log(aT)': sf.get('log_aT', 0.0),
                })
            except Exception as e:
                app.logger.error(
                    f"Error processing SF for {temp_str}: {e}")

        if sf_rows:
            df_sf = pd.DataFrame(sf_rows)
            df_sf.to_excel(
                writer, sheet_name='Shift Factors', index=False)
            app.logger.info(
                f"Shift Factors: {len(sf_rows)} rows "
                f"(= {len(sf_rows)} temperatures) ✓")

        # ── Sheet 3: Parameters ──
        ref_temp = data.get('reference_temperature', 'N/A')
        params = {
            'Parameter': [
                'Reference Temperature [°C]',
                'Adjustment Type',
                'Number of Temperatures',
                'Number of Shift Factors',
                'Export Date',
            ],
            'Value': [
                ref_temp,
                'Manual',
                len(data.get('original_data', {})),
                len(data.get('shift_factors', {})),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ]
        }
        pd.DataFrame(params).to_excel(
            writer, sheet_name='Parameters', index=False)

    app.logger.info(f"Excel exported: {filepath}")


# =============================================================
# Download
# =============================================================
@app.route('/download/<filename>')
def download_file(filename):
    """Download result file"""
    try:
        filename = secure_filename(filename)

        possible_paths = [
            os.path.join('static', 'results', filename),
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                app.logger.info(f"Download: {path}")
                return send_file(
                    path,
                    as_attachment=True,
                    download_name=filename,
                )

        return jsonify({'error': f'File not found: {filename}'}), 404

    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# =============================================================
# Clear
# =============================================================
@app.route('/clear', methods=['POST'])
def clear_uploads():
    """Clear uploaded files and session"""
    try:
        folder = app.config['UPLOAD_FOLDER']
        for f in os.listdir(folder):
            fpath = os.path.join(folder, f)
            if os.path.isfile(fpath):
                os.remove(fpath)

        clear_store()
        session.clear()

        return jsonify({'status': 'success'})

    except Exception as e:
        app.logger.error(f"Clear error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# =============================================================
# Plot Generation
# =============================================================
def generate_plots(tts):
    """Generate plots and return as Base64"""
    plots = {}
    try:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        temps = sorted(tts.data.keys())
        colors = plt.cm.coolwarm(np.linspace(0, 1, len(temps)))
        factors = tts.get_current_shift_factors()

        # 1. Original data
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

        # 2. Master curve
        ax = axes[0, 1]
        for i, T in enumerate(temps):
            omega_shifted = tts.data[T]['omega'] * factors[T]
            ax.loglog(omega_shifted, tts.data[T]['modulus'],
                      'o-', color=colors[i], label=f'{T}°C',
                      markersize=5, alpha=0.7)
        ax.set_xlabel('ω·aT [rad/s]')
        ax.set_ylabel("G' [Pa]")
        ax.set_title(f'Master Curve (Tref = {tts.T_ref}°C)')
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()

        # 3. Shift factors（★ 温度ごとに1点）
        ax = axes[1, 0]
        temps_arr = np.array(sorted(factors.keys()))
        log_aT = [np.log10(factors[T]) for T in temps_arr]
        ax.plot(temps_arr, log_aT, 'bo-', markersize=10, linewidth=2)
        for T_val, la in zip(temps_arr, log_aT):
            ax.annotate(f'  {T_val:.0f}°C: {la:.3f}',
                        (T_val, la), fontsize=9)
        ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        ax.axvline(x=tts.T_ref, color='r', linestyle='--', alpha=0.5)
        ax.set_xlabel('Temperature [°C]')
        ax.set_ylabel('log(aT)')
        ax.set_title(
            f'Shift Factors ({len(factors)} temperatures)')
        ax.grid(True, alpha=0.3)

        # 4. Method-specific plot
        ax = axes[1, 1]
        if tts.shift_method == 'WLF':
            _plot_wlf(ax, tts, factors)
        elif tts.shift_method == 'Arrhenius':
            _plot_arrhenius(ax, tts, factors)

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plots['master_curve'] = base64.b64encode(
            buf.getvalue()).decode()
        plt.close(fig)

    except Exception as e:
        app.logger.error(f"Plot error: {str(e)}")
        plots['error'] = str(e)

    return plots


def _plot_wlf(ax, tts, factors):
    """WLF plot"""
    try:
        temps_arr = np.array(sorted(factors.keys()))
        non_ref = temps_arr[temps_arr != tts.T_ref]
        T_diff = non_ref - tts.T_ref
        log_aT_nr = [np.log10(factors[T]) for T in non_ref]

        if len(T_diff) > 0:
            x_data = 1 / T_diff
            y_data = -np.array(log_aT_nr) / T_diff
            ax.plot(x_data, y_data, 'ro', markersize=10)

            if tts.WLF_C1 and tts.WLF_C2:
                x_rng = np.linspace(
                    min(x_data) * 1.1, max(x_data) * 1.1, 100)
                y_th = tts.WLF_C1 / (tts.WLF_C2 * x_rng + 1)
                ax.plot(x_rng, y_th, 'b-', linewidth=2, alpha=0.7,
                        label=f'C1={tts.WLF_C1:.2f}, '
                              f'C2={tts.WLF_C2:.2f}')
                ax.legend()

        ax.set_xlabel('1/(T-Tref) [1/°C]')
        ax.set_ylabel('-log(aT)/(T-Tref)')
        ax.set_title('WLF Plot')
        ax.grid(True, alpha=0.3)
    except Exception as e:
        app.logger.error(f"WLF plot error: {e}")


def _plot_arrhenius(ax, tts, factors):
    """Arrhenius plot"""
    try:
        temps_arr = np.array(sorted(factors.keys()))
        T_K = temps_arr + 273.15
        log_aT_all = [np.log10(factors[T]) for T in temps_arr]
        ax.plot(1000 / T_K, log_aT_all, 'ro', markersize=10)

        if tts.Ea:
            T_rng = np.linspace(
                min(temps_arr) - 20, max(temps_arr) + 20, 100
            ) + 273.15
            T_ref_K = tts.T_ref + 273.15
            R = 8.314
            log_th = (tts.Ea / R) * (1 / T_rng - 1 / T_ref_K) \
                     / np.log(10)
            ax.plot(1000 / T_rng, log_th, 'b-', linewidth=2,
                    alpha=0.7,
                    label=f'Ea={tts.Ea / 1000:.1f} kJ/mol')
            ax.legend()

        ax.set_xlabel('1000/T [1/K]')
        ax.set_ylabel('log(aT)')
        ax.set_title('Arrhenius Plot')
        ax.grid(True, alpha=0.3)
    except Exception as e:
        app.logger.error(f"Arrhenius plot error: {e}")


# =============================================================
# Error Handlers
# =============================================================
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"Server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500


# =============================================================
# Main
# =============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'

    print(f"\n{'=' * 50}")
    print(f"  TTS Analysis Tool v2.0")
    print(f"  http://0.0.0.0:{port}")
    print(f"  Debug: {debug}")
    print(f"{'=' * 50}\n")

    app.run(host='0.0.0.0', port=port, debug=debug)
    