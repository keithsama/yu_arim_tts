<h1>時間温度換算則プロット自動生成ツール</h1>
<h3>提供元：山形大学エイリム YU-ARIM</h3>
<p>このプログラムは、時間温度換算則（Time–Temperature Superposition, TTS） を用いて、任意の周波数依存データ（例：G’, G’’ など）からマスターカーブを自動生成し、プロットする Python ツールです。</p>
<p>使用する粘弾性データはARIM Data Portalからダウンロード(有料)して使用いただくことができます。データポータルにあるデータは構造化されて機械学習などに使いやすい形式になっています。料金については下記ページからご確認ください。ご自身でお持ちのデータも使用いただけます。</p>

<a href="https://nanonet.go.jp/data_service/" target="_blank">ARIM Data Portal</a></p>

<h2>粘弾性データの測定</h2>
<p>共用装置：YG-001　ツインドライブ型レオメータ</p>
<p>TTSに使いたい材料の粘弾性を新たに取得することも可能です。代行も行っています。</p>

<p><a href="https://arim.yz.yamagata-u.ac.jp/eq_rheo.html" target="_blank">ツインドライブ型レオメータの紹介</a></p>

<h3>How to Use/使い方</h3>
<p>テンプレートエクセル、A列（Frequency [rad/s]）,B列（Storage Modulus [Pa]）, C列（Loss modulus [Pa]）となっています。それぞれデータをA2, B2, C3から下へコピーしてください。エクセルファイルの名前を温度に変更します。（例えば180度なら180.xlsx）ご自身の粘弾性データを使用される場合も同様です。</p>

テンプレート.xlsx(.template.xlsx)



<p>STEP 1 ファイルをアップロード </p>
<p>STEP 2 基準温度（Reference Temp.）,WLF or Arrheniusを選択, [RUN Analysys]をクリック、結果をダウンロード</p>
<p>STEP 3 [Manual Adjustment]手動でパラメータを調整

<h3>Features</h3>
<ul>
<li>任意の測定温度データから、基準温度への シフトファクター aₜ を自動計算</li>
<li>WLF式またはアレニウス式を選択可能</li>
<li>シフト後のデータを自動で統合し マスターカーブをプロット</li>
<li>グラフを PNG / SVG / PDF に保存可能</li>
</ul>

<h4>使用プログラム</h4>
<p>python, Flask, Github, Render</p>
