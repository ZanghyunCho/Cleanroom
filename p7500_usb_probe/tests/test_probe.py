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
    def test_usb_serial_mismatch_fails(self):
        d,e=self.hardware_fixture();d['serial']='DIFFERENT1'
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_zero_response_does_not_pass(self):
        d,e=self.hardware_fixture();e[2]['response_window_hex']='00'*4096
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_wrong_opened_model_fails(self):
        d,e=self.hardware_fixture();e[0]['device_id_hex']=b'EPSON OTHER'.hex()
        self.assertFalse(evaluate_run(d,e,self.key,0xa3)['success'])
    def test_identity_and_usb_generated_instance_not_serial(self):
        ev={'port':0,'ieee1284_hex':b'\x00\x50MFG:EPSON;MDL:SC-P7500;SN:ABC1234567;'.hex()}
        d=device_from_event(ev);self.assertEqual(d['serial'],'ABC1234567');self.assertTrue(d['supported'])
        ev={'port':0,'parent_utf16':'USB\\VID_04B8&PID_0001\\6&12345&0&1'.encode('utf-16le').hex()}
        self.assertEqual(device_from_event(ev)['serial'],'')
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
    @unittest.skipUnless(shutil.which('cc'),'native compiler unavailable')
    def test_native_builder_matches_reference_protocol(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'fixture';subprocess.run(['cc',str(ROOT/'tests/packet_fixture.c'),'-o',str(exe)],check=True)
            for serial,region,off,count in ((0,0xa3,0x7010,64),(0,0xa3,0x6d000,64),(0,0xd6,0x7010,64),(1,0,0x644,10)):
                r=subprocess.check_output([str(exe),str(serial),f'{region:x}',f'{off:x}',str(count)]).decode()
                self.assertEqual(bytes.fromhex(r),request_bytes(off,count,None if serial else region))
            self.assertNotEqual(subprocess.run([str(exe),'0','a3','0','64'],capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
