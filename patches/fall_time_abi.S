.syntax unified
.thumb

.section .rodata.fall_time_abi, "a", %progbits
.balign 4

/* Custom settings supplies the duration ID. Unassigned retains stock fall time. */
.global fall_time_duration_var_id
.type fall_time_duration_var_id, %object
fall_time_duration_var_id:
    .short 0xffff
