#ifndef P7500_NATIVE_ADAPTER_H
#define P7500_NATIVE_ADAPTER_H
#include "virtual_cartridge.h"
struct vm_store;
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
int vr_native_prepare(const struct vr_native_bindings *);
/* Requires this context's core IO to be backed by the same metadata store.
 * All twelve ink images must already exist; no automatic profile seeding. */
int vr_native_metadata_attach(struct vm_store *);
int vr_native_waste_bind(uint8_t *,uint8_t *,uint8_t *);
uint64_t vr_native_capacity(uint32_t);
uint32_t vr_native_waste_read_words(uint32_t,uint32_t);
uint32_t vr_native_waste_flush_mirror(uint32_t,uint32_t);
uint32_t vr_native_waste_mode_get(uint32_t,uint16_t *);
uint32_t vr_native_waste_mode_set(uint32_t,uint32_t);
uint32_t vr_native_waste_control(uint32_t,uint32_t);
uint32_t vr_native_waste_check(uint32_t);
void vr_native_waste_presence(uint8_t *);
uint32_t vr_native_zero(void);
uint32_t vr_native_unsupported(void);
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
/* Owner identity comes from virtual core state. When metadata is attached, all
 * image bytes are durable; the legacy unbound mode retains a RAM-only view. */
uint32_t vr_native_ink_read_words(uint32_t slot,uint32_t words);
uint32_t vr_native_ink_flush_mirror(uint32_t slot,uint32_t keep_dirty);
#endif
