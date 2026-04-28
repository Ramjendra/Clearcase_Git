/*
 * $Header: /vobs/shared_libs/include/fw_types.h@@/main/2 $
 * Common firmware types — shared across ALL 15 VOBs.
 */
#ifndef SHARED_LIBS_FW_TYPES_H
#define SHARED_LIBS_FW_TYPES_H

#include <cstdint>
#include <cstddef>

namespace fw {

using u8  = uint8_t;
using u16 = uint16_t;
using u32 = uint32_t;
using u64 = uint64_t;
using i8  = int8_t;
using i16 = int16_t;
using i32 = int32_t;
using i64 = int64_t;

enum class Status {
    OK = 0,
    ERR_TIMEOUT,
    ERR_BUSY,
    ERR_INVALID_PARAM,
    ERR_NOT_INITIALIZED,
    ERR_HARDWARE,
    ERR_NO_MEMORY,
};

template<typename T>
struct Result {
    Status status;
    T      value;
    bool ok() const { return status == Status::OK; }
};

} // namespace fw

#endif // SHARED_LIBS_FW_TYPES_H
