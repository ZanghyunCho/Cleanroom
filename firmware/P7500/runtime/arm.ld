ENTRY(vr_init)
SECTIONS {
    /* Isolated emulator placement only. This is not an approved printer RAM
       allocation and must not be used as a flash-image patch address. */
    . = 0x45000000;
    .text : { KEEP(*(.text*)) }
    .rodata : { KEEP(*(.rodata*)) }
    .ARM.exidx : { *(.ARM.exidx*) }
    .ARM.extab : { *(.ARM.extab*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.comment) *(.note*) }
}
