#pragma once
#include "pet_state.h"
#include <array>
#include <cstddef>

// Explicit little-endian format: no compiler padding, pointers or raw-struct persistence.
struct PetSnapshot {
    static constexpr size_t kSize = 92;
    static constexpr size_t kV2Size = 88;
    static constexpr size_t kLegacySize = 84;
    using Bytes = std::array<uint8_t,kSize>;
    PetState state;
    uint64_t saved_wall = 0;
    uint32_t last_volume = 60;
    bool muted = false;
    uint32_t brightness = 75;
    bool sleep_pending = false;

    static constexpr void Put(Bytes& bytes,size_t index,uint32_t word) {
        for (size_t i=0;i<4;++i) bytes[index*4+i] = static_cast<uint8_t>(word>>(8*i));
    }
    static constexpr uint32_t Get(const Bytes& bytes,size_t index) {
        uint32_t word = 0;
        for (size_t i=0;i<4;++i) word |= uint32_t(bytes[index*4+i])<<(8*i);
        return word;
    }
    constexpr Bytes Encode() const {
        Bytes b{};
        const uint32_t words[] = {0x31544550,3,uint32_t(state.satiety),uint32_t(state.mood),
            uint32_t(state.energy),state.satiety_elapsed,state.mood_elapsed,state.awake_energy_elapsed,
            state.sleep_energy_elapsed,uint32_t(state.closeness),state.window_seconds,state.since_interaction,
            state.feed_cooldown,state.pet_cooldown,state.interactions,uint32_t(state.sleeping),state.revision,
            uint32_t(saved_wall),uint32_t(saved_wall>>32),last_volume,uint32_t(muted),brightness,uint32_t(sleep_pending)};
        for (size_t i=0;i<23;++i) Put(b,i,words[i]);
        return b;
    }
    static constexpr bool Decode(const Bytes& b,PetSnapshot& output) {
        if (Get(b,0)!=0x31544550 || Get(b,1)!=3 || Get(b,21)<10 || Get(b,21)>100 || Get(b,22)>1) return false;
        if (Get(b,2)>100 || Get(b,3)>100 || Get(b,4)>100 ||
            Get(b,5)>=3600 || Get(b,6)>=3600 || Get(b,7)>=900 || Get(b,8)>=300 ||
            Get(b,9)<10 || Get(b,9)>100 || Get(b,10)>=86400 || Get(b,11)>600 ||
            Get(b,12)>60 || Get(b,13)>10 || Get(b,14)>3 || Get(b,15)>1 ||
            Get(b,19)<1 || Get(b,19)>100 || Get(b,20)>1) return false;
        const uint64_t wall = uint64_t(Get(b,17)) | (uint64_t(Get(b,18))<<32);
        if (wall && (wall<1704067200 || wall>4102444800)) return false; // 2024..2100 or unknown
        PetSnapshot p;
        p.state.satiety = Get(b,2); p.state.mood = Get(b,3); p.state.energy = Get(b,4);
        p.state.satiety_elapsed = Get(b,5); p.state.mood_elapsed = Get(b,6);
        p.state.awake_energy_elapsed = Get(b,7); p.state.sleep_energy_elapsed = Get(b,8);
        p.state.closeness = Get(b,9); p.state.window_seconds = Get(b,10);
        p.state.since_interaction = Get(b,11); p.state.feed_cooldown = Get(b,12);
        p.state.pet_cooldown = Get(b,13); p.state.interactions = Get(b,14);
        p.state.sleeping = Get(b,15); p.state.revision = Get(b,16);
        p.saved_wall = wall; p.last_volume = Get(b,19); p.muted = Get(b,20);
        p.brightness = Get(b,21);
        p.sleep_pending = Get(b,22);
        output = p;
        return true;
    }
    static constexpr bool DecodeSized(const Bytes& bytes,size_t length,PetSnapshot& output) {
        if (length==kSize) return Decode(bytes,output);
        const bool v1 = length==kLegacySize && Get(bytes,1)==1;
        const bool v2 = length==kV2Size && Get(bytes,1)==2;
        if (!v1 && !v2) return false;
        // V1 has no brightness; V2 has no committed sleep intent.
        Bytes migrated = bytes;
        Put(migrated,1,3); Put(migrated,22,0);
        if (v1) Put(migrated,21,75);
        return Decode(migrated,output);
    }
};
