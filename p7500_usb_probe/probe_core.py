"""Read-only P7500 USB experiment: binary parsing, identity and evidence reports."""
from __future__ import annotations
import hashlib,json,re,struct,subprocess,threading,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DRIVER_SHA256='42f775bdd44425227a36750d6942104db99c9a37dfe82c4ce2d810b7b38eda18'
OFFSETS=(0x7010,0x6d000)
REGION_SIZES={0xa3:0x10000,0xd6:0x1000}
BOUND_OFFSETS={0xa3:(0,0x644,0xffc0,0x10000),0xd6:(0,0xfc0,0x1000)}
P=2**256-2**224+2**192+2**96-1
B=int('5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b',16)

class ProbeError(Exception):pass

class BridgeError(ProbeError):
    """A stopped helper retains every record received before the interruption."""
    def __init__(self,message,events,stdout='',stderr='',operation='',reason=''):
        super().__init__(message)
        self.events=list(events);self.partial_stdout=stdout;self.stderr=stderr
        self.operation=operation;self.reason=reason

def na_response(raw):
    return bool(re.fullmatch(rb'(?:\|\|:|@BDC PS\r\n)?[0-9a-fA-F]{2}:NA;\x0c\x00*',raw))

def valid_public_key(data):
    if len(data)!=64:return False
    x,y=int.from_bytes(data[:32],'big'),int.from_bytes(data[32:],'big')
    return 0<=x<P and 0<=y<P and (y*y-x*x*x+3*x-B)%P==0

def reference_key(path):
    b=Path(path).read_bytes()
    if len(b)==65 and b[0]==4:b=b[1:]
    if not valid_public_key(b):raise ProbeError('참조 파일은 유효한 P-256 공개키여야 합니다. 64바이트 X||Y 또는 65바이트 04||X||Y 형식입니다.')
    return b

def read_offsets(region,profile='keys'):
    if region not in BOUND_OFFSETS or profile not in ('keys','bounds','full'):raise ProbeError('허용되지 않은 읽기 시험입니다.')
    return tuple(range(0,REGION_SIZES[region],64)) if profile=='full' else OFFSETS if profile=='keys' else BOUND_OFFSETS[region]

def request_bytes(offset,count,region=None):
    if region is None:
        if (offset,count)!=(0x644,10):raise ProbeError('시리얼 읽기 주소가 올바르지 않습니다.')
        body=b'\x5d\xa2\xae'+struct.pack('<IH',offset,count)
    else:
        if region not in BOUND_OFFSETS or (offset not in (*OFFSETS,*BOUND_OFFSETS[region]) and not (0<=offset<REGION_SIZES[region] and offset%64==0)) or count!=64:raise ProbeError('허용된 고정 읽기 범위를 벗어났습니다.')
        body=b'\x98\x67\x4c'+bytes([region])+struct.pack('<IH',offset,count)
    return b'||'+struct.pack('<H',len(body)+2)+b'\x75\x06'+body

def parse_reply(raw,offset,count,serial=False):
    # Consume exactly the requested binary payload; never strip zero bytes from it.
    if na_response(raw):raise ProbeError('프린터가 NA를 반환했습니다. 데이터는 없습니다.')
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
    return {'port':event['port'],'name':name,'model':model,'usb_id':serial,'usb_id_source':source,
            'epson':epson,'supported':'P7500' in model.upper() or 'P-7500' in model.upper(),
            'path':_wide(event,'path_utf16'),'instance':_wide(event,'instance_utf16'),'parent':parent,
            'ieee1284':text,'identity_error':event.get('identity_error',0),'raw_event':event}

