/* $Id: bootloader.cpp,v 5.2 2024/03/12 admin $ */
#include "bootloader/include/bootloader.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace boot {
Bootloader::Bootloader(storage::FlashStorage* f, security::CryptoEngine* c) : m_flash(f), m_crypto(c) {}
Status Bootloader::init() {
    FW_LOG_INFO("BOOT","Init");
    return m_flash->init();
}
Status Bootloader::verifyImage() {
    u8 header_buf[sizeof(FwHeader)];
    Status s = m_flash->read(FW_HEADER_OFFSET, header_buf, sizeof(header_buf));
    if (s != Status::OK) return s;
    FwHeader* hdr = reinterpret_cast<FwHeader*>(header_buf);
    if (hdr->magic != BOOT_MAGIC) { FW_LOG_ERROR("BOOT","Bad magic 0x%08lx",(unsigned long)hdr->magic); return Status::ERR_HARDWARE; }
    FW_LOG_INFO("BOOT","Image v%lu size=%lu",(unsigned long)hdr->version,(unsigned long)hdr->size);
    return Status::OK;
}
Status Bootloader::loadAndBoot() { FW_LOG_INFO("BOOT","Booting firmware"); return Status::OK; }
Status Bootloader::enterDfu()    { FW_LOG_INFO("BOOT","DFU mode"); return Status::OK; }
}} // namespace fw::boot
