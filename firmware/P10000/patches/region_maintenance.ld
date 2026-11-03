ENTRY(any_region)
SECTIONS {
 .p_mt_write0 0x43b16eb0 : { *(.p_mt_write0) }
 .p_mt_write1 0x43b16edc : { *(.p_mt_write1) }
 .p_mt_check 0x43b1bdf8 : { *(.p_mt_check) }
 .p_mt_power 0x43b1c230 : { *(.p_mt_power) }
 .p_mt_status 0x43b1c600 : { *(.p_mt_status) }
 .p_mt_rw 0x43b1c948 : { *(.p_mt_rw) }
 .p_mt_check2 0x43b1ddf0 : { *(.p_mt_check2) }
 .p_mt_status_entry 0x43b20654 : { *(.p_mt_status_entry) }
 .p_region 0x43b2c794 : { *(.p_region) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
 ASSERT(SIZEOF(.p_mt_write0)<=0x2c,"write0 overflow")
 ASSERT(SIZEOF(.p_mt_write1)<=0x17c,"write1 overflow")
 ASSERT(SIZEOF(.p_mt_check)<=0x158,"check overflow")
 ASSERT(SIZEOF(.p_mt_power)<=0x3d0,"power overflow")
 ASSERT(SIZEOF(.p_mt_rw)<=0x198,"rw overflow")
 ASSERT(SIZEOF(.p_mt_check2)<=0x78,"check2 overflow")
 ASSERT(SIZEOF(.p_mt_status)<=0x23c,"status overflow")
 ASSERT(SIZEOF(.p_mt_status_entry)<=4,"status entry overflow")
 ASSERT(SIZEOF(.p_region)<=0x2f0,"region overflow")
 ASSERT(SIZEOF(.text)==0,"unexpected shared code")
 ASSERT(SIZEOF(.rodata)==0,"unexpected shared constants")
}
