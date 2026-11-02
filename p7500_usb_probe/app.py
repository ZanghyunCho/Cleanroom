"""Windows 10/11 Tk GUI for the experimental, read-only P7500 USB probe."""
from pathlib import Path
import json,os,queue,threading,time,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from probe_core import Bridge,ProbeError,ROOT,check_driver,reference_key,evaluate_run,save_report,demo_report
from report_view import event_description,hex_dump,report_details

class App:
    def __init__(self,root):
        self.root=root;root.title('SC-P7500 USB 공개키 읽기 시험 v0.3');root.geometry('1050x780');root.minsize(900,700)
        style=ttk.Style()
        if 'vista' in style.theme_names():style.theme_use('vista')
        self.queue=queue.Queue();self.bridge=None;self.busy=False;self.devices=[];self.last_path=None;self.last_report=None;self.closed=False
        self.driver=tk.StringVar();self.ref=tk.StringVar(value=str(ROOT/'reference/epson-p7500-original-public.bin'))
        self.region=tk.StringVar(value='A3');self.printer_mode=tk.StringVar(value='미기록');self.output=tk.StringVar(value=str(Path.home()/'Documents'/'P7500_USB_probe_results'))
        self.status=tk.StringVar(value='USB 검색을 눌러 연결된 프린터를 선택하세요.')
        self.identity=tk.StringVar(value='모델: —     USB ID: —     NVRAM 시리얼: —')
        self.note=tk.StringVar(value='선택 영역 A3/D6의 후보 오프셋을 시험합니다. 실제 플래시 주소와의 대응은 아직 미확인입니다.')
        page=ttk.Frame(root,padding=18);page.pack(fill='both',expand=True);page.columnconfigure(1,weight=1);page.rowconfigure(10,weight=1)
        ttk.Label(page,text='SC-P7500 공개키 읽기 시험',font=('Segoe UI',19,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,7))
        ttk.Label(page,text='USB 프린터 검색 → 시리얼 확인 → 두 후보 위치를 각각 64바이트씩 2회 읽고 참조 키와 비교',wraplength=930).grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,14))
        self.controls=[]
        self.entry_row(page,2,'통신 DLL',self.driver,self.choose_driver)
        self.entry_row(page,3,'참조 공개키',self.ref,lambda:self.choose_file(self.ref,'P-256 공개키 선택'))
        self.entry_row(page,4,'결과 저장 폴더',self.output,self.choose_output)
        ttk.Label(page,text='USB 프린터').grid(row=5,column=0,sticky='w',pady=6)
        self.combo=ttk.Combobox(page,state='readonly');self.combo.grid(row=5,column=1,sticky='ew',padx=10);self.combo.bind('<<ComboboxSelected>>',self.select)
        self.scan_button=ttk.Button(page,text='USB 검색',command=self.scan);self.scan_button.grid(row=5,column=2,sticky='ew');self.controls.append(self.scan_button)
        ttk.Label(page,textvariable=self.identity,wraplength=930).grid(row=6,column=0,columnspan=3,sticky='w',pady=(3,10))
        bars=ttk.Frame(page);bars.grid(row=7,column=0,columnspan=3,sticky='ew',pady=(0,10))
        bar=ttk.Frame(bars);bar.pack(fill='x')
        ttk.Label(bar,text='시험 선택 영역').pack(side='left')
        self.region_combo=ttk.Combobox(bar,textvariable=self.region,values=('A3','D6'),state='readonly',width=5);self.region_combo.pack(side='left',padx=(8,20))
        ttk.Label(bar,text='모드 (기록용)').pack(side='left')
        self.mode_combo=ttk.Combobox(bar,textvariable=self.printer_mode,values=('미기록','일반','Repair'),state='readonly',width=8);self.mode_combo.pack(side='left',padx=(8,16))
        self.read_button=ttk.Button(bar,text='두 위치 읽기 시험',command=self.probe);self.read_button.pack(side='left',padx=(0,8));self.controls.append(self.read_button)
        bounds_button=ttk.Button(bar,text='영역 범위 읽기',command=lambda:self.probe('bounds'));bounds_button.pack(side='left',padx=(0,8));self.controls.append(bounds_button)
        self.cancel_button=ttk.Button(bar,text='중지',command=self.cancel,state='disabled');self.cancel_button.pack(side='right')
        bar2=ttk.Frame(bars);bar2.pack(fill='x',pady=(7,0))
        self.demo_button=ttk.Button(bar2,text='GUI 데모',command=self.demo);self.demo_button.pack(side='left');self.controls.append(self.demo_button)
        load_button=ttk.Button(bar2,text='JSON 열기',command=self.load_report);load_button.pack(side='left',padx=8);self.controls.append(load_button)
        ttk.Button(bar2,text='수신 HEX 보기',command=self.show_details).pack(side='left')
        ttk.Label(bar2,text='모드 항목은 현재 상태를 기록하며 프린터 모드를 변경하지 않습니다.').pack(side='left',padx=12)
        ttk.Label(page,textvariable=self.note,wraplength=930,foreground='#775500').grid(row=8,column=0,columnspan=3,sticky='w',pady=(0,8))
        self.table=ttk.Treeview(page,columns=('offset','result','data','stable','curve','digest'),show='headings',height=4)
        for key,label,width in [('offset','후보 오프셋',100),('result','읽기 결과',270),('data','실제 데이터',95),('stable','2회 동일',75),('curve','P-256 형식',90),('digest','첫 응답 SHA-256',220)]:
            self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=70)
        self.table.grid(row=9,column=0,columnspan=3,sticky='ew',pady=(0,8))
        self.table.bind('<Double-1>',lambda e:self.show_details(selected=True))
        logs=ttk.Frame(page);logs.grid(row=10,column=0,columnspan=3,sticky='nsew');logs.rowconfigure(0,weight=1);logs.columnconfigure(0,weight=1)
        self.log=tk.Text(logs,wrap='word',height=10,state='disabled',font=('Consolas',10));self.log.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(logs,command=self.log.yview);scroll.grid(row=0,column=1,sticky='ns');self.log.configure(yscrollcommand=scroll.set)
        footer=ttk.Frame(page);footer.grid(row=11,column=0,columnspan=3,sticky='ew',pady=(10,0));footer.columnconfigure(0,weight=1)
        ttk.Label(footer,textvariable=self.status,wraplength=740).grid(row=0,column=0,sticky='w')
        ttk.Button(footer,text='결과 폴더 열기',command=self.open_results).grid(row=0,column=1,padx=(10,0))
        self.progress=ttk.Progressbar(page,mode='indeterminate');self.progress.grid(row=12,column=0,columnspan=3,sticky='ew',pady=(8,0))
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll)
        self.add_log('공개키 후보 읽기와 영역 범위 확인 읽기를 지원합니다. 현재 모드는 직접 선택해 기록하세요. 프린터 모드는 자동 변경하지 않습니다.')

    def entry_row(self,page,row,label,var,command):
        ttk.Label(page,text=label).grid(row=row,column=0,sticky='w',pady=5)
        entry=ttk.Entry(page,textvariable=var);entry.grid(row=row,column=1,sticky='ew',padx=10);self.controls.append(entry)
        button=ttk.Button(page,text='찾아보기',command=command);button.grid(row=row,column=2,sticky='ew');self.controls.append(button)
    def choose_file(self,var,title):
        value=filedialog.askopenfilename(title=title)
        if value:var.set(value)
    def choose_driver(self):
        value=filedialog.askopenfilename(title='서비스 도구 폴더의 EprisDrv.dll 선택',filetypes=[('Epson 통신 DLL','EprisDrv.dll'),('DLL','*.dll')])
        if value:self.driver.set(value)
    def choose_output(self):
        value=filedialog.askdirectory(title='결과 저장 폴더')
        if value:self.output.set(value)
    def add_log(self,text):
        self.log.configure(state='normal');self.log.insert('end',time.strftime('%H:%M:%S')+'  '+text+'\n');self.log.see('end');self.log.configure(state='disabled')
    def select(self,event=None):
        i=self.combo.current()
        if i>=0:
            d=self.devices[i];self.identity.set(f"모델: {d['model']}    USB ID: {d.get('usb_id',d.get('serial')) or '미확인'}\nNVRAM 시리얼: 읽기 시험에서 조회")
    def set_busy(self,value):
        self.busy=value
        for c in self.controls:c.configure(state='disabled' if value else 'normal')
        self.combo.configure(state='disabled' if value else 'readonly');self.region_combo.configure(state='disabled' if value else 'readonly');self.mode_combo.configure(state='disabled' if value else 'readonly')
        self.cancel_button.configure(state='normal' if value else 'disabled')
        if value:self.progress.start(12)
        else:self.progress.stop()
    def start(self,job,label):
        if self.busy:return
        self.set_busy(True);self.status.set(label);self.bridge=Bridge()
        def work():
            try:self.queue.put(('result',job()))
            except Exception as e:self.queue.put(('error',str(e)))
            finally:self.queue.put(('idle',None))
        threading.Thread(target=work,daemon=True).start()
    def scan(self):
        if os.name!='nt':messagebox.showerror('Windows 필요','실기 USB 검색은 Windows 10/11에서 실행하세요. GUI 데모는 사용할 수 있습니다.');return
        self.start(lambda:('devices',self.bridge.scan(on_event=lambda e:self.queue.put(('progress',e)))),'USB 프린터를 검색하고 있습니다…')
    def probe(self,profile='keys'):
        i=self.combo.current()
        if i<0:messagebox.showinfo('프린터 선택','USB 검색 후 SC-P7500을 선택하세요.');return
        device=self.devices[i].copy()
        if not device['supported']:messagebox.showerror('대상 모델','이 버전의 키 읽기 시험 대상은 SC-P7500입니다.');return
        if not 0<=device['port']<=9:messagebox.showerror('USB 포트','서비스 DLL이 지원하는 USB 포트 번호(0..9)를 확인하지 못했습니다.');return
        try:driver=check_driver(self.driver.get());ref=reference_key(self.ref.get())
        except Exception as e:messagebox.showerror('파일 확인',str(e));return
        region=int(self.region.get(),16);directory=self.output.get();printer_mode=self.printer_mode.get()
        self.table.delete(*self.table.get_children());self.add_log(f"선택 영역 {region:02X}, 모드 기록 {printer_mode}, 시험 {profile} 읽기를 시작합니다.")
        def job():
            events=[]
            def progress(event):
                events.append(event);self.queue.put(('progress',event))
            try:
                fresh=self.bridge.scan(on_event=progress)
                if not any(d['path']==device['path'] and d['port']==device['port'] for d in fresh):raise ProbeError('선택한 USB 장치가 변경되었습니다. 다시 검색하세요.')
                result=self.bridge.run(['probe',driver,device['port'],f'{region:X}',profile],60,on_event=progress)
                report=evaluate_run(device,events,ref,region,profile,printer_mode);report['bridge_exit_code']=result['exit_code'];report['bridge_stderr']=result['stderr']
                if result['exit_code']!=0:
                    report['errors'].append('USB 보조 프로그램 종료 코드: '+str(result['exit_code']));report['success']=False
            except Exception as e:
                report=evaluate_run(device,events,ref,region,profile,printer_mode);report['errors'].append(str(e));report['success']=False
                report['interruption']={'message':str(e),'operation':getattr(e,'operation','unknown'),'reason':getattr(e,'reason','error')}
                if hasattr(e,'partial_stdout'):report['partial_helper_stdout']=e.partial_stdout
                if hasattr(e,'stderr'):report['bridge_stderr']=e.stderr
            path=save_report(report,directory);return ('report',(report,str(path)))
        self.start(job,'USB 읽기 시험 중… 각 고정 위치를 2회 읽습니다. 보조 프로그램 제한 60초.')
    def demo(self):
        try:ref=reference_key(self.ref.get());report=demo_report(ref);path=save_report(report,self.output.get());self.show_report(report,str(path))
        except Exception as e:messagebox.showerror('데모 실패',str(e))
    def show_report(self,r,path):
        self.last_path=path;self.last_report=r;self.table.delete(*self.table.get_children())
        demo=r['mode'].startswith('DEMO')
        for row in r['locations']:
            self.table.insert('','end',values=(row['offset'],('[데모] ' if demo else '')+row['status'],f"64B × {len(row['samples'])}" if row['samples'] else '0B','예' if row['stable'] else '아니오', '유효' if row['valid_p256'] else '아니오',row['samples'][0]['sha256'] if row['samples'] else '—'))
            if row.get('error'):self.add_log(row['offset']+': '+row['error'])
            if 'nvram_serial_prefix_match' in row:self.add_log(f"{row['offset']} 앞 10바이트와 NVRAM 시리얼 일치: {row['nvram_serial_prefix_match']}")
            for i,sample in enumerate(row['samples']):
                self.add_log(f"{row['offset']} / 회차 {sample.get('repeat',i)+1} / 실제 수신 데이터:\n"+hex_dump(bytes.fromhex(sample['data_hex']),int(row['offset'],16)))
        self.identity.set(f"모델: {r['device']['model']}    USB ID: {r.get('usb_id') or '미확인'}\nNVRAM 시리얼: {r['serial'] or '미확인'}")
        for error in r.get('errors',[]):self.add_log('오류: '+error)
        if r.get('serial_read_error'):self.add_log('NVRAM 시리얼 조회: '+r['serial_read_error'])
        summary=r.get('read_summary',{});count=summary.get('decoded_data_bytes',summary.get('decoded_key_data_bytes',0));self.add_log(f"자료 읽기 반환 {summary.get('data_responses_recorded',summary.get('key_responses_recorded',0))}회 / 추출 데이터 {count}바이트 (반복 포함) / NA {summary.get('na_responses',0)}회 / 모드 기록 {r.get('printer_mode_declared','미기록')}")
        self.add_log(('기존 기록 재분석: ' if r.get('analysis_only') else '결과 저장: ')+path)
        self.status.set('데모 완료 — 합성 데이터이며 실기 결과가 아닙니다.' if demo else '영역 확인 시험을 기록했습니다. 범위 안과 경계 밖의 데이터·NA·무응답을 비교하세요.' if r.get('profile')=='bounds' else '두 후보 위치의 반복 읽기와 참조 키 비교가 일치했습니다.' if r['success'] else '키 읽기 데이터 0바이트 — 연결 단계와 NA 응답을 확인하세요.' if not count else '수신 데이터를 표시했습니다. 공개키 비교 결과를 확인하세요.')

    def load_report(self):
        path=filedialog.askopenfilename(title='이전 하드웨어 JSON 열기',filetypes=[('읽기 보고서','*.json')])
        if not path:return
        try:
            if Path(path).stat().st_size>8*1024*1024:raise ProbeError('JSON 파일은 8MiB 이하여야 합니다.')
            source=json.loads(Path(path).read_text(encoding='utf8'))
            if not isinstance(source.get('device'),dict) or not isinstance(source.get('events'),list):raise ProbeError('읽기 보고서 형식이 아닙니다.')
            r=evaluate_run(source['device'],source['events'],reference_key(self.ref.get()),int(source['region'],16),source.get('profile','keys'),source.get('printer_mode_declared','미기록'))
            r['analysis_only']=True;r['source_utc']=source.get('utc');r['source_errors']=source.get('errors',[])
            if source.get('mode','').startswith('DEMO'):r['mode']='DEMO_IMPORTED';r['success']=False
            if source.get('interruption'):r['interruption']=source['interruption']
            if source.get('interruption') or source.get('bridge_exit_code',0)!=0:r['success']=False
            self.show_report(r,path);self.show_details()
        except Exception as e:messagebox.showerror('JSON 열기 실패',str(e))

    def show_details(self,selected=False):
        if not self.last_report:messagebox.showinfo('수신 내용','읽기 시험 후 또는 JSON 열기로 결과를 선택하세요.');return
        offset=None
        if selected and self.table.selection():offset=self.table.item(self.table.selection()[0],'values')[0]
        content=report_details(self.last_report,offset)
        win=tk.Toplevel(self.root);win.title('실제 수신 바이트 / 요청 / 연결 단계');win.geometry('1010x700')
        frame=ttk.Frame(win,padding=12);frame.pack(fill='both',expand=True);frame.rowconfigure(1,weight=1);frame.columnconfigure(0,weight=1)
        def copy_text():win.clipboard_clear();win.clipboard_append(content)
        ttk.Button(frame,text='전체 내용 복사',command=copy_text).grid(row=0,column=0,sticky='w',pady=(0,8))
        text=tk.Text(frame,wrap='none',font=('Consolas',10));text.grid(row=1,column=0,sticky='nsew');text.insert('1.0',content);text.configure(state='disabled')
        y=ttk.Scrollbar(frame,command=text.yview);y.grid(row=1,column=1,sticky='ns');x=ttk.Scrollbar(frame,orient='horizontal',command=text.xview);x.grid(row=2,column=0,sticky='ew');text.configure(yscrollcommand=y.set,xscrollcommand=x.set)
    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,value=self.queue.get_nowait()
                if kind=='idle':self.set_busy(False)
                elif kind=='error':self.add_log(value);self.status.set(value)
                elif kind=='progress':
                    description=event_description(value);self.add_log(description);self.status.set(description)
                elif kind=='result':
                    what,data=value
                    if what=='devices':
                        self.devices=[d for d in data if d['epson']]
                        self.combo['values']=[f"{d['model']} | USB 포트 {d['port']} | USB ID {d.get('usb_id') or '미확인'}" for d in self.devices]
                        if self.devices:self.combo.current(0);self.select()
                        else:self.combo.set('');self.identity.set('모델: —     USB ID: —     NVRAM 시리얼: —')
                        self.status.set(f'Epson USB 프린터 {len(self.devices)}대 발견')
                        self.add_log(self.status.get())
                        for d in self.devices:
                            if d['identity_error']:self.add_log(f"{d['model']}: USB 장치 ID 조회 오류 {d['identity_error']}")
                    elif what=='report':self.show_report(*data)
        except queue.Empty:pass
        self.root.after(100,self.poll)
    def cancel(self):
        if self.bridge:self.bridge.stop();self.status.set('USB 작업을 중지하고 있습니다…')
    def open_results(self):
        folder=Path(self.output.get());folder.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':os.startfile(str(folder))
        else:messagebox.showinfo('결과 경로',str(folder))
    def close(self):
        self.closed=True
        if self.bridge:self.bridge.stop()
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
