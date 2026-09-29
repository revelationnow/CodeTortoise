#ifndef HAL_REGS_H
#define HAL_REGS_H

#define REG_CTRL 0
#define REG_STATUS 1

struct Regs {
    int ctrl;
    int status;
};

int hal_read(struct Regs *r, int reg);
int hal_write(struct Regs *r, int reg, int value);

#endif
