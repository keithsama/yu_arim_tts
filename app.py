"""
YU-ARIM Time-Temperature Superposition Web Application
Flask-based TTS analysis tool - Complete Version
"""
"""
app.py - TTS Analysis Tool Web Application
修正版: セッション問題解消、シフトファクター重複解消、構造整理
"""
"""
app.py - TTS Analysis Tool Web Application
修正版v3: "The string did not match the expected pattern" 対応
"""

import os
import io
import re
import base64
import json
import uuid
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask import (Flask, render_template, request, jsonify,
                   send_file, session, make_response)
from werkzeug.utils import secure_filename

from tts_core import TTS

# =============================================================
# App Configuration
# =============================================================
app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER='uploads',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    ALLOWED_EXTENSIONS={'xlsx', 'xls', 'csv'},
    SECRET_KEY=os.environ.get('SECRET_KEY', uuid.uuid4().hex),
    SESSION_COOKIE_SAMESITE='Lax',
)

# ★ サーバーサイドストレージ（Cookie 4KB制限回避）
_server_store = {}

# Create directories
for d in ['uploads', 'static/results', 'static/css',
          'static/js', 'templates']:
    os.makedirs(d, exist_ok=True)


def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower()
            in app.config['ALLOWED_EXTENSIONS'])


def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def save_to_store(data):
    sid = get_session_id()
    _server_store[sid] = data


def load_from_store():
    sid = session.get('session_id')
    if sid:
        return _server_store.get(sid)
    return None


def clear_store():
    sid = session.get('session_id')
    if sid and sid in _server_store:
        del _server_store[sid]


