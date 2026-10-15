# Activate Chromium's accessibility tree, then try to read the WebView2 DOM through UI Automation.
#
# **Why the tree is empty without this.** Chromium builds its accessibility tree lazily: the renderer keeps it off
# until something asks for it, because building it costs memory and every non-screen-reader user would pay. The
# documented trigger is `WM_GETOBJECT` with `OBJID_CLIENT`, which is what a real screen reader sends when it attaches.
# Until that has happened, a UIA walk of a Chromium window returns a couple of anonymous panes and stops -- which is
# exactly what the first probe here returned, and it is not evidence that the content is unreachable.
#
# **So this file has three parts and the order matters**: find the renderer window, wake the tree, then walk it. The
# control is still File Explorer, because "I read nothing" and "reading does not work here" are different answers.

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Wake {
    [DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, IntPtr wParam,
        IntPtr lParam, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWnd, EnumProc cb, IntPtr param);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder sb, int max);
    public delegate bool EnumProc(IntPtr hWnd, IntPtr param);
    public const uint WM_GETOBJECT = 0x003D;
    public static readonly IntPtr OBJID_CLIENT = new IntPtr(unchecked((int)0xFFFFFFFC));
    public static IntPtr[] Children(IntPtr parent) {
        var list = new System.Collections.Generic.List<IntPtr>();
        EnumChildWindows(parent, (h, p) => { list.Add(h); return true; }, IntPtr.Zero);
        return list.ToArray();
    }
    public static string ClassOf(IntPtr h) {
        var sb = new System.Text.StringBuilder(256);
        GetClassName(h, sb, 256);
        return sb.ToString();
    }
}
'@

$Auto = [System.Windows.Automation.AutomationElement]
$walkerCtrl = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$walkerRaw = [System.Windows.Automation.TreeWalker]::RawViewWalker

function Show-Tree {
    param($Element, [int]$Depth = 0, [int]$Limit = 40, $Walker)
    $out = New-Object System.Collections.ArrayList
    $child = $Walker.GetFirstChild($Element)
    $n = 0
    while ($child -and $n -lt $Limit) {
        $name = ''; $ctype = ''; $cls = ''
        try { $name = $child.Current.Name } catch {}
        try { $ctype = ($child.Current.ControlType.ProgrammaticName -replace 'ControlType\.', '') } catch {}
        try { $cls = $child.Current.ClassName } catch {}
        [void]$out.Add(('{0}{1,-14} {2,-22} "{3}"' -f ('  ' * $Depth), $ctype, $cls, $name))
        if ($Depth -lt 4) {
            foreach ($line in (Show-Tree -Element $child -Depth ($Depth + 1) -Limit $Limit -Walker $Walker)) { [void]$out.Add($line) }
        }
        $child = $Walker.GetNextSibling($child)
        $n++
    }
    return $out
}

$root = $Auto::RootElement
$target = $null
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
    try { if ($w.Current.ClassName -eq 'Tauri Window') { $target = $w; break } } catch {}
}
if (-not $target) { Write-Output 'Pixiv Viewer is not running.'; exit 1 }

$hwnd = [IntPtr]$target.Current.NativeWindowHandle
Write-Output ("  window handle: 0x{0:X}" -f $hwnd.ToInt64())

Write-Output ''
Write-Output '=== the child windows, which is where the renderer lives ==='
foreach ($h in [Wake]::Children($hwnd)) {
    Write-Output ("  0x{0:X}  {1}" -f $h.ToInt64(), [Wake]::ClassOf($h))
}

Write-Output ''
Write-Output '=== waking the accessibility tree: WM_GETOBJECT / OBJID_CLIENT to every child ==='
foreach ($h in [Wake]::Children($hwnd)) {
    $res = [IntPtr]::Zero
    [void][Wake]::SendMessageTimeout($h, [Wake]::WM_GETOBJECT, [IntPtr]::Zero, [Wake]::OBJID_CLIENT, 2, 2000, [ref]$res)
}
Start-Sleep -Seconds 3
Write-Output '  sent; the renderer builds the tree asynchronously, so the walk below happens a few seconds later'

Write-Output ''
Write-Output '=== the control view ==='
$t = Show-Tree -Element $target -Limit 40 -Walker $walkerCtrl
Write-Output ("  nodes: {0}" -f $t.Count)
$t | Select-Object -First 25 | ForEach-Object { Write-Output "  $_" }

Write-Output ''
Write-Output '=== the raw view, which exposes more than the control view ==='
$t2 = Show-Tree -Element $target -Limit 40 -Walker $walkerRaw
Write-Output ("  nodes: {0}" -f $t2.Count)
$t2 | Select-Object -First 25 | ForEach-Object { Write-Output "  $_" }

Write-Output ''
Write-Output '=== any element at all with a non-empty name, anywhere under the window ==='
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
Write-Output ("  descendants: {0}" -f $all.Count)
$named = 0
foreach ($e in $all) {
    try { if ($e.Current.Name) { $named++; if ($named -le 12) { Write-Output ('    {0,-20} "{1}"' -f ($e.Current.ControlType.ProgrammaticName -replace 'ControlType\.', ''), $e.Current.Name) } } } catch {}
}
Write-Output ("  with a name: {0}" -f $named)
