@echo off

setlocal EnableExtensions

setlocal EnableDelayedExpansion

rem 用法：tools\run_yosys.bat case01

if "%~1"=="" (
  echo Usage: %~nx0 case01
  exit /b 1
)

rem 定位根目录（tools的上一层）
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"

set "CASE=%~1"
set "CASE_DIR=%ROOT%\tests\verilog_cases\%CASE%"
set "OUT_DIR=%ROOT%\out\%CASE%"

if not exist "%CASE_DIR%" (
  echo [ERROR] Case folder not found: %CASE_DIR%
  exit /b 1
)

if not exist "%OUT_DIR%" (
  mkdir "%OUT_DIR%" >nul 2>&1
)

rem 进入用例目录，收集所有.v文件名
pushd "%CASE_DIR%" >nul

set "FILES="
for %%F in (*.v) do (
  set "FILES=!FILES! %%F"
)

if "!FILES!"=="" (
  echo [ERROR] No .v files in: %CASE_DIR%
  popd >nul
  exit /b 1
)

rem 从用例目录回到根目录的相对路径：tests\verilog_cases\caseXX
set "FLOW_ABS=%ROOT%\tools\flow.ys"
set "YOSYS_OUT_ABS=%OUT_DIR%\yosys.json"
set "FLOW_YOSYS=%FLOW_ABS:\=/%"
set "YOSYS_OUT_YOSYS=%YOSYS_OUT_ABS:\=/%"
echo [INFO] CASE = %CASE%
echo [INFO] FLOW     = %FLOW_ABS%
echo [INFO] YOSYS_OUT= %YOSYS_OUT_ABS%
rem 运行yosys：读入当前目录下的所有.v，然后跑flow.ys，再写出yosys.json
set "YOSYS_EXE=yosys"
where yosys >nul 2>&1
if errorlevel 1 (
  rem 如果PATH里没有，尝试用OSSCAD_HOME
  if defined OSSCAD_HOME (
    set "YOSYS_EXE=%OSSCAD_HOME%\bin\yosys.exe"
    if exist "%OSSCAD_HOME%\environment.bat" (
    call "%OSSCAD_HOME%\environment.bat" >nul 2>&1
  )
  )
)
if not exist "%YOSYS_EXE%" (
  where yosys >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] yosys not found. Please run in OSS CAD Suite shell or set OSSCAD_HOME.
    popd >nul
    exit /b 1
  ) else (
    set "YOSYS_EXE=yosys"
  )
)

"%YOSYS_EXE%" -p "read_verilog -sv !FILES!; script %FLOW_YOSYS%; write_json %YOSYS_OUT_YOSYS%" > "%OUT_DIR%\yosys.log" 2>&1
if errorlevel 1 (
  echo [ERROR] Yosys failed for %CASE%
  popd >nul
  exit /b 1
)

if not exist "%YOSYS_OUT_ABS%" (
  echo [ERROR] yosys.json not generated: %YOSYS_OUT_ABS%
  dir "%OUT_DIR%"
  popd >nul
  exit /b 1
)

popd >nul
echo [OK] Done: out\%CASE%\yosys.json
exit /b 0
