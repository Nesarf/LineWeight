# Can a WebView2 window be read through UI Automation?
#
# **The question this answers, and why it needs a control.** A Tauri app on Windows is a WebView2 control, which is
# Chromium, and Chromium exposes UI Automation -- so in principle the whole DOM is reachable as a tree of automation
# elements and the app can be driven without it cooperating. In principle.
#
# This machine has already recorded one negative result of exactly this shape: a tkinter window cannot be read through
# UI Automation, measured with a control. **So the control is the point.** Without one, "I found no elements" cannot be
# told apart from "UI Automation does not work from here", and those two lead to opposite next steps.
#
# The control used here is File Explorer: an ordinary Win32 window whose contents are known and which is certainly not
# a WebView. If Explorer yields a tree and Pixiv-Viewer does not, that is a fact about Pixiv-Viewer.

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$Auto = [System.Windows.Automation.AutomationElement]
$root = $Auto::RootElement

function Get-Tree {
    param($Element, [int]$Depth, [int]$Limit = 60)
    $out = New-Object System.Collections.ArrayList
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $child = $walker.GetFirstChild($Element)
    $n = 0
    while ($child -and $n -lt $Limit) {
        $name = ''
        $ctype = ''
        try { $name = $child.Current.Name } catch {}
        try { $ctype = $child.Current.ControlType.ProgrammaticName } catch {}
        $short = $ctype -replace 'ControlType\.', ''
        [void]$out.Add(('{0}{1}  "{2}"' -f ('  ' * $Depth), $short, $name))
        if ($Depth -lt 3) {
            foreach ($line in (Get-Tree -Element $child -Depth ($Depth + 1) -Limit $Limit)) { [void]$out.Add($line) }
        }
        $child = $walker.GetNextSibling($child)
        $n++
    }
    return $out
}

function Probe {
    param([string]$Label, $Window)
    Write-Output "=== $Label"
    if (-not $Window) { Write-Output "    (no window)"; return }
    try {
        $name = $Window.Current.Name
        $cls = $Window.Current.ClassName
        $ct = $Window.Current.ControlType.ProgrammaticName
        Write-Output ("    window: {0}   class {1}   type {2}" -f $name, $cls, ($ct -replace 'ControlType\.', ''))
    } catch {
        Write-Output "    could not read the window itself: $($_.Exception.Message)"
        return
    }
    $tree = Get-Tree -Element $Window -Depth 0
    Write-Output ("    control-view descendants: {0}" -f $tree.Count)
    $tree | Select-Object -First 14 | ForEach-Object { Write-Output $_ }
    if ($tree.Count -gt 14) { Write-Output ("    ... and {0} more" -f ($tree.Count - 14)) }
    Write-Output ""
}

# --- the control: File Explorer, a plain Win32 window -------------------------
$explorer = $null
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
    try { if ($w.Current.ClassName -eq 'CabinetWClass') { $explorer = $w; break } } catch {}
}
Probe -Label 'CONTROL: File Explorer (Win32, expecting a tree)' -Window $explorer

# --- the subject: Pixiv Viewer, a WebView2 window -----------------------------
$pixiv = $null
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
    try { if ($w.Current.ClassName -match 'Tauri|WebView|Chrome_WidgetWin') { $pixiv = $w; break } } catch {}
}
if (-not $pixiv) {
    foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
        try { if ($w.Current.Name -match 'Pixiv') { $pixiv = $w; break } } catch {}
    }
}
Probe -Label 'SUBJECT: Pixiv Viewer (WebView2)' -Window $pixiv

# --- and every top-level window, so the labels above can be trusted -----------
Write-Output '=== every top-level window UI Automation can see'
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
    try {
        Write-Output ('    {0,-34} {1,-26} {2}' -f $w.Current.ClassName, ($w.Current.ControlType.ProgrammaticName -replace 'ControlType\.', ''), $w.Current.Name)
    } catch {}
}
