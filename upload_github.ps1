# EcoAgyn: загрузка проекта на GitHub (вход подтверждается с телефона).
# 1) показывает одноразовый код — его вводят на телефоне на github.com/login/device;
# 2) создаёт закрытый репозиторий ecoagyn и загружает в него проект;
# 3) показывает адрес репозитория для share.streamlit.io.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$host.UI.RawUI.WindowTitle = "EcoAgyn — загрузка на GitHub (не закрывайте окно)"
$env:PATH = "C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;" + $env:PATH
$env:GH_BROWSER = "none"          # браузер на ноутбуке не открываем — вход с телефона
Set-Location $root

Write-Host ""
Write-Host "  ШАГ 1. На ТЕЛЕФОНЕ откройте:  https://github.com/login/device" -ForegroundColor Cyan
Write-Host "  ШАГ 2. Введите код, который появится ниже (XXXX-XXXX), и нажмите Authorize." -ForegroundColor Cyan
Write-Host ""

gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh auth login --hostname github.com --git-protocol https --web --skip-ssh-key
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Вход не выполнен. Закройте окно и запустите ярлык ещё раз." -ForegroundColor Red
        Read-Host "Нажмите Enter"
        exit 1
    }
}
gh auth setup-git | Out-Null
$login = gh api user --jq .login
Write-Host ""
Write-Host "  Вход выполнен: $login" -ForegroundColor Green

$remote = git remote 2>$null
if (-not ($remote -contains "origin")) {
    $exists = gh repo view "$login/ecoagyn" --json name 2>$null
    if ($LASTEXITCODE -eq 0) {
        git remote add origin "https://github.com/$login/ecoagyn.git"
        git push -u origin main
    } else {
        gh repo create ecoagyn --private --source . --remote origin --push
    }
} else {
    git push -u origin main
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "  ГОТОВО! Проект загружен:  https://github.com/$login/ecoagyn" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Теперь на телефоне откройте https://share.streamlit.io , войдите через GitHub и нажмите" -ForegroundColor Cyan
    Write-Host "  Create app -> Deploy a public app from GitHub:" -ForegroundColor Cyan
    Write-Host "    Repository:      $login/ecoagyn" -ForegroundColor Cyan
    Write-Host "    Branch:          main" -ForegroundColor Cyan
    Write-Host "    Main file path:  app.py" -ForegroundColor Cyan
    Set-Content -Path (Join-Path $root "github_repo.txt") -Value "https://github.com/$login/ecoagyn" -Encoding UTF8
} else {
    Write-Host "Загрузка не удалась — сфотографируйте это окно и отправьте мне." -ForegroundColor Red
}
Read-Host "Нажмите Enter, чтобы закрыть окно"
