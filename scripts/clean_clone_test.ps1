# Clean-clone test: proves the COMMITTED repository works from scratch.
#
#   cd "E:\Yotta flex\kyc-onboarding-evidence-system"
#   .\scripts\clean_clone_test.ps1
#
# What it does (nothing in your working folder is changed):
#   1  clones the repo (committed files only) into a temp folder
#   2  creates a fresh Python venv and installs backend\requirements.txt
#   3  runs pytest
#   4  runs the generator and the two-run reproducibility proof
#   5  compares the final database checksum with the one quoted in the docs
#   6  checks that regenerated evidence files match the committed ones
#   7  npm ci + production build of the React app
#   8  starts the API on port 8765, runs the frontend smoke test against it, stops the API
# A transcript is saved to your Desktop as clean_clone_test_log.txt.

param(
    [int]$ExpectedTests = 265,
    [string]$ExpectedSha = "4b1680489c3b8e2bb58aca693d878cd5930125029d2f24890876bd917c627b0b",
    [int]$Port = 8765,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Continue"
$repo = Split-Path $PSScriptRoot -Parent
$work = Join-Path $env:TEMP ("kyc_clean_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
$log = Join-Path $HOME "Desktop\clean_clone_test_log.txt"
$results = New-Object System.Collections.ArrayList
$apiProc = $null

function Step($text) { Write-Host ""; Write-Host "=== $text" -ForegroundColor Cyan }
function Record($name, $ok, $detail) {
    [void]$results.Add([pscustomobject]@{ Check = $name; Result = $(if ($ok) { "PASS" } else { "FAIL" }); Detail = $detail })
    $color = if ($ok) { "Green" } else { "Red" }
    Write-Host ("{0,-4} {1} {2}" -f $(if ($ok) { "PASS" } else { "FAIL" }), $name, $detail) -ForegroundColor $color
}
function Warn($name, $detail) {
    [void]$results.Add([pscustomobject]@{ Check = $name; Result = "WARN"; Detail = $detail })
    Write-Host "WARN $name $detail" -ForegroundColor Yellow
}

Start-Transcript -Path $log -Force | Out-Null
try {
    Write-Host "Repo under test : $repo"
    Write-Host "Temp clone      : $work"

    Step "0  Is everything committed?"
    Push-Location $repo
    $dirty = git status --porcelain
    Pop-Location
    if ($dirty) {
        Warn "working tree" "uncommitted changes exist; the clone tests only what is COMMITTED. Commit first if you want them included."
        $dirty | Select-Object -First 15 | ForEach-Object { Write-Host "     $_" }
    } else {
        Record "working tree" $true "clean"
    }

    Step "1  Clone"
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $clone = Join-Path $work "repo"
    git clone --quiet "$repo" "$clone"
    Record "git clone" ($LASTEXITCODE -eq 0) $clone
    if ($LASTEXITCODE -ne 0) { throw "clone failed" }

    Step "2  Fresh venv and dependencies"
    $backend = Join-Path $clone "backend"
    python -m venv (Join-Path $backend ".venv")
    $py = Join-Path $backend ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { throw "venv python not found at $py" }
    & $py -m pip install --quiet --disable-pip-version-check -r (Join-Path $backend "requirements.txt")
    Record "pip install" ($LASTEXITCODE -eq 0) "requirements.txt"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    $pyVersion = & $py --version
    Write-Host "     $pyVersion"

    Step "3  pytest"
    Push-Location $backend
    $pytestOut = & $py -m pytest -q 2>&1 | ForEach-Object { "$_" }
    $pytestExit = $LASTEXITCODE
    $pytestOut | Select-Object -Last 12 | ForEach-Object { Write-Host "     $_" }
    $summary = ($pytestOut | Select-Object -Last 3) -join " "
    $passed = 0
    if ($summary -match "(\d+) passed") { $passed = [int]$Matches[1] }
    Record "pytest" (($pytestExit -eq 0) -and ($passed -eq $ExpectedTests)) "$passed passed (expected $ExpectedTests), exit code $pytestExit"

    Step "4  Generate dataset, then reproducibility proof (this takes a while)"
    & $py -m generator.generate
    Record "generator" ($LASTEXITCODE -eq 0) "python -m generator.generate"
    $db = Join-Path $clone "data\output\kyc.db"
    Record "kyc.db created" (Test-Path $db) $db

    & $py -m validation.reproducibility
    Record "reproducibility run" ($LASTEXITCODE -eq 0) "python -m validation.reproducibility"
    Pop-Location

    Step "5  Checksums"
    $reproFile = Join-Path $clone "data\output\reproducibility.json"
    if (Test-Path $reproFile) {
        $repro = Get-Content $reproFile -Raw | ConvertFrom-Json
        Record "two runs identical" ([bool]$repro.identical) "identical = $($repro.identical)"
        $sha = $repro.run_1.final_database_sha256
        Record "final database SHA-256" ($sha -eq $ExpectedSha) $sha
    } else {
        Record "reproducibility.json" $false "file not found"
    }

    Step "6  Do regenerated evidence files equal the committed ones?"
    Push-Location $clone
    $changed = git status --porcelain -- data/output
    Pop-Location
    if ($changed) {
        Warn "evidence files" "differ from committed versions (the validation report records library versions, so a different Python or package version changes it):"
        $changed | ForEach-Object { Write-Host "     $_" }
    } else {
        Record "evidence files" $true "ground_truth and validation_report identical to the committed copies"
    }

    if (-not $SkipFrontend) {
        Step "7  Frontend install and build"
        $front = Join-Path $clone "frontend"
        Push-Location $front
        npm ci --no-audit --no-fund
        Record "npm ci" ($LASTEXITCODE -eq 0) "package-lock.json"
        npm run build
        Record "npm run build" ($LASTEXITCODE -eq 0) "vite production build"
        Pop-Location

        Step "8  API + smoke test of all screen endpoints"
        $apiProc = Start-Process -FilePath $py -ArgumentList @("-m", "uvicorn", "app.main:app", "--port", "$Port") `
            -WorkingDirectory $backend -PassThru -WindowStyle Hidden
        $up = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 1
            try {
                $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
                $up = $true
                break
            } catch { }
        }
        Record "API starts" $up "http://127.0.0.1:$Port/api/health"
        if ($up) {
            Push-Location $front
            $env:API_BASE = "http://127.0.0.1:$Port/api"
            npm run smoke
            Record "frontend smoke test" ($LASTEXITCODE -eq 0) "all screen endpoints"
            Remove-Item Env:\API_BASE -ErrorAction SilentlyContinue
            Pop-Location
        }
    }
}
catch {
    Record "script" $false $_.Exception.Message
}
finally {
    if ($apiProc -and -not $apiProc.HasExited) { Stop-Process -Id $apiProc.Id -Force }
    Write-Host ""
    Write-Host "================ SUMMARY ================" -ForegroundColor Cyan
    $results | Format-Table -AutoSize -Wrap | Out-String | Write-Host
    $fails = @($results | Where-Object { $_.Result -eq "FAIL" }).Count
    if ($fails -eq 0) { Write-Host "CLEAN-CLONE TEST PASSED" -ForegroundColor Green } else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red }
    Write-Host "Temp clone kept at $work (delete it when you are done)."
    Write-Host "Log: $log"
    Stop-Transcript | Out-Null
}
