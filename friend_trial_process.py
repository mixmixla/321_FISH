"""Create only new trial children, suspended until assigned to a private Job.

The Job is unnamed, cannot break away, and its handle is not inherited. Closing
the owner, including unexpected owner death, terminates its child processes.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time
from test_sandbox import DesktopProcess, _create_private_desktop, _STARTUPINFOW, _PROCESS_INFORMATION

class _StartupEx(ctypes.Structure):
    _fields_=[('startup',_STARTUPINFOW),('attributes',ctypes.c_void_p)]

class _Limits(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
              ('flags',wintypes.DWORD),('min_working_set',ctypes.c_size_t),
              ('max_working_set',ctypes.c_size_t),('active_limit',wintypes.DWORD),
              ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]

class _IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]

class _Extended(ctypes.Structure):
    _fields_=[('basic',_Limits),('io',_IO),('process_memory',ctypes.c_size_t),
              ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]

class _Accounting(ctypes.Structure):
    _fields_=[(n,ctypes.c_longlong) for n in ('user','kernel','period_user','period_kernel')]+[
              (n,wintypes.DWORD) for n in ('page_faults','total','active','terminated')]

def _kernel():
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    declarations={
        'CreateJobObjectW':(wintypes.HANDLE,[ctypes.c_void_p,wintypes.LPCWSTR]),
        'SetInformationJobObject':(wintypes.BOOL,[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]),
        'QueryInformationJobObject':(wintypes.BOOL,[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]),
        'AssignProcessToJobObject':(wintypes.BOOL,[wintypes.HANDLE,wintypes.HANDLE]),
        'TerminateJobObject':(wintypes.BOOL,[wintypes.HANDLE,wintypes.UINT]),
        'TerminateProcess':(wintypes.BOOL,[wintypes.HANDLE,wintypes.UINT]),
        'ResumeThread':(wintypes.DWORD,[wintypes.HANDLE]),
        'CloseHandle':(wintypes.BOOL,[wintypes.HANDLE]),
        'InitializeProcThreadAttributeList':(wintypes.BOOL,[ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.c_size_t)]),
        'UpdateProcThreadAttribute':(wintypes.BOOL,[ctypes.c_void_p,wintypes.DWORD,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_void_p]),
        'DeleteProcThreadAttributeList':(None,[ctypes.c_void_p]),
        'CreateProcessW':(wintypes.BOOL,[wintypes.LPCWSTR,wintypes.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL,wintypes.DWORD,ctypes.c_void_p,wintypes.LPCWSTR,ctypes.c_void_p,ctypes.POINTER(_PROCESS_INFORMATION)]),
    }
    for name,(result,args) in declarations.items():
        fn=getattr(api,name);fn.restype=result;fn.argtypes=args
    return api

def _error(message):return OSError(ctypes.get_last_error(),message)

class OwnedJobProcess(DesktopProcess):
    def __init__(self,*,job_handle,**kwargs):
        super().__init__(**kwargs)
        self._job_handle=job_handle;self._closed=False

    def active_count(self):
        info=_Accounting()
        if not _kernel().QueryInformationJobObject(self._job_handle,1,ctypes.byref(info),ctypes.sizeof(info),None):
            raise _error('Cannot query the owned trial Job')
        return info.active

    def terminate_tree(self):
        if self._closed:return True
        if self.active_count() and not _kernel().TerminateJobObject(self._job_handle,124):
            raise _error('Cannot stop the owned trial Job')
        deadline=time.monotonic()+10
        while self.active_count():
            if time.monotonic()>=deadline:return False
            time.sleep(0.05)
        return True

    def close(self):
        if self._closed:return
        try:
            # The caller reports orderly cleanup failures separately.
            if not _kernel().CloseHandle(self._job_handle):raise _error('Cannot close the owned trial Job')
        finally:
            self._closed=True
            super().close()

def launch_owned(command,*,cwd:str,env:dict[str,str],log_path:Path,desktop_name:str|None=None):
    if os.name!='nt':raise OSError('This trial entry requires Windows')
    import _winapi
    import msvcrt
    api=_kernel();job=api.CreateJobObjectW(None,None)
    if not job:raise _error('Cannot create an owned trial Job')
    process=thread=desktop=None
    output=input_file=None
    attributes=None
    attributes_initialized=False
    inherited=[]
    try:
        limits=_Extended();limits.basic.flags=0x2000 # KILL_ON_JOB_CLOSE; no breakaway
        if not api.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            raise _error('Cannot protect the owned trial Job')
        log_path.parent.mkdir(parents=True,exist_ok=True)
        output=log_path.open('wb');input_file=open(os.devnull,'rb')
        current=_winapi.GetCurrentProcess()
        for stream in (input_file,output):
            inherited.append(_winapi.DuplicateHandle(current,msvcrt.get_osfhandle(stream.fileno()),current,0,True,_winapi.DUPLICATE_SAME_ACCESS))
        size=ctypes.c_size_t()
        api.InitializeProcThreadAttributeList(None,1,0,ctypes.byref(size))
        if not size.value:raise _error('Cannot size the trial handle list')
        attributes=ctypes.create_string_buffer(size.value)
        if not api.InitializeProcThreadAttributeList(attributes,1,0,ctypes.byref(size)):
            raise _error('Cannot initialize the trial handle list')
        attributes_initialized=True
        handle_list=(wintypes.HANDLE*len(inherited))(*inherited)
        if not api.UpdateProcThreadAttribute(attributes,0,0x20002,handle_list,ctypes.sizeof(handle_list),None,None):
            raise _error('Cannot restrict the trial inherited handles')
        si=_StartupEx();si.startup.cb=ctypes.sizeof(si)
        si.startup.dwFlags=_winapi.STARTF_USESTDHANDLES
        si.startup.hStdInput=inherited[0];si.startup.hStdOutput=si.startup.hStdError=inherited[1]
        si.attributes=ctypes.cast(attributes,ctypes.c_void_p)
        if desktop_name:
            desktop=_create_private_desktop(desktop_name)
            si.startup.lpDesktop='WinSta0\\'+desktop_name
        # Assign before the first instruction, including onefile descendants.
        flags=0x4|0x200|0x08000000|0x400|0x80000 # +UNICODE|EXTENDED_STARTUPINFO
        command_buffer=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(v) for v in command]))
        environment=ctypes.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items(),key=lambda item:item[0].upper()))+'\0\0')
        info=_PROCESS_INFORMATION()
        if not api.CreateProcessW(str(command[0]),command_buffer,None,None,True,flags,environment,cwd,ctypes.byref(si),ctypes.byref(info)):
            raise _error('Cannot create the suspended trial process')
        process,thread,pid=info.hProcess,info.hThread,info.dwProcessId
        if not api.AssignProcessToJobObject(job,process):raise _error('Cannot assign the new suspended trial process')
        if api.ResumeThread(thread)==0xffffffff:raise _error('Cannot resume the protected trial process')
        _winapi.CloseHandle(thread);thread=None
        result=OwnedJobProcess(job_handle=job,process_handle=process,thread_handle=None,desktop_handle=desktop,log_file=output,pid=pid)
        job=process=desktop=output=None
        return result
    except BaseException:
        if process:
            api.TerminateProcess(process,124)
            _winapi.WaitForSingleObject(process,10000)
        raise
    finally:
        if attributes_initialized:api.DeleteProcThreadAttributeList(attributes)
        for handle in inherited:_winapi.CloseHandle(handle)
        if input_file:input_file.close()
        if thread:_winapi.CloseHandle(thread)
        if process:_winapi.CloseHandle(process)
        if job:api.CloseHandle(job)
        if output:output.close()
        if desktop:
            from test_sandbox import _windows_handles
            _windows_handles()[1].CloseDesktop(desktop)
