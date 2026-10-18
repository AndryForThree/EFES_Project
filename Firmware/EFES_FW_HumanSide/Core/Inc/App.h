#ifndef APP_H
#define APP_H

/* Call Init after GPIO and UI initialization, then Process in the superloop. */
void App_Init(void);
void App_Process(void);

#endif
