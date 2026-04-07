"""
Time-Temperature Superposition Core Module
元のTTSクラスをWebアプリ用に調整
"""
"""
シフトファクターは「温度ごとに1つ」を厳守
"""

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from pathlib import Path
from datetime import datetime
import re
import warnings

warnings.filterwarnings('ignore')


class TTS:
    """時間温度換算則によるマスターカーブ作成クラス"""

    def __init__(self, T_ref=None):
        self.T_ref = T_ref
        self.data = {}                   # {温度: {'omega': array, 'modulus': array}}
        self.shift_factors = {}          # {温度: aT}  ← 温度ごとに1つ
        self.shift_factors_manual = {}   # {温度: aT}  ← 温度ごとに1つ
        self.shift_method = None
        self.WLF_C1 = None
        self.WLF_C2 = None
        self.Ea = None
        self.manual_adjustment_done = False

    # ==========================================================
    # データ読み込み
    # ==========================================================
    def load_excel(self, folder_path='.', pattern='*.xlsx'):
        """フォルダ内のExcel/CSVファイルを自動読み込み"""
        folder = Path(folder_path)

        # xlsx, xls, csv を検索
        files = []
        for ext in ['*.xlsx', '*.xls', '*.csv']:
            files.extend(folder.glob(ext))

        if not files:
            raise FileNotFoundError(
                f"No data files found in {folder_path}")

        print(f"\nFound {len(files)} data files")

        for file in sorted(files):
            temperature = self._extract_temperature(file.stem)
            if temperature is None:
                print(f"  ⚠ Cannot extract temperature "
                      f"from '{file.name}' - skipping")
                continue

            try:
                if file.suffix.lower() == '.csv':
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)

                if len(df.columns) >= 2:
                    omega = pd.to_numeric(
                        df.iloc[:, 0], errors='coerce').values
                    modulus = pd.to_numeric(
                        df.iloc[:, 1], errors='coerce').values

                    mask = ~(np.isnan(omega) | np.isnan(modulus))
                    omega = omega[mask]
                    modulus = modulus[mask]

                    if len(omega) > 0:
                        self.data[temperature] = {
                            'omega': omega,
                            'modulus': modulus
                        }
                        print(f"  ✓ {file.name}: T={temperature}°C, "
                              f"{len(omega)} points")
                    else:
                        print(f"  ⚠ {file.name}: No valid data points")
                else:
                    print(f"  ⚠ {file.name}: Insufficient columns")

            except Exception as e:
                print(f"  ✗ Error reading {file.name}: {e}")

        if not self.data:
            raise ValueError("No valid data loaded")

        # シフトファクター初期化（温度ごとに1つ）
        self._init_shift_factors()
        print(f"\nLoaded: {sorted(self.data.keys())}°C")

    def load_from_dict(self, data_dict):
        """辞書からデータを読み込み（Web API用）"""
        for temp_str, temp_data in data_dict.items():
            T = float(temp_str)
            omega = np.array(temp_data['omega'], dtype=float)
            modulus = np.array(temp_data['modulus'], dtype=float)
            if len(omega) > 0:
                self.data[T] = {'omega': omega, 'modulus': modulus}

        self._init_shift_factors()

    def _extract_temperature(self, filename):
        """ファイル名から温度を抽出"""
        numbers = re.findall(r'-?\d+\.?\d*', filename)
        if numbers:
            return float(numbers[0])
        return None

    def _init_shift_factors(self):
        """全温度のシフトファクターを1.0で初期化"""
        for T in self.data:
            self.shift_factors[T] = 1.0
        print(f"  Initialized {len(self.shift_factors)} shift factors "
              f"(one per temperature)")

    # ==========================================================
    # 現在有効なシフトファクター取得
    # ==========================================================
    def get_current_shift_factors(self):
        """温度ごとに1つのシフトファクター辞書を返す"""
        if self.manual_adjustment_done and self.shift_factors_manual:
            return dict(self.shift_factors_manual)
        return dict(self.shift_factors)

    def get_shift_factors_summary(self):
        """シフトファクターのサマリーを辞書で返す（API用）"""
        factors = self.get_current_shift_factors()
        summary = {}
        for T in sorted(factors.keys()):
            aT = factors[T]
            summary[str(T)] = {
                'aT': float(aT),
                'log_aT': float(np.log10(aT))
            }
        return summary

    # ==========================================================
    # WLF シフト
    # ==========================================================
    def shift_WLF(self, C1=8.86, C2=101.6, fit_constants=True):
        if self.T_ref is None:
            raise ValueError("Reference temperature not set")

        self.shift_method = 'WLF'

        # 温度ごとに1つだけ計算
        for T in self.data:
            if T == self.T_ref:
                self.shift_factors[T] = 1.0
            else:
                dT = T - self.T_ref
                if abs(C2 + dT) < 1e-10:
                    self.shift_factors[T] = 1.0
                else:
                    log_aT = -C1 * dT / (C2 + dT)
                    self.shift_factors[T] = 10 ** log_aT

        # フィッティング
        if fit_constants and len(self.data) >= 3:
            try:
                C1_fit, C2_fit = self._fit_WLF_constants()
                self.WLF_C1 = C1_fit
                self.WLF_C2 = C2_fit

                for T in self.data:
                    if T == self.T_ref:
                        self.shift_factors[T] = 1.0
                    else:
                        dT = T - self.T_ref
                        log_aT = -C1_fit * dT / (C2_fit + dT)
                        self.shift_factors[T] = 10 ** log_aT
            except Exception:
                self.WLF_C1 = C1
                self.WLF_C2 = C2
        else:
            self.WLF_C1 = C1
            self.WLF_C2 = C2

        self._print_shift_factors()

    def _fit_WLF_constants(self):
        temps = []
        log_aT_data = []
        for T in self.data:
            if T != self.T_ref:
                temps.append(T)
                log_aT_data.append(np.log10(self.shift_factors[T]))

        def wlf_eq(T_arr, c1, c2):
            return -c1 * (T_arr - self.T_ref) / (c2 + T_arr - self.T_ref)

        popt, _ = curve_fit(wlf_eq, np.array(temps),
                            np.array(log_aT_data),
                            p0=[8.86, 101.6], maxfev=5000)
        return popt[0], popt[1]

    # ==========================================================
    # Arrhenius シフト
    # ==========================================================
    def shift_Arrhenius(self, Ea=80000, fit_Ea=False):
        if self.T_ref is None:
            raise ValueError("Reference temperature not set")

        self.shift_method = 'Arrhenius'
        R = 8.314
        T_ref_K = self.T_ref + 273.15

        for T in self.data:
            if T == self.T_ref:
                self.shift_factors[T] = 1.0
            else:
                T_K = T + 273.15
                log_aT = (Ea / R) * (1 / T_K - 1 / T_ref_K) / np.log(10)
                self.shift_factors[T] = 10 ** log_aT

        if fit_Ea and len(self.data) >= 3:
            try:
                Ea_fit = self._fit_Arrhenius_Ea()
                self.Ea = Ea_fit
                for T in self.data:
                    if T == self.T_ref:
                        self.shift_factors[T] = 1.0
                    else:
                        T_K = T + 273.15
                        log_aT = (Ea_fit / R) * (1 / T_K - 1 / T_ref_K) \
                                 / np.log(10)
                        self.shift_factors[T] = 10 ** log_aT
            except Exception:
                self.Ea = Ea
        else:
            self.Ea = Ea

        self._print_shift_factors()

    def _fit_Arrhenius_Ea(self):
        temps_K = []
        log_aT_data = []
        for T in self.data:
            if T != self.T_ref:
                temps_K.append(T + 273.15)
                log_aT_data.append(np.log10(self.shift_factors[T]))

        T_ref_K = self.T_ref + 273.15
        x = np.array([1 / t - 1 / T_ref_K for t in temps_K])
        y = np.array(log_aT_data) * np.log(10)
        slope, _ = np.polyfit(x, y, 1)
        return slope * 8.314

    # ==========================================================
    # 表示
    # ==========================================================
    def _print_shift_factors(self):
        factors = self.get_current_shift_factors()
        n = len(factors)
        label = "Manual" if self.manual_adjustment_done else "Auto"

        print(f"\n{'=' * 50}")
        print(f" Shift Factors ({label})  |  Tref = {self.T_ref}°C")
        print(f" Total: {n} factors (= {n} temperatures)")
        print(f"{'=' * 50}")
        print(f" {'Temp [°C]':>10}  {'aT':>12}  {'log(aT)':>10}")
        print(f" {'-' * 36}")
        for T in sorted(factors.keys()):
            aT = factors[T]
            print(f" {T:10.1f}  {aT:12.3e}  {np.log10(aT):10.3f}")
        print(f"{'=' * 50}")

    # ==========================================================
    # エクスポート
    # ==========================================================
    def export_results(self, filepath, use_manual=None):
        """結果をExcelに出力"""
        if use_manual is None:
            factors = self.get_current_shift_factors()
            adj_type = "Manual" if self.manual_adjustment_done else "Auto"
        elif use_manual and self.shift_factors_manual:
            factors = self.shift_factors_manual
            adj_type = "Manual"
        else:
            factors = self.shift_factors
            adj_type = "Auto"

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:

            # Sheet 1: Master Curve Data（aT列は含めない）
            rows = []
            for T in sorted(self.data.keys()):
                aT = factors.get(T, 1.0)
                for i in range(len(self.data[T]['omega'])):
                    rows.append({
                        'Temperature [°C]': T,
                        'omega [rad/s]': self.data[T]['omega'][i],
                        "G' [Pa]": self.data[T]['modulus'][i],
                        'omega*aT [rad/s]': self.data[T]['omega'][i] * aT,
                    })
            pd.DataFrame(rows).to_excel(
                writer, sheet_name='Master Curve Data', index=False)

            # Sheet 2: Shift Factors（温度ごとに1行だけ！）
            sf_rows = []
            for T in sorted(factors.keys()):
                aT = factors[T]
                sf_rows.append({
                    'Temperature [°C]': T,
                    'aT': aT,
                    'log(aT)': np.log10(aT),
                })
            pd.DataFrame(sf_rows).to_excel(
                writer, sheet_name='Shift Factors', index=False)

            # Sheet 3: Parameters
            params = {
                'Parameter': [
                    'Reference Temperature [°C]',
                    'Adjustment Type',
                    'Shift Method',
                    'Number of Temperatures',
                    'Number of Shift Factors',
                    'Export Date',
                ],
                'Value': [
                    self.T_ref, adj_type,
                    self.shift_method or 'N/A',
                    len(self.data), len(factors),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ]
            }
            if self.shift_method == 'WLF' and self.WLF_C1:
                params['Parameter'] += ['WLF C1', 'WLF C2']
                params['Value'] += [self.WLF_C1, self.WLF_C2]
            elif self.shift_method == 'Arrhenius' and self.Ea:
                params['Parameter'].append('Ea [kJ/mol]')
                params['Value'].append(self.Ea / 1000)

            pd.DataFrame(params).to_excel(
                writer, sheet_name='Parameters', index=False)

        print(f"✓ Exported: {filepath} "
              f"({len(factors)} shift factors)")