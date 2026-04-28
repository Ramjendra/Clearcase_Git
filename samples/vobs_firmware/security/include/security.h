/* $Header: /vobs/security/include/security.h@@/main/rel2_bugfix/4 $ */
#ifndef SECURITY_H
#define SECURITY_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
namespace fw { namespace security {
constexpr u32 AES_BLOCK_SIZE = 16;
constexpr u32 SHA256_DIGEST_SIZE = 32;
class CryptoEngine {
public:
    Status init();
    Status aesEncrypt(const u8* key, u32 key_len, const u8* in, u8* out, u32 len);
    Status aesDecrypt(const u8* key, u32 key_len, const u8* in, u8* out, u32 len);
    Status sha256(const u8* data, u32 len, u8 digest[SHA256_DIGEST_SIZE]);
    Status verifySignature(const u8* data, u32 len, const u8* sig, u32 sig_len);
};
}} // namespace fw::security
#endif
