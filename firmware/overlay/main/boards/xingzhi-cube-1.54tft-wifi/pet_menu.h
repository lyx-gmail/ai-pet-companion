#pragma once
#include <cstdint>

// Pure UI state. Driver changes occur only in PetRuntime after these transitions.
struct PetMenu {
    enum class Key { Main,Feed,Pet };
    enum class Mode { Closed,List,Edit,Memory,Diagnostics };
    enum Effect { None,Preview,Commit,Close };
    Mode mode = Mode::Closed;
    int page = 0;
    int diagnostic_page = 0;
    int volume = 60;
    int brightness = 75;
    int draft = 0;
    int64_t last_input = 0;

    static constexpr int Clamp(int value,int low,int high) {
        return value<low ? low : value>high ? high : value;
    }
    constexpr bool active() const { return mode!=Mode::Closed; }
    constexpr void Open(int v,int b,int64_t now) {
        volume = Clamp(v,0,100); brightness = Clamp(b,10,100);
        page = diagnostic_page = 0; mode = Mode::List; last_input = now;
    }
    constexpr Effect Exit() {
        if (mode==Mode::Edit) draft = page==0 ? volume : brightness;
        mode = Mode::Closed;
        return Close;
    }
    constexpr Effect Press(Key key,bool held,int64_t now) {
        if (!active()) return None;
        if (held && key!=Key::Main) return None;
        last_input = now;
        if (held) return Exit();
        if (mode==Mode::List) {
            if (key!=Key::Main) page = (page+(key==Key::Feed ? 4 : 1))%5;
            else if (page==4) return Exit();
            else if (page==2) mode = Mode::Memory;
            else if (page==3) mode = Mode::Diagnostics;
            else { mode = Mode::Edit; draft = page==0 ? volume : brightness; }
        } else if (mode==Mode::Edit) {
            if (key==Key::Main) {
                if (page==0) volume = draft;
                else brightness = draft;
                mode = Mode::List;
                return Commit;
            }
            draft = Clamp(draft+(key==Key::Feed ? -10 : 10),page==0 ? 0 : 10,100);
            return Preview;
        } else if (key==Key::Main) mode = Mode::List;
        else if (mode==Mode::Diagnostics) diagnostic_page = (diagnostic_page+(key==Key::Feed ? 2 : 1))%3;
        return None;
    }
    constexpr bool Timeout(int64_t now) {
        if (!active() || now-last_input<30) return false;
        Exit();
        return true;
    }
};
