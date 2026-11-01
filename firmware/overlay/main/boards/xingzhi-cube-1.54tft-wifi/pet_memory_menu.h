#pragma once
#include "pet_menu.h"

// Pure UI transitions. No network/storage operation runs from navigation alone.
struct PetMemoryMenu {
    enum class Phase { Closed,Loading,Browse,Creating,Pending,Committing,Uncertain,Error,Done,Help };
    enum Action { None,Load,Create,Confirm,Cancel,Back };
    Phase phase=Phase::Closed;
    int page=0;
    bool valid=false;
    bool unresolved=false;
    unsigned present=0;
    uint64_t generation=0;
    int64_t deadline=0;

    constexpr Action Open() {
        ++generation;valid=false;present=0;page=0;
        phase=unresolved ? Phase::Uncertain : Phase::Loading;
        return unresolved ? None : Load;
    }
    constexpr void Close() { ++generation;phase=Phase::Closed;valid=false;present=0; }
    constexpr void Loaded(unsigned mask) { valid=true;present=mask&31;phase=Phase::Browse; }
    constexpr void Draft(int64_t now,int seconds) { phase=Phase::Pending;deadline=now+seconds; }
    constexpr void Failed(Action action,bool definite) {
        valid=false;present=0;
        if (action==Confirm && !definite) { unresolved=true;phase=Phase::Uncertain; }
        else { unresolved=false;phase=Phase::Error; }
    }
    constexpr Action Timeout(int64_t now) {
        if (phase!=Phase::Pending || now<deadline) return None;
        valid=false;present=0;phase=Phase::Loading;
        return Cancel;
    }
    constexpr Action Press(PetMenu::Key key,bool held,int64_t now) {
        if (held) {
            if (key!=PetMenu::Key::Main) return None;
            Close();return Back;
        }
        if (phase==Phase::Pending) {
            if (key!=PetMenu::Key::Main || now>=deadline) {
                valid=false;present=0;phase=Phase::Loading;return Cancel;
            }
            valid=false;present=0;unresolved=true;phase=Phase::Committing;return Confirm;
        }
        if (phase==Phase::Uncertain) {
            if (key==PetMenu::Key::Main) { phase=Phase::Committing;return Confirm; }
            Close();return Back;
        }
        if (phase==Phase::Error || phase==Phase::Done) {
            if (key==PetMenu::Key::Main) { phase=Phase::Loading;return Load; }
            Close();return Back;
        }
        if (phase==Phase::Help) { phase=Phase::Browse;return None; }
        if (phase!=Phase::Browse || !valid) return None;
        if (key!=PetMenu::Key::Main) { page=(page+(key==PetMenu::Key::Feed ? 7 : 1))%8;return None; }
        if (page==7) { Close();return Back; }
        if (page==6) { phase=Phase::Help;return None; }
        if (page<5 && !(present&(1u<<page))) return None;
        phase=Phase::Creating;return Create;
    }
};
