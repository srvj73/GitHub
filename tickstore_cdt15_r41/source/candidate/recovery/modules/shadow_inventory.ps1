#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutFile)
$ErrorActionPreference='Stop';Set-StrictMode -Version 2.0
$vol=Get-CimInstance -ClassName Win32_Volume -Filter "DriveLetter='D:'"
if($null -eq $vol){throw 'D_VOLUME_NOT_FOUND'}
$volumeName=[string]$vol.DeviceID;$items=@()
foreach($s in @(Get-CimInstance -ClassName Win32_ShadowCopy)){
 if(([string]$s.VolumeName).TrimEnd('\\') -cne $volumeName.TrimEnd('\\')){continue}
 $install=$null;if($null-ne$s.InstallDate){try{$install=([DateTime]$s.InstallDate).ToUniversalTime().ToString('o')}catch{$install=[string]$s.InstallDate}}
 $items += [ordered]@{id=[string]$s.ID;set_id=[string]$s.SetID;device_object=[string]$s.DeviceObject;volume_name=[string]$s.VolumeName;provider_id=[string]$s.ProviderID;install_utc=$install;state=[int]$s.State;persistent=[bool]$s.Persistent;no_auto_release=[bool]$s.NoAutoRelease;client_accessible=[bool]$s.ClientAccessible;exposed_locally=[bool]$s.ExposedLocally;exposed_name=[string]$s.ExposedName}
}
$items=@($items|Sort-Object install_utc,id)
$obj=[ordered]@{schema='TICKSTORE_VSS_SHADOW_INVENTORY_V001';captured_utc=[DateTime]::UtcNow.ToString('o');drive='D:';volume_name=$volumeName;count=$items.Count;snapshots=$items}
[IO.File]::WriteAllText($OutFile,($obj|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
Write-Host ('SHADOW_INVENTORY=PASS count='+$items.Count);Write-Host ('SHADOW_INVENTORY_OUT='+$OutFile)
