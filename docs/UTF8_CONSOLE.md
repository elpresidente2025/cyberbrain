# UTF-8 콘솔 실행 가이드

Windows PowerShell 5.1에서는 `chcp 65001`만으로 한글 파이프 입력이 안전해지지 않는다.  
`$OutputEncoding`이 기본적으로 ASCII라서 `python -` 같은 네이티브 프로세스로 한글을 넘길 때 `?`로 손실될 수 있다.

## 빠른 해결

현재 세션을 UTF-8로 맞추려면 아래를 실행한다.

```powershell
. .\tools\Set-Utf8Process.ps1
```

## 권장 실행 방식

inline Python 재현 스크립트는 파이프 대신 래퍼를 사용한다.

```powershell
.\tools\Invoke-Utf8Python.ps1 -Code @'
print("주진우")
'@
```

파일 실행도 동일하게 UTF-8 모드로 강제할 수 있다.

```powershell
.\tools\Invoke-Utf8Python.ps1 -FilePath .\path\to\script.py
```

## 이유

- `[Console]::InputEncoding`
- `[Console]::OutputEncoding`
- `$OutputEncoding`
- `PYTHONIOENCODING`
- `PYTHONUTF8`

이 값들이 서로 어긋나면 PowerShell 5.1에서 한글이 파이프 단계 또는 Python stdin 단계에서 깨질 수 있다.