class Bridge:
    def __init__(self,path=None,command_prefix=None):
        self.path=Path(path or ROOT/'bin/usb_bridge32.exe');self.cancel=threading.Event();self.process=None
        self.command_prefix=list(command_prefix or [])
    def stop(self):
        self.cancel.set()
        p=self.process
        if p and p.poll() is None:p.terminate()
    def run(self,args,timeout=60,on_event=None):
        import queue
        if self.cancel.is_set():raise ProbeError('취소되었습니다.')
        if not self.path.is_file():raise ProbeError('bin/usb_bridge32.exe가 없습니다.')
        operation=str(args[0]) if args else 'unknown'
        self.process=subprocess.Popen([*self.command_prefix,str(self.path),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        proc=self.process;lines=queue.Queue();events=[];stdout=[];stderr=[]
        def emit(event):
            event=dict(event);event.setdefault('operation',operation)
            event.setdefault('received_at_utc',datetime.now(timezone.utc).isoformat())
            events.append(event)
            if on_event:on_event(event)
        emit({'event':'bridge_launch','helper':self.path.name,'pid':proc.pid,'timeout_seconds':timeout})
        def read_stdout():
            try:
                for line in iter(proc.stdout.readline,b''):lines.put(line)
            finally:lines.put(None)
        def read_stderr():
            for block in iter(lambda:proc.stderr.read(4096),b''):stderr.append(block)
        out_thread=threading.Thread(target=read_stdout,daemon=True);err_thread=threading.Thread(target=read_stderr,daemon=True)
        out_thread.start();err_thread.start();finished=False;reason=''
        deadline=time.monotonic()+timeout
        while True:
            if not reason and (self.cancel.is_set() or time.monotonic()>deadline):
                reason='cancelled' if self.cancel.is_set() else 'timeout'
                if proc.poll() is None:proc.kill()
            try:line=lines.get(timeout=.05)
            except queue.Empty:line=b''
            if line is None:finished=True
            elif line:
                stdout.append(line)
                try:
                    event=json.loads(line.decode('utf8'))
                    if not isinstance(event,dict):raise ValueError('not an object')
                    emit(event)
                except (ValueError,UnicodeError):emit({'event':'native_output','text':line.decode('utf8',errors='replace').rstrip()})
            if finished and proc.poll() is not None:break
        proc.wait();out_thread.join();err_thread.join();proc.stdout.close();proc.stderr.close()
        err=b''.join(stderr).decode('utf8',errors='replace')
        if reason:
            message='USB 작업을 중지했습니다.' if reason=='cancelled' else 'USB 작업 제한 시간을 초과했습니다.'
            raise BridgeError(message,events,b''.join(stdout).decode('utf8',errors='replace'),err,operation,reason)
        if not any(e.get('event') not in ('bridge_launch','native_output') for e in events):
            raise BridgeError('USB 보조 프로그램이 진단 기록을 남기지 않았습니다: '+str(proc.returncode),events,
                              b''.join(stdout).decode('utf8',errors='replace'),err,operation,'no_helper_events')
        return {'events':events,'exit_code':proc.returncode,'stderr':err}

    def scan(self,on_event=None):
        result=self.run(['scan'],30,on_event=on_event)
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

def evaluate_run(device,events,reference,region,profile='keys',printer_mode='미기록'):
    offsets=read_offsets(region,profile)
    report={'version':3,'app_version':'0.4','utc':datetime.now(timezone.utc).isoformat(),'mode':'hardware',
            'profile':profile,'printer_mode_declared':printer_mode,'printer_mode_source':'operator declaration, not firmware detection',
            'device':device,'region':hex(region),'candidate_mapping':'UNCONFIRMED: service offsets are hypotheses, not proven flash addresses',
            'reference_sha256':hashlib.sha256(reference).hexdigest(),'events':events,'locations':[],'errors':[],
            'usb_id':device.get('usb_id',device.get('serial','')),
            'usb_id_source':device.get('usb_id_source',device.get('serial_source','미확인')),
            'serial':'','serial_source':'NVRAM 미확인'}
    report['planned_reads']=[{'kind':'serial','offset':'0x644','requested':10,
                             'request_hex':request_bytes(0x644,10).hex()}]
    for offset in offsets:
        for repeat in range(2):
            report['planned_reads'].append({'kind':'key','region':hex(region),'offset':hex(offset),
                                           'requested':64,'repeat':repeat,'request_hex':request_bytes(offset,64,region).hex()})
    opened=[e for e in events if e.get('event')=='opened']
    if len(opened)!=1:report['errors'].append('프린터 열기 확인 응답이 없습니다.')
    else:
        identity=bytes.fromhex(opened[0].get('device_id_hex','')).decode('ascii',errors='replace')
        if not re.search(r'P-?7500',identity,re.I):report['errors'].append('열린 프린터의 모델이 P7500과 다릅니다.')
        report['opened_identity']=identity
        if 'port' in opened[0] and opened[0]['port']!=device.get('port'):report['errors'].append('열린 USB 포트가 선택한 장치의 포트와 다릅니다.')
    report['errors'] += [str(e) for e in events if e.get('event')=='error']
    if not any(e.get('event')=='done' for e in events):report['errors'].append('읽기 세션이 정상 종료되지 않았습니다.')
    serials=[e for e in events if e.get('event')=='read' and e.get('kind')=='serial']
    try:
        if len(serials)!=1:raise ProbeError('시리얼 읽기 응답 수가 올바르지 않습니다.')
        s=serials[0]
        if s['driver_result']!=0 or bytes.fromhex(s['request_hex'])!=request_bytes(0x644,10):raise ProbeError('시리얼 읽기 요청 또는 전송 결과가 올바르지 않습니다.')
        value=parse_reply(bytes.fromhex(s['response_window_hex']),0x644,10,True)
        report['serial_data_hex']=value.hex()
        if not re.fullmatch(rb'[A-Za-z0-9]{10}',value):raise ProbeError('시리얼 값이 유효한 10자리 영숫자가 아닙니다.')
        sn=value.decode('ascii');report['nvram_serial']=sn
        report['serial']=sn;report['serial_source']='NVRAM 0x0644 (10바이트 읽기)'
    except (ProbeError,KeyError,ValueError) as e:report['serial_read_error']=str(e)
    for offset in offsets:
        row={'offset':hex(offset),'status':'데이터 수신 없음','matched_reference':False,'stable':False,
             'valid_p256':False,'samples':[],'response_errors':[],'na_responses':0}
        samples=[e for e in events if e.get('event')=='read' and e.get('kind')=='key' and e.get('offset')==offset]
        row['returned_reads']=len(samples)
        for e in samples:
            try:
                if e['driver_result']!=0:raise ProbeError('USB 통신 실패: '+str(e['driver_result']))
                if e.get('region')!=region or e.get('requested')!=64 or bytes.fromhex(e['request_hex'])!=request_bytes(offset,64,region):raise ProbeError('수집된 요청이 예정된 읽기 요청과 다릅니다.')
                if e.get('profile',profile)!=profile:raise ProbeError('응답이 선택한 읽기 시험과 다릅니다.')
                raw=bytes.fromhex(e['response_window_hex'])
                if na_response(raw):row['na_responses']+=1
                data=parse_reply(raw,offset,64)
                row['samples'].append({'repeat':e.get('repeat'),'data_hex':data.hex(),
                                       'sha256':hashlib.sha256(data).hexdigest(),
                                       'content':'all_ff' if data==b'\xff'*64 else 'all_zero' if data==b'\0'*64 else 'mixed'})
            except (ProbeError,KeyError,ValueError) as error:row['response_errors'].append(str(error))
        repeats=[s.get('repeat') for s in row['samples']]
        complete=len(row['samples'])==2 and set(repeats)=={0,1} and not row['response_errors']
        if row['samples']:
            data=bytes.fromhex(row['samples'][0]['data_hex'])
            row['valid_p256']=all(valid_public_key(bytes.fromhex(s['data_hex'])) for s in row['samples'])
            row['stable']=complete and row['samples'][0]['data_hex']==row['samples'][1]['data_hex']
            row['matched_reference']=row['stable'] and data==reference
            if not complete:row['status']=f"64바이트 {len(row['samples'])}회 수신 / 비교 미완료"
            elif not row['stable']:row['status']='반복 읽기 불일치'
            elif data==b'\xff'*64:row['status']='FF 64바이트 (2회 동일, 키 아님)'
            elif data==b'\0'*64:row['status']='00 64바이트 (2회 동일, 키 아님)'
            elif row['matched_reference']:row['status']='참조 공개키 일치 (2회 동일)'
            elif row['valid_p256']:row['status']='다른 P-256 키 수신 (2회 동일)'
            else:row['status']='64바이트 수신 / 공개키 아님'
        elif row['na_responses']:row['status']='NA 응답 (데이터 없음)'
        if not complete and not row['response_errors']:row['response_errors'].append('독립적인 읽기 응답 2개를 확인하지 못했습니다.')
        if row['response_errors']:row['error']=' / '.join(row['response_errors'])
        if profile=='bounds' and region==0xa3 and offset==0x644 and row['samples'] and report['serial']:
            row['nvram_serial_prefix_match']=all(bytes.fromhex(s['data_hex'])[:10]==report['serial'].encode('ascii') for s in row['samples'])
        report['locations'].append(row)
    report['key_reads_match']=profile=='keys' and all(r['matched_reference'] for r in report['locations'])
    report['identity_confirmed']=bool(report['serial']) and not report['errors']
    report['success']=report['key_reads_match'] and report['identity_confirmed']
    stages=[e for e in events if e.get('event')=='stage']
    key_returns=[e for e in events if e.get('event')=='read' and e.get('kind')=='key']
    report['read_summary']={'key_responses_recorded':len(key_returns),
                          'decoded_key_samples':sum(len(r['samples']) for r in report['locations']),
                          'decoded_key_data_bytes':sum(len(bytes.fromhex(s['data_hex'])) for r in report['locations'] for s in r['samples']),
                          'na_responses':sum(r['na_responses'] for r in report['locations']),
                          'last_stage':stages[-1].get('stage') if stages else None}
    summary=report['read_summary']
    summary.update(data_responses_recorded=len(key_returns),decoded_payload_samples=summary['decoded_key_samples'],
                   decoded_data_bytes=summary['decoded_key_data_bytes'])
    if profile!='keys':
        summary.update(key_responses_recorded=0,decoded_key_samples=0,decoded_key_data_bytes=0)
        report['bounds_basis']='Host service backup sizes: A3 64KiB and D6 4KiB. Device-enforced limits are being tested, not assumed.'
    if profile=='full':
        size=REGION_SIZES[region]
        passes=[]
        for repeat in range(2):
            blocks={int(row['offset'],16):bytes.fromhex(sample['data_hex']) for row in report['locations'] for sample in row['samples'] if sample['repeat']==repeat}
            missing=[off for off in offsets if off not in blocks]
            data=b''.join(blocks[off] for off in offsets) if not missing else None
            passes.append({'repeat':repeat,'complete':not missing,'bytes_read':len(blocks)*64,'missing_offsets':[hex(off) for off in missing],
                           'sha256':hashlib.sha256(data).hexdigest() if data is not None else None})
        report['full_read']={'size':size,'passes':passes,'complete':all(p['complete'] for p in passes),
                             'identical':all(p['complete'] for p in passes) and passes[0]['sha256']==passes[1]['sha256'],
                             'unstable_offsets':[row['offset'] for row in report['locations'] if len(row['samples'])==2 and not row['stable']]}
    return report

def save_report(report,directory):
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    name=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path=folder/(name+'-'+report.get('mode','hardware')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    if report.get('profile')=='full':
        for repeat in range(2):
            blocks=sorted((int(row['offset'],16),bytes.fromhex(sample['data_hex'])) for row in report['locations'] for sample in row['samples'] if sample['repeat']==repeat)
            # Sparse JSON retains exact offsets; incomplete reads must never become padded full images.
            if len(blocks)*64==report['full_read']['size']:
                path.with_name(path.stem+f'-pass{repeat+1}.bin').write_bytes(b''.join(data for _,data in blocks))
        return path
    for row in report.get('locations',[]):
        for i,sample in enumerate(row.get('samples',[])):
            path.with_name(path.stem+'-'+row['offset']+'-'+str(sample.get('repeat',i))+'.bin').write_bytes(bytes.fromhex(sample['data_hex']))
    return path

def demo_report(reference):
    """Entirely synthetic; never instantiate Bridge or label results as hardware."""
    device={'model':'SC-P7500 [데모]','serial':'USB-DEMO-ID','serial_source':'합성 USB ID','port':0}
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
