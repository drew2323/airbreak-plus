.syntax unified
.thumb

.section .rodata.st_ibr_abi, "a", %progbits
.balign 4

/* Custom settings supplies RXW's ID. Unassigned keeps stock fixed-rate ST. */
.global st_ibr_enable_var_id
.type st_ibr_enable_var_id, %object
st_ibr_enable_var_id:
    .short 0xffff
