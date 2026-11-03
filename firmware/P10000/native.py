"""Original P10000 ARM code runners. Hardware/OS substitutions must be explicit."""
from pathlib import Path
import struct,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'P7500/tools'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
STOP=0x45000000
class Machine:
 def call(self,pc,*args,count=200_000_000):
  u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x13);u.reg_write(UC_ARM_REG_SP,0x421ff000);u.reg_write(UC_ARM_REG_LR,STOP)
  for reg,val in zip(REGS,args):u.reg_write(reg,val)
  u.emu_start(pc,STOP,count=count)
  if u.reg_read(UC_ARM_REG_PC)!=STOP:raise RuntimeError('Instruction budget exceeded at '+hex(u.reg_read(UC_ARM_REG_PC)))
  return u.reg_read(UC_ARM_REG_R0)
 def return_value(self,n):self.u.reg_write(UC_ARM_REG_R0,n);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def read32(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def write32(self,a,v):self.u.mem_write(a,struct.pack('<I',v))
 def base(self):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
  for a,n in [(0x42000000,0x200000),(0x43000000,0x200000),(STOP,0x1000)]:self.u.mem_map(a,n)
class Updater(Machine):
 AUTH=0x380009d8;GATE=0x38009ffc;SUM=0x3800a798;LOG=0x38000da4
 def __init__(self,rcx):
  self.base();self.raw=rcx;self.u.mem_map(0x38000000,0x200000);self.u.mem_write(0x38000000,rcx[0x54f:0xee33]);self.logs=[]
  self.u.hook_add(UC_HOOK_CODE,self.log,begin=self.LOG,end=self.LOG)
  self.call(0x3800a8b0)
 def log(self,u,a,n,x):self.logs.append(a);self.return_value(0)
class Boot(Machine):
 AUTH=0x3680;GATE=0x1878;SELF_CHECK=0x1988;LOG=0x12cc
 def __init__(self,image):
  self.base();self.image=bytes(image);self.u.mem_map(0,0x2000000);self.u.mem_write(0,self.image)
  self.u.mem_map(0x44e00000,0x10000);self.u.mem_map(0x43b00000,0x300000);self.logs=[]
  self.u.hook_add(UC_HOOK_CODE,self.log,begin=self.LOG,end=self.LOG)
  self.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:self.return_value(0),begin=0x4d28,end=0x4d28)
  self.call(0x1208)
 def log(self,u,a,n,x):self.logs.append({'error':u.reg_read(UC_ARM_REG_R0),'line':u.reg_read(UC_ARM_REG_R1)});self.return_value(0)
