#include "pet_sleep.h"

constexpr bool GoodnightThenSleep() {
    PetSleep pending;
    pending.Request(1000,7,10);
    if (pending.Ready(1500,7,10,true)) return false; // no TTS stop yet
    if (pending.Ready(2000,7,11,false)) return false; // stop, audio still buffered
    if (pending.Ready(2199,7,11,true)) return false; // allow output tail to drain
    return pending.Ready(2200,7,11,true);
}
constexpr bool SleepSurvivesVoiceCancellation() {
    PetSleep pending;
    pending.Request(1000,7,10);
    if (pending.Ready(2000,8,11,true)) return false; // another channel's stop is irrelevant
    pending.Request(4000,8,11); // a repeated accepted request cannot extend the deadline
    if (pending.Ready(5999,8,11,true)) return false;
    if (!pending.Ready(6000,8,11,false)) return false; // timeout even when audio fails
    pending.Clear();
    return !pending.Ready(9000,8,12,true);
}
static_assert(GoodnightThenSleep(),"A stop signal alone must not truncate pending audio");
static_assert(SleepSurvivesVoiceCancellation(),"Cancellation or repeated requests must not discard or delay committed sleep");
