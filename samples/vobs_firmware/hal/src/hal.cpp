/*
 * $Id: hal.cpp,v 2.7 2024/02/20 mary.jones $
 * HAL implementation — wraps bare-metal register access.
 */
#include "hal/include/hal.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"

namespace fw {
namespace hal {

class HalImpl : public IHal {
public:
    Status init() override {
        FW_LOG_INFO("HAL", "Hardware init");
        return Status::OK;
    }
    Status gpioInit(const GpioConfig& cfg) override {
        FW_LOG_DEBUG("HAL", "GPIO pin %d dir=%s", cfg.pin, cfg.output ? "OUT" : "IN");
        return Status::OK;
    }
    Status gpioWrite(u8 pin, bool val) override { (void)pin; (void)val; return Status::OK; }
    bool   gpioRead(u8 pin) override             { (void)pin; return false; }
    Status clockInit(const ClockConfig& cfg) override {
        FW_LOG_INFO("HAL", "Clock %lu Hz", (unsigned long)cfg.freq_hz);
        return Status::OK;
    }
    u32  getTickMs() override { return 0; }
    void delayMs(u32 ms) override { (void)ms; }
};

static HalImpl g_hal;
IHal* getHal() { return &g_hal; }

} // namespace hal
} // namespace fw
