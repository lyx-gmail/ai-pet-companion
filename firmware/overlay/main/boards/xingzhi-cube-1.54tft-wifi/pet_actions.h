#pragma once
#include "pet_state.h"
#include <array>

// Request identity comes from the transport adapter, never model arguments.
// Keep the last 64 IDs; reject anything behind the window rather than replay it.
// Connection-scoped only: this is not a cross-reboot transaction journal.
struct PetActions {
    enum class Code { Ok,Cooldown,Full,Asleep,Busy,Invalid,Duplicate };
    enum class Action { Feed,Pet,SetSleep };
    struct Result {
        Code code = Code::Invalid;
        int delta = 0;
        Code original = Code::Invalid;
        uint32_t revision = 0;
    };
    struct Entry { uint32_t id = 0; bool valid = false; Result result; };
    std::array<Entry,64> entries{};
    uint32_t epoch = 0;
    uint32_t highest = 0;

    constexpr Result Apply(PetState& state,uint32_t channel,uint32_t id,bool petting,bool allowed) {
        return Apply(state,channel,id,petting ? Action::Pet : Action::Feed,allowed);
    }
    constexpr Result Apply(PetState& state,uint32_t channel,uint32_t id,Action action,bool allowed) {
        if (!allowed) return {Code::Busy,0,Code::Busy,state.revision};
        if (!channel || !id || id>0x7fffffff) return {Code::Invalid,0,Code::Invalid,state.revision};
        if (channel!=epoch) { entries = {}; epoch = channel; highest = id; }
        if (id<=highest && highest-id>=entries.size())
            return {Code::Invalid,0,Code::Invalid,state.revision};
        auto& entry = entries[id%entries.size()];
        if (entry.valid && entry.id==id)
            return {Code::Duplicate,0,entry.result.code,entry.result.revision};
        if (id>highest) highest = id;
        if (action==Action::SetSleep) {
            Result result{Code::Ok,0,Code::Ok,state.revision};
            entry = {id,true,result};
            return result;
        }
        const bool petting = action==Action::Pet;
        const int before = petting ? state.mood : state.satiety;
        const auto changed = petting ? state.Pet() : state.Feed();
        Code code = Code::Full;
        if (changed==PetState::Result::Ok) code = Code::Ok;
        else if (changed==PetState::Result::Cooldown) code = Code::Cooldown;
        else if (changed==PetState::Result::Sleeping) code = Code::Asleep;
        Result result{code,(petting ? state.mood : state.satiety)-before,code,state.revision};
        entry = {id,true,result};
        return result;
    }
    static constexpr const char* Name(Code code) {
        switch (code) {
            case Code::Ok: return "OK";
            case Code::Cooldown: return "COOLDOWN";
            case Code::Full: return "FULL";
            case Code::Asleep: return "ASLEEP";
            case Code::Busy: return "BUSY";
            case Code::Duplicate: return "DUPLICATE";
            default: return "INVALID";
        }
    }
};
