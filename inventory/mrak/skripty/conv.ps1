$ErrorActionPreference = 'Continue'
$list = Get-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'conv_list.txt')
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
foreach ($line in $list) {
    if (-not $line.Trim()) { continue }
    $p = $line.Split("`t")
    try {
        if ($p[0] -eq '.doc') {
            $d = $word.Documents.Open($p[1], $false, $true)
            $d.SaveAs2($p[2], 16)
            $d.Close($false)
        } else {
            $wb = $excel.Workbooks.Open($p[1], 0, $true)
            $wb.SaveAs($p[2], 51)
            $wb.Close($false)
        }
        Write-Output "OK $($p[2])"
    } catch {
        Write-Output "FAIL $($p[1]): $($_.Exception.Message)"
    }
}
$word.Quit()
$excel.Quit()
