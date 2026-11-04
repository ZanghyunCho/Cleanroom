/* Isolate V3's two cache normalizers while retaining V2's control procedures. */
SECTIONS {
 .ink_info 0x43b1fef4 : { KEEP(*(.ink_info)) }
 .ink_status 0x43b20014 : { KEEP(*(.ink_status)) }
 /DISCARD/ : { *(.ink_*) *(.chip_*) *(.text*) *(.data*) *(.bss*)
              *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
 ASSERT(SIZEOF(.ink_info)<=0xf0,"info normalizer exceeds original function")
 ASSERT(SIZEOF(.ink_status)<=0x9c,"status normalizer exceeds original function")
}
