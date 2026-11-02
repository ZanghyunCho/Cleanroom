"""Read-only P7500 USB experiment: binary parsing, identity and evidence reports."""
from __future__ import annotations
import hashlib,json,re,struct,subprocess,threading,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DRIVER_SHA256='42f775bdd44425227a36750d6942104db99c9a37dfe82c4ce2d810b7b38eda18'
OFFSETS=(0x7010,0x6d000)
P=2**256-2**224+2**192+2**96-1
B=int('5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b',16)

class ProbeError(Exception):pass

def valid_public_key(data):
    if len(data)!=64:return False
    x,y=int.from_bytes(data[:32],'big'),int.from_bytes(data[32:],'big')
    return 0<=x<P and 0<=y<P and (y*y-x*x*x+3*x-B)%P==0

def reference_key(path):
    b=Path(path).read_bytes()
    if len(b)==65 and b[0]==4:b=b[1:]
    if not valid_public_key(b):raise ProbeError('참조 파일은 유효한 P-256 공개키여야 합니다. 64바이트 X||Y 또는 65바이트 04||X||Y 형식입니다.')
    return b

def request_bytes(offset,count,region=None):
    if region is None:
        if (offset,count)!=(0x644,10):raise ProbeError('시리얼 읽기 주소가 올바르지 않습니다.')
        body=b'\x5d\xa2\xae'+struct.pack('<IH',offset,count)
    else:
        if region not in (0xa3,0xd6) or offset not in OFFSETS or count!=64:raise ProbeError('허용된 키 읽기 범위를 벗어났습니다.')
        body=b'\x98\x67\x4c'+bytes([region])+struct.pack('<IH',offset,count)
    return b'||'+struct.pack('<H',len(body)+2)+b'\x75\x06'+body

def parse_reply(raw,offset,count,serial=False):
    # Consume exactly the requested binary payload; never strip zero bytes from it.
    token=b'EE:' if serial else b'SF:'
    pos=raw.find(token)
    if pos<0:
        diagnostic=raw[:180].split(b'\0',1)[0].decode('ascii',errors='replace')
        raise ProbeError('데이터 응답이 없습니다: '+repr(diagnostic))
    prefix=raw[:pos]
    if prefix not in (b'',b'@BDC PS\r\n'):raise ProbeError('알 수 없는 응답 머리글입니다. 원문 로그를 확인하세요.')
    start=pos+len(token)
    if serial:
        address=raw[start:start+8]
        if not re.fullmatch(rb'[0-9a-fA-F]{8}',address) or int(address,16)!=offset:raise ProbeError('시리얼 응답 주소가 요청과 다릅니다.')
        start+=8
    payload=raw[start:start+count]
    if len(payload)!=count or raw[start+count:start+count+2]!=b';\x0c':raise ProbeError('응답 길이 또는 종료 표식이 올바르지 않습니다.')
    if raw[start+count+2:].strip(b'\0'):raise ProbeError('응답 뒤에 해석되지 않은 데이터가 있습니다.')
    return payload

def _wide(event,key):return bytes.fromhex(event.get(key,'')).decode('utf-16le',errors='replace')

def device_from_event(event):
    raw=bytes.fromhex(event.get('ieee1284_hex',''))
    # Drivers may prepend a two-byte IEEE-1284 size. Locate the first field.
    start=raw.find(b'MFG:')
    if start<0:start=raw.find(b'MANUFACTURER:')
    text=(raw[start:] if start>=0 else raw).rstrip(b'\0').decode('ascii',errors='replace')
    fields={k.strip().upper():v.strip() for k,v in re.findall(r'([^:;]+):([^;]*);',text)}
    name=_wide(event,'name_utf16');parent=_wide(event,'parent_utf16')
    model=fields.get('MDL') or fields.get('MODEL') or name
    serial='';source='미확인'
    for k in ('SN','SERN','SERIALNUMBER','SERIAL'):
        if fields.get(k):serial=fields[k];source='USB IEEE-1284 '+k;break
    if not serial and re.match(r'USB\\VID_04B8',parent,re.I):
        last=parent.rsplit('\\',1)[-1]
        if last and '&' not in last:serial=last;source='USB 상위 장치 인스턴스 ID'
    epson='EPSON' in (text+' '+name).upper() or 'VID_04B8' in parent.upper()
    return {'port':event['port'],'name':name,'model':model,'serial':serial,'serial_source':source,
            'epson':epson,'supported':'P7500' in model.upper() or 'P-7500' in model.upper(),
            'path':_wide(event,'path_utf16'),'instance':_wide(event,'instance_utf16'),'parent':parent,
            'ieee1284':text,'identity_error':event.get('identity_error',0),'raw_event':event}

