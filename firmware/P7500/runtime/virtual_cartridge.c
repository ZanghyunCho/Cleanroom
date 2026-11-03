#include "virtual_cartridge.h"

static void copy(void *dst,const void *src,uint32_t n) {
    uint8_t *d=dst;const uint8_t *s=src;while(n--)*d++=*s++;
}
static void fill(void *dst,uint8_t v,uint32_t n) {uint8_t *d=dst;while(n--)*d++=v;}
static int equal(const void *a,const void *b,uint32_t n) {
    const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;
}
static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint64_t get64(const uint8_t *p) {return get32(p)|((uint64_t)get32(p+4)<<32);}
static void put32(uint8_t *p,uint32_t v) {for(uint32_t i=0;i<4;i++){p[i]=(uint8_t)v;v>>=8;}}
static void put64(uint8_t *p,uint64_t v) {put32(p,(uint32_t)v);put32(p+4,(uint32_t)(v>>32));}
static uint64_t divide(uint64_t a,uint64_t b) {
    uint64_t q=0,r=0;
    for(uint32_t bit=64;bit;){--bit;r=(r<<1)|((a>>bit)&1);if(r>=b){r-=b;q|=UINT64_C(1)<<bit;}}
    return q;
}
static uint32_t crc_step(uint32_t crc,const uint8_t *p,uint32_t n) {
    while(n--){crc^=*p++;for(uint32_t k=0;k<8;k++)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1)));}
    return crc;
}
static uint32_t crc_record(const uint8_t *p) {
    uint32_t crc=crc_step(0xffffffffu,p,24);
    return ~crc_step(crc,p+32,VR_RECORD_SIZE-32);
}
static const uint8_t magic[8]={'P','7','V','R','S','T','0','1'};
#define COMMITTED 0x54494d43u

static int blank(const uint8_t *p) {
    for(uint32_t i=0;i<VR_RECORD_SIZE;i++)if(p[i]!=255)return 0;
    return 1;
}
static int validate(const uint8_t *p,int require_commit) {
    if(!equal(p,magic,8))return VR_CORRUPT;
    if(get32(p+24)!=crc_record(p))return VR_CORRUPT;
    if(get32(p+8)!=1)return VR_VERSION;
    if(get32(p+20)!=VR_SLOTS*20 || !get64(p+12))return VR_CORRUPT;
    if(require_commit && get32(p+28)!=COMMITTED)return VR_CORRUPT;
    for(uint32_t s=0;s<VR_SLOTS;s++) {
        const uint8_t *q=p+32+s*20;
        if(get64(q)>VR_MAX_USAGE || get64(q+12)<10000 || get64(q+12)>VR_MAX_USAGE)return VR_CORRUPT;
    }
    return VR_OK;
}
static void decode(struct vr_context *c,const uint8_t *p) {
    c->sequence=get64(p+12);
    for(uint32_t s=0;s<VR_SLOTS;s++) {
        const uint8_t *q=p+32+s*20;
        c->slots[s].used=get64(q);c->slots[s].generation=get32(q+8);c->slots[s].capacity=get64(q+12);
    }
}
static void encode(uint8_t *p,const struct vr_slot *slots,uint64_t sequence) {
    fill(p,255,VR_RECORD_SIZE);copy(p,magic,8);put32(p+8,1);put64(p+12,sequence);put32(p+20,VR_SLOTS*20);
    for(uint32_t s=0;s<VR_SLOTS;s++) {
        uint8_t *q=p+32+s*20;
        put64(q,slots[s].used);put32(q+8,slots[s].generation);put64(q+12,slots[s].capacity);
    }
    put32(p+24,crc_record(p));
}
static int usable(const struct vr_context *c) {return c && c->ready && !c->fault;}
static int guard(struct vr_context *c) {
    if(!usable(c))return VR_NOT_READY;
    if(c->busy)return VR_BUSY;
    return VR_OK;
}

int vr_init(struct vr_context *c,const struct vr_io *io,const uint8_t covers[VR_SLOTS]) {
    if(!c || !io || !covers || !io->read || !io->write || !io->erase || !io->sync)return VR_ARGUMENT;
    /* Preserve the arguments even if the caller passes c->io/c->covers. */
    struct vr_io backend=*io;uint8_t map[VR_SLOTS];copy(map,covers,VR_SLOTS);
    for(uint32_t i=0;i<VR_SLOTS;i++)if(map[i]>1)return VR_ARGUMENT;
    fill(c,0,sizeof(*c));c->io=backend;copy(c->covers,map,VR_SLOTS);
    uint8_t a[VR_RECORD_SIZE],b[VR_RECORD_SIZE];
    if(backend.read(backend.user,0,0,a,sizeof(a))!=1 || backend.read(backend.user,1,0,b,sizeof(b))!=1)return VR_IO;
    int va=validate(a,1),vb=validate(b,1);
    if(va==VR_VERSION || vb==VR_VERSION)return VR_VERSION;
    if(va!=VR_OK && vb!=VR_OK) {
        c->empty=blank(a)&&blank(b);return c->empty?VR_EMPTY:VR_CORRUPT;
    }
    uint32_t bank=0;
    if(va!=VR_OK)bank=1;
    else if(vb==VR_OK) {
        uint64_t sa=get64(a+12),sb=get64(b+12);
        if(sa==sb && !equal(a,b,VR_RECORD_SIZE))return VR_CORRUPT;
        if(sb>sa)bank=1;
    }
    decode(c,bank?b:a);c->active=bank;c->ready=1;return VR_OK;
}

