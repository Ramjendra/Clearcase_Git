/*
 * $Header: /vobs/hal/include/hal.h@@/main/rel2_bugfix/7 2024/02/20 11:30:00 mary.jones $
 * Hardware Abstraction Layer — interface for all hardware drivers.
 */
#ifndef HAL_H
#define HAL_H

#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h@@/main/2"
#include <cstdint>

namespace fw {
namespace hal {

struct GpioConfig {
    u8  pin;
    bool output;
    bool pull_up;
};

struct ClockConfig {
    u32 freq_hz;
    u8  pll_multiplier;
    u8  pll_divider;
};

class IHal {
public:
    virtual ~IHal() = default;
    virtual Status init()                          = 0;
    virtual Status gpioInit(const GpioConfig& cfg) = 0;
    virtual Status gpioWrite(u8 pin, bool val)     = 0;
    virtual bool   gpioRead(u8 pin)                = 0;
    virtual Status clockInit(const ClockConfig& cfg) = 0;
    virtual u32    getTickMs()                     = 0;
    virtual void   delayMs(u32 ms)                 = 0;
};

IHal* getHal();

} // namespace hal
} // namespace fw

#endif // HAL_H
