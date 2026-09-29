#ifndef DRIVER_UART_H
#define DRIVER_UART_H

#include "hal/regs.h"

struct Stats {
    int tx;
    int rx;
};

struct Uart {
    struct Regs *regs;
    int baud;
    int errors;
    struct Stats stats;
};

int uart_init(struct Uart *u, struct Regs *regs, int baud);
int uart_send(struct Uart *u, const char *buf, int len);
int uart_errors(const struct Uart *u);

#endif
