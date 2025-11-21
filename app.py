"""
Time-Temperature Superposition Web Application
Flask-based TTS analysis tool - Complete Version
"""

from flask import Flask, render_template, request, jsonify, send_file, session
import os
import io
import base64
import json
import uuid
from werkzeug.utils import secure_filename
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # バックエンドを設定
import matplotlib.pyplot as plt
from datetime import datetime
import tempfile
from pathlib import Path

# TTSクラスをインポート（tts_core.pyが必要）
from tts_core import TTS

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['SECRET_KEY'] = 'your-secure-random-key'
app.config['ENV'] = 'production'
PORT = 10000

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/results', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('templates', exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/download/<filename>')
def download_file(filename):
    """Download result file"""
    try:
        # Security check - ensure filename is safe
        filename = secure_filename(filename)
        
        # Try different possible locations
        possible_paths = [
            os.path.join('static', 'results', filename),
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            filename
        ]
        
        filepath = None
        for path in possible_paths:
            if os.path.exists(path):
                filepath = path
                break
        
        if filepath:
            app.logger.info(f"Downloading file from: {filepath}")
            return send_file(
                filepath, 
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            app.logger.error(f"File not found in any location: {filename}")
            return jsonify({'error': f'File not found: {filename}'}), 404
            
    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/save_manual_adjustment', methods=['POST'])
def save_manual_adjustment():
    """Save manual adjustment results - Fixed version"""
    try:
        data = request.json
        
        # Create results directory if it doesn't exist
        results_dir = os.path.join('static', 'results')
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'manual_adjustment_{timestamp}.xlsx'
        filepath = os.path.join(results_dir, filename)
        
        app.logger.info(f"Saving manual adjustment to: {filepath}")
        
        # Create Excel file with manual adjustment results
        export_manual_results(data, filepath)
        
        # Verify file was created
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            app.logger.info(f"File created successfully: {filepath} ({file_size} bytes)")
            
            return jsonify({
                'status': 'success',
                'filename': filename,
                'download_url': f'/download/{filename}',
                'file_size': file_size
            })
        else:
            raise Exception("File was not created")
        
    except Exception as e:
        app.logger.error(f"Save manual adjustment error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def export_manual_results(data, filepath):
    """Export manual adjustment results to Excel - Fixed version"""
    try:
        import openpyxl  # Ensure openpyxl is imported
        
        # Create a new workbook
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Master curve data
            all_data = []
            
            # Check if we have the required data
            if 'original_data' not in data:
                raise ValueError("No original_data in request")
            
            if 'shift_factors' not in data:
                raise ValueError("No shift_factors in request")
            
            for temp_str, temp_data in data.get('original_data', {}).items():
                try:
                    temp = float(temp_str)
                    sf = data.get('shift_factors', {}).get(temp_str, {})
                    aT = sf.get('aT', 1.0)
                    log_aT = sf.get('log_aT', 0.0)
                    
                    omega_list = temp_data.get('omega', [])
                    modulus_list = temp_data.get('modulus', [])
                    
                    for i in range(len(omega_list)):
                        all_data.append({
                            'Temperature [°C]': temp,
                            'ω [rad/s]': omega_list[i],
                            "G' [Pa]": modulus_list[i],
                            'aT': aT,
                            'log(aT)': log_aT,
                            'ω·aT [rad/s]': omega_list[i] * aT
                        })
                except Exception as e:
                    app.logger.error(f"Error processing temp {temp_str}: {str(e)}")
                    continue
            
            if all_data:
                df = pd.DataFrame(all_data)
                df.to_excel(writer, sheet_name='Master Curve Data', index=False)
                app.logger.info(f"Wrote {len(all_data)} rows to Master Curve Data sheet")
            
            # Shift factors sheet
            shift_data = []
            for temp_str, sf in data.get('shift_factors', {}).items():
                try:
                    shift_data.append({
                        'Temperature [°C]': float(temp_str),
                        'aT': sf.get('aT', 1.0),
                        'log(aT)': sf.get('log_aT', 0.0)
                    })
                except Exception as e:
                    app.logger.error(f"Error processing shift factor for {temp_str}: {str(e)}")
                    continue
            
            if shift_data:
                df_shift = pd.DataFrame(shift_data)
                df_shift = df_shift.sort_values('Temperature [°C]')
                df_shift.to_excel(writer, sheet_name='Shift Factors', index=False)
                app.logger.info(f"Wrote {len(shift_data)} rows to Shift Factors sheet")
            
            # Parameters sheet
            params_data = {
                'Parameter': [
                    'Reference Temperature [°C]',
                    'Export Date',
                    'Export Time',
                    'Adjustment Type'
                ],
                'Value': [
                    data.get('reference_temperature', 'N/A'),
                    datetime.now().strftime("%Y-%m-%d"),
                    datetime.now().strftime("%H:%M:%S"),
                    'Manual'
                ]
            }
            
            df_params = pd.DataFrame(params_data)
            df_params.to_excel(writer, sheet_name='Parameters', index=False)
            
        app.logger.info(f"Excel file created successfully: {filepath}")
        
    except Exception as e:
        app.logger.error(f"Export error details: {str(e)}")
        raise

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
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filepath)
            
            # Extract temperature from filename
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
    """Run TTS analysis"""
    try:
        data = request.json
        
        # Get parameters
        ref_temp = float(data.get('reference_temperature', 25))
        method = data.get('method', 'WLF')  # WLF or Arrhenius
        
        # Create TTS instance
        tts = TTS(T_ref=ref_temp)
        
        # Load data
        tts.load_excel(folder_path=app.config['UPLOAD_FOLDER'])
        
        # Perform shift calculation
        if method == 'WLF':
            C1 = float(data.get('C1', 8.86))
            C2 = float(data.get('C2', 101.6))
            fit = data.get('fit_constants', False)
            tts.shift_WLF(C1=C1, C2=C2, fit_constants=fit)
        else:  # Arrhenius
            Ea = float(data.get('Ea', 80000))
            fit = data.get('fit_Ea', False)
            tts.shift_Arrhenius(Ea=Ea, fit_Ea=fit)
        
        # Save to session for manual adjustment
        session['tts_data'] = {
            'reference_temperature': ref_temp,
            'method': method,
            'original_data': {},
            'shift_factors': {}
        }
        
        # Store data in session
        for T in tts.data:
            session['tts_data']['original_data'][str(T)] = {
                'omega': tts.data[T]['omega'].tolist(),
                'modulus': tts.data[T]['modulus'].tolist()
            }
        
        for T in tts.shift_factors:
            session['tts_data']['shift_factors'][str(T)] = {
                'aT': float(tts.shift_factors[T]),
                'log_aT': float(np.log10(tts.shift_factors[T]))
            }
        
        session['last_analysis'] = session['tts_data']
        session.modified = True
        
        # Generate plots
        plot_data = generate_plots(tts)
        
        # Prepare shift factors for response
        shift_factors = {}
        for T in tts.shift_factors:
            shift_factors[str(T)] = {
                'aT': float(tts.shift_factors[T]),
                'log_aT': float(np.log10(tts.shift_factors[T]))
            }
        
        # Prepare result
        result = {
            'status': 'success',
            'reference_temperature': ref_temp,
            'method': method,
            'shift_factors': shift_factors,
            'plots': plot_data
        }
        
        # Add method-specific parameters
        if method == 'WLF' and hasattr(tts, 'WLF_C1') and tts.WLF_C1:
            result['WLF_C1'] = float(tts.WLF_C1)
            result['WLF_C2'] = float(tts.WLF_C2)
        elif method == 'Arrhenius' and hasattr(tts, 'Ea') and tts.Ea:
            result['Ea_kJ'] = float(tts.Ea / 1000)
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Analysis error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def generate_plots(tts):
    """Generate plots and return as Base64 encoded images"""
    plots = {}
    
    try:
        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        temps = sorted(tts.data.keys())
        colors = plt.cm.coolwarm(np.linspace(0, 1, len(temps)))
        
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
            omega_shifted = tts.data[T]['omega'] * tts.shift_factors[T]
            ax.loglog(omega_shifted, tts.data[T]['modulus'], 
                     'o-', color=colors[i], label=f'{T}°C',
                     markersize=5, alpha=0.7)
        ax.set_xlabel('ω·aT [rad/s]')
        ax.set_ylabel("G' [Pa]")
        ax.set_title(f'Master Curve (Tref = {tts.T_ref}°C)')
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        
        # 3. Shift factors
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
        
        # 4. WLF or Arrhenius plot
        ax = axes[1, 1]
        if hasattr(tts, 'shift_method') and tts.shift_method == 'WLF':
            plot_wlf(ax, tts)
        elif hasattr(tts, 'shift_method') and tts.shift_method == 'Arrhenius':
            plot_arrhenius(ax, tts)
        
        plt.tight_layout()
        
        # Convert to Base64
        img = io.BytesIO()
        plt.savefig(img, format='png', dpi=100, bbox_inches='tight')
        img.seek(0)
        plots['master_curve'] = base64.b64encode(img.getvalue()).decode()
        plt.close()
        
    except Exception as e:
        app.logger.error(f"Plot generation error: {str(e)}")
        plots['error'] = str(e)
    
    return plots

def plot_wlf(ax, tts):
    """Create WLF plot"""
    try:
        temps_arr = np.array(sorted(tts.shift_factors.keys()))
        T_diff = temps_arr[temps_arr != tts.T_ref] - tts.T_ref
        log_aT_nonref = [np.log10(tts.shift_factors[T]) for T in temps_arr if T != tts.T_ref]
        
        if len(T_diff) > 0:
            x_data = 1 / T_diff
            y_data = -np.array(log_aT_nonref) / T_diff
            ax.plot(x_data, y_data, 'ro', markersize=10)
            
            if hasattr(tts, 'WLF_C1') and hasattr(tts, 'WLF_C2') and tts.WLF_C1 and tts.WLF_C2:
                x_range = np.linspace(min(x_data)*1.1, max(x_data)*1.1, 100)
                y_theory = tts.WLF_C1 / (tts.WLF_C2 * x_range + 1)
                ax.plot(x_range, y_theory, 'b-', linewidth=2, alpha=0.7)
            
            ax.set_xlabel('1/(T-Tref) [1/°C]')
            ax.set_ylabel('-log(aT)/(T-Tref)')
            ax.set_title('WLF Plot')
            ax.grid(True, alpha=0.3)
    except Exception as e:
        app.logger.error(f"WLF plot error: {str(e)}")

def plot_arrhenius(ax, tts):
    """Create Arrhenius plot"""
    try:
        temps_arr = np.array(sorted(tts.shift_factors.keys()))
        T_K = temps_arr + 273.15
        log_aT_all = [np.log10(tts.shift_factors[T]) for T in temps_arr]
        ax.plot(1000/T_K, log_aT_all, 'ro', markersize=10)
        
        if hasattr(tts, 'Ea') and tts.Ea:
            T_range = np.linspace(min(temps_arr)-20, max(temps_arr)+20, 100) + 273.15
            T_ref_K = tts.T_ref + 273.15
            R = 8.314
            log_aT_theory = (tts.Ea/R) * (1/T_range - 1/T_ref_K) / np.log(10)
            ax.plot(1000/T_range, log_aT_theory, 'b-', linewidth=2, alpha=0.7)
        
        ax.set_xlabel('1000/T [1/K]')
        ax.set_ylabel('log(aT)')
        ax.set_title('Arrhenius Plot')
        ax.grid(True, alpha=0.3)
    except Exception as e:
        app.logger.error(f"Arrhenius plot error: {str(e)}")

# Manual adjustment routes
@app.route('/manual_adjustment')
def manual_adjustment_page():
    """Manual adjustment page"""
    return render_template('manual_adjustment.html')

@app.route('/get_current_data', methods=['GET'])
def get_current_data():
    """Get current analysis data from session"""
    if 'last_analysis' in session:
        return jsonify(session['last_analysis'])
    return jsonify({'error': 'No data available'}), 404

@app.route('/update_shift_factor', methods=['POST'])
def update_shift_factor():
    """Update shift factor in real-time"""
    try:
        data = request.json
        temperature = float(data['temperature'])
        log_aT = float(data['log_aT'])
        
        if 'tts_data' in session:
            tts_data = session['tts_data']
            tts_data['shift_factors'][str(temperature)] = {
                'aT': 10**log_aT,
                'log_aT': log_aT
            }
            session['tts_data'] = tts_data
            session.modified = True
            
            return jsonify({'status': 'success'})
        
        return jsonify({'error': 'No TTS data in session'}), 400
        
    except Exception as e:
        app.logger.error(f"Update shift factor error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/save_manual_adjustment', methods=['POST'])
def save_manual_adjustment():
    """Save manual adjustment results"""
    try:
        data = request.json
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'manual_adjustment_{timestamp}.xlsx'
        filepath = os.path.join('static', 'results', filename)
        
        # Create Excel file with manual adjustment results
        export_manual_results(data, filepath)
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'download_url': f'/download/{filename}'
        })
        
    except Exception as e:
        app.logger.error(f"Save manual adjustment error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def export_manual_results(data, filepath):
    """Export manual adjustment results to Excel"""
    try:
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Master curve data
            all_data = []
            for temp_str, temp_data in data.get('original_data', {}).items():
                temp = float(temp_str)
                sf = data.get('shift_factors', {}).get(temp_str, {})
                aT = sf.get('aT', 1.0)
                
                for i in range(len(temp_data.get('omega', []))):
                    all_data.append({
                        'Temperature [°C]': temp,
                        'ω [rad/s]': temp_data['omega'][i],
                        "G' [Pa]": temp_data['modulus'][i],
                        'aT': aT,
                        'log(aT)': np.log10(aT) if aT > 0 else 0,
                        'ω·aT [rad/s]': temp_data['omega'][i] * aT
                    })
            
            if all_data:
                df = pd.DataFrame(all_data)
                df.to_excel(writer, sheet_name='Master Curve Data', index=False)
            
            # Shift factors
            shift_data = []
            for temp_str, sf in data.get('shift_factors', {}).items():
                shift_data.append({
                    'Temperature [°C]': float(temp_str),
                    'aT': sf.get('aT', 1.0),
                    'log(aT)': sf.get('log_aT', 0)
                })
            
            if shift_data:
                df_shift = pd.DataFrame(shift_data)
                df_shift.to_excel(writer, sheet_name='Shift Factors', index=False)
                
    except Exception as e:
        app.logger.error(f"Export error: {str(e)}")
        raise

@app.route('/download/<filename>')
def download_file(filename):
    """Download result file"""
    try:
        # Security check - ensure filename is safe
        filename = secure_filename(filename)
        filepath = os.path.join('static', 'results', filename)
        
        if os.path.exists(filepath):
            return send_file(filepath, 
                           as_attachment=True,
                           download_name=filename,
                           mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/clear', methods=['POST'])
def clear_uploads():
    """Clear uploaded files"""
    try:
        for file in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        
        # Clear session
        session.clear()
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        app.logger.error(f"Clear uploads error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint for deployment"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"Server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Get port from environment variable for deployment
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )