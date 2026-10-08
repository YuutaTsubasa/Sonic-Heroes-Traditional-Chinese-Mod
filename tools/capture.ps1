# Capture the Dolphin render window every few seconds with PrintWindow (works while covered).
# usage: powershell -File tools/capture.ps1 -ProcId <pid> -OutDir work/shots -Count 60 -Interval 3
param([int]$ProcId, [string]$OutDir, [int]$Count = 60, [double]$Interval = 3)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L, T, R, B; }
}
"@
New-Item -ItemType Directory -Force $OutDir | Out-Null
for ($k = 0; $k -lt $Count; $k++) {
  $best = [IntPtr]::Zero; $bestArea = 0
  $cb = [W+EnumProc]{ param($h, $l)
    $p = 0; [W]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
    if ($p -eq $ProcId -and [W]::IsWindowVisible($h)) {
      $r = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
      $a = ($r.R - $r.L) * ($r.B - $r.T)
      if ($a -gt $script:bestArea) { $script:bestArea = $a; $script:best = $h }
    }
    return $true }
  [W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  if ($best -ne [IntPtr]::Zero) {
    $r = New-Object W+RECT; [W]::GetWindowRect($best, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $h = $r.B - $r.T
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
    [W]::PrintWindow($best, $dc, 2) | Out-Null
    $g.ReleaseHdc($dc); $g.Dispose()
    $bmp.Save((Join-Path $OutDir ("{0:D3}.png" -f $k)), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
  }
  Start-Sleep -Milliseconds ([int]($Interval * 1000))
}
