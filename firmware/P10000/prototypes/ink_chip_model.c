/* Default context is emulator workspace. Production integration overrides its address explicitly. */
typedef unsigned short u16;
typedef unsigned int u32;
#define SEC(n) __attribute__((section(n),noinline,used))
#ifndef CHIP_STATE_ADDRESS
#define CHIP_STATE_ADDRESS 0x43080000
#endif
#define STATE ((volatile u16 *)CHIP_STATE_ADDRESS)
#define WORDS 84u
#define SLOTS 10u
#ifdef CHIP_PRODUCTION
extern void ink_ensure(void);
#define ENSURE() ink_ensure()
#else
#define ENSURE() ((void)0)
#endif
SEC(".chip_read") u32 chip_read(u32 slot,u32 address,u16 *out) {
 if(slot>=SLOTS || address>=WORDS)return 1;
 ENSURE();
 *out=STATE[slot*WORDS+address];return 0;
}
SEC(".chip_write") u32 chip_write(u32 slot,u32 address,u32 value) {
 if(slot>=SLOTS || address>=WORDS || value>65535)return 1;
 ENSURE();
 STATE[slot*WORDS+address]=(u16)value;return 0;
}
SEC(".chip_reset") u32 chip_reset(u32 region) {
 u32 slot,i;const u16 *codes;
 if(region<1 || region>4)return 1;
 codes=(const u16 *)(0x43c927d2+60*(region-1));
 for(slot=0;slot<SLOTS;slot++){
  for(i=0;i<WORDS;i++)STATE[slot*WORDS+i]=0;
  STATE[slot*WORDS+0x2e]=codes[20+slot];
  /* Element 0x24: 3400 / 5 = 680 in the original capacity parser. */
  STATE[slot*WORDS+0x2d]=3400;
 }
 return 0;
}
