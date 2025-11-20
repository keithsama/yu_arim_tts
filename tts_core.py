"""
Time-Temperature Superposition Core Module
元のTTSクラスをWebアプリ用に調整
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # GUIを使わないバックエンド
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import pandas as pd
from pathlib import Path
import warnings
from datetime import datetime
warnings.filterwarnings('ignore')

# matplotlibの設定
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class TTS:
    """時間温度換算則によるマスターカーブ作成クラス（Web版）"""
    
    def __init__(self, T_ref=None):
        """
        Parameters:
        -----------
        T_ref : float or None
            基準温度 [°C]（Noneの場合は後で設定）
        """
        self.T_ref = T_ref
        self.data = {}
        self.shift_factors = {}
        self.shift_factors_manual = {}
        self.shift_method = None
        self.WLF_C1 = None
        self.WLF_C2 = None
        self.Ea = None
        self.manual_adjustment_done = False
        
    def load_excel(self, folder_path='.', pattern='*.xlsx'):
        """
        フォルダ内のExcelファイルを自動読み込み
        """
        folder = Path(folder_path)
        files = list(folder.glob(pattern))
        
        if not files:
            raise FileNotFoundError(f"No Excel files found in {folder_path}")
        
        for file in sorted(files):
            temperature = self._extract_temperature(file.stem)
            if temperature is None:
                continue
            
            try:
                df = pd.read_excel(file)
                
                if len(df.columns) >= 2:
                    omega = df.iloc[:, 0].values
                    modulus = df.iloc[:, 1].values
                    
                    mask = ~(np.isnan(omega) | np.isnan(modulus))
                    omega = omega[mask]
                    modulus = modulus[mask]
                    
                    self.data[temperature] = {
                        'omega': omega,
                        'modulus': modulus
                    }
                    
            except Exception as e:
                continue
        
        if not self.data:
            raise ValueError("No valid data loaded")
    
    def _extract_temperature(self, filename):
        """ファイル名から温度を抽出"""
        import re
        numbers = re.findall(r'-?\d+\.?\d*', filename)
        if numbers:
            return float(numbers[0])
        return None
    
    def shift_WLF(self, C1=8.86, C2=101.6, fit_constants=True):
        """WLF式による自動シフト"""
        if self.T_ref is None:
            raise ValueError("Reference temperature not set")
        
        self.shift_method = 'WLF'
        
        for T in self.data:
            if T == self.T_ref:
                self.shift_factors[T] = 1.0
            else:
                log_aT = -C1 * (T - self.T_ref) / (C2 + T - self.T_ref)
                self.shift_factors[T] = 10**log_aT
        
        if fit_constants and len([t for t in self.data if t != self.T_ref]) >= 2:
            try:
                C1_fit, C2_fit = self._fit_WLF_constants()
                self.WLF_C1 = C1_fit
                self.WLF_C2 = C2_fit
                
                for T in self.data:
                    if T == self.T_ref:
                        self.shift_factors[T] = 1.0
                    else:
                        log_aT = -C1_fit * (T - self.T_ref) / (C2_fit + T - self.T_ref)
                        self.shift_factors[T] = 10**log_aT
            except:
                self.WLF_C1 = C1
                self.WLF_C2 = C2
        else:
            self.WLF_C1 = C1
            self.WLF_C2 = C2
    
    def _fit_WLF_constants(self):
        """WLF定数をデータからフィッティング"""
        temps = []
        log_aT_data = []
        
        for T in self.data:
            if T != self.T_ref:
                temps.append(T)
                log_aT = np.log10(self.shift_factors[T])
                log_aT_data.append(log_aT)
        
        temps = np.array(temps)
        log_aT_data = np.array(log_aT_data)
        
        def WLF_equation(T, C1, C2):
            return -C1 * (T - self.T_ref) / (C2 + T - self.T_ref)
        
        popt, _ = curve_fit(WLF_equation, temps, log_aT_data, 
                           p0=[8.86, 101.6], maxfev=5000)
        
        return popt[0], popt[1]
    
    def shift_Arrhenius(self, Ea=80000, fit_Ea=False):
        """Arrhenius式による自動シフト"""
        if self.T_ref is None:
            raise ValueError("Reference temperature not set")
        
        self.shift_method = 'Arrhenius'
        R = 8.314
        
        for T in self.data:
            if T == self.T_ref:
                self.shift_factors[T] = 1.0
            else:
                T_K = T + 273.15
                T_ref_K = self.T_ref + 273.15
                log_aT = (Ea/R) * (1/T_K - 1/T_ref_K) / np.log(10)
                self.shift_factors[T] = 10**log_aT
        
        if fit_Ea and len([t for t in self.data if t != self.T_ref]) >= 2:
            try:
                Ea_fit = self._fit_Arrhenius_Ea()
                self.Ea = Ea_fit
                
                for T in self.data:
                    if T == self.T_ref:
                        self.shift_factors[T] = 1.0
                    else:
                        T_K = T + 273.15
                        T_ref_K = self.T_ref + 273.15
                        log_aT = (Ea_fit/R) * (1/T_K - 1/T_ref_K) / np.log(10)
                        self.shift_factors[T] = 10**log_aT
            except:
                self.Ea = Ea
        else:
            self.Ea = Ea
    
    def _fit_Arrhenius_Ea(self):
        """活性化エネルギーをフィッティング"""
        temps = []
        log_aT_data = []
        
        for T in self.data:
            if T != self.T_ref:
                temps.append(T + 273.15)
                log_aT_data.append(np.log10(self.shift_factors[T]))
        
        temps = np.array(temps)
        T_ref_K = self.T_ref + 273.15
        
        x = 1/temps - 1/T_ref_K
        y = log_aT_data * np.log(10)
        
        slope, _ = np.polyfit(x, y, 1)
        Ea_fitted = slope * 8.314
        
        return Ea_fitted
    
    def update_manual_shift(self, temperature, log_aT_value):
        """手動シフト値の更新（Web用）"""
        if temperature in self.data:
            if not self.shift_factors_manual:
                self.shift_factors_manual = self.shift_factors.copy()
            self.shift_factors_manual[temperature] = 10**log_aT_value
            self.manual_adjustment_done = True
    
    def get_master_curve_data(self):
        """マスターカーブデータを取得（Web用）"""
        factors = self.shift_factors_manual if self.manual_adjustment_done else self.shift_factors
        
        result = {
            'original': {},
            'shifted': {},
            'shift_factors': {}
        }
        
        for T in self.data:
            result['original'][T] = {
                'omega': self.data[T]['omega'].tolist(),
                'modulus': self.data[T]['modulus'].tolist()
            }
            
            if T in factors:
                result['shifted'][T] = {
                    'omega': (self.data[T]['omega'] * factors[T]).tolist(),
                    'modulus': self.data[T]['modulus'].tolist()
                }
                result['shift_factors'][T] = {
                    'aT': factors[T],
                    'log_aT': np.log10(factors[T])
                }
        
        return result
    
    def export_to_excel(self, filename='tts_results.xlsx'):
        """結果をExcelファイルに出力"""
        factors = self.shift_factors_manual if self.manual_adjustment_done else self.shift_factors
        
        with pd.ExcelWriter(filename) as writer:
            # マスターカーブデータ
            all_data = []
            for T in sorted(self.data.keys()):
                aT = factors.get(T, 1.0)
                for i in range(len(self.data[T]['omega'])):
                    all_data.append({
                        'Temperature [°C]': T,
                        'ω [rad/s]': self.data[T]['omega'][i],
                        "G' [Pa]": self.data[T]['modulus'][i],
                        'aT': aT,
                        'log(aT)': np.log10(aT),
                        'ω·aT [rad/s]': self.data[T]['omega'][i] * aT
                    })
            
            df = pd.DataFrame(all_data)
            df.to_excel(writer, sheet_name='Master Curve Data', index=False)
            
            # シフトファクター
            shift_data = []
            for T in sorted(factors.keys()):
                shift_data.append({
                    'Temperature [°C]': T,
                    'aT': factors[T],
                    'log(aT)': np.log10(factors[T])
                })
            
            df_shift = pd.DataFrame(shift_data)
            df_shift.to_excel(writer, sheet_name='Shift Factors', index=False)
            
            # パラメータ
            params_data = {
                'Parameter': ['Reference Temperature [°C]'],
                'Value': [self.T_ref]
            }
            
            if self.shift_method:
                params_data['Parameter'].append('Shift Method')
                params_data['Value'].append(self.shift_method)
                
                if self.shift_method == 'WLF' and self.WLF_C1:
                    params_data['Parameter'].extend(['WLF C1', 'WLF C2'])
                    params_data['Value'].extend([self.WLF_C1, self.WLF_C2])
                elif self.shift_method == 'Arrhenius' and self.Ea:
                    params_data['Parameter'].append('Ea [kJ/mol]')
                    params_data['Value'].append(self.Ea/1000)
            
            df_params = pd.DataFrame(params_data)
            df_params.to_excel(writer, sheet_name='Parameters', index=False)
        
        return filename