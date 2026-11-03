ENTRY(chip_read)
SECTIONS {
 .chip_read 0x47000000 : { *(.chip_read) }
 .chip_write 0x47000100 : { *(.chip_write) }
 .chip_reset 0x47000200 : { *(.chip_reset) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
 ASSERT(SIZEOF(.chip_read)<=0x100,"read overflow")
 ASSERT(SIZEOF(.chip_write)<=0x100,"write overflow")
 ASSERT(SIZEOF(.chip_reset)<=0x200,"reset overflow")
}
