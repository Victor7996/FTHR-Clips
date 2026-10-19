# Script to deploy compiled FTHR Clips to Program Files
Get-Process -Name FTHR* -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 600
robocopy 'H:\desktop\fthr-clips\FTHR-Clips\dist\FTHRClips' 'C:\Program Files\FTHRClips' /E /R:2 /W:1
Write-Host 'Klart! FTHR Clips har uppdaterats i Program Files.' -ForegroundColor Green
Start-Sleep -Seconds 3
