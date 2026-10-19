// SX584-0204 firmware function addresses

#define NSTUB(addr,name) \
	.global name; \
	.type name, %function; \
	name = addr

.text

// Memory and clinical menus
NSTUB(0x0803B435, malloc)
NSTUB(0x080408F1, memcpy_unrolled)
NSTUB(0x080379C9, gui_create_menus)
NSTUB(0x0803CBAF, scrollbar_init)
NSTUB(0x0803C6A5, scrollbar_add_item)
NSTUB(0x0803B1B9, variable_0x1bc_and_0x1bd_writer_setup)
NSTUB(0x0803CE59, gui_create_back_button)
NSTUB(0x0803D7E9, menu_create_text_or_float)
NSTUB(0x0803E585, menu_create_numeric_var)
NSTUB(0x0803DA69, menu_create_static_string)

// Variable access and config storage
NSTUB(0x0803F1A1, variable_get_by_id)
NSTUB(0x0803EC6D, variable_lookup_handler)
NSTUB(0x0803EC89, variable_handler_release)
NSTUB(0x0803EF4D, variable_set_visible_from_handler)
NSTUB(0x080A13B1, file_get_size)
