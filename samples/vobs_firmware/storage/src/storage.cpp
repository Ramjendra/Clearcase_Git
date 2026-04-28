/* $Id: storage.cpp,v 3.3 2024/02/10 build_svc $ */
#include "storage/include/storage.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace storage {
FlashStorage::FlashStorage(drivers::SpiDriver* spi) : m_spi(spi) {}
Status FlashStorage::init()                                  { FW_LOG_INFO("FLASH","Init 16MB"); m_initialized=true; return Status::OK; }
Status FlashStorage::read(u32 a, u8* b, u32 l)               { (void)a;(void)b;(void)l; return Status::OK; }
Status FlashStorage::write(u32 a, const u8* b, u32 l)        { (void)a;(void)b;(void)l; return Status::OK; }
Status FlashStorage::erase(u32 a, u32 l)                     { FW_LOG_INFO("FLASH","Erase addr=0x%08lx len=%lu",(unsigned long)a,(unsigned long)l); return Status::OK; }
}} // namespace fw::storage
