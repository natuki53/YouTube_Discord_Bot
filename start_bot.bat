@echo off
REM Discord YouTube Bot 起動スクリプト (Windows)

echo ========================================
echo Discord YouTube Bot を起動しています...
echo ========================================
echo.

REM Pythonのバージョンを確認
python --version
if errorlevel 1 (
    echo エラー: Pythonが見つかりません。
    echo Python 3.8以上をインストールしてください。
    pause
    exit /b 1
)

echo.
echo ボットを起動中...
echo.

REM ボットを起動
python main.py

REM エラーが発生した場合は一時停止
if errorlevel 1 (
    echo.
    echo エラーが発生しました。
    pause
)

