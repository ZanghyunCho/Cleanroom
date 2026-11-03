#ifndef P7500_NATIVE_NV_H
#define P7500_NATIVE_NV_H
#include "virtual_cartridge.h"
#define VR_NV_OWNER_A UINT32_C(0x01607500)
#define VR_NV_OWNER_B UINT32_C(0x01607501)
#define VR_NV_CONFIG_ROWS 157u
/* Native API request ABI, explicitly verified against ARM wrappers. */
struct vr_nv_request {
    uint32_t id,bytes;
    uint16_t first,last;
    uint8_t reserved[2],mode,pad;
    uint32_t tail[2];
};
struct vr_nv_api {
    uint32_t (*read)(struct vr_nv_request *,void *);
    uint32_t (*write)(struct vr_nv_request *,const void *);
};
struct vr_nv_backend {
    struct vr_nv_api api;
    uint64_t capacities[VR_SLOTS];
    uint8_t stage[2][VR_RECORD_SIZE];
    uint32_t dirty[2],loaded[2],fault;
};
/* Must run before native NV layout initialization. Uses only the two duplicate
 * rows, preserving their allocated footprint. Does not write storage or create
 * records. Returns NOT_READY for an unrecognized native profile. */
int vr_nv_register_owner(uint8_t *table,uint32_t rows);
int vr_nv_backend_init(struct vr_nv_backend *,const struct vr_nv_api *,
                       const uint8_t *table,uint32_t rows,
                       const uint64_t *capacities,struct vr_io *);
/* Explicit INSTALLER operation: overwrite both owner records with empty data.
 * Destroys previous virtual usage/generations. Never use on normal startup,
 * on a read error, or to recover corrupt records. Requires a bound backend. */
int vr_nv_install_empty_records(struct vr_nv_backend *);
typedef uint32_t (*vr_nv_validator)(struct vr_nv_request *,void *,uint32_t,uint8_t *);
/* Attach a verified relocated original validator before patching its entry. */
int vr_nv_guard_attach(vr_nv_validator);
uint32_t vr_nv_guard(struct vr_nv_request *,void *,uint32_t,uint8_t *);
/* Original P7500 addresses. Registration precedes native NV layout setup;
 * backend calls must run outside the NV service task. No RAM placement/startup
 * hook is implied by these bindings. */
int vr_nv_p7500_register_owner(void);
int vr_nv_p7500_init(struct vr_nv_backend *,const uint64_t *,struct vr_io *);
#endif
