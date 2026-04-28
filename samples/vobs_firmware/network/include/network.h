/* $Header: /vobs/network/include/network.h@@/main/5 $ */
#ifndef NETWORK_H
#define NETWORK_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/drivers/uart/include/uart_driver.h"
namespace fw { namespace net {
struct IpAddr { u8 bytes[4]; };
struct NetConfig { IpAddr ip; IpAddr gateway; IpAddr netmask; u16 port; };
class NetworkStack {
public:
    Status init(const NetConfig& cfg);
    Status send(const u8* data, u32 len, const IpAddr& dest, u16 port);
    Status receive(u8* buf, u32 buf_len, u32* received, u32 timeout_ms);
    bool   isConnected() const { return m_connected; }
private:
    bool m_connected{false};
    NetConfig m_cfg{};
};
}} // namespace fw::net
#endif
