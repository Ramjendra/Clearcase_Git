/* $Header: /vobs/drivers/uart/include/uart_driver.h@@/main/3 $ */
#ifndef UART_DRIVER_H
#define UART_DRIVER_H

#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h@@/main/2"
#include "/view/fw_migration_view/vobs/hal/include/hal.h@@/main/rel2_bugfix/7"

namespace fw { namespace drivers {

struct UartConfig { u32 baud; u8 data_bits; u8 stop_bits; bool parity; };

class UartDriver {
public:
    explicit UartDriver(hal::IHal* hal);
    Status init(const UartConfig& cfg);
    Status write(const u8* buf, u32 len);
    Status read(u8* buf, u32 len, u32 timeout_ms);
    Status flush();
private:
    hal::IHal* m_hal;
    UartConfig m_cfg{};
    bool       m_initialized{false};
};

}} // namespace fw::drivers
#endif
