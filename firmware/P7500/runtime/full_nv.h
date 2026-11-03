#ifndef P7500_FULL_NV_H
#define P7500_FULL_NV_H
#include "metadata_store.h"
#include "native_nv.h"
#define VF_ID UINT32_C(0x01600fff)
#define VF_PREFIX 1024u
#define VF_OBJECT (VF_PREFIX+2*VM_RECORD_SIZE)
typedef uint32_t (*vf_raw_read)(struct vr_nv_request *,void *,void *);
typedef uint32_t (*vf_raw_write)(struct vr_nv_request *,const void *,void *);
struct vf_nv {
    struct vr_nv_api api;
    uint8_t object[VF_OBJECT],check[VF_OBJECT],stage[2][VM_RECORD_SIZE];
    uint32_t loaded[2],fault;
};
int vf_extend_profile(uint8_t *,uint32_t);
int vf_validate_layout(const uint8_t *,const uint8_t *,const uint8_t *);
int vf_guard_attach(vr_nv_validator);
uint32_t vf_guard(struct vr_nv_request *,void *,uint32_t,uint8_t *);
int vf_worker_attach(vf_raw_read,vf_raw_write,void *,uint32_t);
uint32_t vf_worker_write(struct vr_nv_request *,const void *,void *);
int vf_init(struct vf_nv *,const struct vr_nv_api *,struct vr_io *);
int vf_install_empty(struct vf_nv *);
#endif
