"""Run the C provider as ARM code alongside unmodified P7500 functions.

Unicorn hooks supply the candidate bindings and storage transport. This does
not patch a flash image or implement the remaining Epson ASIC/SPI interfaces.
"""
from pathlib import Path
import json
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

CTX=0x46000000
IO=0x46001000
COVERS=0x46001100
CAPS=0x46001200
OUT=0x46002000
STOP=0x42fff000
CB_READ,CB_ERASE,CB_WRITE,CB_SYNC=[0x47000000+i*16 for i in range(4)]
AFTER_ID,AFTER_PRESENCE,AFTER_PRESENCE_VALUE=0x47000100,0x47000110,0x47000120
CAPACITY=7_000_000
NATIVE_MIRROR=0x437c4fb4

class Machine:
    def __init__(self,flash=None,cut=None):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        for a,n in [(0x43000000,0x1000000),(0x45000000,0x100000),
                    (0x46000000,0x100000),(0x47000000,4096),(STOP,4096)]:self.u.mem_map(a,n)
        self.u.mem_write(0x433e0000,(ROOT/'decoded/crom-00070000-0.bin').read_bytes())
        with open(ROOT/'build/virtual_cartridge.arm.elf','rb') as f:
            elf=ELFFile(f)
            for segment in elf.iter_segments():
                if segment['p_type']=='PT_LOAD':self.u.mem_write(segment['p_vaddr'],segment.data())
            self.symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        self.flash=bytearray(flash if flash is not None else b'\xff'*1024)
        self.cut=cut;self.mutations=0;self.identity_bypass=False
        self.counts={'read':0,'erase':0,'write':0,'sync':0,'native_counter_get':0,
                     'native_counter_add':0,'native_cover_set':0,'native_identity_read':0,
                     'native_presence':0,'mocked_os_notifications':0}
        self.u.mem_write(IO,struct.pack('<5I',0,CB_READ,CB_ERASE,CB_WRITE,CB_SYNC))
        self.u.mem_write(COVERS,bytes([1]*6+[0]*6))
        self.u.mem_write(CAPS,struct.pack('<12Q',*([CAPACITY]*12)))
        trap_addresses=[CB_READ,CB_ERASE,CB_WRITE,CB_SYNC,AFTER_ID,AFTER_PRESENCE,AFTER_PRESENCE_VALUE,
                        0x433f57c0,0x433f5b4c,0x433f5934,0x43403f68,0x4340e59c,0x4340e67c,
                        0x434027b0,0x43408d30]
        for address in trap_addresses:
            self.u.hook_add(UC_HOOK_CODE,self.hook,begin=address,end=address)
        code=(ROOT/'decoded/crom-00070000-0.bin').read_bytes()
        self.cover_flags=struct.unpack_from('<I',code,0x43403d8c-0x433e0000)[0]
        if self.call(0x43409858)!=1:raise AssertionError('Native ink config initialization failed')
        for slot in range(12):
            self.u.mem_write(0x437c74e0+slot*4,struct.pack('<I',700))
            self.u.mem_write(NATIVE_MIRROR+slot*192,bytes((i*17+slot)&255 for i in range(192)))
        self.init_status=self.call('vr_init',CTX,IO,COVERS)

    def reg(self,r):return self.u.reg_read(r)
    def ret(self,result=1):
        self.u.reg_write(UC_ARM_REG_R0,result&0xffffffff)
        self.u.reg_write(UC_ARM_REG_PC,self.reg(UC_ARM_REG_LR))
    def read32(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
    def push_frame(self,values):
        sp=self.reg(UC_ARM_REG_SP)-16
        self.u.mem_write(sp,struct.pack('<4I',*values));self.u.reg_write(UC_ARM_REG_SP,sp)
    def mutate(self,index,value,erase=False):
        if self.cut is not None and self.mutations>=self.cut:return False
        if not erase and self.flash[index]&value!=value:raise AssertionError('Illegal simulated NOR write')
        self.flash[index]=value;self.mutations+=1;return True

    def hook(self,u,address,size,_):
        if address in (CB_READ,CB_ERASE,CB_WRITE,CB_SYNC):
            bank=self.reg(UC_ARM_REG_R1)
            if bank>1:raise AssertionError('Storage bank out of bounds')
            if address==CB_READ:
                offset=self.reg(UC_ARM_REG_R2);dst=self.reg(UC_ARM_REG_R3)
                count=self.read32(self.reg(UC_ARM_REG_SP));self.counts['read']+=1
                if offset+count>512:raise AssertionError('Storage read out of bounds')
                u.mem_write(dst,bytes(self.flash[bank*512+offset:bank*512+offset+count]));self.ret()
            elif address==CB_ERASE:
                self.counts['erase']+=1
                for i in range(512):
                    if not self.mutate(bank*512+i,255,True):self.ret(0);return
                self.ret()
            elif address==CB_WRITE:
                offset=self.reg(UC_ARM_REG_R2);src=self.reg(UC_ARM_REG_R3)
                count=self.read32(self.reg(UC_ARM_REG_SP));self.counts['write']+=1
                if offset+count>512:raise AssertionError('Storage write out of bounds')
                for i,v in enumerate(u.mem_read(src,count)):
                    if not self.mutate(bank*512+offset+i,v):self.ret(0);return
                self.ret()
            else:self.counts['sync']+=1;self.ret()
            return

        if address==0x433f57c0:   # native GetArrayData40(group,field,slot)
            group,field,slot=[self.reg(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
            if (group,field)!=(0x2f,0x30) or slot>=12:raise AssertionError('Unsupported native GetArrayData40 binding')
            self.counts['native_counter_get']+=1
            u.reg_write(UC_ARM_REG_R0,CTX);u.reg_write(UC_ARM_REG_R1,slot)
            u.reg_write(UC_ARM_REG_PC,self.symbols['vr_get_usage']);return
        if address==0x433f5b4c:   # native AddArrayData40; 64-bit value passed on stack
            group,field,slot=[self.reg(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
            if (group,field)!=(0x2f,0x30) or slot>=12:raise AssertionError('Unsupported native AddArrayData40 binding')
            lo,hi=struct.unpack('<2I',u.mem_read(self.reg(UC_ARM_REG_SP),8))
            self.counts['native_counter_add']+=1
            for r,v in [(UC_ARM_REG_R0,CTX),(UC_ARM_REG_R1,slot),(UC_ARM_REG_R2,lo),(UC_ARM_REG_R3,hi)]:u.reg_write(r,v)
            u.reg_write(UC_ARM_REG_PC,self.symbols['vr_consume']);return
        if address==0x433f5934:
            raise AssertionError('Unbound native generic counter correction/reset must not be silently accepted')

        if address==0x43403f68:   # native cover setter called by original open/close functions
            cover,value=self.reg(UC_ARM_REG_R0),self.reg(UC_ARM_REG_R1)
            if cover>1 or value>1:raise AssertionError('Unexpected native cover arguments')
            u.mem_write(self.cover_flags+cover,bytes([value]));self.counts['native_cover_set']+=1
            u.reg_write(UC_ARM_REG_R0,CTX);u.reg_write(UC_ARM_REG_R1,cover)
            u.reg_write(UC_ARM_REG_PC,self.symbols['vr_cover_open' if value else 'vr_cover_close']);return
        if address in (0x4340e59c,0x4340e67c):
            self.counts['mocked_os_notifications']+=1;self.ret();return

        if address==0x434027b0:
            if self.identity_bypass:self.identity_bypass=False;return
            slot,field,out=[self.reg(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
            if not (0x71<=field<=0x7a or 0x88<=field<=0x8c):return
            if slot>=12:raise AssertionError('Invalid native identity slot')
            self.counts['native_identity_read']+=1
            self.push_frame([self.reg(UC_ARM_REG_LR),slot,field,out])
            for r,v in [(UC_ARM_REG_R0,CTX),(UC_ARM_REG_R1,slot),(UC_ARM_REG_R2,NATIVE_MIRROR+slot*192),
                        (UC_ARM_REG_R3,192),(UC_ARM_REG_LR,AFTER_ID)]:u.reg_write(r,v)
            u.reg_write(UC_ARM_REG_PC,self.symbols['vr_publish_ink_identity']);return
        if address==AFTER_ID:
            if self.reg(UC_ARM_REG_R0)!=0:raise AssertionError('Identity provider failed')
            sp=self.reg(UC_ARM_REG_SP);lr,slot,field,out=struct.unpack('<4I',u.mem_read(sp,16))
            for r,v in [(UC_ARM_REG_SP,sp+16),(UC_ARM_REG_LR,lr),(UC_ARM_REG_R0,slot),
                        (UC_ARM_REG_R1,field),(UC_ARM_REG_R2,out)]:u.reg_write(r,v)
            self.identity_bypass=True;u.reg_write(UC_ARM_REG_PC,0x434027b0);return

        if address==0x43408d30:  # native GetInkPresencePtr
            slot=self.reg(UC_ARM_REG_R0)
            self.push_frame([self.reg(UC_ARM_REG_LR),slot,0,0])
            u.reg_write(UC_ARM_REG_LR,AFTER_PRESENCE);self.counts['native_presence']+=1;return
        if address==AFTER_PRESENCE:
            sp=self.reg(UC_ARM_REG_SP);slot=self.read32(sp+4);pointer=self.reg(UC_ARM_REG_R0)
            if not 0x43000000<=pointer<0x44000000:raise AssertionError('Native presence pointer invalid')
            u.mem_write(sp+8,struct.pack('<I',pointer))
            u.reg_write(UC_ARM_REG_R0,CTX);u.reg_write(UC_ARM_REG_R1,slot)
            u.reg_write(UC_ARM_REG_LR,AFTER_PRESENCE_VALUE)
            u.reg_write(UC_ARM_REG_PC,self.symbols['vr_presence_value']);return
        if address==AFTER_PRESENCE_VALUE:
            value=self.reg(UC_ARM_REG_R0);sp=self.reg(UC_ARM_REG_SP)
            lr,_,pointer,_=struct.unpack('<4I',u.mem_read(sp,16))
            u.mem_write(pointer,bytes([1 if value==1 else 0]))
            u.reg_write(UC_ARM_REG_SP,sp+16);u.reg_write(UC_ARM_REG_LR,lr)
            u.reg_write(UC_ARM_REG_R0,pointer);u.reg_write(UC_ARM_REG_PC,lr);return

    def call(self,name,*args):
        address=self.symbols[name] if isinstance(name,str) else name
        regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
        sp=0x43fdf000
        for r,v in zip(regs,args[:4]):self.u.reg_write(r,v&0xffffffff)
        if len(args)>4:self.u.mem_write(sp,struct.pack('<'+'I'*len(args[4:]),*args[4:]))
        saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        for i,r in enumerate(saved):self.u.reg_write(r,0x12340000+i)
        self.u.reg_write(UC_ARM_REG_SP,sp);self.u.reg_write(UC_ARM_REG_LR,STOP)
        try:self.u.emu_start(address,STOP,count=5000000,timeout=5000000)
        except UcError as e:raise AssertionError((str(e),name,hex(self.reg(UC_ARM_REG_PC)))) from e
        if self.reg(UC_ARM_REG_PC)!=STOP:raise AssertionError(('ARM call did not finish',name,hex(self.reg(UC_ARM_REG_PC))))
        if self.reg(UC_ARM_REG_SP)!=sp:raise AssertionError(('ARM stack was not restored',name))
        if any(self.reg(r)!=0x12340000+i for i,r in enumerate(saved)):raise AssertionError(('ARM callee-saved ABI violation',name))
        return self.reg(UC_ARM_REG_R0)
    def format(self):
        if self.init_status!=0xffffffff:raise AssertionError(('Unexpected init status',hex(self.init_status)))
        if self.call('vr_format_empty',CTX,CAPS)!=0:raise AssertionError('ARM format failed')
    def info(self,slot):
        if self.call('vr_get_info',CTX,slot,OUT)!=0:raise AssertionError('ARM info failed')
        data=bytes(self.u.mem_read(OUT,72))
        used,capacity,generation,present,virtualized,percent,ml=struct.unpack_from('<QQ5I',data)
        return {'used':used,'capacity':capacity,'generation':generation,'present':present,
                'virtualized':virtualized,'percent':percent,'ml':ml,
                'serial':data[36:47].split(b'\0')[0].decode(),'vendor':data[47:53].split(b'\0')[0].decode()}
    def native_identity(self,slot):
        chars=[]
        for field in list(range(0x71,0x7b))+list(range(0x88,0x8d)):
            self.u.mem_write(OUT,b'\xa5'*4);self.call(0x434027b0,slot,field,OUT)
            value=self.read32(OUT)
            if value>127:raise AssertionError('Native identity field not ASCII')
            chars.append(chr(value))
        return ''.join(chars[:10]),''.join(chars[10:])

def main():
    started=time.monotonic();m=Machine();m.format()
    boundary_cases=0;native_reads=0
    for slot in range(12):
        cover=m.call(0x4340a9f8,slot)
        p=m.call(0x43408d30,slot)
        if m.u.mem_read(p,1)!=b'\x01':raise AssertionError('Virtual presence not visible to native pointer caller')
        serial0,vendor=m.native_identity(slot)
        if vendor!='EPSON':raise AssertionError('Vendor field mismatch')
        # Original ARM consumption wrapper calls the C journal-backed provider.
        m.call(0x433ffe50,slot,CAPACITY*90//100)
        if m.call(0x433fffd8,slot)!=10:raise AssertionError('Native exactly-10 boundary failed')
        m.call(0x4340e5c8,cover)
        if m.call(0x4340e6a0,cover)!=1:raise AssertionError('Native close failed')
        if m.info(slot)['generation']!=0:raise AssertionError('Exactly 10 reset generation')
        m.call(0x433ffe50,slot,1)
        if m.call(0x433fffd8,slot)!=9:raise AssertionError('Native below-10 boundary failed')
        before=m.info(slot)
        m.call(0x4340e6a0,cover)
        if m.info(slot)!=before:raise AssertionError('Duplicate native close changed state')
        m.call(0x4340e5c8,cover);m.call(0x4340e6a0,cover)
        after=m.info(slot)
        if (after['generation'],after['used'],after['percent'])!=(1,0,100):raise AssertionError('ARM generation/reset transaction failed')
        if m.call(0x433fffd8,slot)!=100:raise AssertionError('Native caller did not see reset counter')
        serial1,vendor=m.native_identity(slot)
        if serial1==serial0 or serial1!=after['serial'] or vendor!='EPSON':raise AssertionError('Native serial did not advance')
        boundary_cases+=2;native_reads+=2
    maintenance=m.info(12)
    if (maintenance['present'],maintenance['percent'],maintenance['used'])!=(1,100,0):raise AssertionError('ARM maintenance profile failed')
    expected=[m.info(slot) for slot in range(13)]
    reboot=Machine(bytes(m.flash))
    if reboot.init_status!=0:raise AssertionError('ARM reboot restore failed')
    for slot in range(13):
        if reboot.info(slot)!=expected[slot]:raise AssertionError('ARM persistent state/serial changed on reboot')
        if slot<12 and reboot.native_identity(slot)[0]!=expected[slot]['serial']:raise AssertionError('Native serial restore mismatch')
    # Independently exercise the byte-programming failure path on the ARM build.
    recovery_cases=0
    seed=Machine();seed.format();seed.call(0x433ffe50,0,CAPACITY*95//100);baseline=bytes(seed.flash)
    for cut in (0,1,511,512,539,540,1019,1020,1021,1023,1024):
        probe=Machine(baseline);probe.call(0x4340e5c8,1);probe.cut=cut;probe.mutations=0
        probe.call(0x4340e6a0,1)
        restored=Machine(bytes(probe.flash))
        if restored.init_status!=0:raise AssertionError('ARM torn-write recovery lost both records')
        card=restored.info(0)
        if (card['generation'],card['used']) not in ((0,CAPACITY*95//100),(1,0)):
            raise AssertionError('ARM torn-write recovery mixed generation and usage')
        recovery_cases+=1
    report={
        'scope':'Compiled ARM C runtime plus original ARM consumption, percentage, cover, mirror and presence functions',
        'native_boundary_cases_passed':boundary_cases,'native_serial_generation_cases_passed':native_reads//2,
        'native_slot_presence_cases_passed':12,'restored_profiles_passed':13,'arm_torn_write_cases_passed':recovery_cases,
        'maintenance_logical_profile_passed':True,'native_calls':m.counts,
        'elapsed_seconds':round(time.monotonic()-started,3),
        'bindings':'Unicorn hooks; no flash-image patch addresses allocated',
        'storage':'Simulated independent erase/program banks, not printer NVRAM',
        'hardware_asic_spi_authentication_tested':False,'os_notifications':'mocked',
        'generic_native_counter_corrections_bound':False,
    }
    (ROOT/'analysis/virtual-runtime-arm-results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
