typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define SECTION(n) __attribute__((section(n),noinline,used))
#define CALL1(a,t) ((t (*)(void *))(a))
#define MT_STATUS ((volatile u8 *)0x43e5d62c)
#define DIRTY ((volatile u16 *)0x43e5d500)
#define MAX_FREE 688000000u

/* Retain slot and class checks, but accept every known regional T-code table. */
SECTION(".p_region") u32 any_region(u8 *p) {
 u32 slot=*(u32 *)p;u16 code=0xffff;u32 region,k;

 if(slot>=10)return 0;
 ((u32 (*)(u32,u32,void *))0x43b2c0ec)(slot,0x25,&code);
 if(code==0xffff){*(u32 *)(p+8)=0;*(u32 *)(p+12)=0;p[6]=0;return 0;}
 if(p[4]==1){
  for(region=0;region<4;region++)for(k=0;k<3;k++)if(((const u16 *)0x43c927d2)[region*30+k*10+slot]==code){
   p[6]=(u8)k;*(u32 *)(p+8)=k==0?100:(k==1?340:680);*(u32 *)(p+12)=k==0?130:(k==1?390:770);return 1;
  }
 }else if(p[4]==0 && code==6980){p[6]=2;*(u32 *)(p+8)=200;*(u32 *)(p+12)=770;return 1;}
 return 0;
}

/* Publish normal/full virtual maintenance state. No physical ink status changes. */
SECTION(".p_mt_status") void mt_status(const u8 *ignored) {
 u32 s;u32 changed=0;(void)ignored;
 for(s=0;s<2;s++){
  volatile u8 *p=MT_STATUS+12*s;
  if(p[0]!=0 || p[1]!=100 || *(volatile u32 *)(p+4)!=MAX_FREE || *(volatile u16 *)(p+8)!=0)changed=1;
  p[0]=0;p[1]=100;*(volatile u32 *)(p+4)=MAX_FREE;*(volatile u16 *)(p+8)=0;
 }
 if(changed)DIRTY[5]=1;
}

/* Called in place of maintenance-only power-on; retain original metadata setters. */
SECTION(".p_mt_power") u32 mt_power(u32 slot) {
 u8 chip[112],info[32];u32 i;
 if(slot>=2)return 0;
 CALL1(0x43b1e860,void)(chip);CALL1(0x43b1ea3c,void)(info);
 for(i=0;i<56;i++)chip[slot*56+i]=0;
 chip[slot*56+1]=2; /* native initialization's supported maintenance chip type */
 for(i=0;i<16;i++)info[slot*16+i]=0;
 CALL1(0x43b20140,void)(chip);CALL1(0x43b204fc,void)(info);
 mt_status((void *)0);return 1;
}
SECTION(".p_mt_check") u32 mt_check(void *selected) {
 (void)selected;mt_power(0);mt_power(1);return 0;
}
SECTION(".p_mt_rw") u32 mt_rw(u32 slot) { return mt_power(slot); }
SECTION(".p_mt_check2") u32 mt_check2(u32 slot) { return mt_power(slot)?0:1; }
SECTION(".p_mt_write0") u32 mt_write0(u32 slot) { (void)slot;return 0; }
SECTION(".p_mt_write1") u32 mt_write1(u32 slot) { (void)slot;return 0; }

SECTION(".p_mt_status_entry") __attribute__((naked)) void mt_status_entry(void) { __asm__ volatile("b mt_status"); }
