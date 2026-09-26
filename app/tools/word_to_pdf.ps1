param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $document = $word.Documents.Open($Source, $false, $true)
    try {
        $document.ExportAsFixedFormat($Destination, 17)
    } finally {
        $document.Close(0)
    }
} finally {
    $word.Quit()
}
