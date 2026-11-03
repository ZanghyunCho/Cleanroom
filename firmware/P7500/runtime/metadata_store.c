#include "metadata_store.h"
#define CORE 32u
#define IMAGES (CORE+2*VR_RECORD_SIZE)
#define LENGTHS (IMAGES+VM_PROFILES*VM_IMAGE_BYTES)
#define VALID (LENGTHS+VM_PROFILES*2)
#define CONTROL (VALID+4)
#define MARK UINT32_C(0x54494d43)
_Static_assert(VALID+4<=VM_RECORD_SIZE,"Metadata layout exceeds record");
static void cp(void *d,const void *s,uint32_t n){uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;}
static void fill(void *d,uint8_t v,uint32_t n){uint8_t *p=d;while(n--)*p++=v;}
static int eq(const void *a,const void *b,uint32_t n){const uint8_t *p=a,*q=b;while(n--)if(*p++!=*q++)return 0;return 1;}
static uint32_t rd(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void wr(uint8_t *p,uint32_t v){for(uint32_t i=0;i<4;i++){p[i]=(uint8_t)v;v>>=8;}}
static uint64_t seq(const uint8_t *p){return rd(p+12)|((uint64_t)rd(p+16)<<32);}
static uint32_t crc_step(uint32_t c,const uint8_t *p,uint32_t n){while(n--){c^=*p++;for(uint32_t k=0;k<8;k++)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}return c;}
static uint32_t crc(const uint8_t *p){return ~crc_step(crc_step(UINT32_MAX,p,24),p+32,VM_RECORD_SIZE-32);}
static int blank(const uint8_t *p){for(uint32_t i=0;i<VM_RECORD_SIZE;i++)if(p[i]!=255)return 0;return 1;}
static int valid(const uint8_t *p,int committed){
    if(!eq(p,"P7VMETA1",8) || rd(p+24)!=crc(p))return VR_CORRUPT;
    if(rd(p+8)!=1)return VR_VERSION;
    if(!seq(p) || rd(p+20)!=VM_RECORD_SIZE || (rd(p+VALID)&~0x1fffu))return VR_CORRUPT;
    if(committed && rd(p+28)!=MARK)return VR_CORRUPT;
    for(uint32_t s=0;s<VM_PROFILES;s++){
        uint32_t n=p[LENGTHS+s*2]|((uint32_t)p[LENGTHS+s*2+1]<<8);
        if(n>VM_IMAGE_BYTES || ((rd(p+VALID)&(1u<<s)) && !n))return VR_CORRUPT;
    }
    return VR_OK;
}
uint32_t vm_store_bytes(void){return sizeof(struct vm_store);}
int vm_init(struct vm_store *s,const struct vr_io *io){
    if(!s || !io || !io->read || !io->erase || !io->write || !io->sync)return VR_ARGUMENT;
    struct vr_io saved=*io;fill(s,0,sizeof(*s));s->io=saved;
    if(saved.read(saved.user,0,0,s->work,VM_RECORD_SIZE)!=1 ||
       saved.read(saved.user,1,0,s->check,VM_RECORD_SIZE)!=1)return VR_IO;
    int a=valid(s->work,1),b=valid(s->check,1);
    if(a==VR_VERSION || b==VR_VERSION)return VR_VERSION;
    if(a && b){s->empty=blank(s->work)&&blank(s->check);return s->empty?VR_EMPTY:VR_CORRUPT;}
    s->active=a?1:0;
    if(!a && !b){
        if(seq(s->work)==seq(s->check) && !eq(s->work,s->check,VM_RECORD_SIZE))return VR_CORRUPT;
        if(seq(s->check)>seq(s->work))s->active=1;
    }
    cp(s->current,s->active?s->check:s->work,VM_RECORD_SIZE);s->ready=1;return VR_OK;
}
static int usable(struct vm_store *s){return s && s->ready && !s->fault;}
static int commit(struct vm_store *s){
    uint64_t next=s->ready?seq(s->current)+1:1;if(!next)return VR_LIMIT;
    uint32_t bank=s->ready?(s->active^1u):0;
    cp(s->work,"P7VMETA1",8);wr(s->work+8,1);wr(s->work+12,(uint32_t)next);
    wr(s->work+16,(uint32_t)(next>>32));wr(s->work+20,VM_RECORD_SIZE);
    wr(s->work+28,UINT32_MAX);wr(s->work+24,crc(s->work));
    struct vr_io *io=&s->io;
    if(io->erase(io->user,bank)!=1 || io->write(io->user,bank,0,s->work,28)!=1 ||
       io->write(io->user,bank,32,s->work+32,VM_RECORD_SIZE-32)!=1 || io->sync(io->user,bank)!=1 ||
       io->read(io->user,bank,0,s->check,VM_RECORD_SIZE)!=1 || valid(s->check,0) ||
       !eq(s->work,s->check,VM_RECORD_SIZE))return VR_IO;
    wr(s->work+28,MARK);
    if(io->write(io->user,bank,28,s->work+28,4)!=1 || io->sync(io->user,bank)!=1 ||
       io->read(io->user,bank,0,s->check,VM_RECORD_SIZE)!=1 || valid(s->check,1) ||
       !eq(s->work,s->check,VM_RECORD_SIZE)){s->fault=1;return VR_IO;}
    cp(s->current,s->work,VM_RECORD_SIZE);s->active=bank;s->ready=1;s->empty=0;return VR_OK;
}
int vm_format_empty(struct vm_store *s){
    if(!s)return VR_ARGUMENT;
    if(s->busy)return VR_BUSY;
    if(s->ready || !s->empty || s->fault)return VR_NOT_READY;
    fill(s->work,255,VM_RECORD_SIZE);fill(s->work+LENGTHS,0,VM_PROFILES*4+4);
    s->busy=1;int r=commit(s);s->busy=0;return r;
}
int vm_get(struct vm_store *s,uint32_t slot,void *out,uint32_t n){
    if(!out || slot>=VM_PROFILES || !n || n>VM_IMAGE_BYTES)return VR_ARGUMENT;
    if(!usable(s))return VR_NOT_READY;
    if(!(rd(s->current+VALID)&(1u<<slot)))return VR_EMPTY;
    uint32_t length=s->current[LENGTHS+slot*2]|((uint32_t)s->current[LENGTHS+slot*2+1]<<8);
    if(n!=length)return VR_ARGUMENT;
    cp(out,s->current+IMAGES+slot*VM_IMAGE_BYTES,n);return VR_OK;
}
int vm_put(struct vm_store *s,uint32_t slot,const void *data,uint32_t n){
    if(!data || slot>=VM_PROFILES || !n || n>VM_IMAGE_BYTES)return VR_ARGUMENT;
    if(!usable(s))return VR_NOT_READY;
    if(s->busy)return VR_BUSY;
    const uint8_t *old=s->current+IMAGES+slot*VM_IMAGE_BYTES;
    uint32_t length=s->current[LENGTHS+slot*2]|((uint32_t)s->current[LENGTHS+slot*2+1]<<8);
    if((rd(s->current+VALID)&(1u<<slot)) && length==n && eq(old,data,n))return VR_OK;
    cp(s->work,s->current,VM_RECORD_SIZE);fill(s->work+IMAGES+slot*VM_IMAGE_BYTES,255,VM_IMAGE_BYTES);
    cp(s->work+IMAGES+slot*VM_IMAGE_BYTES,data,n);s->work[LENGTHS+slot*2]=(uint8_t)n;
    s->work[LENGTHS+slot*2+1]=0;wr(s->work+VALID,rd(s->work+VALID)|(1u<<slot));
    s->busy=1;int r=commit(s);s->busy=0;return r;
}
static int core_read(void *u,uint32_t bank,uint32_t off,void *out,uint32_t n){
    struct vm_store *s=u;
    if(!usable(s) || bank>1 || off>VR_RECORD_SIZE || n>VR_RECORD_SIZE-off || (!out && n))return 0;
    cp(out,s->current+CORE+bank*VR_RECORD_SIZE+off,n);return 1;
}
static int core_erase(void *u,uint32_t bank){
    struct vm_store *s=u;if(!usable(s) || s->busy || bank>1)return 0;
    fill(s->stage[bank],255,VR_RECORD_SIZE);s->loaded[bank]=1;return 1;
}
static int core_write(void *u,uint32_t bank,uint32_t off,const void *data,uint32_t n){
    struct vm_store *s=u;
    if(!usable(s) || s->busy || bank>1 || !s->loaded[bank] || off>VR_RECORD_SIZE || n>VR_RECORD_SIZE-off || (!data && n))return 0;
    const uint8_t *p=data;for(uint32_t i=0;i<n;i++)if((s->stage[bank][off+i]&p[i])!=p[i])return 0;
    cp(s->stage[bank]+off,data,n);return 1;
}
static int core_sync(void *u,uint32_t bank){
    struct vm_store *s=u;if(!usable(s) || s->busy || bank>1 || !s->loaded[bank])return 0;
    cp(s->work,s->current,VM_RECORD_SIZE);cp(s->work+CORE+bank*VR_RECORD_SIZE,s->stage[bank],VR_RECORD_SIZE);
    s->busy=1;int r=commit(s);s->busy=0;return r==VR_OK;
}
int vm_core_io(struct vm_store *s,struct vr_io *io){
    if(!io)return VR_ARGUMENT;
    if(!usable(s))return VR_NOT_READY;
    io->user=s;io->read=core_read;io->erase=core_erase;io->write=core_write;io->sync=core_sync;return VR_OK;
}
int vm_control_get(struct vm_store *s,uint32_t slot,uint16_t *out){
    if(!out || slot>=VM_PROFILES)return VR_ARGUMENT;
    if(!usable(s))return VR_NOT_READY;
    *out=(uint16_t)(s->current[CONTROL+slot*2]|((uint16_t)s->current[CONTROL+slot*2+1]<<8));return VR_OK;
}
int vm_control_set(struct vm_store *s,uint32_t slot,uint16_t value){
    if(slot>=VM_PROFILES)return VR_ARGUMENT;
    if(!usable(s))return VR_NOT_READY;
    if(s->busy)return VR_BUSY;
    uint16_t old;vm_control_get(s,slot,&old);if(old==value)return VR_OK;
    cp(s->work,s->current,VM_RECORD_SIZE);s->work[CONTROL+slot*2]=(uint8_t)value;
    s->work[CONTROL+slot*2+1]=(uint8_t)(value>>8);s->busy=1;int r=commit(s);s->busy=0;return r;
}
