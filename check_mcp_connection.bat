@echo off
REM Скрипт проверки подключения к MCP серверу 1c-syntax-helper

echo ============================================
echo Проверка MCP сервера 1c-syntax-helper
echo ============================================
echo.

REM 1. Проверка Docker контейнеров
echo [1/4] Проверка Docker контейнеров...
docker-compose ps | findstr "mcp-1c-helper"
if %ERRORLEVEL% neq 0 (
    echo ОШИБКА: MCP сервер не запущен!
    echo Запустите: docker-compose up -d
    goto :end
)
echo OK: MCP сервер запущен
echo.

REM 2. Проверка health endpoint
echo [2/4] Проверка health endpoint...
curl -s -o nul -w "%%{http_code}" http://localhost:8002/health | findstr "200" > nul
if %ERRORLEVEL% neq 0 (
    echo ОШИБКА: Health endpoint не отвечает!
    goto :end
)
echo OK: Health endpoint доступен
echo.

REM 3. Проверка SSE endpoint
echo [3/4] Проверка SSE endpoint...
curl -s -o nul -w "%%{http_code}" http://localhost:8002/sse | findstr "200" > nul
if %ERRORLEVEL% neq 0 (
    echo ОШИБКА: SSE endpoint не отвечает!
    goto :end
)
echo OK: SSE endpoint доступен
echo.

REM 4. Проверка MCP initialize
echo [4/4] Проверка MCP initialize...
curl -s -X POST "http://localhost:8002/sse" ^
  -H "Content-Type: application/json" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}" ^
  | findstr "protocolVersion" > nul
if %ERRORLEVEL% neq 0 (
    echo ОШИБКА: MCP initialize не работает!
    goto :end
)
echo OK: MCP initialize успешен
echo.

echo ============================================
echo ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!
echo ============================================
echo.
echo Следующие шаги:
echo 1. Добавьте конфигурацию в %%USERPROFILE%%\.qwen\settings.json
echo 2. Перезапустите Qwen Code
echo 3. Протестируйте подключение
echo.

:end
pause
