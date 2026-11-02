/* Windows x86 helper: enumeration, identity and fixed read requests only. */
#define WIN32_LEAN_AND_MEAN
#if !defined(_WIN32) || (!defined(__i386__) && !defined(_M_IX86))
#error Build this helper for Windows x86 (32-bit).
#endif
#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <wchar.h>
#include <string.h>
#include "read_packets.h"
static const GUID usbprint={0x28d78fad,0x5a12,0x11d1,{0xae,0x5b,0,0,0xf8,3,0xa8,0xc2}};
static void hex(const void *p,size_t n){const unsigned char*b=p;for(size_t i=0;i<n;i++)printf("%02x",b[i]);}
static void wh(const wchar_t*s){hex(s,wcslen(s)*sizeof(wchar_t));}
static void stage(const char*s){printf("{\"event\":\"stage\",\"stage\":\"%s\",\"helper_version\":\"0.3\",\"ticks_ms\":%llu}\n",s,(unsigned long long)GetTickCount64());fflush(stdout);}
static int fail(const char*s,long long code){printf("{\"event\":\"error\",\"message\":\"%s\",\"code\":%lld}\n",s,code);fflush(stdout);return 1;}
static int scan(void){
 stage("scan_started");
 HDEVINFO set=SetupDiGetClassDevsW(&usbprint,NULL,NULL,DIGCF_PRESENT|DIGCF_DEVICEINTERFACE);
 if(set==INVALID_HANDLE_VALUE)return fail("SetupDiGetClassDevs",GetLastError());
 for(DWORD index=0;;index++){
  SP_DEVICE_INTERFACE_DATA it={0};it.cbSize=sizeof(it);
  if(!SetupDiEnumDeviceInterfaces(set,NULL,&usbprint,index,&it)){if(GetLastError()!=ERROR_NO_MORE_ITEMS)fail("SetupDiEnumDeviceInterfaces",GetLastError());break;}
  DWORD size=0;SetupDiGetDeviceInterfaceDetailW(set,&it,NULL,0,&size,NULL);
  if(size<sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)||size>65536){fail("invalid USB interface detail size",ERROR_INVALID_DATA);continue;}
  PSP_DEVICE_INTERFACE_DETAIL_DATA_W detail=calloc(1,size);if(!detail)continue;detail->cbSize=sizeof(*detail);
  SP_DEVINFO_DATA info={0};info.cbSize=sizeof(info);
  if(!SetupDiGetDeviceInterfaceDetailW(set,&it,detail,size,NULL,&info)){free(detail);continue;}
  DWORD port=0xffffffff,type=0,n=sizeof(port);HKEY key=SetupDiOpenDeviceInterfaceRegKey(set,&it,0,KEY_READ);
  if(key!=INVALID_HANDLE_VALUE){if(RegQueryValueExW(key,L"Port Number",NULL,&type,(LPBYTE)&port,&n)!=ERROR_SUCCESS||type!=REG_DWORD)port=0xffffffff;RegCloseKey(key);}
  wchar_t name[512]={0},instance[512]={0},parent_id[512]={0};
  SetupDiGetDeviceRegistryPropertyW(set,&info,SPDRP_FRIENDLYNAME,NULL,(PBYTE)name,sizeof(name),NULL);
  if(!name[0])SetupDiGetDeviceRegistryPropertyW(set,&info,SPDRP_DEVICEDESC,NULL,(PBYTE)name,sizeof(name),NULL);
  SetupDiGetDeviceInstanceIdW(set,&info,instance,512,NULL);
  DEVINST parent=info.DevInst;
  for(int j=0;j<4;j++){DEVINST next;if(CM_Get_Parent(&next,parent,0)!=CR_SUCCESS)break;parent=next;CM_Get_Device_IDW(parent,parent_id,512,0);if(wcsncmp(parent_id,L"USB\\VID_",8)==0)break;}
  unsigned char id[4096]={0};DWORD got=0,id_error=0;
  stage("device_id_start");
  HANDLE h=CreateFileW(detail->DevicePath,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
  if(h!=INVALID_HANDLE_VALUE){if(!DeviceIoControl(h,0x221804,NULL,0,id,sizeof(id),&got,NULL)){id_error=GetLastError();if(DeviceIoControl(h,0x16000c,NULL,0,id,sizeof(id),&got,NULL))id_error=0;}CloseHandle(h);}else id_error=GetLastError();
  stage("device_id_done");
  printf("{\"event\":\"device\",\"index\":%lu,\"port\":%lu,\"name_utf16\":\"",(unsigned long)index,(unsigned long)port);wh(name);
  printf("\",\"path_utf16\":\"");wh(detail->DevicePath);printf("\",\"instance_utf16\":\"");wh(instance);printf("\",\"parent_utf16\":\"");wh(parent_id);
  printf("\",\"ieee1284_hex\":\"");hex(id,got<=sizeof(id)?got:0);printf("\",\"identity_error\":%lu}\n",(unsigned long)id_error);fflush(stdout);free(detail);
 }
 SetupDiDestroyDeviceInfoList(set);printf("{\"event\":\"scan_done\"}\n");return 0;
}
typedef void* (__thiscall *Ctor)(void*);
typedef void (__thiscall *Dtor)(void*);
typedef int (__thiscall *Open)(void*,int,int);
typedef void (__thiscall *GetID)(void*,char*,int);
typedef int (__thiscall *Ctl)(void*,const unsigned char*,unsigned int,unsigned char*);
static void read_request(Ctl ctl,void*object,unsigned region,unsigned offset,unsigned count,int serial,int repeat,const char*profile){
 /* Only command 98 (selected read) and 5D (NVRAM serial read) can be emitted. */
 unsigned char req[16];unsigned n=make_fixed_read(req,serial,region,offset,count);
 if(!n){fail("read request rejected",ERROR_INVALID_PARAMETER);return;}
 unsigned char *reply=calloc(1,1024*1024);if(!reply){fail("allocation",ERROR_NOT_ENOUGH_MEMORY);return;}
 printf("{\"event\":\"read_start\",\"profile\":\"%s\",\"kind\":\"%s\",\"region\":%u,\"offset\":%u,\"requested\":%u,\"repeat\":%d,\"request_hex\":\"",profile,serial?"serial":"key",region,offset,count,repeat);hex(req,n);printf("\"}\n");fflush(stdout);
 int rc=ctl(object,req,n,reply);
 printf("{\"event\":\"read\",\"profile\":\"%s\",\"kind\":\"%s\",\"region\":%u,\"offset\":%u,\"requested\":%u,\"repeat\":%d,\"driver_result\":%d,\"request_hex\":\"",profile,serial?"serial":"key",region,offset,count,repeat,rc);hex(req,n);
 printf("\",\"capture_window_bytes\":4096,\"response_window_hex\":\"");hex(reply,4096);printf("\"}\n");fflush(stdout);free(reply);
}
int wmain(int argc,wchar_t**argv){
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
 setvbuf(stdout,NULL,_IONBF,0);stage("helper_started");if(argc==2&&wcscmp(argv[1],L"scan")==0)return scan();
 if((argc!=5&&argc!=6)||wcscmp(argv[1],L"probe")!=0)return fail("expected scan or probe DLL PORT REGION [keys|bounds]",ERROR_INVALID_PARAMETER);
 int bounds=argc==6&&wcscmp(argv[5],L"bounds")==0;
 if(argc==6&&!bounds&&wcscmp(argv[5],L"keys")!=0)return fail("unknown read profile",ERROR_INVALID_PARAMETER);
 const char*profile=bounds?"bounds":"keys";
 wchar_t*end;unsigned long port=wcstoul(argv[3],&end,10);if(*end||port>9)return fail("USB port must be 0..9",ERROR_INVALID_PARAMETER);
 unsigned long region=wcstoul(argv[4],&end,16);if(*end||(region!=0xa3&&region!=0xd6))return fail("region must be A3 or D6",ERROR_INVALID_PARAMETER);
 stage("load_library_start");
 HMODULE dll=LoadLibraryExW(argv[2],NULL,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);if(!dll)return fail("LoadLibraryEx EprisDrv (check x86 VC++ runtime)",GetLastError());
 stage("load_library_done");stage("resolve_exports_start");
 Ctor ctor=(Ctor)GetProcAddress(dll,"??0CWinEprisDrv@@QAE@XZ");Dtor dtor=(Dtor)GetProcAddress(dll,"??1CWinEprisDrv@@QAE@XZ");
 Open open=(Open)GetProcAddress(dll,"?Open@CWinEprisDrv@@QAE?AW4ERR_EPRISDRV@@HH@Z");GetID getid=(GetID)GetProcAddress(dll,"?GetDeviceID@CWinEprisDrv@@QAEXPADH@Z");
 Ctl ctl=(Ctl)GetProcAddress(dll,"?Ctl_SendReceive@CWinEprisDrv@@QAE?AW4ERR_EPRISDRV@@PBEIPAE@Z");
 if(!ctor||!dtor||!open||!getid||!ctl)return fail("required DLL exports missing",ERROR_PROC_NOT_FOUND);
 stage("resolve_exports_done");stage("constructor_start");
 void*object=calloc(1,4096);if(!object)return fail("allocation",ERROR_NOT_ENOUGH_MEMORY);ctor(object);stage("constructor_done");
 stage("usb_open_start");
 int rc=open(object,10+(int)port,1);
 stage("usb_open_done");
 if(rc<0){fail("EprisDrv USB Open",rc);stage("close_start");dtor(object);free(object);FreeLibrary(dll);return 1;}
 stage("identity_start");char id[1024]={0};getid(object,id,sizeof(id));id[sizeof(id)-1]=0;stage("identity_done");
 printf("{\"event\":\"opened\",\"device_id_hex\":\"");hex(id,strlen(id));printf("\",\"port\":%lu}\n",port);
 if(!strstr(id,"P7500")&&!strstr(id,"P-7500")){fail("opened printer is not SC-P7500",ERROR_NOT_SUPPORTED);stage("close_start");dtor(object);free(object);FreeLibrary(dll);return 1;}
 read_request(ctl,object,0,0x644,10,1,0,profile);
 const unsigned keys[]={0x7010,0x6d000},a3_bounds[]={0,0x644,0xffc0,0x10000},d6_bounds[]={0,0xfc0,0x1000};
 const unsigned*offsets=bounds?(region==0xa3?a3_bounds:d6_bounds):keys;
 unsigned total=bounds?(region==0xa3?4:3):2;
 for(unsigned i=0;i<total;i++)for(int repeat=0;repeat<2;repeat++)read_request(ctl,object,region,offsets[i],64,0,repeat,profile);
 stage("close_start");dtor(object);free(object);FreeLibrary(dll);stage("close_done");printf("{\"event\":\"done\"}\n");return 0;
}
