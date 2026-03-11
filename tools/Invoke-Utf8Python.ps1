param(
    [Parameter(ParameterSetName = "Code", Mandatory = $true)]
    [string]$Code,

    [Parameter(ParameterSetName = "File", Mandatory = $true)]
    [string]$FilePath,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PythonArgs = @()
)

. "$PSScriptRoot/Set-Utf8Process.ps1"

function Invoke-PythonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResolvedPath,

        [string[]]$Args = @()
    )

    & python -X utf8 $ResolvedPath @Args
    $script:Utf8PythonExitCode = $LASTEXITCODE
}

if ($PSCmdlet.ParameterSetName -eq "File") {
    $resolved = (Resolve-Path -LiteralPath $FilePath).Path
    $script:Utf8PythonExitCode = 0
    Invoke-PythonFile -ResolvedPath $resolved -Args $PythonArgs
    exit $script:Utf8PythonExitCode
}

$tempFile = [System.IO.Path]::Combine(
    [System.IO.Path]::GetTempPath(),
    ("codex-utf8-{0}.py" -f [System.Guid]::NewGuid().ToString("N"))
)
$script:Utf8PythonExitCode = 0

try {
    [System.IO.File]::WriteAllText(
        $tempFile,
        $Code,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Invoke-PythonFile -ResolvedPath $tempFile -Args $PythonArgs
}
finally {
    if (Test-Path -LiteralPath $tempFile) {
        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
    }
}

exit $script:Utf8PythonExitCode
