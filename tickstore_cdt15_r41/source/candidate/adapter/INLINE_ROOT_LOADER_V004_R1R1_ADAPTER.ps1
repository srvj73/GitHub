# Audit artifact: the owner must deliver this function text through the trusted UI.
# Do not execute a downloaded loader by path. Defining this function launches nothing.
function Invoke-TickstoreInlineRootV004R1Adapter {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$BundlePath,
        [Parameter(Mandatory=$true)][string]$PythonPath,
        [Parameter(Mandatory=$true)][string]$ExternalAnchorJson,
        [Parameter(Mandatory=$true)][string]$AdapterEntryPath,
        [Parameter(Mandatory=$true)][string]$ExpectedAdapterEntrySha
    )
    $ErrorActionPreference = 'Stop'
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'WINDOWS_POWERSHELL_5_1_REQUIRED'
    }
    if (-not ('TickstoreRootV004R1' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Threading;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

public static class TickstoreRootV004R1 {
    [StructLayout(LayoutKind.Sequential)] struct Security { public int length; public IntPtr descriptor; public int inherit; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Startup {
        public int cb; public string reserved,desktop,title;
        public uint x,y,xsize,ysize,xchars,ychars,fill,flags;
        public ushort show,reserved2; public IntPtr reservedBytes,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)] struct StartupEx { public Startup basic; public IntPtr list; }
    [StructLayout(LayoutKind.Sequential)] struct ProcessInfo { public IntPtr process,thread; public uint pid,tid; }
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long processTime,jobTime; public uint flags; public UIntPtr min,max; public uint active;
        public UIntPtr affinity; public uint priority,scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters { public ulong a,b,c,d,e,f; }
    [StructLayout(LayoutKind.Sequential)] struct JobLimits {
        public BasicLimits basic; public IoCounters io; public UIntPtr processMemory,jobMemory,peakProcess,peakJob;
    }
    [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateFileW(string p,uint access,uint share,IntPtr sa,uint creation,uint flags,IntPtr template);
    [DllImport("kernel32", SetLastError=true)] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32", SetLastError=true)] static extern bool GetFileInformationByHandleEx(IntPtr h,int kind,IntPtr data,uint size);
    [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern uint GetFinalPathNameByHandleW(IntPtr h,StringBuilder name,uint size,uint flags);
    [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr sa,string name);
    [DllImport("kernel32", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int kind,ref JobLimits limits,int size);
    [DllImport("kernel32", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32", SetLastError=true)] static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool assigned);
    [DllImport("kernel32", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int kind,IntPtr data,uint size,IntPtr returned);
    [DllImport("kernel32", SetLastError=true)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref Security sa,uint size);
    [DllImport("kernel32", SetLastError=true)] static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
    [DllImport("kernel32", SetLastError=true)] static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32", SetLastError=true)] static extern bool DuplicateHandle(IntPtr sp,IntPtr source,IntPtr tp,out IntPtr target,uint access,bool inherit,uint options);
    [DllImport("kernel32", SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,uint flags,ref IntPtr size);
    [DllImport("kernel32", SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr prior,IntPtr returned);
    [DllImport("kernel32")] static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string app,StringBuilder command,IntPtr psa,IntPtr tsa,bool inherit,uint flags,IntPtr env,string cwd,ref StartupEx startup,out ProcessInfo pi);
    [DllImport("kernel32", SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint timeout);
    [DllImport("kernel32", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32", SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
    static void Check(bool ok,string label) { if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error(),label); }
    static void Close(ref IntPtr h) { if(h!=IntPtr.Zero && h!=new IntPtr(-1)) { Check(CloseHandle(h),"CloseHandle"); h=IntPtr.Zero; } }
    static string Normal(string value) { return Path.GetFullPath(value).TrimEnd('\\').ToUpperInvariant(); }
    static void Validate(IntPtr h,string path,bool directory) {
        IntPtr data=Marshal.AllocHGlobal(32);
        try {
            Check(GetFileInformationByHandleEx(h,9,data,8),"AttributeTagInfo");
            if((Marshal.ReadInt32(data)&0x400)!=0 || Marshal.ReadInt32(data,4)!=0) throw new Exception("REPARSE");
            Check(GetFileInformationByHandleEx(h,1,data,24),"StandardInfo");
            if((Marshal.ReadByte(data,21)!=0)!=directory || Marshal.ReadByte(data,20)!=0) throw new Exception("FILE_TYPE");
            if(!directory && Marshal.ReadInt32(data,16)!=1) throw new Exception("HARDLINK");
            Check(GetFileInformationByHandleEx(h,18,data,24),"FileIdInfo");
            StringBuilder final=new StringBuilder(32768); uint length=GetFinalPathNameByHandleW(h,final,32768,0);
            if(length==0 || length>=32768) throw new Exception("FINAL_PATH");
            string value=final.ToString(); if(value.StartsWith("\\\\?\\")) value=value.Substring(4);
            if(Normal(value)!=Normal(path)) throw new Exception("FINAL_PATH_IDENTITY");
        } finally { Marshal.FreeHGlobal(data); }
    }
    public sealed class Pin : IDisposable {
        public FileStream Stream;
        readonly List<SafeFileHandle> parents=new List<SafeFileHandle>();
        public Pin(string path) {
            path=Path.GetFullPath(path);
            try {
                List<string> chain=new List<string>();
                DirectoryInfo dir=new FileInfo(path).Directory;
                while(dir!=null) { chain.Add(dir.FullName); dir=dir.Parent; }
                chain.Reverse();
                foreach(string item in chain) {
                    IntPtr h=CreateFileW(item,0x001000a1,3,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
                    Check(h!=new IntPtr(-1),"PinDirectory");
                    SafeFileHandle safe=new SafeFileHandle(h,true); parents.Add(safe); Validate(h,item,true);
                }
                IntPtr file=CreateFileW(path,0x80000000,1,IntPtr.Zero,3,0x00200000,IntPtr.Zero);
                Check(file!=new IntPtr(-1),"PinFile");
                SafeFileHandle pinned=new SafeFileHandle(file,true);
                try { Validate(file,path,false); Stream=new FileStream(pinned,FileAccess.Read); }
                catch { pinned.Dispose(); throw; }
            } catch { Dispose(); throw; }
        }
        public void Dispose() { if(Stream!=null) {Stream.Dispose();Stream=null;} for(int i=parents.Count-1;i>=0;i--)parents[i].Dispose();parents.Clear(); }
    }
    public static string Hash(byte[] data) { using(SHA256 s=SHA256.Create()) return BitConverter.ToString(s.ComputeHash(data)).Replace("-",""); }
    public static string HashStream(Stream stream) { stream.Position=0; string h; using(SHA256 s=SHA256.Create())h=BitConverter.ToString(s.ComputeHash(stream)).Replace("-",""); stream.Position=0; return h; }
    public static int Launch(string python,byte[] source,byte[] bootstrap) {
        IntPtr job=IntPtr.Zero,sr=IntPtr.Zero,sw=IntPtr.Zero,br=IntPtr.Zero,bw=IntPtr.Zero,output=IntPtr.Zero,error=IntPtr.Zero,list=IntPtr.Zero,handles=IntPtr.Zero;
        ProcessInfo pi=new ProcessInfo(); bool assigned=false;
        try {
            job=CreateJobObjectW(IntPtr.Zero,null); Check(job!=IntPtr.Zero,"CreateJob");
            JobLimits limits=new JobLimits(); limits.basic.flags=0x2000; // kill-on-close; neither breakaway flag is set.
            Check(SetInformationJobObject(job,9,ref limits,Marshal.SizeOf(typeof(JobLimits))),"JobLimits");
            Security sa=new Security(); sa.length=Marshal.SizeOf(typeof(Security)); sa.inherit=1;
            Check(CreatePipe(out sr,out sw,ref sa,0),"SourcePipe"); Check(SetHandleInformation(sw,1,0),"SourceParentPrivate");
            Check(CreatePipe(out br,out bw,ref sa,0),"BootstrapPipe"); Check(SetHandleInformation(bw,1,0),"BootstrapParentPrivate");
            Check(DuplicateHandle(GetCurrentProcess(),GetStdHandle(-11),GetCurrentProcess(),out output,0,true,2),"Stdout");
            Check(DuplicateHandle(GetCurrentProcess(),GetStdHandle(-12),GetCurrentProcess(),out error,0,true,2),"Stderr");
            IntPtr size=IntPtr.Zero; InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
            list=Marshal.AllocHGlobal(size);Check(InitializeProcThreadAttributeList(list,1,0,ref size),"HandleList");
            handles=Marshal.AllocHGlobal(4*IntPtr.Size);
            IntPtr[] inherited={sr,br,output,error};for(int i=0;i<4;i++)Marshal.WriteIntPtr(handles,i*IntPtr.Size,inherited[i]);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(4*IntPtr.Size),IntPtr.Zero,IntPtr.Zero),"ExplicitHandles");
            StartupEx si=new StartupEx(); si.basic.cb=Marshal.SizeOf(typeof(StartupEx));si.basic.flags=0x100;
            si.basic.input=sr;si.basic.output=output;si.basic.error=error;si.list=list;
            StringBuilder cmd=new StringBuilder("\""+python+"\" -I -S -B - --bootstrap-handle "+br.ToInt64());
            // CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW. No breakaway.
            Check(CreateProcessW(python,cmd,IntPtr.Zero,IntPtr.Zero,true,0x08080004,IntPtr.Zero,null,ref si,out pi),"CreateSuspended");
            Check(AssignProcessToJobObject(job,pi.process),"AssignBeforeResume");
            Check(IsProcessInJob(pi.process,job,out assigned)&&assigned,"VerifyJobAssignment");
            IntPtr preResume=Marshal.AllocHGlobal(8+IntPtr.Size);
            try {
                for(int i=0;i<8+IntPtr.Size;i++)Marshal.WriteByte(preResume,i,0);
                Check(QueryInformationJobObject(job,3,preResume,(uint)(8+IntPtr.Size),IntPtr.Zero),"PreResumeJobAccounting");
                int preAssigned=Marshal.ReadInt32(preResume);int preActive=Marshal.ReadInt32(preResume,4);
                long prePid=IntPtr.Size==8 ? Marshal.ReadInt64(preResume,8) : Marshal.ReadInt32(preResume,8);
                if(preAssigned!=1 || preActive!=1 || prePid!=(long)pi.pid)throw new Exception("PRE_RESUME_JOB_SINGLETON");
            } finally { Marshal.FreeHGlobal(preResume); }
            if(ResumeThread(pi.thread)==0xffffffff)throw new Win32Exception(Marshal.GetLastWin32Error(),"ResumeThread");
            Close(ref sr);Close(ref br);Close(ref output);Close(ref error);
            using(FileStream input=new FileStream(new SafeFileHandle(sw,true),FileAccess.Write)) { sw=IntPtr.Zero;input.Write(source,0,source.Length);input.Flush(); }
            using(FileStream input=new FileStream(new SafeFileHandle(bw,true),FileAccess.Write)) { bw=IntPtr.Zero;input.Write(bootstrap,0,bootstrap.Length);input.Flush(); }
            while(WaitForSingleObject(pi.process,1000)==258) { }
            uint exit;Check(GetExitCodeProcess(pi.process,out exit),"ChildExit");
            // A terminated console process can leave its OS-managed conhost descendant in the
            // dedicated Job briefly. Release process/thread handles first, then wait for a
            // bounded zero-member census while the Job lifetime handle remains open.
            Close(ref pi.thread);Close(ref pi.process);
            IntPtr accounting=Marshal.AllocHGlobal(2048);
            try {
                Stopwatch drain=Stopwatch.StartNew();
                while(true) {
                    for(int i=0;i<2048;i++)Marshal.WriteByte(accounting,i,0);
                    Check(QueryInformationJobObject(job,3,accounting,2048,IntPtr.Zero),"FinalJobAccounting");
                    int assignedNow=Marshal.ReadInt32(accounting);int activeNow=Marshal.ReadInt32(accounting,4);
                    if(assignedNow==0 && activeNow==0)break;
                    if(assignedNow!=activeNow)throw new Exception("JOB_MEMBERSHIP_TRUNCATED");
                    if(drain.ElapsedMilliseconds>=5000)throw new Exception("RESIDUAL_JOB_PROCESSES");
                    Thread.Sleep(10);
                }
            }
            finally { Marshal.FreeHGlobal(accounting); }
            return checked((int)exit);
        } finally {
            if(pi.process!=IntPtr.Zero && !assigned)TerminateProcess(pi.process,2);
            Close(ref job); // closes lifetime authority before releasing any runtime pins in the caller.
            if(pi.process!=IntPtr.Zero)WaitForSingleObject(pi.process,120000);
            Close(ref pi.thread);Close(ref pi.process);Close(ref sr);Close(ref sw);Close(ref br);Close(ref bw);Close(ref output);Close(ref error);
            if(list!=IntPtr.Zero) {DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);}
            if(handles!=IntPtr.Zero)Marshal.FreeHGlobal(handles);
        }
    }
}
'@
    }
    Add-Type -AssemblyName System.IO.Compression
    $tickstoreAnchor = $ExternalAnchorJson | ConvertFrom-Json
    foreach ($tickstoreField in @('release_bundle_sha256','release_manifest_sha256','recovery_source_sha256','owner_gate_sha256','python_exe_sha256')) {
        if ($tickstoreAnchor.$tickstoreField -cnotmatch '^[0-9A-F]{64}$') { throw ('ANCHOR_HASH_REQUIRED:'+$tickstoreField) }
    }
    if ($tickstoreAnchor.inline_root_loader_revision -cne 'INLINE_ROOT_LOADER_V004_R1' -or $tickstoreAnchor.python_version -cne '3.14.7') { throw 'ANCHOR_RUNTIME_CONTRACT' }
    $tickstoreBundlePin = $null
    $tickstorePythonPin = $null
    $tickstoreAdapterPin = $null
    $tickstoreArchive = $null
    try {
        $tickstoreBundlePin = New-Object TickstoreRootV004R1+Pin($BundlePath)
        if ([TickstoreRootV004R1]::HashStream($tickstoreBundlePin.Stream) -cne $tickstoreAnchor.release_bundle_sha256) { throw 'BUNDLE_HASH_MISMATCH' }
        $tickstoreArchive = New-Object System.IO.Compression.ZipArchive($tickstoreBundlePin.Stream,[System.IO.Compression.ZipArchiveMode]::Read,$true)
        $tickstoreMembers = @{}
        $tickstoreSource = $null
        $tickstoreTotal = 0
        foreach ($tickstoreEntry in $tickstoreArchive.Entries) {
            if ($tickstoreEntry.FullName -cnotmatch '^[A-Za-z0-9_.-]+$' -or $tickstoreMembers.ContainsKey($tickstoreEntry.FullName)) { throw 'ZIP_MEMBER_GRAMMAR_OR_DUPLICATE' }
            $tickstoreTotal += $tickstoreEntry.Length
            if ($tickstoreTotal -gt 33554432) { throw 'ZIP_UNCOMPRESSED_LIMIT' }
            $tickstoreMemory = New-Object IO.MemoryStream
            $tickstoreInput = $tickstoreEntry.Open()
            try { $tickstoreInput.CopyTo($tickstoreMemory); $tickstoreRaw=$tickstoreMemory.ToArray() } finally { $tickstoreInput.Dispose(); $tickstoreMemory.Dispose() }
            if ($tickstoreEntry.Name -eq 'tickstore_publisher_recovery_v004.py') { $tickstoreSource=$tickstoreRaw }
            $tickstoreMembers[$tickstoreEntry.FullName]=[Convert]::ToBase64String($tickstoreRaw)
        }
        if ($null -eq $tickstoreSource -or [TickstoreRootV004R1]::Hash($tickstoreSource) -cne $tickstoreAnchor.recovery_source_sha256) { throw 'SOURCE_HASH_MISMATCH' }
        foreach ($tickstorePair in @(@('RELEASE_MANIFEST.json','release_manifest_sha256'),@('OWNER_GATE.json','owner_gate_sha256'))) {
            if ([TickstoreRootV004R1]::Hash([Convert]::FromBase64String($tickstoreMembers[$tickstorePair[0]])) -cne $tickstoreAnchor.($tickstorePair[1])) { throw 'ANCHOR_MEMBER_HASH_MISMATCH' }
        }
        $tickstorePythonPin = New-Object TickstoreRootV004R1+Pin($PythonPath)
        if ([TickstoreRootV004R1]::HashStream($tickstorePythonPin.Stream) -cne $tickstoreAnchor.python_exe_sha256) { throw 'PYTHON_HASH_MISMATCH' }
        if ([Diagnostics.FileVersionInfo]::GetVersionInfo($PythonPath).ProductVersion -notmatch '^3\.14\.7(?:\D|$)') { throw 'PYTHON_VERSION_MISMATCH' }
        if ($ExpectedAdapterEntrySha -cnotmatch '^[0-9A-F]{64}$') { throw 'ADAPTER_ENTRY_SHA_GRAMMAR' }
        $tickstoreAdapterPin = New-Object TickstoreRootV004R1+Pin($AdapterEntryPath)
        if ([TickstoreRootV004R1]::HashStream($tickstoreAdapterPin.Stream) -cne $ExpectedAdapterEntrySha) { throw 'ADAPTER_ENTRY_HASH_MISMATCH' }
        $tickstoreAdapterMemory = New-Object IO.MemoryStream
        try { $tickstoreAdapterPin.Stream.CopyTo($tickstoreAdapterMemory); $tickstoreAdapterSource=$tickstoreAdapterMemory.ToArray(); $tickstoreAdapterPin.Stream.Position=0 } finally { $tickstoreAdapterMemory.Dispose() }
        $tickstorePayload = [Text.Encoding]::UTF8.GetBytes((@{anchor=$tickstoreAnchor;members=$tickstoreMembers} | ConvertTo-Json -Depth 30 -Compress))
        return [TickstoreRootV004R1]::Launch($PythonPath,$tickstoreAdapterSource,$tickstorePayload)
    }
    finally {
        if ($null -ne $tickstoreArchive) { $tickstoreArchive.Dispose() }
        if ($null -ne $tickstoreBundlePin) { $tickstoreBundlePin.Dispose() }
        if ($null -ne $tickstorePythonPin) { $tickstorePythonPin.Dispose() }
        if ($null -ne $tickstoreAdapterPin) { $tickstoreAdapterPin.Dispose() }
    }
}
