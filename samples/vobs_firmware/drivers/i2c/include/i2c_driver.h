/* $Header: /vobs/drivers/i2c/include/i2c_driver.h@@/main/2 $ */
#ifndef I2C_DRIVER_H
#define I2C_DRIVER_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/hal/include/hal.h"
namespace fw { namespace drivers {
struct I2cConfig { u32 freq_hz; bool ten_bit_addr; };
class I2cDriver {
public:
    explicit I2cDriver(hal::IHal* hal);
    Status init(const I2cConfig& cfg);
    Status write(u8 addr, const u8* buf, u32 len);
    Status read(u8 addr, u8* buf, u32 len);
    Status writeRead(u8 addr, const u8* wr, u32 wr_len, u8* rd, u32 rd_len);
private:
    hal::IHal* m_hal;
    bool       m_initialized{false};
};
}} // namespace fw::drivers
#endif
