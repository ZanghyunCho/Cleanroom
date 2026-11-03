#include "native_nv.h"
_Static_assert(sizeof(struct vr_nv_request)==24,"Native NV request layout");
static vr_nv_validator original_validator;
int vr_nv_guard_attach(vr_nv_validator callback) {
    if(!callback || callback==vr_nv_guard)return VR_ARGUMENT;
    original_validator=callback;return VR_OK;
}
uint32_t vr_nv_guard(struct vr_nv_request *r,void *buffer,uint32_t operation,uint8_t *mode) {
    if(!original_validator)return 0x1001;
    uint32_t result=original_validator(r,buffer,operation,mode);
    if(result)return result;
    /* The original validator accepts index == record_count. Its address
     * resolver then lands in the following row. For this legacy duplicate ID,
     * index 10 aliases owner bank A. Close that existing off-by-one path.
     * Whole-object deletion operations do not have index-range arguments. */
    if(operation!=5 && operation!=0x105) {
        if(r->id==0x01600945 && (r->first>=10 || r->last>=10))return 0x1002;
        if((r->id==VR_NV_OWNER_A || r->id==VR_NV_OWNER_B) && (r->first || r->last))return 0x1002;
    }
    return 0;
}
static void bytes_copy(void *d,const void *s,uint32_t n) {
    uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;
}
static void bytes_fill(void *d,uint8_t v,uint32_t n) {uint8_t *p=d;while(n--)*p++=v;}
static int bytes_equal(const void *a,const void *b,uint32_t n) {
    const uint8_t *p=a,*q=b;while(n--)if(*p++!=*q++)return 0;return 1;
}
static uint32_t read32(const uint8_t *p) {
    return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void write32(uint8_t *p,uint32_t v){for(uint32_t i=0;i<4;i++){p[i]=(uint8_t)v;v>>=8;}}
static int native_row(const uint8_t *r) {
    static const uint8_t permissions[12]={0x10,1,1,1,1,0,0,0,0,0,0,0};
    return read32(r)==0x01600945 && read32(r+4)==0x000a0001 && bytes_equal(r+8,permissions,12);
}
static int owner_row(const uint8_t *r,uint32_t id) {
    static const uint8_t permissions[12]={0x10,1,1,1,1,0,0,0,0,0,0,0};
    return read32(r)==id && read32(r+4)==0x00010080 && bytes_equal(r+8,permissions,12);
}
static int profile(const uint8_t *t,uint32_t rows,int installed) {
    if(!t || rows!=VR_NV_CONFIG_ROWS || !native_row(t+120*20))return 0;
    if(installed) {
        if(!owner_row(t+121*20,VR_NV_OWNER_A) || !owner_row(t+122*20,VR_NV_OWNER_B))return 0;
    } else if(!native_row(t+121*20) || !native_row(t+122*20))return 0;
    for(uint32_t i=0;i<rows;i++)if(i!=121 && i!=122) {
        uint32_t id=read32(t+i*20);
        if(id==VR_NV_OWNER_A || id==VR_NV_OWNER_B)return 0;
    }
    return 1;
}
int vr_nv_register_owner(uint8_t *t,uint32_t rows) {
    if(profile(t,rows,1))return VR_OK;
    if(!profile(t,rows,0))return VR_NOT_READY;
    write32(t+121*20,VR_NV_OWNER_A);write32(t+121*20+4,0x00010080);
    write32(t+122*20,VR_NV_OWNER_B);write32(t+122*20+4,0x00010080);
    return VR_OK;
}
static void request(struct vr_nv_request *r,uint32_t bank) {
    bytes_fill(r,0,sizeof(*r));r->id=bank?VR_NV_OWNER_B:VR_NV_OWNER_A;r->bytes=VR_COMPACT_SIZE;
}
static int load(struct vr_nv_backend *b,uint32_t bank,uint8_t *out) {
    struct vr_nv_request r;uint8_t packed[VR_COMPACT_SIZE];request(&r,bank);
    if(b->api.read(&r,packed)!=0)return 0;
    int blank=1;for(uint32_t i=0;i<VR_COMPACT_SIZE;i++)if(packed[i]!=255)blank=0;
    if(blank){bytes_fill(out,255,VR_RECORD_SIZE);return 1;}
    int result=vr_record_expand(packed,b->capacities,out);
    /* Corruption becomes an invalid core bank, allowing its existing fallback
     * rules. An unknown format is an error, never an empty/default cartridge. */
    if(result==VR_CORRUPT){bytes_fill(out,0,VR_RECORD_SIZE);return 1;}
    return result==VR_OK;
}
static int nv_read(void *user,uint32_t bank,uint32_t offset,void *out,uint32_t n) {
    struct vr_nv_backend *b=user;
    if(!b || b->fault || bank>1 || offset>VR_RECORD_SIZE || n>VR_RECORD_SIZE-offset || (!out && n))return 0;
    uint8_t record[VR_RECORD_SIZE];if(!load(b,bank,record))return 0;
    bytes_copy(out,record+offset,n);return 1;
}
static int nv_erase(void *user,uint32_t bank) {
    struct vr_nv_backend *b=user;if(!b || b->fault || bank>1)return 0;
    bytes_fill(b->stage[bank],255,VR_RECORD_SIZE);b->loaded[bank]=1;b->dirty[bank]=1;return 1;
}
static int nv_write(void *user,uint32_t bank,uint32_t offset,const void *data,uint32_t n) {
    struct vr_nv_backend *b=user;
    if(!b || b->fault || bank>1 || !b->loaded[bank] || offset>VR_RECORD_SIZE ||
       n>VR_RECORD_SIZE-offset || (!data && n))return 0;
    const uint8_t *p=data;
    for(uint32_t i=0;i<n;i++)if((b->stage[bank][offset+i]&p[i])!=p[i])return 0;
    bytes_copy(b->stage[bank]+offset,data,n);b->dirty[bank]=1;return 1;
}
static int nv_sync(void *user,uint32_t bank) {
    struct vr_nv_backend *b=user;if(!b || b->fault || bank>1 || !b->loaded[bank])return 0;
    if(!b->dirty[bank])return 1;
    uint8_t packed[VR_COMPACT_SIZE],check[VR_COMPACT_SIZE];
    if(vr_record_compact(b->stage[bank],b->capacities,packed)!=VR_OK)return 0;
    struct vr_nv_request r;request(&r,bank);
    /* The synchronous NV API waits for module 0x1B's completion message. Queue
     * submission alone is not success. Read the logical record back as well. */
    if(b->api.write(&r,packed)!=0){b->fault=1;return 0;}
    request(&r,bank);
    if(b->api.read(&r,check)!=0 || !bytes_equal(packed,check,sizeof(check))){b->fault=1;return 0;}
    b->dirty[bank]=0;return 1;
}
int vr_nv_backend_init(struct vr_nv_backend *b,const struct vr_nv_api *api,const uint8_t *table,
                       uint32_t rows,const uint64_t *capacities,struct vr_io *io) {
    if(!b || !api || !api->read || !api->write || !capacities || !io)return VR_ARGUMENT;
    if(!profile(table,rows,1))return VR_NOT_READY;
    for(uint32_t s=0;s<VR_SLOTS;s++)if(capacities[s]<10000 || capacities[s]>VR_MAX_USAGE)return VR_ARGUMENT;
    struct vr_nv_api copy_api=*api;uint64_t copy_caps[VR_SLOTS];bytes_copy(copy_caps,capacities,sizeof(copy_caps));
    bytes_fill(b,0,sizeof(*b));b->api=copy_api;bytes_copy(b->capacities,copy_caps,sizeof(copy_caps));
    io->user=b;io->read=nv_read;io->erase=nv_erase;io->write=nv_write;io->sync=nv_sync;return VR_OK;
}
int vr_nv_install_empty_records(struct vr_nv_backend *b) {
    if(!b || !b->api.read || !b->api.write)return VR_ARGUMENT;
    if(b->fault)return VR_NOT_READY;
    uint8_t empty[VR_COMPACT_SIZE],check[VR_COMPACT_SIZE];bytes_fill(empty,255,sizeof(empty));
    for(uint32_t bank=0;bank<2;bank++) {
        struct vr_nv_request r;request(&r,bank);
        if(b->api.write(&r,empty)!=0){b->fault=1;return VR_IO;}
        request(&r,bank);
        if(b->api.read(&r,check)!=0 || !bytes_equal(empty,check,sizeof(empty))){b->fault=1;return VR_IO;}
        b->dirty[bank]=b->loaded[bank]=0;
    }
    return VR_OK;
}
int vr_nv_p7500_register_owner(void) {
    const uint8_t *entry=(const uint8_t *)(uintptr_t)0x435f3274;
    if(!original_validator || read32(entry)!=0xe51ff004 ||
       read32(entry+4)!=(uint32_t)(uintptr_t)vr_nv_guard)return VR_NOT_READY;
    return vr_nv_register_owner((uint8_t *)(uintptr_t)0x43740e74,VR_NV_CONFIG_ROWS);
}
int vr_nv_p7500_init(struct vr_nv_backend *b,const uint64_t *capacity,struct vr_io *io) {
    const uint8_t *entry=(const uint8_t *)(uintptr_t)0x435f3274;
    if(!original_validator || read32(entry)!=0xe51ff004 ||
       read32(entry+4)!=(uint32_t)(uintptr_t)vr_nv_guard)return VR_NOT_READY;
    /* Config registration alone is insufficient: the native constructor must
     * have rebuilt its ID-to-offset map before any object can be accessed. */
    const uint8_t *map=(const uint8_t *)(uintptr_t)0xb9a5802c;
    const uint8_t *a=map+121*12,*next=map+122*12;
    if(read32(a)!=VR_NV_OWNER_A || read32(next)!=VR_NV_OWNER_B ||
       read32(a+8)!=0x16 || read32(next+8)!=0x16 ||
       read32(next+4)!=read32(a+4)+140 ||
       read32(map+123*12+4)!=read32(next+4)+140)return VR_NOT_READY;
    const struct vr_nv_api api={
        (uint32_t (*)(struct vr_nv_request *,void *))(uintptr_t)0x435efdd4,
        (uint32_t (*)(struct vr_nv_request *,const void *))(uintptr_t)0x435efdf0
    };
    return vr_nv_backend_init(b,&api,(const uint8_t *)(uintptr_t)0x43740e74,
                              VR_NV_CONFIG_ROWS,capacity,io);
}
