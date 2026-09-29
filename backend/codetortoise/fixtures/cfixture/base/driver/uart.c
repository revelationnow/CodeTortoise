#include "driver/uart.h"

int uart_init(struct Uart *u, struct Regs *regs, int baud)
{
    u->regs = regs;
    u->baud = baud;
    u->errors = 0;
    return hal_write(regs, REG_CTRL, baud);
}

int uart_send(struct Uart *u, const char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++)
        hal_write(u->regs, REG_STATUS, buf[i]);
    return 0;
}

int uart_errors(const struct Uart *u)
{
    return u->errors;
}
