# Stop Qwen-Image-2.1 service -- precise targeting only.
# NOTE: do NOT match processes by "server.py" alone. The H3 helper server also runs
# "server.py", so the old pattern killed an unrelated public service as a side effect.
$ErrorActionPreference = "SilentlyContinue"
$root = $PSScriptRoot
$lock = Join-Path $root ".server.lock"
$killed = 0

# 1) PID recorded by the service itself (most precise).
if (Test-Path $lock) {
    $t = (Get-Content $lock -Raw).Trim()
    if ($t -match '^\d+$') {
        $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $t)
        if ($p) {
            Stop-Process -Id ([int]$t) -Force
            Write-Output ("[OK] stopped PID " + $t)
            $killed++
        }
    }
    Remove-Item $lock -Force
}

# 2) Fallback: only processes whose command line points into THIS project folder.
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*Qwen_image2.1*" -and $_.CommandLine -like "*server.py*" }
foreach ($p in $procs) {
    Stop-Process -Id ([int]$p.ProcessId) -Force
    Write-Output ("[OK] stopped PID " + $p.ProcessId)
    $killed++
}

if ($killed -eq 0) {
    Write-Output "NO_RUNNING_SERVICE"
} else {
    Write-Output ("STOPPED_COUNT=" + $killed)
}
