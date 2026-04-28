/* $Header: /vobs/storage/include/storage.h@@/main/rel3/3 $ */
#ifndef STORAGE_H
#define STORAGE_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/drivers/spi/include/spi_driver.h"
namespace fw { namespace storage {
class FlashStorage {
public:
    explicit FlashStorage(drivers::SpiDriver* spi);
    Status init();
    Status read(u32 addr, u8* buf, u32 len);
    Status write(u32 addr, const u8* buf, u32 len);
    Status erase(u32 addr, u32 len);
    u32    capacity() const { return 16 * 1024 * 1024; } // 16MB
private:
    drivers::SpiDriver* m_spi;
    bool m_initialized{false};
};
}} // namespace fw::storage
#endif
