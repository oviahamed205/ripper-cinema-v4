# Autonomous Self-Healing CLI Shim for PowerShell
# Captures non-zero exit codes, checks healer pipe, and suggests/applies remediation.

function Invoke-RipperHealed {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$ArgsList
    )

    $cmd = $ArgsList -join " "
    Invoke-Expression $cmd
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "[Autonomous Healer] Command exited with code $exitCode. Querying Healer Engine..." -ForegroundColor Yellow
        $pipeName = "\\.\pipe\ripper_watchdog"
        if (Test-Path $pipeName) {
            $payload = @{
                timestamp = (Get-Date).ToString("o")
                source = "PowerShell_Shim"
                level = "ERROR"
                message = "Process exited with $exitCode"
                metadata = @{ command = $cmd; exit_code = $exitCode }
            } | ConvertTo-Json -Compress

            try {
                $pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "ripper_watchdog", [System.IO.Pipes.PipeDirection]::InOut)
                $pipe.Connect(500)
                $writer = New-Object System.IO.StreamWriter($pipe)
                $writer.WriteLine($payload)
                $writer.Flush()
                $pipe.Close()
                Write-Host "[Autonomous Healer] Telemetry dispatched to background daemon." -ForegroundColor Green
            } catch {
                Write-Host "[Autonomous Healer] Background daemon busy or offline." -ForegroundColor DarkGray
            }
        }
    }
}

Set-Alias -Name ripper-heal -Value Invoke-RipperHealed
