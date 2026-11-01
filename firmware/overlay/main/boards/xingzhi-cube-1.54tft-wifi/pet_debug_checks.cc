#include "pet_debug.h"

constexpr bool DebugCommands() {
    PetDebug parser;
    for (char c : "pet.state\r") if (c && parser.Push(c)!=PetDebug::Command::None) return false;
    if (parser.Push('\n')!=PetDebug::Command::State) return false;
    for (char c : "pet.main") if (c) parser.Push(c);
    if (parser.Push('\n')!=PetDebug::Command::Main) return false;
    for (char c : "pet.memory_demo") if (c) parser.Push(c);
    if (parser.Push('\n')!=PetDebug::Command::MemoryDemo) return false;
    for (char c : "pet.wifi_pause") if (c) parser.Push(c);
    if (parser.Push('\n')!=PetDebug::Command::WifiPause) return false;
    return parser.Push('\n')==PetDebug::Command::None;
}
constexpr bool DebugRejectsBadFrames() {
    PetDebug parser;
    for (int i=0;i<40;++i) parser.Push('x');
    for (char c : "pet.main") if (c) parser.Push(c);
    if (parser.Push('\n')!=PetDebug::Command::None) return false;
    parser.Push('\0');
    for (char c : "pet.feed") if (c) parser.Push(c);
    if (parser.Push('\n')!=PetDebug::Command::None) return false;
    for (char c : "pet.feed_hold") if (c) parser.Push(c);
    return parser.Push('\n')==PetDebug::Command::FeedHold;
}
static_assert(DebugCommands(),"USB command framing must dispatch once on newline");
static_assert(DebugRejectsBadFrames(),"Oversized or binary USB frames must be discarded through newline");
