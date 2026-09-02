@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where gh.exe >nul 2>&1 || (
  echo ERROR: GitHub CLI ^(gh.exe^) is required. Install it and run gh auth login.
  exit /b 1
)
gh auth status >nul 2>&1 || (
  echo ERROR: GitHub CLI is not authenticated. Run: gh auth login
  exit /b 1
)
if not exist "private-data\hrm-v060b1-fernet.key" (
  echo ERROR: private key is missing. Run PREPARE-REAL-DATA-V060B1.cmd first.
  exit /b 1
)
git check-ignore -q private-data\hrm-v060b1-fernet.key || (
  echo ERROR: private key is not protected by .gitignore.
  exit /b 1
)

echo Creating or updating protected GitHub Environment...
gh api --method PUT "repos/{owner}/{repo}/environments/real-data-validation" >nul || exit /b 1

echo Uploading HRM_REAL_DATA_KEY without printing it...
type "private-data\hrm-v060b1-fernet.key" | gh secret set HRM_REAL_DATA_KEY --env real-data-validation || exit /b 1

gh secret list --env real-data-validation | findstr /b /c:"HRM_REAL_DATA_KEY" >nul || (
  echo ERROR: GitHub did not confirm the protected environment secret.
  exit /b 1
)
echo PASS: protected GitHub Environment secret is configured.
exit /b 0
