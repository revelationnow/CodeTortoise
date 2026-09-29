#include "service/logger.h"

static struct Regs g_regs;
static struct Uart g_uart;
static struct Logger g_log;

int main(void)
{
    uart_init(&g_uart, &g_regs, 115200);
    logger_init(&g_log, &g_uart);
    logger_write(&g_log, "hello", 5);
    logger_flush(&g_log);
    return uart_errors(&g_uart);
}