class Bridge:
    def __init__(self,path=None):
        self.path=Path(path or ROOT/'bin/usb_bridge32.exe');self.cancel=threading.Event();self.process=None
    def stop(self):
        self.cancel.set()
        p=self.process
        if p and p.poll() is None:p.terminate()
    def run(self,args,timeout=60):
        if self.cancel.is_set():raise ProbeError('취소되었습니다.')
        if not self.path.is_file():raise ProbeError('bin/usb_bridge32.exe가 없습니다.')
        self.process=subprocess.Popen([str(self.path),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        deadline=time.monotonic()+timeout
        while True:
            try:out,err=self.process.communicate(timeout=.15);break
            except subprocess.TimeoutExpired:
                if self.cancel.is_set() or time.monotonic()>deadline:
                    self.process.kill();out,err=self.process.communicate()
                    ex=ProbeError('USB 작업이 취소되었거나 제한 시간을 초과했습니다.')
                    ex.partial_stdout=out.decode('utf8',errors='replace');raise ex
        try:events=[json.loads(line) for line in out.decode('utf8').splitlines() if line.strip()]
        except (ValueError,UnicodeError) as e:raise ProbeError('보조 프로그램 응답을 해석하지 못했습니다: '+out[:300].decode(errors='replace')) from e
        if not events:raise ProbeError('USB 보조 프로그램 실행 실패: '+err[:500].decode(errors='replace'))
        return {'events':events,'exit_code':self.process.returncode,'stderr':err.decode(errors='replace')}

    def scan(self):
        result=self.run(['scan'],30)
        errors=[e for e in result['events'] if e.get('event')=='error']
        if errors:raise ProbeError(str(errors))
        if result['exit_code']!=0 or not any(e.get('event')=='scan_done' for e in result['events']):
            raise ProbeError('USB 검색이 정상 종료되지 않았습니다: '+str(result['exit_code']))
        return [device_from_event(e) for e in result['events'] if e.get('event')=='device']

def check_driver(path):
    path=Path(path).resolve()
    if not path.is_file():raise ProbeError('서비스 도구 폴더의 EprisDrv.dll을 선택하세요.')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=DRIVER_SHA256:raise ProbeError('분석한 버전의 EprisDrv.dll과 해시가 다릅니다. 호환되지 않는 DLL은 호출하지 않습니다.')
    return path

def evaluate_run(device,events,reference,region):
    report={'version':1,'utc':datetime.now(timezone.utc).isoformat(),'mode':'hardware',
            'device':device,'region':hex(region),'candidate_mapping':'UNCONFIRMED: service offsets are hypotheses, not proven flash addresses',
            'reference_sha256':hashlib.sha256(reference).hexdigest(),'events':events,'locations':[],'errors':[],
            'serial':device.get('serial',''),'serial_source':device.get('serial_source','미확인')}
    opened=[e for e in events if e.get('event')=='opened']
    if len(opened)!=1:report['errors'].append('프린터 열기 확인 응답이 없습니다.')
    else:
        identity=bytes.fromhex(opened[0].get('device_id_hex','')).decode('ascii',errors='replace')
        if not re.search(r'P-?7500',identity,re.I):report['errors'].append('열린 프린터의 모델이 P7500과 다릅니다.')
        report['opened_identity']=identity
    report['errors'] += [str(e) for e in events if e.get('event')=='error']
    if not any(e.get('event')=='done' for e in events):report['errors'].append('읽기 세션이 정상 종료되지 않았습니다.')
    serials=[e for e in events if e.get('event')=='read' and e.get('kind')=='serial']
    try:
        if len(serials)!=1:raise ProbeError('시리얼 읽기 응답 수가 올바르지 않습니다.')
        s=serials[0]
        if s['driver_result']!=0 or bytes.fromhex(s['request_hex'])!=request_bytes(0x644,10):raise ProbeError('시리얼 읽기 요청 또는 전송 결과가 올바르지 않습니다.')
        value=parse_reply(bytes.fromhex(s['response_window_hex']),0x644,10,True)
        if not re.fullmatch(rb'[A-Za-z0-9]{10}',value):raise ProbeError('시리얼 값이 유효한 10자리 영숫자가 아닙니다.')
        sn=value.decode('ascii');report['nvram_serial']=sn
        if report['serial'] and report['serial']!=sn:report['errors'].append('USB 시리얼과 NVRAM 시리얼이 다릅니다.')
        else:report['serial']=sn;report['serial_source']='NVRAM 0x0644 (서비스 도구와 동일한 10바이트 읽기)'
    except (ProbeError,KeyError,ValueError) as e:report['serial_read_error']=str(e)
    for offset in OFFSETS:
        row={'offset':hex(offset),'status':'읽기 실패','matched_reference':False,'stable':False,'valid_p256':False,'samples':[]}
        samples=[e for e in events if e.get('event')=='read' and e.get('kind')=='key' and e.get('offset')==offset]
        try:
            if len(samples)!=2 or sorted(e.get('repeat') for e in samples)!=[0,1]:raise ProbeError('독립적인 읽기 응답 2개가 필요합니다.')
            for e in sorted(samples,key=lambda x:x['repeat']):
                if e['driver_result']!=0:raise ProbeError('USB 통신 실패: '+str(e['driver_result']))
                if e.get('region')!=region or e.get('requested')!=64 or bytes.fromhex(e['request_hex'])!=request_bytes(offset,64,region):raise ProbeError('수집된 요청이 예정된 읽기 요청과 다릅니다.')
                data=parse_reply(bytes.fromhex(e['response_window_hex']),offset,64)
                row['samples'].append({'data_hex':data.hex(),'sha256':hashlib.sha256(data).hexdigest()})
            row['stable']=row['samples'][0]['data_hex']==row['samples'][1]['data_hex']
            data=bytes.fromhex(row['samples'][0]['data_hex']);row['valid_p256']=valid_public_key(data)
            row['matched_reference']=row['stable'] and data==reference
            row['status']='참조 키 일치 (2회 동일)' if row['matched_reference'] else '반복 응답 불일치' if not row['stable'] else '참조 키 불일치'
        except (ProbeError,KeyError,ValueError) as e:row['error']=str(e)
        report['locations'].append(row)
    report['key_reads_match']=all(r['matched_reference'] for r in report['locations'])
    report['identity_confirmed']=bool(report['serial']) and not report['errors']
    report['success']=report['key_reads_match'] and report['identity_confirmed']
    return report

def save_report(report,directory):
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    name=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path=folder/(name+'-'+report.get('mode','hardware')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for row in report.get('locations',[]):
        for i,sample in enumerate(row.get('samples',[])):
            path.with_name(path.stem+'-'+row['offset']+'-'+str(i)+'.bin').write_bytes(bytes.fromhex(sample['data_hex']))
    return path

def demo_report(reference):
    """Entirely synthetic; never instantiate Bridge or label results as hardware."""
    device={'model':'SC-P7500 [데모]','serial':'DEMO000001','serial_source':'합성 데이터','port':0}
    def event(offset,data,repeat=0,serial=False):
        prefix=b'EE:00000644' if serial else b'SF:'
        raw=b'@BDC PS\r\n'+prefix+data+b';\x0c'
        return {'event':'read','kind':'serial' if serial else 'key','region':0 if serial else 0xa3,'offset':offset,
                'requested':len(data),'repeat':repeat,'driver_result':0,
                'request_hex':request_bytes(offset,len(data),None if serial else 0xa3).hex(),
                'response_window_hex':(raw+b'\0'*(4096-len(raw))).hex()}
    events=[{'event':'opened','device_id_hex':b'EPSON SC-P7500'.hex()},event(0x644,b'DEMO000001',serial=True)]
    for off in OFFSETS:
        for repeat in range(2):events.append(event(off,reference,repeat))
    events.append({'event':'done'})
    report=evaluate_run(device,events,reference,0xa3);report['mode']='DEMO_SYNTHETIC';report['success']=False
    report['demo_note']='합성 응답으로 GUI만 시험했습니다. 실기 읽기 성공이 아닙니다.'
    return report
