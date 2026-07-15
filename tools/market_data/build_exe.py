"""
把 K 線 UI 伺服器打包成單一 Windows 執行檔（PyInstaller）。

用法：
    pip install pyinstaller
    python build_exe.py

產出：
    dist/kbar-server.exe   ← 雙擊即可啟動，會自動開瀏覽器
    下載的 CSV 會存到 exe 旁邊的 data/ 資料夾（可保存、可換機器帶著走）

備註：
    - exe 內含 pandas / yfinance，檔案較大（~百MB）、首次啟動需解壓數秒。
    - web/index.html 打包在 exe 內；data/ 放 exe 旁邊（server.py 已做 frozen 判斷）。
"""

import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
SEP = ';' if sys.platform.startswith('win') else ':'   # --add-data 分隔符依平台


def main():
    cmd = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
        '--name', 'kbar-server',
        '--add-data', f'web{SEP}web',        # 打包前端頁面
        '--collect-all', 'yfinance',         # yfinance 的資料與子模組
        '--collect-all', 'curl_cffi',        # yfinance 依賴的二進位
        '--collect-all', 'numpy',            # pattern_scanner.py 用到
        'server.py',
    ]
    print('執行：', ' '.join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)
    exe = HERE / 'dist' / ('kbar-server.exe' if sys.platform.startswith('win') else 'kbar-server')
    print(f"\n✓ 完成：{exe}")
    print("  雙擊即可啟動；下載的 CSV 會存到 exe 旁邊的 data/。")


if __name__ == '__main__':
    main()
