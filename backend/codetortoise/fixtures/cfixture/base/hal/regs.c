#include "hal/regs.h"

int hal_read(struct Regs *r, int reg)
{
    if (reg == REG_CTRL)
        return r->ctrl;
    return r->status;
}

int hal_write(struct Regs *r, int reg, int value)
{
    if (reg == REG_CTRL)
        r->ctrl = value;
    else
        r->status = value;
    return 0;
}
