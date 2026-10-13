#include "st7789.h"

#include "st7789_transport.h"
#include "st7789_graphics.h"

/* Controller details stay private; project configuration is in config.h. */
#define ST7789_COLMOD 0x3A
#define ST7789_MADCTL 0x36
#define ST7789_CASET  0x2A
#define ST7789_RASET  0x2B
#define ST7789_RAMWR  0x2C
#define ST7789_SLPOUT 0x11
#define ST7789_NORON  0x13
#define ST7789_DISPON 0x29
#define ST7789_INVON  0x21
#define ST7789_INVOFF 0x20
#define ST7789_MADCTL_MY  0x80
#define ST7789_MADCTL_MX  0x40
#define ST7789_MADCTL_MV  0x20
#define ST7789_MADCTL_RGB 0x00
#define ST7789_COLOR_MODE_16bit 0x55
/**
 * @brief Write command to ST7789 controller
 * @param cmd -> command to write
 * @return none
 */
static void ST7789_WriteCommand(uint8_t cmd)
{
    if (ST7789_TransportCommand(cmd) != HAL_OK)
        ST7789_GraphicsError();
}

/**
 * @brief Write data to ST7789 controller
 * @param buff -> pointer of data buffer
 * @param buff_size -> size of the data buffer
 * @return none
 */
static void ST7789_WriteData(const uint8_t *buff, size_t buff_size)
{
    if (ST7789_TransportData(buff, buff_size) != HAL_OK)
        ST7789_GraphicsError();
}
/**
 * @brief Write data to ST7789 controller, simplify for 8bit data.
 * data -> data to write
 * @return none
 */
static void ST7789_WriteSmallData(uint8_t data)
{
    ST7789_WriteData(&data, 1);
}

/**
 * @brief Set the rotation direction of the display
 * @param m -> rotation parameter(please refer it in st7789.h)
 * @return none
 */
ST7789_Result ST7789_SetRotation(uint8_t m)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (m != 1 && m != 3) return ST7789_INVALID_ARGUMENT;
	ST7789_WriteCommand(ST7789_MADCTL);	// MADCTL
	switch (m) {
	case 1:
		ST7789_WriteSmallData(ST7789_MADCTL_MY | ST7789_MADCTL_MV | ST7789_MADCTL_RGB);
		break;
	case 3:
		ST7789_WriteSmallData(ST7789_MADCTL_MX | ST7789_MADCTL_MV | ST7789_MADCTL_RGB);
		break;
	default:
		break;
	}
    return ST7789_GetState() == ST7789_STATE_ERROR ? ST7789_ERROR : ST7789_OK;
}

/**
 * @brief Set address of DisplayWindow
 * @param xi&yi -> coordinates of window
 * @return none
 */
ST7789_Result ST7789_BeginWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1)
{
	uint16_t x_start = x0, x_end = x1;
	uint16_t y_start = y0, y_end = y1;
	
	/* Column Address set */
	ST7789_WriteCommand(ST7789_CASET); 
	{
		uint8_t data[] = {x_start >> 8, x_start & 0xFF, x_end >> 8, x_end & 0xFF};
		ST7789_WriteData(data, sizeof(data));
	}

	/* Row Address set */
	ST7789_WriteCommand(ST7789_RASET);
	{
		uint8_t data[] = {y_start >> 8, y_start & 0xFF, y_end >> 8, y_end & 0xFF};
		ST7789_WriteData(data, sizeof(data));
	}
	/* Write to RAM */
	ST7789_WriteCommand(ST7789_RAMWR);
    if (ST7789_GetState() == ST7789_STATE_ERROR) return ST7789_ERROR;
    if (ST7789_TransportBeginPixels() != HAL_OK) {
        ST7789_GraphicsError();
        return ST7789_ERROR;
    }
    return ST7789_OK;
}

/**
 * @brief Initialize ST7789 controller
 * @param none
 * @return none
 */
