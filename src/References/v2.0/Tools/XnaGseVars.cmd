@Echo Off
Echo Setting environment for using Microsoft XNA Game Studio tools.
TITLE XNA Game Studio Command Prompt
SET PATH=%1;%2;%XNAGSv2%Tools;%XNAGSShared%XnaPack;%PATH%
CD /D "%HOMEDRIVE%%HOMEPATH%"