def safe_float(value, default=0.0):
    """★ 安全にfloat変換（エラー防止）"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def numpy_to_python(obj):
    """★ numpy型をPython標準型に変換（JSON直列化エラー防止）"""
    if isinstance(obj, dict):
        return {str(k): numpy_to_python(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [numpy_to_python(item) for item in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    else:
        return obj


# =============================================================
# Routes
# =============================================================
@app.route('/')
def index():
    template_path = os.path.join('templates', 'index.html')
    if os.path.exists(template_path):
        return render_template('index.html')

    return jsonify({
        'application': 'TTS Analysis Tool',
        'status': 'running',
        'version': '3.0.0',
        'endpoints': {
            'upload': '/upload [POST]',
            'analyze': '/analyze [POST]',
            'manual': '/manual_adjustment [GET]',
            'get_data': '/get_current_data [GET]',
            'update_shift': '/update_shift_factor [POST]',
            'save_manual': '/save_manual_adjustment [POST]',
            'download': '/download/<filename> [GET]',
            'clear': '/clear [POST]',
            'health': '/health [GET]',
        }
    })


@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# =============================================================
# File Upload
# =============================================================
@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('files')
    uploaded_files = []
    temperatures = []

    for file in files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filepath)

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
# ★ Analysis（主要修正箇所）
# =============================================================
@app.route('/analyze', methods=['POST'])
def analyze():
    """Run TTS analysis"""
    try:
        # ★ 修正1: request.json が None の場合の防御
        data = request.get_json(force=True, silent=True)

        if data is None:
            # フォームデータとして送られた場合の対処
            data = {}
            for key in ['reference_temperature', 'method',
                        'C1', 'C2', 'Ea',
                        'fit_constants', 'fit_Ea']:
                val = request.form.get(key)
                if val is not None:
                    data[key] = val

        if not data:
            return jsonify({
                'error': 'No data received. '
                         'Send JSON with Content-Type: application/json'
            }), 400

        app.logger.info(f"Analyze request: {data}")

        # ★ 修正2: safe_float で安全に変換
        ref_temp = safe_float(data.get('reference_temperature'), 25.0)
        method = str(data.get('method', 'WLF')).strip()

        # アップロードファイルの存在確認
        upload_dir = app.config['UPLOAD_FOLDER']
        data_files = [f for f in os.listdir(upload_dir)
                      if f.endswith(('.xlsx', '.xls', '.csv'))]

        if not data_files:
            return jsonify({
                'error': 'No data files found. '
                         'Please upload files first.'
            }), 400

        app.logger.info(
            f"Files in upload dir: {data_files}")

        # Create TTS instance
        tts = TTS(T_ref=ref_temp)

        try:
            tts.load_excel(folder_path=upload_dir)
        except FileNotFoundError as e:
            return jsonify({
                'error': f'Data loading failed: {str(e)}'
            }), 400
        except ValueError as e:
            return jsonify({
                'error': f'Data validation failed: {str(e)}'
            }), 400

        # ★ 修正3: 基準温度がデータに存在するか確認
        available_temps = sorted(tts.data.keys())
        if ref_temp not in tts.data:
            # 最も近い温度を選択
            closest = min(available_temps,
                          key=lambda t: abs(t - ref_temp))
            app.logger.warning(
                f"Tref={ref_temp}°C not found. "
                f"Using closest: {closest}°C")
            tts.T_ref = closest
            ref_temp = closest

        # Perform shift
        if method.upper() == 'WLF':
            C1 = safe_float(data.get('C1'), 8.86)
            C2 = safe_float(data.get('C2'), 101.6)
            fit = bool(data.get('fit_constants', False))
            tts.shift_WLF(C1=C1, C2=C2, fit_constants=fit)
        elif method.upper() == 'ARRHENIUS':
            Ea = safe_float(data.get('Ea'), 80000)
            fit = bool(data.get('fit_Ea', False))
            tts.shift_Arrhenius(Ea=Ea, fit_Ea=fit)
        else:
            return jsonify({
                'error': f'Unknown method: {method}. '
                         f'Use "WLF" or "Arrhenius".'
            }), 400

        # ★ 修正4: サーバーサイドストアに保存（numpy→python変換）
        store_data = {
            'reference_temperature': float(ref_temp),
            'method': method,
            'original_data': {},
            'shift_factors': {},
        }

        for T in tts.data:
            store_data['original_data'][str(float(T))] = {
                'omega': tts.data[T]['omega'].tolist(),
                'modulus': tts.data[T]['modulus'].tolist()
            }

        # ★ シフトファクター: 温度ごとに1つだけ
        factors = tts.get_current_shift_factors()
        for T in sorted(factors.keys()):
            aT = float(factors[T])
            store_data['shift_factors'][str(float(T))] = {
                'aT': aT,
                'log_aT': float(np.log10(aT)) if aT > 0 else 0.0
            }

        save_to_store(store_data)

        # Generate plots
        plot_data = generate_plots(tts)

        # ★ 修正5: レスポンスを全て Python標準型に変換
        result = numpy_to_python({
            'status': 'success',
            'reference_temperature': ref_temp,
            'method': method,
            'shift_factors': store_data['shift_factors'],
            'num_shift_factors': len(store_data['shift_factors']),
            'num_temperatures': len(tts.data),
            'available_temperatures': available_temps,
            'plots': plot_data,
        })

        # Method-specific parameters
        if method.upper() == 'WLF' and tts.WLF_C1 is not None:
            result['WLF_C1'] = float(tts.WLF_C1)
            result['WLF_C2'] = float(tts.WLF_C2)
        elif method.upper() == 'ARRHENIUS' and tts.Ea is not None:
            result['Ea_kJ'] = float(tts.Ea / 1000)

        # ★ 修正6: 明示的にJSON文字列を作成
        response = make_response(
            json.dumps(result, ensure_ascii=False, default=str))
        response.headers['Content-Type'] = 'application/json'
        return response

    except Exception as e:
        error_detail = traceback.format_exc()
        app.logger.error(f"Analysis error: {error_detail}")
        return jsonify({
            'error': str(e),
            'detail': error_detail
        }), 500


# =============================================================
# Manual Adjustment
# =============================================================
@app.route('/manual_adjustment')
def manual_adjustment_page():
    template_path = os.path.join(
        'templates', 'manual_adjustment.html')
    if os.path.exists(template_path):
        return render_template('manual_adjustment.html')
    return jsonify({
        'message': 'Manual adjustment page',
        'note': 'Create templates/manual_adjustment.html'
    })


@app.route('/get_current_data', methods=['GET'])
def get_current_data():
    """Get current analysis data"""
    try:
        data = load_from_store()
        if data:
            data['num_shift_factors'] = len(
                data.get('shift_factors', {}))
            safe_data = numpy_to_python(data)

            response = make_response(
                json.dumps(safe_data,
                           ensure_ascii=False, default=str))
            response.headers['Content-Type'] = 'application/json'
            return response

        return jsonify({
            'error': 'No data available. Run analysis first.'
        }), 404

    except Exception as e:
        app.logger.error(f"get_current_data error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/update_shift_factor', methods=['POST'])
def update_shift_factor():
    """Update a single shift factor"""
    try:
        req = request.get_json(force=True, silent=True)
        if not req:
            return jsonify({
                'error': 'No JSON data received'
            }), 400

        temperature = str(safe_float(req.get('temperature')))
        log_aT = safe_float(req.get('log_aT'), 0.0)

        data = load_from_store()
        if not data:
            return jsonify({
                'error': 'No data in session. Run analysis first.'
            }), 400

        # ★ 温度ごとに1つだけ更新
        aT = float(10 ** log_aT)
        data['shift_factors'][temperature] = {
            'aT': aT,
            'log_aT': float(log_aT)
        }
        save_to_store(data)

        return jsonify({
            'status': 'success',
            'temperature': temperature,
            'aT': aT,
            'log_aT': float(log_aT),
            'total_shift_factors': len(data['shift_factors'])
        })

    except Exception as e:
        app.logger.error(f"Update shift factor error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/save_manual_adjustment', methods=['POST'])
def save_manual_adjustment():
    """Save manual adjustment results to Excel"""
    try:
        req_data = request.get_json(force=True, silent=True)
        store_data = load_from_store()

        if req_data and 'original_data' in req_data:
            data = req_data
        elif store_data:
            data = store_data
            if req_data and 'shift_factors' in req_data:
                data['shift_factors'] = req_data['shift_factors']
        else:
            return jsonify({
                'error': 'No data available'
            }), 400

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
        app.logger.error(
            f"Save error: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


def export_manual_results(data, filepath):
    """
    Export manual adjustment results to Excel
    ★ シフトファクターは温度ごとに1行のみ
    """
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:

        # Sheet 1: Master Curve Data（aT列なし）
        rows = []
        for temp_str, temp_data in data.get(
                'original_data', {}).items():
            try:
                T = float(temp_str)
                sf = data.get('shift_factors', {}).get(
                    temp_str, {})
                aT = safe_float(sf.get('aT'), 1.0)

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
                    f"Error on temp {temp_str}: {e}")

        if rows:
            pd.DataFrame(rows).to_excel(
                writer, sheet_name='Master Curve Data',
                index=False)

        # ★ Sheet 2: Shift Factors（温度ごとに1行のみ！）
        sf_rows = []
        for temp_str in sorted(
                data.get('shift_factors', {}).keys(),
                key=lambda x: float(x)):
            sf = data['shift_factors'][temp_str]
            sf_rows.append({
                'Temperature [°C]': float(temp_str),
                'aT': safe_float(sf.get('aT'), 1.0),
                'log(aT)': safe_float(sf.get('log_aT'), 0.0),
            })

        if sf_rows:
            pd.DataFrame(sf_rows).to_excel(
                writer, sheet_name='Shift Factors',
                index=False)
            app.logger.info(
                f"Shift Factors: {len(sf_rows)} rows ✓")

        # Sheet 3: Parameters
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
                ref_temp, 'Manual',
                len(data.get('original_data', {})),
                len(data.get('shift_factors', {})),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ]
        }
        pd.DataFrame(params).to_excel(
            writer, sheet_name='Parameters', index=False)

    app.logger.info(f"Excel exported: {filepath}")


# =============================================================
# Download / Clear
# =============================================================
@app.route('/download/<filename>')
def download_file(filename):
    try:
        filename = secure_filename(filename)
        for path in [
            os.path.join('static', 'results', filename),
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
        ]:
            if os.path.exists(path):
                return send_file(path, as_attachment=True,
                                 download_name=filename)

        return jsonify({
            'error': f'File not found: {filename}'
        }), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/clear', methods=['POST'])
def clear_uploads():
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
        return jsonify({'error': str(e)}), 500


# =============================================================
# Plot Generation
# =============================================================
def generate_plots(tts):
    plots = {}
    try:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        temps = sorted(tts.data.keys())
        colors = plt.cm.coolwarm(
            np.linspace(0, 1, max(len(temps), 1)))
        factors = tts.get_current_shift_factors()

        # 1. Original
        ax = axes[0, 0]
        for i, T in enumerate(temps):
            ax.loglog(tts.data[T]['omega'],
                      tts.data[T]['modulus'],
                      'o-', color=colors[i],
                      label=f'{T}°C',
                      markersize=5, alpha=0.7)
        ax.set_xlabel('ω [rad/s]')
        ax.set_ylabel("G' [Pa]")
        ax.set_title('Original Data')
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()

        # 2. Master curve
        ax = axes[0, 1]
        for i, T in enumerate(temps):
            omega_s = tts.data[T]['omega'] * factors.get(T, 1.0)
            ax.loglog(omega_s, tts.data[T]['modulus'],
                      'o-', color=colors[i],
                      label=f'{T}°C',
                      markersize=5, alpha=0.7)
        ax.set_xlabel('ω·aT [rad/s]')
        ax.set_ylabel("G' [Pa]")
        ax.set_title(
            f'Master Curve (Tref = {tts.T_ref}°C)')
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()

        # 3. Shift factors
        ax = axes[1, 0]
        ta = np.array(sorted(factors.keys()))
        la = [np.log10(max(factors[T], 1e-30))
              for T in ta]
        ax.plot(ta, la, 'bo-', markersize=10, linewidth=2)
        for tv, lv in zip(ta, la):
            ax.annotate(f'  {tv:.0f}°C: {lv:.3f}',
                        (tv, lv), fontsize=9)
        ax.axhline(y=0, color='r', ls='--', alpha=0.5)
        ax.axvline(x=tts.T_ref, color='r', ls='--', alpha=0.5)
        ax.set_xlabel('Temperature [°C]')
        ax.set_ylabel('log(aT)')
        ax.set_title(
            f'Shift Factors ({len(factors)} temperatures)')
        ax.grid(True, alpha=0.3)

        # 4. Method plot
        ax = axes[1, 1]
        if tts.shift_method == 'WLF':
            _plot_wlf(ax, tts, factors)
        elif tts.shift_method == 'Arrhenius':
            _plot_arrhenius(ax, tts, factors)
        else:
            ax.text(0.5, 0.5, 'No method selected',
                    ha='center', va='center',
                    transform=ax.transAxes)

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100,
                    bbox_inches='tight')
        buf.seek(0)
        plots['master_curve'] = base64.b64encode(
            buf.getvalue()).decode('ascii')
        plt.close(fig)

    except Exception as e:
        app.logger.error(f"Plot error: {e}")
        plots['error'] = str(e)

    return plots


def _plot_wlf(ax, tts, factors):
    try:
        ta = np.array(sorted(factors.keys()))
        non_ref = ta[ta != tts.T_ref]
        dT = non_ref - tts.T_ref
        la_nr = [np.log10(max(factors[T], 1e-30))
                 for T in non_ref]

        if len(dT) > 0 and all(abs(d) > 1e-10 for d in dT):
            x = 1 / dT
            y = -np.array(la_nr) / dT
            ax.plot(x, y, 'ro', markersize=10)

            if tts.WLF_C1 and tts.WLF_C2:
                xr = np.linspace(
                    min(x) * 1.1, max(x) * 1.1, 100)
                yt = tts.WLF_C1 / (tts.WLF_C2 * xr + 1)
                ax.plot(xr, yt, 'b-', lw=2, alpha=0.7,
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
    try:
        ta = np.array(sorted(factors.keys()))
        T_K = ta + 273.15
        la = [np.log10(max(factors[T], 1e-30))
              for T in ta]
        ax.plot(1000 / T_K, la, 'ro', markersize=10)

        if tts.Ea:
            Tr = np.linspace(
                min(ta) - 20, max(ta) + 20, 100) + 273.15
            Tref_K = tts.T_ref + 273.15
            R = 8.314
            lt = (tts.Ea / R) * (1 / Tr - 1 / Tref_K) \
                 / np.log(10)
            ax.plot(1000 / Tr, lt, 'b-', lw=2, alpha=0.7,
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
    return jsonify({'error': 'Internal server error'}), 500


# =============================================================
# Main
# =============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug = os.environ.get(
        'FLASK_ENV', 'production') == 'development'

    print(f"\n{'=' * 50}")
    print(f"  TTS Analysis Tool v3.0")
    print(f"  http://0.0.0.0:{port}")
    print(f"{'=' * 50}\n")

    app.run(host='0.0.0.0', port=port, debug=debug)