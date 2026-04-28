/* $Header: /vobs/drivers/spi/include/spi_driver.h@@/main/2 $ */
#ifndef SPI_DRIVER_H
#define SPI_DRIVER_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/hal/include/hal.h"

namespace fw { namespace drivers {
struct SpiConfig { u32 freq_hz; u8 mode; bool lsb_first; };
class SpiDriver {
public:
    explicit SpiDriver(hal::IHal* hal);
    Status init(const SpiConfig& cfg);
    Status transfer(const u8* tx, u8* rx, u32 len);
    Status csAssert(bool assert_low);
private:
    hal::IHal* m_hal;
    bool       m_initialized{false};
};
}} // namespace fw::drivers
#endif
