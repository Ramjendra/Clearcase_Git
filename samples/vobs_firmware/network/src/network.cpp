/* $Id: network.cpp,v 5.2 2024/03/01 mary.jones $ */
#include "network/include/network.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace net {
Status NetworkStack::init(const NetConfig& cfg) {
    m_cfg = cfg;
    FW_LOG_INFO("NET", "Init IP=%d.%d.%d.%d port=%d",
        cfg.ip.bytes[0],cfg.ip.bytes[1],cfg.ip.bytes[2],cfg.ip.bytes[3], cfg.port);
    m_connected = true;
    return Status::OK;
}
Status NetworkStack::send(const u8* data, u32 len, const IpAddr& dest, u16 port)   { (void)data;(void)len;(void)dest;(void)port; return Status::OK; }
Status NetworkStack::receive(u8* buf, u32 bl, u32* rcv, u32 tms)                   { (void)buf;(void)bl;(void)tms; *rcv=0; return Status::OK; }
}} // namespace fw::net
