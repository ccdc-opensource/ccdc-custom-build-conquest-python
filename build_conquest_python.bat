REM so, this is the one number to change when the list of installed packages changes
REM be a good person, change this number when the contents of this package change
set CQP_PATCHVERSION=1

set CQP_PYTHONVERSION=2.7.17
set CQP_VERSION=conquest_python-%CQP_PYTHONVERSION%-%CQP_PATCHVERSION%-64bit
set CQP_PATH=D:\x_mirror\buildman\tools\conquest_python\%CQP_VERSION%
set CQP_DOWNLOADDIR=D:\cp-build

rmdir /s /q %CQP_DOWNLOADDIR% 
mkdir %CQP_DOWNLOADDIR%
d:
cd %CQP_DOWNLOADDIR%

wget https://www.python.org/ftp/python/%CQP_PYTHONVERSION%/python-%CQP_PYTHONVERSION%.amd64.msi
wget https://github.com/rogerbinns/apsw/releases/download/3.31.1-r1/apsw-3.31.1-r1.win-amd64-py2.7.exe

REM Originally Obtained from
REM https://www.lfd.uci.edu/~gohlke/pythonlibs/#bsddb3
REM See https://stackoverflow.com/questions/33714698/installing-bsddb3-6-1-1-in-windows-filenotfounderror-db-include-db-h
wget https://artifactory.ccdc.cam.ac.uk/ccdc-3rdparty-windows-pythontools/bsddb3-6.2.6-cp27-cp27m-win_amd64.whl

REM Togl compiled from here
REM https://github.com/rockdreamer/togl
REM https://ci.appveyor.com/project/rockdreamer/togl/build/job/yvhnhasfenv955m9/artifacts
REM Installed in tcl\tk8.5\Togl
wget https://artifactory.ccdc.cam.ac.uk/ccdc-3rdparty-windows-pythontools/Togl-2.2-pre.zip

REM Remove apsw if there
%CQP_PATH%\Removeapsw.exe

REM remove existing python install
msiexec /qn /passive /x ^
  python-2.7.17.amd64.msi

rmdir /s /q %CQP_PATH%
mkdir D:\x_mirror\buildman\tools\conquest_python\


msiexec /qn /passive /i python-2.7.17.amd64.msi ^
  TARGETDIR=%CQP_PATH% ^
  ADDLOCAL=TclTk,Tools,Testsuite 

REM TODO can also use 7z to extract contents into site-packages
apsw-3.31.1-r1.win-amd64-py2.7.exe

REM install Claudio's Togl version
7z x -aoa -o%CQP_PATH%\tcl\tk8.5 Togl-2.2-pre.zip

REM ensure pip is installed and up to date
%CQP_PATH%\python.exe -m ensurepip
%CQP_PATH%\python.exe -m pip install --upgrade pip


%CQP_PATH%\python.exe -m pip install ^
  bsddb3-6.2.6-cp27-cp27m-win_amd64.whl

%CQP_PATH%\python.exe -m pip install ^
  PyInstaller==3.5 ^
  PyOpenGL==3.1.0 ^
  pywin32==225 ^
  numpy==1.16.5 ^
  nose==1.3.7 ^
  nose-parameterized==0.6.0 ^
  Pmw==2.0.1

