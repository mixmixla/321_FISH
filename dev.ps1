# 使用项目虚拟环境，避免系统旧版 Python 或 PATH 顺序影响运行。
param(
    [ValidateSet('test', 'server', 'client', 'build')]
    [string] $Command = 'test'
)

# 普通参数绑定保留剩余原始参数，避免 -o 等 pytest 参数与 PowerShell
# 高级脚本的 OutVariable/OutBuffer 公共参数冲突。
$taskArguments = @($args)

$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw '缺少项目虚拟环境，请按 docs/开发环境.md 创建 .venv 并安装 requirements-dev.txt。'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython (Join-Path $PSScriptRoot 'run.py') $Command @taskArguments
    $taskExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $taskExit
