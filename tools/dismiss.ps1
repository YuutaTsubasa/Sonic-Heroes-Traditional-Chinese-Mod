# Click a button (by name) in any dialog of the given process via UI Automation; repeats for -Seconds.
# usage: powershell -File tools/dismiss.ps1 -ProcId <pid> -Button "Ignore for this session" -Seconds 20
param([int]$ProcId, [string]$Button = "Ignore for this session", [int]$Seconds = 20)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcId)
$end = (Get-Date).AddSeconds($Seconds)
$clicked = 0
while ((Get-Date) -lt $end) {
  foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)) {
    $bc = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Button)
    $b = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $bc)
    if ($b) {
      $pat = $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
      $pat.Invoke(); $clicked++
    }
  }
  Start-Sleep -Milliseconds 300
}
"clicked $clicked"
