#include "service/logger.h"

int logger_init(struct Logger *lg, struct Uart *u)
{
    lg->uart = u;
    lg->dropped = 0;
    lg->level = 1;
    return 0;
}

int logger_write(struct Logger *lg, const char *msg, int len)
{
    if (uart_send(lg->uart, msg, len) != 0) {
        lg->dropped++;
        return -1;
    }
    return 0;
}

void logger_flush(struct Logger *lg)
{
    uart_send(lg->uart, "\n", 1);
}

int logger_level(const struct Logger *lg)
{
    return lg->level;
}
