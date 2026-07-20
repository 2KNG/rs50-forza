# 사이드 대시보드 자동 배치 — 주 모니터 좌/우 화면에 /left, /right를 앱 창으로 오픈.
# 모니터 좌표는 실행 시점에 자동 감지 (배치/해상도 바뀌어도 동작).
Add-Type -AssemblyName System.Windows.Forms
$screens = [System.Windows.Forms.Screen]::AllScreens
$primary = $screens | Where-Object Primary
$left  = $screens | Where-Object { $_.Bounds.X -lt $primary.Bounds.X } |
         Sort-Object { $_.Bounds.X } | Select-Object -First 1
$right = $screens | Where-Object { $_.Bounds.X -gt $primary.Bounds.X } |
         Sort-Object { $_.Bounds.X } | Select-Object -Last 1

function Open-Side($url, $scr) {
    if ($null -eq $scr) { return }
    $b = $scr.Bounds
    Start-Process msedge -ArgumentList @(
        "--new-window", "--app=$url",
        "--window-position=$($b.X),$($b.Y)",
        "--window-size=$($b.Width),$($b.Height)")
}

Open-Side "http://127.0.0.1:8777/left"  $left
Open-Side "http://127.0.0.1:8777/right" $right
# 사이드 모니터가 없으면 통합 대시보드로 폴백
if (($null -eq $left) -and ($null -eq $right)) {
    Start-Process "http://127.0.0.1:8777/"
}
