@echo off
setlocal ENABLEDELAYEDEXPANSION
rem Run from Codes\analysis\ ; repo root is parent directory.
set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%"
if not exist "%REPO_ROOT%\src\evrp_instance_generator_framework" (
  echo Expected repo layout: Codes\src\evrp_instance_generator_framework
  popd & exit /b 1
)
set "PYTHONPATH=%REPO_ROOT%\src"
python "%REPO_ROOT%\analysis\scripts\print_scientific_report.py" %*
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
