#include "native_adapter.h"
#include "metadata_store.h"
static struct vr_context *context;
#ifdef P7500_DELIVERY
extern uint64_t original_get40(uint32_t,uint32_t,uint32_t);
extern void original_set40(uint32_t,uint32_t,uint32_t,uint64_t);
extern void original_add40(uint32_t,uint32_t,uint32_t,uint64_t);
extern void original_cover(uint32_t,uint32_t);
extern void original_mirror(uint32_t,uint32_t,uint32_t *);
extern uint8_t *original_presence(uint32_t);
extern uint8_t *original_waste_info(uint32_t);
extern void payload_fault(int);
static struct vr_native_bindings original={original_get40,original_set40,original_add40,
    original_cover,original_mirror,original_presence,payload_fault,(uint8_t *)(uintptr_t)0x437c4fb4,
    original_waste_info,(uint32_t (*)(uint32_t))(uintptr_t)0x4340a84c,(uint8_t *)(uintptr_t)0x437c6f40};
#else
static struct vr_native_bindings original;
#endif
static int last_fault;
static uint8_t slot_access[VR_SLOTS];
static struct vm_store *metadata;
static uint8_t *waste_mirror,*waste_dirty,*waste_errors;

static int ready(void) {return context && !last_fault && vr_presence_value(context,0)==1 &&
    (!metadata || (metadata->ready && !metadata->fault));}
static void failed(int error) {
    if(error<0 && !last_fault) {
        last_fault=error;
        if(original.fault)original.fault(error);
    }
}
int vr_native_prepare(const struct vr_native_bindings *b){
    if(!b || !b->get40 || !b->set40 || !b->add40 || !b->set_cover || !b->read_mirror ||
       !b->presence_ptr || !b->waste_info_ptr)return VR_ARGUMENT;
    original=*b;context=0;metadata=0;waste_mirror=waste_dirty=waste_errors=0;last_fault=0;return VR_OK;
}
int vr_native_attach(struct vr_context *c,const struct vr_native_bindings *b) {
    if(!c || !b || !b->get40 || !b->set40 || !b->add40 || !b->set_cover ||
       !b->read_mirror || !b->presence_ptr || !b->fault || !b->ink_mirror ||
       !b->waste_info_ptr || !b->slot_access || !b->ink_dirty)return VR_ARGUMENT;
    if(c->busy)return VR_BUSY;
    if(vr_presence_value(c,0)!=1)return VR_NOT_READY;
    uint8_t routes[VR_SLOTS];
    for(uint32_t s=0;s<VR_SLOTS;s++) {
        uint32_t access=b->slot_access(s);
        if(access>=32)return VR_ARGUMENT;
        routes[s]=(uint8_t)access;
    }
    for(uint32_t s=0;s<VR_SLOTS;s++)slot_access[s]=routes[s];
    original=*b;context=c;metadata=0;waste_mirror=waste_dirty=waste_errors=0;last_fault=0;return VR_OK;
}
int vr_native_metadata_attach(struct vm_store *s) {
    if(!ready())return VR_NOT_READY;
    if(context->busy)return VR_BUSY;
    if(s && s->busy)return VR_BUSY;
    struct vr_io io;int result=vm_core_io(s,&io);if(result)return result;
    if(context->io.user!=io.user || context->io.read!=io.read || context->io.write!=io.write ||
       context->io.erase!=io.erase || context->io.sync!=io.sync)return VR_ARGUMENT;
    uint8_t image[192];
    for(uint32_t slot=0;slot<VR_SLOTS;slot++){
        result=vm_get(s,slot,image,sizeof(image));if(result)return result;
    }
    for(uint32_t slot=0;slot<VR_SLOTS;slot++){
        result=vm_get(s,slot,image,sizeof(image));if(result)return result;
        result=vr_publish_ink_identity(context,slot,image,sizeof(image));if(result)return result;
        for(uint32_t i=0;i<192;i++)original.ink_mirror[slot*192+i]=image[i];
    }
    if(waste_mirror){
        result=vm_get(s,12,image,sizeof(image));if(result)return result;
        for(uint32_t i=0;i<192;i++)waste_mirror[i]=image[i];
    }
    metadata=s;return VR_OK;
}
int vr_native_waste_bind(uint8_t *mirror,uint8_t *dirty,uint8_t *errors){
    if(!mirror || !dirty || !errors)return VR_ARGUMENT;
    if(!ready())return VR_NOT_READY;
    if(metadata){int r=vm_get(metadata,12,mirror,192);if(r)return r;}
    waste_mirror=mirror;waste_dirty=dirty;waste_errors=errors;return VR_OK;
}
uint64_t vr_native_capacity(uint32_t slot){
    if(slot>=VR_SLOTS || !ready()){failed(slot>=VR_SLOTS?VR_ARGUMENT:VR_NOT_READY);return UINT64_MAX;}
    return context->slots[slot].capacity;
}
uint32_t vr_native_zero(void){return 0;}
uint32_t vr_native_unsupported(void){return 1;}
/* Native GF bus polling uses 0=ready, 1=retry/error. The logical maintenance
 * presence byte returned by waste_info_ptr remains 1 when healthy. */
