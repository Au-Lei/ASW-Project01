param([Parameter(Mandatory=$true)][string]$Path)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
if ($extension -eq '.xls') {
    $office = New-Object -ComObject Excel.Application
    $office.Visible = $false
    $office.DisplayAlerts = $false
    try {
        $book = $office.Workbooks.Open($Path, 0, $true)
        try {
            foreach ($sheet in $book.Worksheets) {
                $range = $sheet.UsedRange
                for ($row = 1; $row -le [Math]::Min($range.Rows.Count, 500); $row++) {
                    $parts = @()
                    for ($col = 1; $col -le [Math]::Min($range.Columns.Count, 50); $col++) {
                        $value = $range.Cells.Item($row, $col).Text
                        if ($value) { $parts += $value }
                    }
                    if ($parts.Count) { Write-Output ($parts -join ' | ') }
                }
            }
        } finally { $book.Close($false) }
    } finally { $office.Quit() }
} elseif ($extension -in @('.doc', '.rtf')) {
    $office = New-Object -ComObject Word.Application
    $office.Visible = $false
    $office.DisplayAlerts = 0
    try {
        $document = $office.Documents.Open($Path, $false, $true)
        try { Write-Output $document.Content.Text } finally { $document.Close(0) }
    } finally { $office.Quit() }
} else { throw "Unsupported format: $extension" }
