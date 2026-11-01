#pragma once
#include <cstdint>

struct PetSleep {
    bool pending = false;
    uint32_t epoch = 0;
    uint32_t stop_serial = 0;
    int64_t deadline_ms = 0;
    int64_t stopped_ms = -1;
    constexpr void Request(int64_t now,uint32_t channel,uint32_t serial) {
        if (pending) return;
        pending = true; epoch = channel; stop_serial = serial;
        deadline_ms = now+5000; stopped_ms = -1;
    }
    constexpr bool Ready(int64_t now,uint32_t channel,uint32_t serial,bool drained) {
        if (!pending) return false;
        if (now>=deadline_ms) return true;
        if (channel!=epoch) return false;
        if (serial!=stop_serial && stopped_ms<0) stopped_ms = now;
        return stopped_ms>=0 && now-stopped_ms>=200 && drained;
    }
    constexpr void Clear() { pending = false; }
};
