#ifndef P7500_VIRTUAL_CARTRIDGE_H
#define P7500_VIRTUAL_CARTRIDGE_H
#include <stdint.h>
#include <stddef.h>

#define VR_SLOTS 12u
#define VR_MAINTENANCE 12u
#define VR_RECORD_SIZE 512u
#define VR_COMPACT_SIZE 128u
#define VR_MAX_USAGE UINT64_C(0xffffffffff)

enum vr_result {
    VR_OK=0, VR_EMPTY=-1, VR_CORRUPT=-2, VR_IO=-3, VR_ARGUMENT=-4,
    VR_NOT_READY=-5, VR_LIMIT=-6, VR_BUSY=-7, VR_VERSION=-8
};

/* Callbacks return exactly 1 on success, 0 or a negative error on failure.
 * A write succeeds only when all bytes were accepted. sync must establish the
 * backend's durability boundary. Banks must be independent erase/write units.
 * These callbacks do not designate any real printer flash address. */
struct vr_io {
    void *user;
    int (*read)(void *,uint32_t,uint32_t,void *,uint32_t);
    int (*erase)(void *,uint32_t);
    int (*write)(void *,uint32_t,uint32_t,const void *,uint32_t);
    int (*sync)(void *,uint32_t);
};
struct vr_slot { uint64_t used,capacity; uint32_t generation; };
struct vr_context {
    struct vr_io io;
    struct vr_slot slots[VR_SLOTS];
    uint64_t sequence;
    uint32_t active,ready,empty,fault,busy,opened;
    uint8_t covers[VR_SLOTS];
};
struct vr_card_info {
    uint64_t used,capacity;
    uint32_t generation,present,virtualized,remaining_percent,nominal_ml;
    char serial[11],manufacturer[6],model[16];
};

/* Calls must be serialized by the caller's dispatcher. Reentrant callbacks are
 * rejected; this guard does not replace an OS mutex across concurrent threads. */
int vr_init(struct vr_context *,const struct vr_io *,const uint8_t covers[VR_SLOTS]);
int vr_format_empty(struct vr_context *,const uint64_t capacity[VR_SLOTS]);
int vr_consume(struct vr_context *,uint32_t slot,uint64_t amount);
/* A stale native/chip report must not reduce durable usage. A cover reset is
 * the only operation that lowers usage and simultaneously advances identity. */
int vr_reconcile_usage(struct vr_context *,uint32_t slot,uint64_t reported);
int vr_cover_open(struct vr_context *,uint32_t cover);
/* Positive return: reset-slot bitmask. Zero: no reset, including ignored close. */
int vr_cover_close(struct vr_context *,uint32_t cover);
uint64_t vr_get_usage(const struct vr_context *,uint32_t slot);
uint32_t vr_get_generation(const struct vr_context *,uint32_t slot);
uint32_t vr_get_percent(const struct vr_context *,uint32_t slot);
int vr_get_info(struct vr_context *,uint32_t slot,struct vr_card_info *);
int vr_presence_value(struct vr_context *,uint32_t slot);

/* Logical provider operations, NOT Epson wire opcodes or a claimed SPI protocol. */
enum vr_operation { VR_PRESENT=1,VR_INFO=2,VR_SERIAL=3,VR_USAGE=4,VR_ADD_USAGE=5 };
int vr_exchange(struct vr_context *,uint32_t operation,uint32_t slot,
                const void *input,uint32_t input_bytes,void *output,uint32_t output_bytes);

/* Update only the confirmed serial/vendor fields in an existing 192-byte ink
 * RAM mirror. Product/authentication/unknown fields remain unchanged. This is
 * not a complete authenticated Epson chip image. */
int vr_publish_ink_identity(struct vr_context *,uint32_t slot,void *mirror,uint32_t bytes);
/* Lossless codec for canonical v1 records using externally supplied capacities.
 * Compact CRC binds those capacities; a different profile cannot silently load.
 * Both committed and uncommitted records are supported. No storage I/O here. */
int vr_record_compact(const uint8_t *,const uint64_t *,uint8_t *);
int vr_record_expand(const uint8_t *,const uint64_t *,uint8_t *);
#endif
