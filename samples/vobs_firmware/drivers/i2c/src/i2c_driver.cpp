/* $Id: i2c_driver.cpp,v 2.0 2024/01/25 rmuller $ */
#include "drivers/i2c/include/i2c_driver.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace drivers {
I2cDriver::I2cDriver(hal::IHal* hal) : m_hal(hal) {}
Status I2cDriver::init(const I2cConfig& cfg) {
    FW_LOG_INFO("I2C", "Init freq=%lu", (unsigned long)cfg.freq_hz);
    m_initialized = true; return Status::OK;
}
Status I2cDriver::write(u8 addr, const u8* buf, u32 len)                        { (void)addr;(void)buf;(void)len; return Status::OK; }
Status I2cDriver::read(u8 addr, u8* buf, u32 len)                               { (void)addr;(void)buf;(void)len; return Status::OK; }
Status I2cDriver::writeRead(u8 a, const u8* w, u32 wl, u8* r, u32 rl)          { (void)a;(void)w;(void)wl;(void)r;(void)rl; return Status::OK; }
}} // namespace fw::drivers
