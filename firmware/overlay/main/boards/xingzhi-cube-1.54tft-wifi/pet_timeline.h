#pragma once
#include "pet_state.h"
#include <array>

// Reconcile a delayed clock by replaying accepted events after the unknown
// pre-boot gap. No storage, network, or authorization happens in this type.
struct PetTimeline {
    enum Kind : uint32_t { Feed,Pet,Sleep,Wake,Chat };
    struct Event { uint32_t second=0;Kind kind=Feed; };
    static constexpr unsigned kCapacity=128;
    PetState anchor;
    uint64_t anchor_wall=0;
    std::array<Event,kCapacity> events{};
    unsigned count=0;
    bool pending=false;
    bool omitted=false;

    constexpr void Begin(const PetState& state,uint64_t wall) {
        anchor=state;anchor_wall=wall;count=0;
        pending=wall>=1704067200 && wall<=4102444800;
        omitted=wall!=0 && !pending;
        if (!pending) anchor_wall=0;
    }
    constexpr void FreezeUnknown() {
        // Bounded storage and a clockless restart cannot prove event timing.
        // Preserve the current state; never reinterpret unknown gaps as debt.
        pending=false;omitted=true;anchor_wall=0;count=0;
    }
    constexpr bool Record(Kind kind,uint64_t second) {
        if (!pending) return false;
        if (kind>Chat || second>UINT32_MAX || count==kCapacity ||
                (count && second<events[count-1].second)) {
            FreezeUnknown();return false;
        }
        events[count++]={static_cast<uint32_t>(second),kind};return true;
    }
    constexpr bool Resolve(PetState& current,uint64_t wall,uint64_t elapsed) {
        if (!pending || wall<1704067200 || wall>4102444800) return false;
        if (elapsed>UINT32_MAX || (count && elapsed<events[count-1].second)) {
            FreezeUnknown();return false;
        }
        const uint64_t accounted=anchor_wall+elapsed;
        const uint64_t missing=wall>accounted ? wall-accounted : 0;
        PetState replay=anchor;
        replay.AdvanceOffline(missing>7*86400 ? 7*86400 : static_cast<uint32_t>(missing));
        uint32_t previous=0;
        for (unsigned i=0;i<count;++i) {
            const auto& event=events[i];
            replay.Advance(event.second-previous);previous=event.second;
            switch (event.kind) {
                case Feed:replay.Feed();break;
                case Pet:replay.Pet();break;
                case Sleep:replay.SetSleeping(true);break;
                case Wake:replay.SetSleeping(false);break;
                case Chat:replay.Chat();break;
            }
        }
        replay.Advance(static_cast<uint32_t>(elapsed)-previous);
        replay.revision=current.revision+1;
        current=replay;pending=false;count=0;anchor_wall=0;
        return true;
    }
};