/* Publish only after durable commit. A failure during/after the marker write
 * latches a fault because the durable outcome can be ambiguous; re-init must
 * reconcile it before another transaction can overwrite the recovered state. */
static int commit(struct vr_context *c,const struct vr_slot *slots) {
    if(c->sequence==UINT64_MAX)return VR_LIMIT;
    uint8_t record[VR_RECORD_SIZE],check[VR_RECORD_SIZE];
    uint64_t next=c->sequence+1;uint32_t bank=c->ready?(c->active^1u):0u;
    encode(record,slots,next);
    struct vr_io *io=&c->io;
    if(io->erase(io->user,bank)!=1 || io->write(io->user,bank,0,record,28)!=1 ||
       io->write(io->user,bank,32,record+32,VR_RECORD_SIZE-32)!=1 || io->sync(io->user,bank)!=1)return VR_IO;
    if(io->read(io->user,bank,0,check,VR_RECORD_SIZE)!=1 || validate(check,0)!=VR_OK ||
       !equal(record,check,VR_RECORD_SIZE))return VR_IO;
    put32(record+28,COMMITTED);
    if(io->write(io->user,bank,28,record+28,4)!=1 || io->sync(io->user,bank)!=1 ||
       io->read(io->user,bank,0,check,VR_RECORD_SIZE)!=1 || validate(check,1)!=VR_OK ||
       !equal(record,check,VR_RECORD_SIZE)) {c->fault=1;return VR_IO;}
    copy(c->slots,slots,sizeof(c->slots));c->sequence=next;c->active=bank;c->ready=1;c->empty=0;
    return VR_OK;
}
int vr_format_empty(struct vr_context *c,const uint64_t capacity[VR_SLOTS]) {
    if(!c || !capacity)return VR_ARGUMENT;
    if(c->busy)return VR_BUSY;
    if(c->ready || !c->empty || c->fault)return VR_NOT_READY;
    struct vr_slot slots[VR_SLOTS];fill(slots,0,sizeof(slots));
    for(uint32_t s=0;s<VR_SLOTS;s++) {
        if(capacity[s]<10000 || capacity[s]>VR_MAX_USAGE)return VR_ARGUMENT;
        slots[s].capacity=capacity[s];
    }
    c->busy=1;int result=commit(c,slots);c->busy=0;return result;
}
int vr_consume(struct vr_context *c,uint32_t slot,uint64_t amount) {
    int result=guard(c);if(result)return result;
    if(slot>=VR_SLOTS)return VR_ARGUMENT;
    if(!amount)return VR_OK;
    struct vr_slot slots[VR_SLOTS];copy(slots,c->slots,sizeof(slots));
    if(amount>VR_MAX_USAGE-slots[slot].used)slots[slot].used=VR_MAX_USAGE;
    else slots[slot].used+=amount;
    c->busy=1;result=commit(c,slots);c->busy=0;return result;
}
int vr_reconcile_usage(struct vr_context *c,uint32_t slot,uint64_t reported) {
    int result=guard(c);if(result)return result;
    if(slot>=VR_SLOTS || reported>VR_MAX_USAGE)return VR_ARGUMENT;
    if(reported<=c->slots[slot].used)return VR_OK;
    return vr_consume(c,slot,reported-c->slots[slot].used);
}
int vr_cover_open(struct vr_context *c,uint32_t cover) {
    int result=guard(c);if(result)return result;
    if(cover>1)return VR_ARGUMENT;
    uint32_t bit=1u<<cover,old=c->opened;c->opened|=bit;return (old&bit)?0:1;
}
uint32_t vr_get_percent(const struct vr_context *c,uint32_t slot) {
    if(!usable(c) || slot>=VR_SLOTS)return 0;
    uint64_t step=divide(c->slots[slot].capacity,100);
    uint64_t percent_used=divide(c->slots[slot].used+step-1,step);
    return percent_used>=99?1u:100u-(uint32_t)percent_used;
}
uint64_t vr_get_usage(const struct vr_context *c,uint32_t slot) {
    return usable(c)&&slot<VR_SLOTS?c->slots[slot].used:UINT64_MAX;
}
uint32_t vr_get_generation(const struct vr_context *c,uint32_t slot) {
    return usable(c)&&slot<VR_SLOTS?c->slots[slot].generation:UINT32_MAX;
}
int vr_cover_close(struct vr_context *c,uint32_t cover) {
    int result=guard(c);if(result)return result;
    if(cover>1)return VR_ARGUMENT;
    uint32_t bit=1u<<cover,mask=0;
    if(!(c->opened&bit))return 0;
    c->opened&=~bit;
    struct vr_slot slots[VR_SLOTS];copy(slots,c->slots,sizeof(slots));
    for(uint32_t s=0;s<VR_SLOTS;s++)if(c->covers[s]==cover && vr_get_percent(c,s)<10) {
        if(slots[s].generation==UINT32_MAX)return VR_LIMIT;
        slots[s].generation++;slots[s].used=0;mask|=1u<<s;
    }
    if(!mask)return 0;
    c->busy=1;result=commit(c,slots);c->busy=0;return result?result:(int)mask;
}
static void serial(char out[11],uint32_t slot,uint32_t generation,int maintenance) {
    static const char hex[]="0123456789ABCDEF";
    out[0]=maintenance?'M':'V';out[1]=hex[slot&15];
    for(uint32_t i=0;i<8;i++)out[2+i]=hex[(generation>>(28-i*4))&15];
    out[10]=0;
}
int vr_presence_value(struct vr_context *c,uint32_t slot) {
    if(slot>VR_MAINTENANCE)return VR_ARGUMENT;
    return usable(c)?1:VR_NOT_READY;
}
int vr_get_info(struct vr_context *c,uint32_t slot,struct vr_card_info *out) {
    if(!out || slot>VR_MAINTENANCE)return VR_ARGUMENT;
    if(!usable(c))return VR_NOT_READY;
    static const char models[VR_SLOTS][8]={"T44M7","T44M3","T44MA","T44M1","T44M6","T44M9",
                                         "T44M5","T44M4","T44MB","T44M8","T44MD","T44M2"};
    fill(out,0,sizeof(*out));out->present=1;out->virtualized=1;
    copy(out->manufacturer,"EPSON",6);
    if(slot==VR_MAINTENANCE) {
        out->remaining_percent=100;copy(out->model,"P7500-MAINT",12);
        serial(out->serial,slot,0,1);return VR_OK;
    }
    out->used=c->slots[slot].used;out->capacity=c->slots[slot].capacity;
    out->generation=c->slots[slot].generation;out->remaining_percent=vr_get_percent(c,slot);out->nominal_ml=700;
    copy(out->model,models[slot],8);serial(out->serial,slot,out->generation,0);return VR_OK;
}
int vr_exchange(struct vr_context *c,uint32_t operation,uint32_t slot,const void *input,
                uint32_t input_bytes,void *output,uint32_t output_bytes) {
    int result=guard(c);if(result)return result;
    if(slot>VR_MAINTENANCE)return VR_ARGUMENT;
    struct vr_card_info info;
    if(operation==VR_ADD_USAGE) {
        if(slot==VR_MAINTENANCE || input_bytes!=8 || !input || output_bytes)return VR_ARGUMENT;
        return vr_consume(c,slot,get64(input));
    }
    if(input_bytes || input)return VR_ARGUMENT;
    if(!output)return VR_ARGUMENT;
    if(operation==VR_INFO) {
        if(output_bytes!=sizeof(info))return VR_ARGUMENT;
        result=vr_get_info(c,slot,&info);if(!result)copy(output,&info,sizeof(info));return result;
    }
    if(operation==VR_PRESENT) {
        if(output_bytes!=4)return VR_ARGUMENT;
        put32(output,1);return VR_OK;
    }
    if(operation==VR_SERIAL) {
        if(output_bytes!=10)return VR_ARGUMENT;
        result=vr_get_info(c,slot,&info);if(!result)copy(output,info.serial,10);return result;
    }
    if(operation==VR_USAGE) {
        if(output_bytes!=8)return VR_ARGUMENT;
        put64(output,slot==VR_MAINTENANCE?0:c->slots[slot].used);return VR_OK;
    }
    return VR_ARGUMENT;
}
int vr_publish_ink_identity(struct vr_context *c,uint32_t slot,void *mirror,uint32_t bytes) {
    if(!mirror || bytes!=192 || slot>=VR_SLOTS)return VR_ARGUMENT;
    struct vr_card_info info;int result=vr_get_info(c,slot,&info);if(result)return result;
    uint8_t *p=mirror;
    /* Confirmed descriptors: 0x71..0x7a -> words 49..53, high byte then low;
     * 0x88..0x8c -> words 57..59, high byte then low. Other bytes preserved. */
    for(uint32_t i=0;i<10;i++)p[2*(49+i/2)+(i%2?0:1)]=(uint8_t)info.serial[i];
    for(uint32_t i=0;i<5;i++)p[2*(57+i/2)+(i%2?0:1)]=(uint8_t)info.manufacturer[i];
    return VR_OK;
}

/* Freestanding compiler-generated structure copies may reference EABI helpers. */
void *__aeabi_memcpy(void *d,const void *s,size_t n){copy(d,s,(uint32_t)n);return d;}
void *__aeabi_memcpy4(void *d,const void *s,size_t n){return __aeabi_memcpy(d,s,n);}
void *__aeabi_memcpy8(void *d,const void *s,size_t n){return __aeabi_memcpy(d,s,n);}
void __aeabi_memclr(void *d,size_t n){fill(d,0,(uint32_t)n);}
void __aeabi_memclr4(void *d,size_t n){__aeabi_memclr(d,n);}
void __aeabi_memclr8(void *d,size_t n){__aeabi_memclr(d,n);}
