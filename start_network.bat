@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  PHANTOM NETWORK — Inicio unificado (Windows)
:: ============================================================
::  Estructura esperada:
::    Node/
::      start_network.bat
::      phantom/
::        core/
::          phantom_daemon.py
::          phantom_relay.py
::          phantom_ws_bridge.py
::          ...
::        app/
::          index.html
::          ...
:: ============================================================

:: ── 1. DETECTAR RUTAS ──────────────────────────────────────
set "BASE_DIR=%~dp0"
set "CORE_DIR=%BASE_DIR%phantom\core"

if not exist "%CORE_DIR%\phantom_core.py" (
    echo [ERROR] No se encuentra phantom_core.py en:
    echo   %CORE_DIR%
    echo.
    echo Asegurate de que la carpeta phantom/core existe.
    pause
    exit /b 1
)

:: ── 2. CERRAR PROCESOS PREVIOS ────────────────────────────
echo [INFO] Cerrando procesos anteriores en puertos 7337, 7338, 7339, 8765...
for %%p in (7337 7338 7339 8765) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":%%p" ^| find "LISTENING"') do (
        taskkill /F /PID %%a 2>nul
    )
)
timeout /t 1 /nobreak >nul

:: ── 3. DETECTAR TOR (opcional) ────────────────────────────
set "TOR_MSG=Conexiones directas (Nivel 1)"
set "TOR_LEVEL=1"

netstat -aon | find ":9050" | find "LISTENING" >nul
if errorlevel 1 goto :no_tor

python -c "import socks" 2>nul
if errorlevel 1 goto :no_tor

set "TOR_MSG=Tor SOCKS5 disponible (Nivel 2)"
set "TOR_LEVEL=2"

python -c "import stem" 2>nul
if errorlevel 1 goto :no_tor

set "TOR_MSG=Tor + onion service disponible (Nivel 3)"
set "TOR_LEVEL=3"

:no_tor
echo [INFO] %TOR_MSG%

:: ── 4. LANZAR PROCESOS ─────────────────────────────────────
cd /d "%CORE_DIR%"

:: 4a. DAEMON (abre ventana nueva)
:: --open-browser: el propio daemon abre el navegador 1.2s despues de que
:: el servidor Flask arranque de verdad (es decir, DESPUES de que
:: introduzcas la passphrase) — no dependemos de adivinar un tiempo fijo.
start "Phantom Daemon" cmd /k "echo [DAEMON] Introduce la passphrase (o Enter para saltar) & python phantom_daemon.py --api-port 7338 --no-autoconnect --open-browser"

:: Esperar unos segundos para que el usuario empiece a ver el prompt
:: (no bloqueante: el navegador NO depende de este timeout, ver 4a)
echo [INFO] Ventana del Daemon abierta. Introduce tu passphrase alli cuando estes listo.
timeout /t 2 /nobreak >nul

:: 4b. RELAY (segundo plano, no pide entrada)
echo [START] Lanzando phantom_relay.py (TCP en puerto 7339)...
start /B python phantom_relay.py --run --port 7339 > relay.log 2>&1

:: 4c. BRIDGE (segundo plano, no pide entrada)
echo [START] Lanzando phantom_ws_bridge.py (WebSocket en puerto 8765)...
start /B python phantom_ws_bridge.py > bridge.log 2>&1

:: Esperar un par de segundos para que arranquen
timeout /t 2 /nobreak >nul

:: ── 5. NAVEGADOR ───────────────────────────────────────────
:: El Daemon abre el navegador el solo (--open-browser) en cuanto el
:: servidor esta realmente listo, asi que no lo forzamos aqui.
echo [INFO] El navegador se abrira automaticamente cuando el Daemon este listo (http://127.0.0.1:7338)

:: ── 6. MOSTRAR RESUMEN ─────────────────────────────────────
echo.
echo ============================================================
echo  [OK] Red Phantom iniciada.
echo.
echo  Web/API:    http://127.0.0.1:7338
echo  Relay TCP:  127.0.0.1:7339
echo  WebSocket:  ws://127.0.0.1:8765
echo.
echo  Logs:       %CORE_DIR%\relay.log, %CORE_DIR%\bridge.log
echo.
echo  IMPORTANTE: La ventana del Daemon pide la passphrase.
echo              Introducela para desbloquear los sellos.
echo              Si no quieres cifrado, pulsa Enter.
echo.
echo  Para detener: cierra la ventana del Daemon y ejecuta:
echo    taskkill /F /IM python.exe
echo ============================================================
echo.
pause