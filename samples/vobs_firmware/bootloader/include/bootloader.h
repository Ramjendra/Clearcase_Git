/* $Header: /vobs/bootloader/include/bootloader.h@@/main/rel3/5 $ */
#ifndef BOOTLOADER_H
#define BOOTLOADER_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/security/include/security.h"
#include "/view/fw_migration_view/vobs/storage/include/storage.h"
namespace fw { namespace boot {
constexpr u32 BOOT_MAGIC       = 0xDEADBEEF;
constexpr u32 FW_HEADER_OFFSET = 0x0000;
constexpr u32 FW_IMAGE_OFFSET  = 0x1000;
struct FwHeader {
    u32 magic;
    u32 version;
    u32 size;
    u8  sha256[security::SHA256_DIGEST_SIZE];
    u8  signature[64];
};
class Bootloader {
public:
    Bootloader(storage::FlashStorage* flash, security::CryptoEngine* crypto);
    Status init();
    Status verifyImage();
    Status loadAndBoot();
    Status enterDfu();
private:
    storage::FlashStorage*  m_flash;
    security::CryptoEngine* m_crypto;
    FwHeader m_header{};
};
}} // namespace fw::boot
#endif
