/* $Id: spi_driver.cpp,v 2.1 2024/01/20 build_svc $ */
#include "drivers/spi/include/spi_driver.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace drivers {
SpiDriver::SpiDriver(hal::IHal* hal) : m_hal(hal) {}
Status SpiDriver::init(const SpiConfig& cfg) {
    FW_LOG_INFO("SPI", "Init freq=%lu mode=%d", (unsigned long)cfg.freq_hz, cfg.mode);
    m_initialized = true; return Status::OK;
}
Status SpiDriver::transfer(const u8* tx, u8* rx, u32 len) { (void)tx;(void)rx;(void)len; return Status::OK; }
Status SpiDriver::csAssert(bool a)                         { (void)a; return Status::OK; }
}} // namespace fw::drivers
