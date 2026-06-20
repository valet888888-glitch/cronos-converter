@echo off
chcp 65001 >nul
echo Установка пакетов CronosMac...
python -m pip install flask crodump chardet pywebview -q
if errorlevel 1 (
    echo ОШИБКА: проверьте что Python установлен
    pause & exit
)
echo.
echo Готово! Теперь запускайте CronosMac.vbs
pause
