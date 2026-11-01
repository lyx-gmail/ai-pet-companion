#pragma once
#include <cstddef>

// Fixed-size USB development commands; no memory/profile or network credentials.
class PetDebug {
public:
    enum class Command { None, State, Main, MainHold, Feed, FeedHold, Pet, PetHold, MemoryDemo, QueryState, RequestFeed, WifiPause };
    constexpr Command Push(char c) {
        if (c=='\r') return Command::None;
        if (c=='\n') {
            Command result = Command::None;
            if (!discard_) {
                if (Is("pet.state")) result=Command::State;
                else if (Is("pet.main")) result=Command::Main;
                else if (Is("pet.main_hold")) result=Command::MainHold;
                else if (Is("pet.feed")) result=Command::Feed;
                else if (Is("pet.feed_hold")) result=Command::FeedHold;
                else if (Is("pet.pet")) result=Command::Pet;
                else if (Is("pet.pet_hold")) result=Command::PetHold;
                else if (Is("pet.memory_demo")) result=Command::MemoryDemo;
                else if (Is("pet.query_state")) result=Command::QueryState;
                else if (Is("pet.request_feed")) result=Command::RequestFeed;
                else if (Is("pet.wifi_pause")) result=Command::WifiPause;
            }
            size_=0; discard_=false;
            return result;
        }
        if (c<32 || c>126 || size_==sizeof(line_)) discard_=true;
        if (!discard_) line_[size_++]=c;
        return Command::None;
    }
private:
    char line_[24]{};
    std::size_t size_=0;
    bool discard_=false;
    constexpr bool Is(const char* text) const {
        std::size_t i=0;
        for (;i<size_;++i) if (!text[i] || line_[i]!=text[i]) return false;
        return !text[i];
    }
};
