Option Explicit
Dim shell, files, scriptPath, command, failed
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
scriptPath = files.BuildPath(files.GetParentFolderName(WScript.ScriptFullName), "Launch Archiver.pyw")
On Error Resume Next
command = "pyw.exe -3 " & Chr(34) & scriptPath & Chr(34)
shell.Run command, 0, False
failed = Err.Number
If failed <> 0 Then
    Err.Clear
    command = "pythonw.exe " & Chr(34) & scriptPath & Chr(34)
    shell.Run command, 0, False
    If Err.Number <> 0 Then
        MsgBox "Archiver needs Python 3.10 or newer with its Windows launcher. Install Python, then open Launch Archiver.vbs again.", 16, "Archiver"
    End If
End If