void vr_native_waste_presence(uint8_t *out){if(out)*out=(uint8_t)(ready()?0:1);}
uint32_t vr_native_waste_read_words(uint32_t box,uint32_t words){
    if(box || words>96){failed(VR_ARGUMENT);return 1;}
    if(!ready() || !waste_mirror){failed(VR_NOT_READY);return 1;}
    if(metadata){uint8_t image[192];int r=vm_get(metadata,12,image,sizeof(image));if(r){failed(r);return 1;}
        for(uint32_t i=0;i<words*2;i++)waste_mirror[i]=image[i];}
    return 0;
}
uint32_t vr_native_waste_flush_mirror(uint32_t box,uint32_t keep_dirty){
    if(box || keep_dirty>1){failed(VR_ARGUMENT);return 1;}
    if(!ready() || !waste_mirror || !waste_dirty){failed(VR_NOT_READY);return 1;}
    if(metadata){int r=vm_put(metadata,12,waste_mirror,192);if(r){failed(r);return 1;}}
    if(!keep_dirty)for(uint32_t i=0;i<96;i++)waste_dirty[i]=0;
    return 0;
}
uint32_t vr_native_waste_mode_get(uint32_t box,uint16_t *value){
    if(box || !value){failed(VR_ARGUMENT);return 1;}
    if(!ready() || !metadata){failed(VR_NOT_READY);return 1;}
    uint16_t state;int r=vm_control_get(metadata,12,&state);if(r){failed(r);return 1;}
    *value=state&15;return 0;
}
uint32_t vr_native_waste_mode_set(uint32_t box,uint32_t value){
    if(box || value>15){failed(VR_ARGUMENT);return 1;}
    if(!ready() || !metadata){failed(VR_NOT_READY);return 1;}
    uint16_t old;int r=vm_control_get(metadata,12,&old);if(r){failed(r);return 1;}
    r=vm_control_set(metadata,12,(uint16_t)((old&0xfff0)|value));if(r){failed(r);return 1;}return 0;
}
uint32_t vr_native_waste_control(uint32_t box,uint32_t value){
    if(box || value>255){failed(VR_ARGUMENT);return 1;}
    if(!ready() || !metadata){failed(VR_NOT_READY);return 1;}
    uint16_t old;int r=vm_control_get(metadata,12,&old);if(r){failed(r);return 1;}
    r=vm_control_set(metadata,12,(uint16_t)((old&255)|(value<<8)));if(r){failed(r);return 1;}return 0;
}
uint32_t vr_native_waste_check(uint32_t box){
    if(box){failed(VR_ARGUMENT);return 1;}
    if(!ready() || !waste_errors){failed(VR_NOT_READY);return 1;}
    for(uint32_t i=0;i<22;i++)waste_errors[i]=0;
    return 0;
}
int vr_native_fault(void) {return last_fault;}
uint64_t vr_native_get40(uint32_t group,uint32_t field,uint32_t slot) {
    if(!context){if(original.get40)return original.get40(group,field,slot);failed(VR_NOT_READY);return UINT64_MAX;}
    if(group!=0x2f || field!=0x30)return original.get40(group,field,slot);
    if(!ready() || slot>=VR_SLOTS){failed(slot>=VR_SLOTS?VR_ARGUMENT:VR_NOT_READY);return UINT64_MAX;}
    return vr_get_usage(context,slot);
}
void vr_native_set40(uint32_t group,uint32_t field,uint32_t slot,uint64_t value) {
    if(!context){if(original.set40){original.set40(group,field,slot,value);return;}failed(VR_NOT_READY);return;}
    if(group!=0x2f || field!=0x30){original.set40(group,field,slot,value);return;}
    if(!ready()){failed(VR_NOT_READY);return;}
    failed(vr_reconcile_usage(context,slot,value));
}
void vr_native_add40(uint32_t group,uint32_t field,uint32_t slot,uint64_t amount) {
    if(!context){if(original.add40){original.add40(group,field,slot,amount);return;}failed(VR_NOT_READY);return;}
    if(group!=0x2f || field!=0x30){original.add40(group,field,slot,amount);return;}
    if(!ready()){failed(VR_NOT_READY);return;}
    failed(vr_consume(context,slot,amount));
}
void vr_native_set_cover(uint32_t cover,uint32_t opened) {
    if(!context){if(original.set_cover){original.set_cover(cover,opened);return;}failed(VR_NOT_READY);return;}
    if(cover>1 || opened>1){failed(VR_ARGUMENT);return;}
    original.set_cover(cover,opened);
    if(!ready()){failed(VR_NOT_READY);return;}
    failed(opened?vr_cover_open(context,cover):vr_cover_close(context,cover));
}
void vr_native_read_mirror(uint32_t slot,uint32_t field,uint32_t *value) {
    if(!context){if(original.read_mirror){original.read_mirror(slot,field,value);return;}if(value)*value=0;failed(VR_NOT_READY);return;}
    int identity=(field>=0x71 && field<=0x7a)||(field>=0x88 && field<=0x8c);
    if(identity) {
        if(!value || slot>=VR_SLOTS || !ready()) {
            if(value)*value=0;
            failed((!value || slot>=VR_SLOTS)?VR_ARGUMENT:VR_NOT_READY);return;
        }
        int result=vr_publish_ink_identity(context,slot,original.ink_mirror+slot*192,192);
        if(result){*value=0;failed(result);return;}
    }
    original.read_mirror(slot,field,value);
}
uint8_t *vr_native_presence_ptr(uint32_t slot) {
    if(!context){if(original.presence_ptr)return original.presence_ptr(slot);failed(VR_NOT_READY);return 0;}
    if(slot>=VR_SLOTS){failed(VR_ARGUMENT);return 0;}
    uint8_t *p=original.presence_ptr(slot);
    if(!p){failed(VR_ARGUMENT);return 0;}
    *p=(uint8_t)(ready()?1:0);return p;
}
uint32_t vr_native_remaining_info(uint32_t slot) {
    if(slot>=VR_SLOTS || !ready()){failed(slot>=VR_SLOTS?VR_ARGUMENT:VR_NOT_READY);return 'n';}
    return vr_get_percent(context,slot);
}
uint8_t *vr_native_waste_info_ptr(uint32_t box) {
    if(!context && original.waste_info_ptr)return original.waste_info_ptr(box);
    if(!context || box!=0){failed(box?VR_ARGUMENT:VR_NOT_READY);return 0;}
    uint8_t *p=original.waste_info_ptr(box);
    if(!p){failed(VR_ARGUMENT);return 0;}
    /* Layout verified from native UpdateWasteStatus: presence at 0, status at
     * 1, CSIC class at 2, percentage at 3, native zeroed words at 4 and 6. */
    int healthy=ready();p[0]=(uint8_t)(healthy?1:0);p[1]=(uint8_t)(healthy?0:2);
    p[2]=0;p[3]=(uint8_t)(healthy?100:0);p[4]=p[5]=p[6]=p[7]=0;
    return p;
}
uint32_t vr_native_waste_remaining_info(uint32_t box) {
    if(box || !ready()){failed(box?VR_ARGUMENT:VR_NOT_READY);return 'n';}
    return 100;
}
uint32_t vr_native_waste_error_code(uint32_t index) {
    if(index>=0x24 || !ready()){failed(index>=0x24?VR_ARGUMENT:VR_NOT_READY);return 1;}
    return 0;
}

