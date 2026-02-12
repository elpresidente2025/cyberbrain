@echo off
echo Creating Cloud Tasks queue 'pipeline-steps'...
call gcloud tasks queues create pipeline-steps --location=asia-northeast3
if %ERRORLEVEL% equ 0 (
    echo Queue created successfully.
) else (
    echo Failed to create queue (it may already exist).
)
pause
