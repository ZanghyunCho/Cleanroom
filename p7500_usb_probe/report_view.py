"""Plain-text, binary-safe inspection of live and imported USB probe reports."""
from probe_core import na_response

STAGES={
 'helper_started':'보조 프로그램 시작', 'scan_started':'USB 장치 검색 시작',
 'device_id_start':'USB 장치 ID 조회 시작', 'device_id_done':'USB 장치 ID 조회 완료',
 'load_library_start':'EprisDrv.dll 로딩 시작', 'load_library_done':'EprisDrv.dll 로딩 완료',
 'resolve_exports_start':'DLL 함수 연결 시작', 'resolve_exports_done':'DLL 함수 연결 완료',
 'constructor_start':'통신 객체 생성 시작', 'constructor_done':'통신 객체 생성 완료',
 'usb_open_start':'Epson USB 열기 시작', 'usb_open_done':'Epson USB 열기 반환',
 'identity_start':'연결된 프린터 모델 조회 시작', 'identity_done':'연결된 프린터 모델 조회 완료',
 'close_start':'USB 통신 객체 정리 시작', 'close_done':'USB 통신 객체 정리 완료',
}

def hex_dump(data,base=0):
    if not data:return '(바이트 없음)'
    rows=[]
    for i in range(0,len(data),16):
        part=data[i:i+16]
        ascii_text=''.join(chr(b) if 32<=b<127 else '.' for b in part)
        rows.append(f'{base+i:08X}  '+part.hex(' ').upper().ljust(47)+'  '+ascii_text)
    return '\n'.join(rows)

def event_description(e):
    op=e.get('operation','')
    kind='영역 자료' if e.get('kind')=='key' and e.get('profile')=='bounds' else e.get('kind')
    if e.get('event')=='bridge_launch':return f"[{op}] 보조 프로그램 실행 (PID {e.get('pid','?')})"
    if e.get('event')=='stage':return f"[{op}] "+STAGES.get(e.get('stage'),str(e.get('stage')))
    if e.get('event')=='read_start':
        target='NVRAM' if e.get('kind')=='serial' else f"영역 {e.get('region',0):02X}"
        return f"읽기 호출 전: {kind} / {target} / 오프셋 {e.get('offset',0):#x} / {e.get('requested')}바이트 / 회차 {e.get('repeat',0)+1}"
    if e.get('event')=='read':
        raw=bytes.fromhex(e.get('response_window_hex',''))
        detail='NA (데이터 없음)' if na_response(raw) else '응답 캡처 있음' if raw.strip(b'\0') else '캡처 창이 모두 00'
        return f"읽기 반환: {kind} / {e.get('offset',0):#x} / 코드 {e.get('driver_result')} / {detail}"
    if e.get('event')=='opened':return f"USB 열기 확인: 포트 {e.get('port','?')}"
    if e.get('event')=='error':return f"오류: {e.get('message')} ({e.get('code')})"
    if e.get('event')=='native_output':return '보조 프로그램 출력: '+str(e.get('text',''))[:240]
    return str(e.get('event','알 수 없는 기록'))

def report_details(r,offset=None):
    nvram_serial=r.get('nvram_serial') or (r.get('serial','') if r.get('serial_source','').startswith('NVRAM') else '')
    lines=[f"실행 유형: {r.get('mode','미확인')}",
           f"모델: {r.get('device',{}).get('model','미확인')}",
           f"USB ID: {r.get('usb_id',r.get('device',{}).get('serial','')) or '미확인'}",
           f"NVRAM 시리얼: {nvram_serial or '미확인'}",
           'USB ID와 NVRAM 시리얼은 서로 다른 식별자이며 동일성 비교를 하지 않습니다.',
           f"선택 영역: {r.get('region','미확인')}",
           f"읽기 시험: {r.get('profile','keys')} / 모드 기록: {r.get('printer_mode_declared','미기록')} (사용자 선택, 자동 감지 아님)",
           '주소는 서비스 공간의 후보 오프셋입니다. 물리 플래시 위치는 미확인입니다.', '']
    if r.get('analysis_only'):lines.append('기존 JSON을 재분석한 결과입니다. 이 분석에서 USB를 새로 읽지는 않았습니다.')
    total=sum(len(bytes.fromhex(s['data_hex'])) for row in r.get('locations',[]) for s in row.get('samples',[]))
    lines.append(f'검증된 데이터 페이로드 합계: {total}바이트 (반복 읽기 포함)')
    if not total:lines.append('선택한 위치에서 추출된 데이터가 없습니다. 아래에 요청·오류 기록을 표시합니다.')
    if r.get('serial_data_hex'):lines.extend(['NVRAM 시리얼 원시 10바이트:',hex_dump(bytes.fromhex(r['serial_data_hex']))])
    for row in r.get('locations',[]):
        if offset and row['offset']!=offset:continue
        lines.extend(['',f"=== {r.get('region')} / {row['offset']} : {row.get('status')} ==="])
        if row.get('error'):lines.append('진단: '+row['error'])
        if 'nvram_serial_prefix_match' in row:lines.append('앞 10바이트와 일반 NVRAM 시리얼 일치: '+str(row['nvram_serial_prefix_match']))
        if not row.get('samples'):lines.append('추출된 64바이트 데이터 없음')
        for i,s in enumerate(row.get('samples',[])):
            data=bytes.fromhex(s['data_hex'])
            lines.extend([f"회차 {s.get('repeat',i)+1}: {len(data)}바이트 / SHA-256 {s['sha256']}",
                          '수신 데이터 HEX (표시 주소는 서비스 후보 오프셋):',hex_dump(data,int(row['offset'],16))])
    lines.extend(['','=== 기록된 호출·반환 / 원시 응답 ==='])
    found=False
    for e in r.get('events',[]):
        if e.get('event') not in ('read_start','read'):continue
        if offset and e.get('kind')=='key' and e.get('offset')!=int(offset,16):continue
        found=True;lines.extend(['',event_description(e)])
        if e.get('request_hex'):lines.append('요청 HEX: '+e['request_hex'].upper())
        if e.get('event')=='read':
            raw=bytes.fromhex(e.get('response_window_hex',''))
            significant=raw.rstrip(b'\0')
            preview=significant[:512] if significant else raw[:64]
            lines.append(f'원시 캡처 창 {len(raw)}바이트. 표시에서 후행 00을 생략하며 실제 수신 길이를 뜻하지 않습니다.')
            lines.extend([hex_dump(preview),'응답 표시: '+repr(preview)])
    if not found:lines.append('읽기 호출·반환 기록 없음. 실제 전송 여부를 확인할 수 없습니다.')
    lines.extend(['','=== 예정된 읽기 요청 (실제 전송 기록과 구별) ==='])
    for item in r.get('planned_reads',[]):
        if offset and item.get('kind')=='key' and item.get('offset')!=offset:continue
        lines.append(f"{item['kind']} {item['offset']} / {item['requested']}바이트 / {item['request_hex'].upper()}")
    lines.extend(['','=== 연결 단계 ==='])
    steps=[event_description(e) for e in r.get('events',[]) if e.get('event') not in ('read','read_start')]
    lines.extend(steps or ['이 로그에는 연결 단계 기록이 없습니다.'])
    if r.get('interruption'):lines.append('중단 정보: '+str(r['interruption']))
    lines.extend('오류: '+str(e) for e in r.get('errors',[]))
    return '\n'.join(lines)+'\n'
