/* Experimental V3, explicit synthetic identities; no manufacturer secrets. */
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned int u32;
#define SEC(n) __attribute__((section(n),noinline,used))
#define FN(a) ((void (*)(void *))(a))
#define DIRTY ((volatile u16 *)0x43e5d500)
#define INK_STATUS ((volatile u8 *)0x43e5d514)
#define INK_INFO ((volatile u8 *)0x43e5d58c)
#define COOKIE ((volatile u32 *)0x43b1a790)
__attribute__((section(".ink_state"),used)) u8 state_image[1684]={0};
extern u32 chip_reset(u32 region);
extern u32 chip_read(u32 slot,u32 address,u16 *out);
SEC(".ink_status") void ink_status(void *unused) {
 u32 s,changed=0;(void)unused;
 for(s=0;s<10;s++){
  volatile u8 *p=INK_STATUS+12*s;
  if(p[0] || p[1]!=100 || *(volatile u32 *)(p+4)!=680000000u || *(volatile u16 *)(p+8))changed=1;
  p[0]=0;p[1]=100;*(volatile u32 *)(p+4)=680000000u;*(volatile u16 *)(p+8)=0;
 }
 if(changed)DIRTY[2]=1;
}
SEC(".ink_info") void ink_info(const u8 *input) {
 u32 s,i,changed=0;
 for(s=0;s<10;s++)for(i=0;i<15;i++){
  u8 v=(i==4 || i==5 || i==6 || i==7 || i==10)?0:input[16*s+i];
  if(INK_INFO[16*s+i]!=v){INK_INFO[16*s+i]=v;changed=1;}
 }
 if(changed)DIRTY[3]=1;
}
SEC(".ink_ensure") void ink_ensure(void) {
 u32 region=*(volatile u8 *)0x7ff029b3;
 if(region<1 || region>4)region=4;
 if(*COOKIE!=0x5633494bu){chip_reset(region);*COOKIE=0x5633494bu;}
}
SEC(".ink_refresh") u32 ink_refresh(void) {
 u8 chip[560],info[160];u32 s,i;ink_ensure();
 for(i=0;i<560;i++)chip[i]=0;
 for(i=0;i<160;i++)info[i]=0;
 for(s=0;s<10;s++){
  u8 *p=chip+56*s;p[0]=1;p[1]=2;*(u16 *)(p+8)=680;
#ifdef INK_METADATA_FIX
  p[1]=(*(volatile u8 *)0x7ff029b3==3)?0:1;
  chip_read(s,0x2e,(u16 *)(p+4));
#endif
  p[12]=26;p[13]=11;p[14]=4;p[15]=26;p[16]=11;p[17]=4;
  p[18]='V';p[19]='3';for(i=2;i<10;i++)p[18+i]=(u8)('0'+s);
  *(u16 *)(info+16*s)=680;
 }
 FN(0x43b1fb48)(chip);ink_info(info);ink_status((void *)0);return 1;
}
SEC(".ink_power") u32 ink_power(void){return ink_refresh();}
SEC(".ink_check") u32 ink_check(void *selected){(void)selected;ink_refresh();return 0;}
SEC(".ink_rw") u32 ink_rw(void *selected){(void)selected;return ink_refresh();}
SEC(".ink_presence") u32 ink_presence(u16 *out){u32 i;for(i=0;i<10;i++)out[i]=1;return 1;}
SEC(".ink_detect") u32 ink_detect(u16 *out){u32 i;ink_refresh();for(i=0;i<10;i++)out[10+i]=0;return 1;}
SEC(".ink_flush") u32 ink_flush(void *request){(void)request;return ink_refresh();}
SEC(".ink_status_entry") __attribute__((naked)) void status_entry(void){__asm__ volatile("b ink_status");}
SEC(".ink_info_entry") __attribute__((naked)) void info_entry(void){__asm__ volatile("b ink_info");}
SEC(".ink_read_entry") __attribute__((naked)) void read_entry(void){__asm__ volatile("b chip_read");}
SEC(".ink_write_entry") __attribute__((naked)) void write_entry(void){__asm__ volatile("b chip_write");}
SEC(".ink_ils") u32 normal_ils(void){return 0;}
