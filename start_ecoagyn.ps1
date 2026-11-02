# Запуск сайта EcoAgyn: поднимает сервер (если он ещё не запущен) и открывает сайт в браузере.
# Сервер работает в свёрнутом окне «EcoAgyn сервер» — закройте это окно, чтобы остановить сайт.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = "http://localhost:8501"

function Test-Site {
    try { (Invoke-WebRequest "$url/_stcore/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false }
}

if (-not (Test-Site)) {
    $cmd = "`$host.UI.RawUI.WindowTitle = 'EcoAgyn сервер'; Set-Location '$root'; " +
           "& '.\.venv\Scripts\streamlit.exe' run app.py --server.port 8501"
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd `
        -WorkingDirectory $root -WindowStyle Minimized
    # Ждём, пока сервер ответит (до 90 секунд)
    for ($i = 0; $i -lt 90 -and -not (Test-Site); $i++) { Start-Sleep -Seconds 1 }
}
Start-Process $url
