#ifndef UI_HEADER_H
#define UI_HEADER_H

#include <stdbool.h>
#include <stdint.h>

/* Shared secondary-page header. Title must remain valid until drawing ends.
 * Page numbers are one-based and include Home; count is the actual page count.
 */
void UI_Header_Reset(const char *title, uint8_t page, uint8_t count);
bool UI_Header_Process(void);

#endif
