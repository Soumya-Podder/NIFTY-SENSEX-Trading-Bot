$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$servicePath = Join-Path $projectRoot 'backend\paper_service.py'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $servicePath + '"') -WorkingDirectory (Join-Path $projectRoot 'backend')
$daily = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '09:10'
$login = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'Options Paper Lab Supervisor' -Action $action -Trigger @($daily,$login) -Principal $principal -Settings $settings -Description 'Start paper service before 09:15 IST; monitor through 15:05 session exit and pending exits. Credentials reload from project .env.' -Force | Select-Object TaskName,State
Start-ScheduledTask -TaskName 'Options Paper Lab Supervisor'
