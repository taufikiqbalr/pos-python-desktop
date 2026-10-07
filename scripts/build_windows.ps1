$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-hardware.txt
python -m pip install -r requirements-build.txt

python -m compileall -q app main.py tests
python -m unittest discover -s tests -v

pyinstaller --noconfirm --clean --onefile --windowed --name "KoperasiBRIN-POS" --collect-all escpos main.py

Write-Host ""
Write-Host "Build selesai: dist\KoperasiBRIN-POS.exe"