static uint32_t ink_job(const uint32_t *mask,uint8_t *result,uint8_t normal) {
    if(!result){failed(VR_ARGUMENT);return 1;}
    if(!context){failed(VR_NOT_READY);return 1;}
    /* Snapshot all selections before writing results: native callers may share
     * input/output storage. A selected slot enables its entire access group. */
    uint32_t selected=0;
    for(uint32_t s=0;s<VR_SLOTS;s++)
        if(!mask || mask[s])selected|=UINT32_C(1)<<slot_access[s];
    if(!selected)return 0;
    int healthy=ready();
    for(uint32_t s=0;s<VR_SLOTS;s++)
        if(selected&(UINT32_C(1)<<slot_access[s]))result[s]=healthy?normal:5;
    if(!healthy){failed(VR_NOT_READY);return 1;}
    return 0;
}
uint32_t vr_native_ink_check_job(const uint32_t *mask,uint8_t *result) {
    return ink_job(mask,result,0);
}
uint32_t vr_native_ink_status_job(uint32_t mode,const uint32_t *mask,uint8_t *result) {
    if(mode>1){failed(VR_ARGUMENT);return 1;}
    return ink_job(mask,result,2);
}
uint32_t vr_native_ink_read_words(uint32_t slot,uint32_t words) {
    if(slot>=VR_SLOTS || words>96){failed(VR_ARGUMENT);return 1;}
    if(!ready()){failed(VR_NOT_READY);return 1;}
    uint8_t snapshot[192],*mirror=original.ink_mirror+slot*192;
    if(metadata){int r=vm_get(metadata,slot,snapshot,sizeof(snapshot));if(r){failed(r);return 1;}}
    else for(uint32_t i=0;i<192;i++)snapshot[i]=mirror[i];
    int result=vr_publish_ink_identity(context,slot,snapshot,sizeof(snapshot));
    if(result){failed(result);return 1;}
    /* A partial native read must not modify words beyond the requested prefix. */
    for(uint32_t i=0;i<words*2;i++)mirror[i]=snapshot[i];
    return 0;
}
uint32_t vr_native_ink_flush_mirror(uint32_t slot,uint32_t keep_dirty) {
    if(slot>=VR_SLOTS || keep_dirty>1){failed(VR_ARGUMENT);return 1;}
    if(!ready()){failed(VR_NOT_READY);return 1;}
    /* The native caller has already written this authoritative RAM view.
     * Durable usage/generation were committed by their own adapters. Never
     * accept a stale mirror's serial/vendor over the owner's virtual identity.
     * With a metadata store, all bytes are committed before clearing dirty
     * flags. Without it, retain the legacy RAM-only view. */
    uint8_t snapshot[192],*mirror=original.ink_mirror+slot*192;
    for(uint32_t i=0;i<192;i++)snapshot[i]=mirror[i];
    int result=vr_publish_ink_identity(context,slot,snapshot,sizeof(snapshot));
    if(result){failed(result);return 1;}
    if(metadata){result=vm_put(metadata,slot,snapshot,sizeof(snapshot));if(result){failed(result);return 1;}}
    for(uint32_t i=0;i<192;i++)mirror[i]=snapshot[i];
    if(!keep_dirty)for(uint32_t i=0;i<96;i++)original.ink_dirty[slot*96+i]=0;
    return 0;
}
