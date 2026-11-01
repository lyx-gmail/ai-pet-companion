#pragma once
#include <cstdint>

// Scheduled Application thread only; no transcript, audio, or personal data retained.
struct PetConversation {
    uint32_t epoch=0, turn=0, playback=0;
    bool active=false, started=false, replied=false, stopped=false, cared=false;
    constexpr void Transcript(uint32_t e,uint32_t t,bool audio,uint32_t serial) {
        if(!audio || !t) { active=false; return; }
        if(epoch==e && t<=turn) return;
        epoch=e; turn=t; playback=serial;
        active=true; started=replied=stopped=cared=false;
    }
    constexpr void Start(uint32_t e,uint32_t serial) {
        if(active && epoch==e && !started) { started=true; playback=serial; }
    }
    constexpr void Reply(uint32_t e,bool nonempty) { if(active && epoch==e && nonempty) replied=true; }
    constexpr void Stop(uint32_t e) { if(active && epoch==e) stopped=true; }
    constexpr void Care(uint32_t e) { if(active && epoch==e) cared=true; }
    constexpr void Cancel() { active=false; }
    constexpr bool Complete(uint32_t e,uint32_t serial,bool drained,bool allowed) {
        if(e!=epoch || !allowed) { active=false; return false; }
        if(!active || !started || !replied || !stopped || serial==playback || !drained) return false;
        active=false;
        return !cared;
    }
};
