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
    uint32_t (*slot_access)(uint32_t);
    uint8_t *ink_dirty;
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
/* Synchronous upper ink-check/status jobs. mask is 12 uint32_t selections,
 * or NULL for all slots. Results cover selected access groups, not just the
 * selected slots. These functions do not emulate physical chip registers. */
uint32_t vr_native_ink_check_job(const uint32_t *,uint8_t *);
uint32_t vr_native_ink_status_job(uint32_t,const uint32_t *,uint8_t *);
/* RAM mirror view: owner serial/vendor come from durable virtual state. Other
 * fields remain native RAM data, not a newly persisted full chip image. */
uint32_t vr_native_ink_read_words(uint32_t slot,uint32_t words);
uint32_t vr_native_ink_flush_mirror(uint32_t slot,uint32_t keep_dirty);
#endif
