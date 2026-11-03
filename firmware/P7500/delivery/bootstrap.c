#include "native_adapter.h"
#include "metadata_store.h"
#include "full_nv.h"
extern uint64_t original_get40(uint32_t,uint32_t,uint32_t);
extern void original_set40(uint32_t,uint32_t,uint32_t,uint64_t);
extern void original_add40(uint32_t,uint32_t,uint32_t,uint64_t);
extern void original_cover(uint32_t,uint32_t);
extern void original_mirror(uint32_t,uint32_t,uint32_t *);
extern uint8_t *original_presence(uint32_t);
extern uint8_t *original_waste_info(uint32_t);
extern uint64_t original_capacity(uint32_t);
extern uint32_t original_layout(void);
extern uint32_t original_restore(void);
extern uint32_t original_validate(struct vr_nv_request *,void *,uint32_t,uint8_t *);
extern uint32_t original_write(struct vr_nv_request *,const void *,void *);
#ifndef INSTALLER
#define INSTALLER 0
#endif
struct payload {
    struct vf_nv nv;
    struct vm_store metadata;
    struct vr_context core;
    struct vr_io outer_io,core_io;
    uint64_t capacity[VR_SLOTS];
    uint8_t covers[VR_SLOTS],worker[VF_OBJECT];
    int fault;
};
static struct payload *state;
static uint32_t profile_ready,boot_ready;
void payload_fault(int r){if(state)state->fault=r;}
static const struct vr_native_bindings bindings={
    original_get40,original_set40,original_add40,original_cover,original_mirror,original_presence,
    payload_fault,(uint8_t *)(uintptr_t)0x437c4fb4,original_waste_info,
    (uint32_t (*)(uint32_t))(uintptr_t)0x4340a84c,(uint8_t *)(uintptr_t)0x437c6f40
};
uint32_t payload_layout(void){
    if(!state){
        void *memory=0;
        ((void (*)(uint32_t,uint32_t,uint32_t,void **))(uintptr_t)0x4360c948)(1,0,sizeof(struct payload)+7,&memory);
        if(memory){state=(void *)(((uintptr_t)memory+7)&~(uintptr_t)7);uint8_t *p=(void *)state;for(uint32_t i=0;i<sizeof(*state);i++)p[i]=0;}
    }
    vf_guard_attach(original_validate);
    if(!state)return original_layout();
    if(vf_worker_attach((vf_raw_read)(uintptr_t)0x435f0dfc,original_write,state->worker,sizeof(state->worker))){payload_fault(VR_NOT_READY);return original_layout();}
    int result=vf_extend_profile((uint8_t *)(uintptr_t)0x43740e74,157);
    uint32_t native=original_layout();
    if(result){payload_fault(result);return native;}
    result=vf_validate_layout((const uint8_t *)(uintptr_t)0x43740e74,
                             (const uint8_t *)(uintptr_t)0xb9a5802c,(const uint8_t *)(uintptr_t)0xb9a57c8c);
    if(result){payload_fault(result);return native;}
    profile_ready=1;return native;
}
uint32_t payload_restore(void){
    boot_ready=0;vr_native_prepare(&bindings);uint32_t native=original_restore();
    if(!state || !profile_ready)return native;
    const struct vr_nv_api api={
        (uint32_t (*)(struct vr_nv_request *,void *))(uintptr_t)0x435efdd4,
        (uint32_t (*)(struct vr_nv_request *,const void *))(uintptr_t)0x435efdf0};
    int r=vf_init(&state->nv,&api,&state->outer_io);if(r){payload_fault(r);return native;}
    r=vm_init(&state->metadata,&state->outer_io);
    if(r && INSTALLER){
        r=vf_install_empty(&state->nv);if(r){payload_fault(r);return native;}
        r=vm_init(&state->metadata,&state->outer_io);
        if(r!=VR_EMPTY){payload_fault(r?r:VR_NOT_READY);return native;}
        r=vm_format_empty(&state->metadata);
    }
    if(r){payload_fault(r);return native;}
    r=vm_core_io(&state->metadata,&state->core_io);if(r){payload_fault(r);return native;}
    for(uint32_t slot=0;slot<VR_SLOTS;slot++){
        state->capacity[slot]=7000000;state->covers[slot]=(uint8_t)(slot<6?1:0);
        ((uint32_t *)(uintptr_t)0x437c74e0)[slot]=700;
    }
    r=vr_init(&state->core,&state->core_io,state->covers);
    if(r==VR_EMPTY && INSTALLER)r=vr_format_empty(&state->core,state->capacity);
    if(r){payload_fault(r);return native;}
    if(INSTALLER){
        uint8_t image[192];
        for(uint32_t slot=0;slot<13;slot++){
            r=vm_get(&state->metadata,slot,image,sizeof(image));
            if(r==VR_EMPTY){
                const uint8_t *source=(const uint8_t *)(uintptr_t)(slot<12?0x437c4fb4+slot*192:0x437c7874);
                for(uint32_t i=0;i<192;i++)image[i]=source[i];
                if(slot<12){r=vr_publish_ink_identity(&state->core,slot,image,192);if(r){payload_fault(r);return native;}}
                r=vm_put(&state->metadata,slot,image,sizeof(image));
            }
            if(r){payload_fault(r);return native;}
        }
    }
    r=vr_native_attach(&state->core,&bindings);if(r){payload_fault(r);return native;}
    r=vr_native_waste_bind((uint8_t *)(uintptr_t)0x437c7874,(uint8_t *)(uintptr_t)0x437c7b74,(uint8_t *)(uintptr_t)0x437c76b4);
    if(r){payload_fault(r);return native;}
    r=vr_native_metadata_attach(&state->metadata);if(r){payload_fault(r);return native;}
    boot_ready=1;state->fault=0;return native;
}
uint64_t payload_capacity(uint32_t slot){return boot_ready?vr_native_capacity(slot):original_capacity(slot);}
uint32_t payload_waste_flush(uint32_t box){return vr_native_waste_flush_mirror(box,0);}
uint32_t payload_waste_control(uint32_t box,uint32_t value){return vr_native_waste_control(box,value);}
uint32_t payload_status(void){return !state?0xffffffffu:boot_ready?0:state->fault?(uint32_t)state->fault:0xfffffffbu;}
uintptr_t payload_context(void){return state?(uintptr_t)&state->core:0;}
uintptr_t payload_metadata(void){return state?(uintptr_t)&state->metadata:0;}
/* Force retention of every entry patched by the static image builder. */
__attribute__((used,section(".roots"))) static const void *roots[]={
    vr_native_get40,vr_native_set40,vr_native_add40,vr_native_set_cover,vr_native_read_mirror,
    vr_native_presence_ptr,vr_native_remaining_info,vr_native_waste_info_ptr,
    vr_native_waste_remaining_info,vr_native_waste_error_code,vr_native_ink_check_job,
    vr_native_ink_status_job,vr_native_ink_read_words,vr_native_ink_flush_mirror,
    vr_native_waste_read_words,vr_native_waste_flush_mirror,vr_native_waste_mode_get,
    vr_native_waste_mode_set,vr_native_waste_check,vr_native_waste_presence,
    vr_native_zero,vr_native_unsupported,payload_capacity,payload_waste_flush,payload_waste_control,payload_restore,payload_layout,
    vf_guard,vf_worker_write,payload_status,payload_context,payload_metadata
};
