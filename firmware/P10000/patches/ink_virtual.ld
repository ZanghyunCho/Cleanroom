ENTRY(ink_refresh)
SECTIONS {
 .ink_check 0x43b19424 : { *(.ink_check) }
 .ink_refresh 0x43b199a8 : { *(.ink_refresh) }
 .ink_state 0x43b1a100 : { *(.ink_state) }
 .ink_detect 0x43b1ab7c : { *(.ink_detect) }
 .ink_presence 0x43b1b328 : { *(.ink_presence) }
 .ink_rw 0x43b1b450 : { *(.ink_rw) }
 .ink_power 0x43b1ce48 : { *(.ink_power) }
 .chip_read 0x43b1cf00 : { *(.chip_read) }
 .chip_write 0x43b1d000 : { *(.chip_write) }
 .chip_reset 0x43b1d100 : { *(.chip_reset) }
 .ink_info 0x43b1d300 : { *(.ink_info) }
 .ink_status 0x43b1d600 : { *(.ink_status) }
 .ink_ensure 0x43b1d900 : { *(.ink_ensure) }
 .ink_flush 0x43b1e274 : { *(.ink_flush) }
 .ink_info_entry 0x43b1fef4 : { *(.ink_info_entry) }
 .ink_status_entry 0x43b20014 : { *(.ink_status_entry) }
 .ink_read_entry 0x43b2aa4c : { *(.ink_read_entry) }
 .ink_write_entry 0x43b2d3c4 : { *(.ink_write_entry) }
 .ink_ils 0x43b3f3a4 : { *(.ink_ils) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
 ASSERT(SIZEOF(.ink_refresh)<=0x758,"refresh overflow")
 ASSERT(SIZEOF(.ink_state)==1684,"state size")
 ASSERT(SIZEOF(.ink_detect)<=0x35c,"detect overflow")
 ASSERT(SIZEOF(.ink_presence)<=0xa4,"presence overflow")
 ASSERT(SIZEOF(.ink_check)<=0x200,"check overflow")
 ASSERT(SIZEOF(.ink_rw)<=0x1f8,"rw overflow")
 ASSERT(SIZEOF(.ink_power)<=0xb8,"power overflow")
 ASSERT(SIZEOF(.chip_read)<=0x100,"read overflow")
 ASSERT(SIZEOF(.chip_write)<=0x100,"write overflow")
 ASSERT(SIZEOF(.chip_reset)<=0x200,"reset overflow")
 ASSERT(SIZEOF(.ink_info)<=0x300,"info overflow")
 ASSERT(SIZEOF(.ink_status)<=0x300,"status overflow")
 ASSERT(SIZEOF(.ink_flush)<=0x4c,"flush overflow")
 ASSERT(SIZEOF(.ink_ensure)<=0x100,"ensure overflow")
 ASSERT(SIZEOF(.ink_ils)<=8,"ils overflow")
}
