@echo off
rem The editor's team folders -> media/ + data/team_photos.json, then push.
rem Drop photos into team-photos\<club>\, write their line in that folder's
rem credits.txt, double-click this. Manual on purpose, like the Oracle
rem library push: a photo is never urgent, and this way there is no half
rem state of copied-but-uncommitted files.
setlocal
cd /d "%~dp0"
set PY="C:\Program Files\Python312\python.exe"
chcp 65001 >nul

%PY% team_photos.py || goto :fail
%PY% shrink_media.py --quiet

git add team-photos media data\team_photos.json
git diff --cached --quiet && echo nothing new to commit && goto :end
git commit -q -m "team photos: the editor's folders [skip ci]" || goto :fail
git push -q origin HEAD:main || goto :fail
echo pushed.
goto :end

:fail
echo.
echo FAILED - nothing was pushed. Read the lines above.
exit /b 1

:end
endlocal
