/* $Id: uart_driver.cpp,v 3.1 2024/01/15 rmuller $ */
#include "drivers/uart/include/uart_driver.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"

namespace fw { namespace drivers {

UartDriver::UartDriver(hal::IHal* hal) : m_hal(hal) {}

Status UartDriver::init(const UartConfig& cfg) {
    m_cfg = cfg;
    FW_LOG_INFO("UART", "Init baud=%lu", (unsigned long)cfg.baud);
    m_initialized = true;
    return Status::OK;
}
Status UartDriver::write(const u8* buf, u32 len)               { (void)buf;(void)len; return m_initialized ? Status::OK : Status::ERR_NOT_INITIALIZED; }
Status UartDriver::read(u8* buf, u32 len, u32 timeout_ms)      { (void)buf;(void)len;(void)timeout_ms; return Status::OK; }
Status UartDriver::flush()                                      { return Status::OK; }

}} // namespace fw::drivers
