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
    struct Stats *st = &u->stats;
    int *err = &u->errors;
    if (len > 64) {
        *err += 1;
        return -2;
    }
    for (i = 0; i < len; i++) {
        hal_write(u->regs, REG_STATUS, buf[i]);
        st->tx++;
    }
    return 0;
}

int uart_errors(const struct Uart *u)
{
    return u->errors;
}
