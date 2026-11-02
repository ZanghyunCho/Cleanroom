import copy,json,sys,tempfile,unittest,subprocess,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from probe_core import *

class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=reference_key(ROOT/'reference/epson-p7500-original-public.bin')
    def test_reference_is_valid_p256(self):
        self.assertTrue(valid_public_key(self.key));self.assertFalse(valid_public_key(b'\0'*64));self.assertFalse(valid_public_key(b'\xff'*64))
    def test_binary_payload_including_zero(self):
        data=bytes(range(64));raw=b'@BDC PS\r\nSF:'+data+b';\x0c'+b'\0'*10
        self.assertEqual(parse_reply(raw,0x7010,64),data)
    def test_reject_error_short_ascii_or_missing_terminator(self):
        for raw in (b'@BDC PS\r\n98:NA;\x0c',b'SF:'+b'x'*63+b';\x0c',b'SF:'+b'01'*64+b';\x0c',b'SF:'+b'x'*64,b'garbageSF:'+b'x'*64+b';\x0c',b'SF:'+b'x'*64+b';\x0cJUNK'):
            with self.subTest(raw=raw[:20]),self.assertRaises(ProbeError):parse_reply(raw,0x7010,64)
    def test_serial_address_echo(self):
        self.assertEqual(parse_reply(b'EE:00000644ABC1234567;\x0c',0x644,10,True),b'ABC1234567')
        with self.assertRaises(ProbeError):parse_reply(b'EE:00000700ABC1234567;\x0c',0x644,10,True)
    def test_only_allow_fixed_reads(self):
        for args in ((0,64,0xa3),(0x7010,65,0xa3),(0x7010,64,0xff),(0,10,None)):
            with self.assertRaises(ProbeError):request_bytes(*args)
    def hardware_fixture(self):
        r=demo_report(self.key);return r['device'],copy.deepcopy(r['events'])
    def test_all_reads_match_and_serial_confirmed(self):
        d,e=self.hardware_fixture();r=evaluate_run(d,e,self.key,0xa3)
        self.assertTrue(r['success']);self.assertEqual(r['serial'],'DEMO000001')
    def test_demo_never_claims_hardware_success(self):
        r=demo_report(self.key);self.assertFalse(r['success']);self.assertEqual(r['mode'],'DEMO_SYNTHETIC')
    def test_driver_failure_cannot_pass_with_matching_data(self):
        d,e=self.hardware_fixture();e[2]['driver_result']=-20
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_repeated_read_difference_fails(self):
        d,e=self.hardware_fixture();b=bytearray.fromhex(e[3]['response_window_hex']);b[b.index(b'SF:')+3]^=1;e[3]['response_window_hex']=b.hex()
        r=evaluate_run(d,e,self.key,0xa3);self.assertFalse(r['success']);self.assertFalse(r['locations'][0]['stable'])
    def test_wrong_request_or_region_does_not_pass(self):
        for key,value in (('region',0xd6),('request_hex','7c7c')):
            d,e=self.hardware_fixture();e[2][key]=value
            self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_missing_read_or_done_does_not_pass(self):
        for index in (2,-1):
            d,e=self.hardware_fixture();del e[index]
            self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_duplicate_repeat_fails(self):
        d,e=self.hardware_fixture();e[3]['repeat']=0
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_usb_id_is_independent_from_nvram_serial(self):
        d,e=self.hardware_fixture();d['serial']='DIFFERENT1'
        r=evaluate_run(d,e,self.key,0xa3)
        self.assertTrue(r['success']);self.assertEqual(r['usb_id'],'DIFFERENT1')
        self.assertEqual(r['serial'],'DEMO000001');self.assertEqual(r['errors'],[])
    def test_usb_id_does_not_substitute_for_failed_nvram_serial(self):
        d,e=self.hardware_fixture();e[1]['driver_result']=-20
        r=evaluate_run(d,e,self.key,0xa3)
        self.assertEqual(r['serial'],'');self.assertTrue(r['usb_id']);self.assertFalse(r['identity_confirmed'])
    def test_zero_response_does_not_pass(self):
        d,e=self.hardware_fixture();e[2]['response_window_hex']='00'*4096
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_wrong_opened_model_fails(self):
        d,e=self.hardware_fixture();e[0]['device_id_hex']=b'EPSON OTHER'.hex()
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_identity_and_usb_generated_instance_not_serial(self):
        ev={'port':0,'ieee1284_hex':b'\x00\x50MFG:EPSON;MDL:SC-P7500;SN:ABC1234567;'.hex()}
        d=device_from_event(ev);self.assertEqual(d['usb_id'],'ABC1234567');self.assertTrue(d['supported'])
        ev={'port':0,'parent_utf16':'USB\\VID_04B8&PID_0001\\6&12345&0&1'.encode('utf-16le').hex()}
        self.assertEqual(device_from_event(ev)['usb_id'],'')
    def test_reference_65_byte_form(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'key.bin';p.write_bytes(b'\4'+self.key);self.assertEqual(reference_key(p),self.key)
    def test_report_keeps_raw_and_separate_payloads(self):
        with tempfile.TemporaryDirectory() as td:
            r=demo_report(self.key);p=save_report(r,td)
            self.assertEqual(json.loads(p.read_text())['events'],r['events'])
            bins=list(Path(td).glob('*.bin'));self.assertEqual(len(bins),4)
            self.assertTrue(all(b.read_bytes()==self.key for b in bins))
    def test_empty_scan_and_incomplete_scan_are_distinguished(self):
        bridge=Bridge()
        bridge.run=lambda *a,**k:{'events':[{'event':'scan_done'}],'exit_code':0,'stderr':''}
        self.assertEqual(bridge.scan(),[])
        for result in ({'events':[],'exit_code':0,'stderr':''},
                       {'events':[{'event':'scan_done'}],'exit_code':1,'stderr':''}):
            bridge.run=lambda *a,_result=result,**k:_result
            with self.assertRaises(ProbeError):bridge.scan()
    def test_partial_valid_payload_is_preserved(self):
        d,e=self.hardware_fixture();del e[3]
        r=evaluate_run(d,e,self.key,0xa3)
        self.assertFalse(r['success']);self.assertEqual(len(r['locations'][0]['samples']),1)
        with tempfile.TemporaryDirectory() as td:
            save_report(r,td);self.assertEqual(len(list(Path(td).glob('*.bin'))),3)
    def ff_na_fixture(self,region=0xa3):
        d,e=self.hardware_fixture()
        for item in e:
            if item.get('kind')!='key':continue
            item['region']=region;item['request_hex']=request_bytes(item['offset'],64,region).hex()
            raw=(b'@BDC PS\r\nSF:'+b'\xff'*64+b';\x0c') if region==0xa3 and item['offset']==0x7010 else b'||:98:NA;\x0c'
            item['response_window_hex']=(raw+b'\0'*(4096-len(raw))).hex()
        return d,e
    def test_ff_read_and_na_are_distinct_results(self):
        d,e=self.ff_na_fixture();r=evaluate_run(d,e,self.key,0xa3)
        self.assertEqual(r['errors'],[]);self.assertTrue(r['identity_confirmed']);self.assertFalse(r['success'])
        self.assertIn('FF 64바이트',r['locations'][0]['status']);self.assertTrue(r['locations'][0]['stable'])
        self.assertFalse(r['locations'][0]['valid_p256']);self.assertIn('NA 응답',r['locations'][1]['status'])
        self.assertEqual(r['read_summary']['decoded_key_data_bytes'],128);self.assertEqual(r['read_summary']['na_responses'],2)
    def test_all_na_has_no_payload_but_does_have_responses(self):
        d,e=self.ff_na_fixture(0xd6);r=evaluate_run(d,e,self.key,0xd6)
        self.assertEqual(r['read_summary']['key_responses_recorded'],4)
        self.assertEqual(r['read_summary']['na_responses'],4);self.assertEqual(r['read_summary']['decoded_key_data_bytes'],0)
    def test_report_details_shows_actual_bytes_and_na(self):
        from report_view import report_details
        d,e=self.ff_na_fixture();r=evaluate_run(d,e,self.key,0xa3);text=report_details(r)
        self.assertIn('FF FF FF FF FF FF FF FF',text);self.assertIn('128바이트',text)
        self.assertIn('98:NA',text);self.assertIn('요청 HEX:',text)
    def test_report_without_reads_does_not_invent_hex_data(self):
        from report_view import report_details
        d,_=self.hardware_fixture();r=evaluate_run(d,[],self.key,0xa3);text=report_details(r)
        self.assertIn('추출된 데이터가 없습니다',text);self.assertIn('예정된 읽기 요청',text)
        self.assertEqual(r['read_summary']['decoded_key_data_bytes'],0)
    def test_timeout_keeps_streamed_records(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'fake_helper.py'
            p.write_text('import json,time\nprint(json.dumps({"event":"stage","stage":"load_library_start"}),flush=True)\ntime.sleep(10)\n')
            bridge=Bridge(p,command_prefix=[sys.executable,'-u']);seen=[]
            with self.assertRaises(BridgeError) as caught:
                bridge.run(['probe'],timeout=.8,on_event=lambda e:seen.append((e,bridge.process.poll())))
            ex=caught.exception
            self.assertEqual(ex.reason,'timeout');self.assertIn('load_library_start',ex.partial_stdout)
            self.assertTrue(any(e.get('stage')=='load_library_start' and state is None for e,state in seen))
            self.assertTrue(any(e.get('stage')=='load_library_start' for e in ex.events))
            self.assertIsNotNone(bridge.process.poll())
    def test_stream_preserves_unknown_native_output(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'fake_helper.py'
            p.write_text('print("native diagnostic",flush=True)\nprint(\'{"event":"done"}\',flush=True)\n')
            result=Bridge(p,command_prefix=[sys.executable,'-u']).run(['probe'])
            self.assertEqual(result['exit_code'],0)
            self.assertTrue(any(e.get('event')=='native_output' for e in result['events']))
            self.assertTrue(any(e.get('event')=='done' for e in result['events']))
    @unittest.skipUnless(shutil.which('cc'),'native compiler unavailable')
    def test_native_builder_matches_reference_protocol(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'fixture';subprocess.run(['cc',str(ROOT/'tests/packet_fixture.c'),'-o',str(exe)],check=True)
            for serial,region,off,count in ((0,0xa3,0x7010,64),(0,0xa3,0x6d000,64),(0,0xd6,0x7010,64),(1,0,0x644,10)):
                r=subprocess.check_output([str(exe),str(serial),f'{region:x}',f'{off:x}',str(count)]).decode()
                self.assertEqual(bytes.fromhex(r),request_bytes(off,count,None if serial else region))
            self.assertNotEqual(subprocess.run([str(exe),'0','a3','0','64'],capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
