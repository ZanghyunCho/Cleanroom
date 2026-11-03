#ifndef P7500_METADATA_STORE_H
#define P7500_METADATA_STORE_H
#include "virtual_cartridge.h"
#define VM_RECORD_SIZE 4096u
#define VM_PROFILES 13u
#define VM_IMAGE_BYTES 192u
struct vm_store {
    struct vr_io io;
    uint8_t current[VM_RECORD_SIZE],work[VM_RECORD_SIZE],check[VM_RECORD_SIZE];
    uint8_t stage[2][VR_RECORD_SIZE];
    uint32_t active,ready,empty,fault,busy,loaded[2];
};
uint32_t vm_store_bytes(void);
int vm_init(struct vm_store *,const struct vr_io *);
int vm_format_empty(struct vm_store *);
int vm_core_io(struct vm_store *,struct vr_io *);
int vm_get(struct vm_store *,uint32_t,void *,uint32_t);
int vm_put(struct vm_store *,uint32_t,const void *,uint32_t);
int vm_control_get(struct vm_store *,uint32_t,uint16_t *);
int vm_control_set(struct vm_store *,uint32_t,uint16_t);
#endif
