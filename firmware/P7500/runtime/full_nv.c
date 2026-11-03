#include "full_nv.h"
#ifdef P7500_DELIVERY
extern uint32_t original_validate(struct vr_nv_request *,void *,uint32_t,uint8_t *);
extern uint32_t original_write(struct vr_nv_request *,const void *,void *);
static vr_nv_validator validate_original=original_validate;
static vf_raw_write write_original=original_write;
#else
static vr_nv_validator validate_original;
static vf_raw_write write_original;
#endif
static vf_raw_read read_original;
static uint8_t *worker_buffer;
static void cp(void *d,const void *s,uint32_t n){uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;}
static void fill(void *d,uint8_t v,uint32_t n){uint8_t *p=d;while(n--)*p++=v;}
static int eq(const void *a,const void *b,uint32_t n){const uint8_t *p=a,*q=b;while(n--)if(*p++!=*q++)return 0;return 1;}
static uint32_t rd(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void wr(uint8_t *p,uint32_t v){for(uint32_t i=0;i<4;i++){p[i]=(uint8_t)v;v>>=8;}}
static uint32_t crc(const uint8_t *p,uint32_t n){uint32_t c=UINT32_MAX;while(n--){c^=*p++;for(uint32_t k=0;k<8;k++)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}return ~c;}
int vf_extend_profile(uint8_t *table,uint32_t rows){
    if(!table || rows!=157)return VR_ARGUMENT;
    uint32_t c=crc(table,rows*20);if(c==0x959319e3)return VR_OK;
    if(c!=0xc4c88490 || rd(table+153*20)!=VF_ID || rd(table+153*20+4)!=0x10400)return VR_NOT_READY;
    wr(table+153*20+4,0x12400);return VR_OK;
}
int vf_validate_layout(const uint8_t *table,const uint8_t *map,const uint8_t *volumes){
    if(!table || !map || !volumes)return VR_ARGUMENT;
    if(crc(table,157*20)!=0x959319e3 || rd(map+153*12)!=VF_ID || rd(map+153*12+8)!=0x16)return VR_NOT_READY;
    const uint8_t *v=volumes+10*32;uint32_t used=rd(v+4),block=rd(v+24),count=rd(v+28);
    if(used!=0x1a1586 || rd(v+12)!=used || block!=0x10000 || count!=0x4c)return VR_NOT_READY;
    /* Preserve room for the existing maximum-sized record and another object
     * in each half of the native append-log volume. No new raw flash address. */
    if((uint64_t)used+13160+VF_OBJECT>(uint64_t)block*(count/2))return VR_LIMIT;
    return VR_OK;
}
int vf_guard_attach(vr_nv_validator original){if(!original || original==vf_guard)return VR_ARGUMENT;validate_original=original;return VR_OK;}
uint32_t vf_guard(struct vr_nv_request *r,void *buffer,uint32_t op,uint8_t *mode){
    if(!validate_original)return 0x1001;
    uint32_t result=validate_original(r,buffer,op,mode);if(result)return result;
    if(r->id==VF_ID && op!=5 && op!=0x105){
        if(r->first || r->last)return 0x1002;
        if(r->bytes>VF_PREFIX && r->bytes!=VF_OBJECT)return 0x1003;
    }
    return 0;
}
int vf_worker_attach(vf_raw_read read,vf_raw_write write,void *scratch,uint32_t n){
    if(!read || !write || write==vf_worker_write || !scratch || n<VF_OBJECT)return VR_ARGUMENT;
    read_original=read;write_original=write;worker_buffer=scratch;return VR_OK;
}
uint32_t vf_worker_write(struct vr_nv_request *r,const void *data,void *volume){
    if(!write_original)return 0x1001;
    if(r->id!=VF_ID || !worker_buffer)return write_original(r,data,volume);
    if(!read_original || !worker_buffer || !data)return 0x1004;
    if(r->first || r->last)return 0x1002;
    if(r->bytes>VF_PREFIX && r->bytes!=VF_OBJECT)return 0x1003;
    struct vr_nv_request full=*r;full.bytes=VF_OBJECT;
    if(r->bytes==VF_OBJECT){
        /* Worker serialization makes this latest-prefix merge atomic relative
         * to native callers. Do not trust the owner's potentially stale prefix. */
        struct vr_nv_request prefix=*r;prefix.bytes=VF_PREFIX;
        uint32_t result=read_original(&prefix,worker_buffer,volume);if(result)return result;
        cp(worker_buffer+VF_PREFIX,(const uint8_t *)data+VF_PREFIX,VF_OBJECT-VF_PREFIX);
    }else{
        uint32_t result=read_original(&full,worker_buffer,volume);if(result)return result;
        cp(worker_buffer,data,r->bytes);
    }
    return write_original(&full,worker_buffer,volume);
}
static void request(struct vr_nv_request *r){fill(r,0,sizeof(*r));r->id=VF_ID;r->bytes=VF_OBJECT;}
static int nv_read(void *u,uint32_t bank,uint32_t off,void *out,uint32_t n){
    struct vf_nv *s=u;
    if(!s || s->fault || bank>1 || off>VM_RECORD_SIZE || n>VM_RECORD_SIZE-off || (!out && n))return 0;
    struct vr_nv_request r;request(&r);if(s->api.read(&r,s->object)!=0)return 0;
    cp(out,s->object+VF_PREFIX+bank*VM_RECORD_SIZE+off,n);return 1;
}
static int nv_erase(void *u,uint32_t bank){struct vf_nv *s=u;if(!s || s->fault || bank>1)return 0;fill(s->stage[bank],255,VM_RECORD_SIZE);s->loaded[bank]=1;return 1;}
static int nv_write(void *u,uint32_t bank,uint32_t off,const void *data,uint32_t n){
    struct vf_nv *s=u;
    if(!s || s->fault || bank>1 || !s->loaded[bank] || off>VM_RECORD_SIZE || n>VM_RECORD_SIZE-off || (!data && n))return 0;
    const uint8_t *p=data;for(uint32_t i=0;i<n;i++)if((s->stage[bank][off+i]&p[i])!=p[i])return 0;
    cp(s->stage[bank]+off,data,n);return 1;
}
static int nv_sync(void *u,uint32_t bank){
    struct vf_nv *s=u;if(!s || s->fault || bank>1 || !s->loaded[bank])return 0;
    struct vr_nv_request r;request(&r);if(s->api.read(&r,s->object)!=0)return 0;
    cp(s->object+VF_PREFIX+bank*VM_RECORD_SIZE,s->stage[bank],VM_RECORD_SIZE);
    if(s->api.write(&r,s->object)!=0){s->fault=1;return 0;}
    request(&r);
    /* The worker may have merged a newer native prefix. Compare only owner
     * bytes, while still checking both banks to detect unintended changes. */
    if(s->api.read(&r,s->check)!=0 || !eq(s->object+VF_PREFIX,s->check+VF_PREFIX,VF_OBJECT-VF_PREFIX)){s->fault=1;return 0;}
    return 1;
}
int vf_init(struct vf_nv *s,const struct vr_nv_api *api,struct vr_io *io){
    if(!s || !api || !api->read || !api->write || !io)return VR_ARGUMENT;
    struct vr_nv_api saved=*api;fill(s,0,sizeof(*s));s->api=saved;
    io->user=s;io->read=nv_read;io->erase=nv_erase;io->write=nv_write;io->sync=nv_sync;return VR_OK;
}
int vf_install_empty(struct vf_nv *s){
    if(!s || !s->api.read || !s->api.write)return VR_ARGUMENT;
    if(s->fault)return VR_NOT_READY;
    struct vr_nv_request r;request(&r);r.bytes=VF_PREFIX;
    if(s->api.read(&r,s->object)!=0)return VR_IO;
    fill(s->object+VF_PREFIX,255,VF_OBJECT-VF_PREFIX);request(&r);
    if(s->api.write(&r,s->object)!=0){s->fault=1;return VR_IO;}
    if(s->api.read(&r,s->check)!=0 || !eq(s->object+VF_PREFIX,s->check+VF_PREFIX,VF_OBJECT-VF_PREFIX)){s->fault=1;return VR_IO;}
    s->loaded[0]=s->loaded[1]=0;return VR_OK;
}
