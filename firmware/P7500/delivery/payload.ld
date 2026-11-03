ENTRY(payload_layout)
SECTIONS {
 . = 0x433f7af8;
 .text : { *(.text*) }
 .rodata : { KEEP(*(.roots)) *(.rodata*) }
 .data : { *(.data*) }
 .ARM.exidx : { *(.ARM.exidx*) }
 .ARM.extab : { *(.ARM.extab*) }
 .bss : { *(.bss*) *(COMMON) }
 payload_end = .;
 ASSERT(payload_end <= 0x433fd090, "Payload exceeds retired chip-code region")
 /DISCARD/ : { *(.comment) *(.note*) }
}
