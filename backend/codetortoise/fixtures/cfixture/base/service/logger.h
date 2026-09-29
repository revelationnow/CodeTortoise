#ifndef SERVICE_LOGGER_H
#define SERVICE_LOGGER_H

#include "driver/uart.h"

struct Logger {
    struct Uart *uart;
    int dropped;
};

int logger_init(struct Logger *lg, struct Uart *u);
int logger_write(struct Logger *lg, const char *msg, int len);
void logger_flush(struct Logger *lg);

#endif
