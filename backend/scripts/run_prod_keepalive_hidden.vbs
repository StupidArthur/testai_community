' Hidden launcher for prod backend keepalive.
' Used by Scheduled Task TestAI-Backend so closing CMD windows does not kill the site.
Set sh = CreateObject("WScript.Shell")
' 0 = hidden window, False = do not wait
sh.Run """" & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\run_prod_keepalive.cmd""", 0, False
