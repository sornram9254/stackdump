<#
 .SYNOPSIS
 Starts Solr, the Stackdump indexing engine.
 .DESCRIPTION
 Starts Solr, by using the Java path specified in the JAVA_CMD file located in 
 the same directory as this script (create as necessary) or java.exe that
 resolves in the current PATH.
 
 No parameters are accepted.
 .EXAMPLE
 Start-Solr
 #>

$ScriptDir = Split-Path $MyInvocation.MyCommand.Path
$JavaCmd = 'java.exe'

if (Test-Path (Join-Path $ScriptDir 'JAVA_CMD')) {
	$JavaCmd = Get-Content (Join-Path $ScriptDir 'JAVA_CMD')
}

$AbsJavaCmd = @(Get-Command $JavaCmd -ErrorAction SilentlyContinue)[0].Path
if ($AbsJavaCmd -ne $null) {
	Write-Host "Using Java $AbsJavaCmd"
	
	Push-Location (Join-Path $ScriptDir 'java\solr\server')
	try {
		& $AbsJavaCmd -Xmx2048M -XX:MaxPermSize=512M '-Djetty.host=127.0.0.1' -jar start.jar
	}
	finally {
		Pop-Location
	}
}
else {
	Write-Error "Java could not be located. Specify its path using JAVA_CMD or check the path in JAVA_CMD."
}
