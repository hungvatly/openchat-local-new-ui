@echo off
REM ─────────────────────────────────────────────
REM  OpenChat Local — Docker Setup (Windows)
REM ─────────────────────────────────────────────

echo.
echo   ══════════════════════════════════
echo        OpenChat Local Setup
echo   ══════════════════════════════════
echo.

REM Check Docker
where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   X Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)
echo   √ Docker found

REM Ask for documents folder
set "DEFAULT_DOCS=%USERPROFILE%\Documents"
set /p "DOCS_FOLDER=  Documents folder to watch [%DEFAULT_DOCS%]: "
if "%DOCS_FOLDER%"=="" set "DOCS_FOLDER=%DEFAULT_DOCS%"

if not exist "%DOCS_FOLDER%" (
    echo   X Folder not found: %DOCS_FOLDER%
    pause
    exit /b 1
)
echo   √ Will watch: %DOCS_FOLDER%

REM Create data directory
if not exist "data" mkdir data

REM Update docker-compose — replace the volume mount
REM On Windows we need to use forward slashes in docker-compose
set "DOCS_DOCKER=%DOCS_FOLDER:\=/%"

powershell -Command "(Get-Content docker-compose.yml) -replace '~/Documents:/documents:ro', '%DOCS_DOCKER%:/documents:ro' | Set-Content docker-compose.yml"

REM Build and start
echo.
echo   Starting containers (this may take a few minutes on first run)...
echo.
docker compose up -d --build

REM Wait for Ollama
echo.
echo   Waiting for Ollama to start...
timeout /t 15 /nobreak >nul

REM Pull model
echo.
echo   Pulling qwen2.5:1.5b model...
docker exec ollama ollama pull qwen2.5:1.5b

echo.
echo   ══════════════════════════════════
echo        Setup Complete!
echo   ══════════════════════════════════
echo.
echo   Open: http://localhost:8000
echo.
echo   Watching: %DOCS_FOLDER%
echo   Model: qwen2.5:1.5b
echo.
echo   Commands:
echo   Stop:    docker compose down
echo   Start:   docker compose up -d
echo   Logs:    docker compose logs -f
echo.
pause
