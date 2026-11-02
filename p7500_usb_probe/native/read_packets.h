#ifndef P7500_READ_PACKETS_H
#define P7500_READ_PACKETS_H
#include <stdint.h>
#include <string.h>
/* The public native helper has no arbitrary-packet or storage-write entry. */
static unsigned make_fixed_read(unsigned char req[16],int serial,unsigned region,unsigned offset,unsigned count){
 if(serial){if(offset!=0x644||count!=10)return 0;}
 else {
  int key=offset==0x7010||offset==0x6d000;
  int boundary=(region==0xa3&&(offset==0||offset==0x644||offset==0xffc0||offset==0x10000))||
               (region==0xd6&&(offset==0||offset==0xfc0||offset==0x1000));
  if((region!=0xa3&&region!=0xd6)||(!key&&!boundary&&!(offset%64==0&&offset<(region==0xa3?0x10000:0x1000)))||count!=64)return 0;
 }
 const unsigned char prefix[]={0x7c,0x7c,12,0,0x75,0x06,0x98,0x67,0x4c,0};
 memset(req,0,16);memcpy(req,prefix,sizeof(prefix));
 unsigned n=16,start=10;
 if(serial){req[2]=11;req[6]=0x5d;req[7]=0xa2;req[8]=0xae;n=15;start=9;}
 else req[9]=(unsigned char)region;
 for(unsigned i=0;i<4;i++)req[start+i]=(unsigned char)(offset>>(8*i));
 req[start+4]=(unsigned char)count;req[start+5]=(unsigned char)(count>>8);return n;
}
#endif
