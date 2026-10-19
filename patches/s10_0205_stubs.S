// SX584-0205 firmware function addresses

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
NSTUB(0x080A1691, file_get_size)

// UART metadata and formatting
NSTUB(0x08004101, ccx_get_globals)
NSTUB(0x0803ED97, variable_handler_get_uart_name)
NSTUB(0x0803EE8B, variable_handler_wire_width)
NSTUB(0x08046147, string_id_lookup_current_locale)
NSTUB(0x08045FB5, strlen_fast)
NSTUB(0x08046565, snprintf)
NSTUB(0x0804FF43, format_hex_u16)
NSTUB(0x0804FF6B, format_fixed_width_hex)
NSTUB(0x080BCFED, parse_hex_u16)