ST7789_Result ST7789_Init(void)
{
    if (ST7789_GetState() == ST7789_STATE_BUSY) return ST7789_BUSY;
    if (ST7789_TransportInit() != HAL_OK) {
        ST7789_GraphicsReset(0);
        return ST7789_ERROR;
    }
    ST7789_GraphicsReset(1);
    /* External reset is released together with MCU nRST. */
    HAL_Delay(120);

    ST7789_WriteCommand(ST7789_COLMOD);		//	Set color mode
    ST7789_WriteSmallData(ST7789_COLOR_MODE_16bit);
  	ST7789_WriteCommand(0xB2);				//	Porch control
	{
		uint8_t data[] = {0x0C, 0x0C, 0x00, 0x33, 0x33};
		ST7789_WriteData(data, sizeof(data));
	}
	ST7789_SetRotation(ST7789_ROTATION);	//	MADCTL (Display Rotation)
	
	/* Internal LCD Voltage generator settings */
    ST7789_WriteCommand(0XB7);				//	Gate Control
    ST7789_WriteSmallData(0x35);			//	Default value
    ST7789_WriteCommand(0xBB);				//	VCOM setting
    ST7789_WriteSmallData(0x19);			//	0.725v (default 0.75v for 0x20)
    ST7789_WriteCommand(0xC0);				//	LCMCTRL	
    ST7789_WriteSmallData (0x2C);			//	Default value
    ST7789_WriteCommand (0xC2);				//	VDV and VRH command Enable
    ST7789_WriteSmallData (0x01);			//	Default value
    ST7789_WriteCommand (0xC3);				//	VRH set
    ST7789_WriteSmallData (0x12);			//	+-4.45v (defalut +-4.1v for 0x0B)
    ST7789_WriteCommand (0xC4);				//	VDV set
    ST7789_WriteSmallData (0x20);			//	Default value
    ST7789_WriteCommand (0xC6);				//	Frame rate control in normal mode
    ST7789_WriteSmallData (0x0F);			//	Default value (60HZ)
    ST7789_WriteCommand (0xD0);				//	Power control
    ST7789_WriteSmallData (0xA4);			//	Default value
    ST7789_WriteSmallData (0xA1);			//	Default value
	/**************** Division line ****************/

	ST7789_WriteCommand(0xE0);
	{
		uint8_t data[] = {0xD0, 0x04, 0x0D, 0x11, 0x13, 0x2B, 0x3F, 0x54, 0x4C, 0x18, 0x0D, 0x0B, 0x1F, 0x23};
		ST7789_WriteData(data, sizeof(data));
	}

    ST7789_WriteCommand(0xE1);
	{
		uint8_t data[] = {0xD0, 0x04, 0x0C, 0x11, 0x13, 0x2C, 0x3F, 0x44, 0x51, 0x2F, 0x1F, 0x1F, 0x20, 0x23};
		ST7789_WriteData(data, sizeof(data));
	}
    ST7789_InvertColors(ST7789_DEFAULT_INVERSION);
	ST7789_WriteCommand (ST7789_SLPOUT);	//	Out of sleep mode
    HAL_Delay(120);
  	ST7789_WriteCommand (ST7789_NORON);		//	Normal Display on
  	ST7789_WriteCommand (ST7789_DISPON);	//	Main screen turned on	

	HAL_Delay(50);
    if (ST7789_GetState() == ST7789_STATE_ERROR) ST7789_GraphicsReset(0);
    return ST7789_GetState() == ST7789_STATE_ERROR ? ST7789_ERROR : ST7789_OK;
}

ST7789_Result ST7789_InvertColors(uint8_t invert)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
	ST7789_WriteCommand(invert ? ST7789_INVON : ST7789_INVOFF);
    return ST7789_GetState() == ST7789_STATE_ERROR ? ST7789_ERROR : ST7789_OK;
}

ST7789_Result ST7789_TearEffect(uint8_t tear)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
	ST7789_WriteCommand(tear ? 0x35 /* TEON */ : 0x34 /* TEOFF */);
    return ST7789_GetState() == ST7789_STATE_ERROR ? ST7789_ERROR : ST7789_OK;
}

