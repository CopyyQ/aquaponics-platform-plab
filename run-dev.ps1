# Khoi dong moi truong dev: SSH tunnel DB (server 192.168.1.182) + backend + frontend.
# Dung: .\run-dev.ps1        (hoac: powershell -ExecutionPolicy Bypass -File .\run-dev.ps1)
# Dung tat ca:  .\run-dev.ps1 -Stop

param([switch]$Stop)

$root         = $PSScriptRoot
$sshHost      = "plab@192.168.1.182"
$pgContainer  = "aquaponics-plab-final-postgres-1"
$pgFallbackIp = "192.168.32.3"   # IP container Postgres lan gan nhat (doi moi lan Docker restart)
$localPort    = 5433
$mqttHost     = "192.168.1.182" # broker Mosquitto tren server (hostname "mqtt" chi resolve trong Docker)

function Stop-Port($port) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}

function Stop-Backend {
    # Kill tien trinh uvicorn kem theo worker con truoc, vi uvicorn --reload spawn
    # worker qua multiprocessing: kill rieng tien trinh cha se de lai worker mo coi
    # van giu cong 8000 va tra loi bang cau hinh DB cu.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match "uvicorn" } |
        ForEach-Object {
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$($_.ProcessId)" |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    for ($i = 0; $i -lt 10; $i++) {
        $owners = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        if (-not $owners) { return }
        $owners | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "Canh bao: cong 8000 van bi giu, backend co the khong khoi dong duoc." -ForegroundColor Yellow
}

if ($Stop) {
    Stop-Backend; Stop-Port 5173; Stop-Port $localPort
    Write-Host "Da tat backend, frontend va SSH tunnel."
    exit 0
}

# 1. Hoi server IP hien tai cua container Postgres.
Write-Host "Dang hoi IP Postgres tren server..."
$pgIp = $null
try {
    $pgIp = (& ssh -o BatchMode=yes -o ConnectTimeout=5 $sshHost `
        "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $pgContainer" 2>$null) |
        Select-Object -First 1
    if ($pgIp) { $pgIp = $pgIp.Trim() }
} catch { $pgIp = $null }

if (-not $pgIp -or $pgIp -notmatch '^\d+\.\d+\.\d+\.\d+$') {
    Write-Host "Khong hoi duoc IP Postgres (server tat / ssh loi). Dung IP fallback $pgFallbackIp." -ForegroundColor Yellow
    $pgIp = $pgFallbackIp
} else {
    Write-Host "Postgres dang o $pgIp"
}
$forward = "${localPort}:${pgIp}:5432"

# 2. SSH tunnel: tat tunnel cu (co the tro sai IP), mo lai.
Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
    Where-Object { $_.CommandLine -match "-L\s*${localPort}:" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Process ssh -ArgumentList "-N","-o","ServerAliveInterval=30","-o","ServerAliveCountMax=3","-o","ExitOnForwardFailure=yes","-L",$forward,$sshHost -WindowStyle Hidden
Write-Host "Dang mo SSH tunnel $forward ..."
$tries = 0
while (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $localPort -InformationLevel Quiet -WarningAction SilentlyContinue) -and $tries -lt 30) {
    Start-Sleep -Seconds 1; $tries++
}
if ($tries -ge 30) { Write-Host "Tunnel khong len duoc. Kiem tra ssh $sshHost" -ForegroundColor Red; exit 1 }

# 3. Backend: tat moi tien trinh cu tren 8000 truoc (tranh 2 uvicorn cung bind cong).
Stop-Backend
$env:MQTT_HOST = $mqttHost
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:MQTT_HOST='$mqttHost'; cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

# 4. Frontend
Stop-Port 5173
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

# 5. Doi backend len roi mo trinh duyet
$tries = 0
while ($tries -lt 60) {
    try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 2 | Out-Null; break }
    catch { Start-Sleep -Seconds 1; $tries++ }
}
Write-Host ""
Write-Host "Backend : http://127.0.0.1:8000/docs"
Write-Host "Frontend: http://127.0.0.1:5173"
Start-Process "http://127.0.0.1:5173"
