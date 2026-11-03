#include "native_adapter.h"
static struct vr_context *context;
static struct vr_native_bindings original;
static int last_fault;
static uint8_t slot_access[VR_SLOTS];

static int ready(void) {return context && !last_fault && vr_presence_value(context,0)==1;}
static void failed(int error) {
    if(error<0 && !last_fault) {
        last_fault=error;
        if(original.fault)original.fault(error);
    }
}
int vr_native_attach(struct vr_context *c,const struct vr_native_bindings *b) {
    if(!c || !b || !b->get40 || !b->set40 || !b->add40 || !b->set_cover ||
       !b->read_mirror || !b->presence_ptr || !b->fault || !b->ink_mirror ||
       !b->waste_info_ptr || !b->slot_access)return VR_ARGUMENT;
    if(c->busy)return VR_BUSY;
    if(vr_presence_value(c,0)!=1)return VR_NOT_READY;
    uint8_t routes[VR_SLOTS];
    for(uint32_t s=0;s<VR_SLOTS;s++) {
        uint32_t access=b->slot_access(s);
        if(access>=32)return VR_ARGUMENT;
        routes[s]=(uint8_t)access;
    }
    for(uint32_t s=0;s<VR_SLOTS;s++)slot_access[s]=routes[s];
    original=*b;context=c;last_fault=0;return VR_OK;
}
int vr_native_fault(void) {return last_fault;}
uint64_t vr_native_get40(uint32_t group,uint32_t field,uint32_t slot) {
    if(!context){failed(VR_NOT_READY);return UINT64_MAX;}
    if(group!=0x2f || field!=0x30)return original.get40(group,field,slot);
    if(!ready() || slot>=VR_SLOTS){failed(slot>=VR_SLOTS?VR_ARGUMENT:VR_NOT_READY);return UINT64_MAX;}
    return vr_get_usage(context,slot);
}
void vr_native_set40(uint32_t group,uint32_t field,uint32_t slot,uint64_t value) {
    if(!context){failed(VR_NOT_READY);return;}
    if(group!=0x2f || field!=0x30){original.set40(group,field,slot,value);return;}
    if(!ready()){failed(VR_NOT_READY);return;}
    failed(vr_reconcile_usage(context,slot,value));
}
void vr_native_add40(uint32_t group,uint32_t field,uint32_t slot,uint64_t amount) {
    if(!context){failed(VR_NOT_READY);return;}
    if(group!=0x2f || field!=0x30){original.add40(group,field,slot,amount);return;}
    if(!ready()){failed(VR_NOT_READY);return;}
    failed(vr_consume(context,slot,amount));
}
void vr_native_set_cover(uint32_t cover,uint32_t opened) {
    if(!context){failed(VR_NOT_READY);return;}
    if(cover>1 || opened>1){failed(VR_ARGUMENT);return;}
    original.set_cover(cover,opened);
    if(!ready()){failed(VR_NOT_READY);return;}
    failed(opened?vr_cover_open(context,cover):vr_cover_close(context,cover));
}
void vr_native_read_mirror(uint32_t slot,uint32_t field,uint32_t *value) {
    if(!context){if(value)*value=0;failed(VR_NOT_READY);return;}
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
    if(!context){failed(VR_NOT_READY);return 0;}
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
