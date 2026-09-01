# ============================================================
#  CloudPhoneBoard 一键启动脚本
#  功能：启动后端(8001) + 前端(5174)，健康检查，打开浏览器
#  用法：双击 start.bat，或 PowerShell 执行  ./start.ps1
# ============================================================
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   CloudPhoneBoard 一键启动" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

function Test-PortListen([int]$port) {
    foreach ($line in (netstat -ano)) {
        $t = $line.Trim() -split '\s+'
        if ($t.Count -ge 4 -and $t[0] -eq 'TCP' -and $t[3] -eq 'LISTENING' -and $t[1] -match ":$port$") { return $true }
    }
    return $false
}

# ---------- 1. 后端 ----------
$backend = Join-Path $Root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[错误] 未找到后端虚拟环境: $py" -ForegroundColor Red
    Write-Host "      请先初始化: cd backend" -ForegroundColor Yellow
    Write-Host "      python -m venv .venv" -ForegroundColor Yellow
    Write-Host "      .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

if (Test-PortListen 8001) {
    Write-Host "[提示] 后端 8001 已在运行，跳过启动" -ForegroundColor Yellow
} else {
    Write-Host "[启动] 后端服务 -> http://localhost:8001" -ForegroundColor Green
    Start-Process -FilePath $py -ArgumentList "run_stable.py" -WorkingDirectory $backend -WindowStyle Minimized
}

# ---------- 2. 前端 ----------
$front = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $front "node_modules"))) {
    Write-Host "[安装] 首次运行，安装前端依赖 npm install ..." -ForegroundColor Yellow
    Push-Location $front
    npm install
    Pop-Location
}

if (Test-PortListen 5174) {
    Write-Host "[提示] 前端 5174 已在运行，跳过启动" -ForegroundColor Yellow
} else {
    Write-Host "[启动] 前端开发服务 -> http://localhost:5174" -ForegroundColor Green
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$front`" && npm run dev" -WindowStyle Minimized
}

# ---------- 3. 等待后端就绪 ----------
Write-Host "[等待] 后端健康检查中 ..." -ForegroundColor Yellow
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8001/api/health" -TimeoutSec 3 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
}
if ($ok) { Write-Host "[完成] 后端已就绪" -ForegroundColor Green }
else { Write-Host "[警告] 后端 30 秒内未就绪，请查看后端窗口日志" -ForegroundColor Red }

# ---------- 4. 汇总 ----------
Write-Host ""
Write-Host "  前端管理台: http://localhost:5174" -ForegroundColor Cyan
Write-Host "  后端接口  : http://localhost:8001" -ForegroundColor Cyan
Write-Host "  云手机投屏: http://192.168.9.131:8100" -ForegroundColor Cyan
Write-Host ""
$ans = Read-Host "是否立即打开浏览器访问前端？(Y/N)"
if ($ans -match '^[Yy]') {
    Start-Process "http://localhost:5174"
}
Write-Host ""
Write-Host "启动完成。后端/前端运行在独立窗口，关闭本窗口不影响服务。"
Read-Host "按回车退出"
