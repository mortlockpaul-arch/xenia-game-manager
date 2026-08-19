@Echo Off
Echo Setting environment for using Microsoft XNA Game Studio 4.0 tools.
TITLE XNA Game Studio 4.0 Command Prompt
SET PATH=%*;%XNAGSv4%Tools;%XNAGSShared%XnaPack;%XNAGSShared%Device Center;%PATH%
CD /D "%HOMEDRIVE%%HOMEPATH%"