#ifndef P7500_NATIVE_ADAPTER_H
#define P7500_NATIVE_ADAPTER_H
#include "virtual_cartridge.h"
struct vr_native_bindings {
    uint64_t (*get40)(uint32_t,uint32_t,uint32_t);
    void (*set40)(uint32_t,uint32_t,uint32_t,uint64_t);
    void (*add40)(uint32_t,uint32_t,uint32_t,uint64_t);
    void (*set_cover)(uint32_t,uint32_t);
    void (*read_mirror)(uint32_t,uint32_t,uint32_t *);
    uint8_t *(*presence_ptr)(uint32_t);
    void (*fault)(int);
    uint8_t *ink_mirror;
    uint8_t *(*waste_info_ptr)(uint32_t);
};
/* Original-function pointers must target verified relocated prologues, not the
 * patched entry addresses. No actual printer storage/RAM placement is selected. */
int vr_native_attach(struct vr_context *,const struct vr_native_bindings *);
int vr_native_fault(void);
uint64_t vr_native_get40(uint32_t,uint32_t,uint32_t);
void vr_native_set40(uint32_t,uint32_t,uint32_t,uint64_t);
void vr_native_add40(uint32_t,uint32_t,uint32_t,uint64_t);
void vr_native_set_cover(uint32_t,uint32_t);
void vr_native_read_mirror(uint32_t,uint32_t,uint32_t *);
uint8_t *vr_native_presence_ptr(uint32_t);
uint32_t vr_native_remaining_info(uint32_t);
uint8_t *vr_native_waste_info_ptr(uint32_t);
uint32_t vr_native_waste_remaining_info(uint32_t);
uint32_t vr_native_waste_error_code(uint32_t);
#endif
