@echo off
REM Construit l'application Windows autonome (dossier dist\TileForge).
REM
REM   packaging\build_windows.bat            paquet « onedir »
REM   set TILEFORGE_ONEFILE=1 && packaging\build_windows.bat    exécutable unique
REM   set TILEFORGE_CONSOLE=1 && packaging\build_windows.bat    garde une console
REM
setlocal enabledelayedexpansion

set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "BUILD_VENV=%ROOT%\.venv-build"
set "DIST=%ROOT%\dist"

echo == TileForge - construction Windows ==
echo projet : %ROOT%

if not exist "%BUILD_VENV%\Scripts\python.exe" (
    echo -- creation de l'environnement de compilation
    py -3 -m venv "%BUILD_VENV%" || goto :error
    "%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip >nul || goto :error
)

echo -- installation des dependances de compilation
"%BUILD_VENV%\Scripts\pip.exe" install -q PySide6 numpy Pillow pyinstaller || goto :error

echo -- PyInstaller
pushd "%ROOT%"
"%BUILD_VENV%\Scripts\pyinstaller.exe" --noconfirm --clean --distpath "%DIST%" --workpath "%ROOT%\build" "%HERE%tileforge.spec" || goto :error
popd

if exist "%DIST%\TileForge\TileForge.exe" (
    echo.
    echo Termine : %DIST%\TileForge\TileForge.exe
    echo.
    echo Pour un installeur, compressez le dossier dist\TileForge avec Inno Setup
    echo ou creez un raccourci vers TileForge.exe.
    exit /b 0
)

echo Echec : %DIST%\TileForge\TileForge.exe introuvable
exit /b 1

:error
echo Echec de la compilation.
exit /b 1
