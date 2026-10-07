param(
    [string]$Server = '47.122.105.169',
    [string]$User = 'root'
)
$ErrorActionPreference = 'Stop'
$sshDir = Join-Path $env:USERPROFILE '.ssh'
$key = Join-Path $sshDir 'asw_aliyun'
$pub = "$key.pub"

if ((Test-Path -LiteralPath $key) -xor (Test-Path -LiteralPath $pub)) {
    throw "密钥文件不完整，已停止，绝不会覆盖：$key"
}
New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $key)) {
    Write-Host '1/3 正在生成这台电脑的专用 SSH 密钥…'
    & ssh-keygen -t ed25519 -f $key -N '""' -C 'asw-deploy'
    if ($LASTEXITCODE -ne 0) { throw '密钥生成失败' }
} else {
    Write-Host '1/3 已找到现有密钥，继续使用，不会覆盖。'
}

Write-Host '2/3 正在把公钥安装到服务器。首次连接请核对 SSH 主机指纹；随后在终端输入服务器密码。'
Get-Content -LiteralPath $pub | & ssh "$User@$Server" 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
if ($LASTEXITCODE -ne 0) { throw '公钥安装失败；可稍后重试，但不要重新生成密钥' }

Write-Host '3/3 正在验证无需密码的登录…'
& ssh -i $key -o BatchMode=yes "$User@$Server" 'uname -a'
if ($LASTEXITCODE -ne 0) { throw '免密登录验证失败；请联系我排查，不要发送密码或私钥' }
Write-Host '密钥登录已成功。只需把上面的 uname -a 系统信息发给我。'
