@Echo Off
Echo Setting environment for using Microsoft XNA Game Studio 3.1 tools.
TITLE XNA Game Studio 3.1 Command Prompt
SET PATH=%1;%2;%XNAGSv3%Tools;%XNAGSShared%XnaPack;%XNAGSShared%Device Center;%PATH%
CD /D "%HOMEDRIVE%%HOMEPATH%"