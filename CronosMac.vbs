Dim fso, shell, appDir

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

' Устанавливаем пакеты тихо (если уже есть — меньше секунды)
shell.Run "cmd /c python -m pip install flask crodump chardet pywebview -q", 0, True

' Запускаем без консоли — pythonw не создаёт терминального окна
shell.Run "pythonw.exe launcher.py", 0, False
