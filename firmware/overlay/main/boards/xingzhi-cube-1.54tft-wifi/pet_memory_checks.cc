#include "pet_memory.h"

constexpr bool ConfirmOnce() {
    PetMemory memory;
    const char* id="b82c20fa-467a-4c7d-a9a5-7a5149323411";
    if (!memory.Offer(id,4,10)) return false;
    if (memory.Offer(id,4,11)) return false;
    if (!memory.Decide(true,4,12)) return false;
    if (memory.Get(id,4,12)!=PetMemory::Status::Confirmed) return false;
    if (memory.Decide(false,4,13)) return false;
    if (memory.Offer(id,4,13)) return false;
    return memory.Get(id,4,13)==PetMemory::Status::Confirmed;
}
constexpr bool FailClosed() {
    PetMemory memory;
    const char* id="b82c20fa-467a-4c7d-a9a5-7a5149323411";
    if (memory.Offer("bad",1,0)) return false;
    if (!memory.Offer(id,1,0)) return false;
    if (memory.Get("other",1,1)!=PetMemory::Status::Unknown) return false;
    if (memory.Decide(true,2,1)) return false;
    if (memory.Get(id,2,1)!=PetMemory::Status::Cancelled) return false;
    PetMemory expired;
    if (!expired.Offer(id,3,0)) return false;
    if (expired.Decide(true,3,30)) return false;
    return expired.Get(id,3,30)==PetMemory::Status::Expired;
}
static_assert(ConfirmOnce(),"Memory needs one non-replayable explicit decision");
static_assert(FailClosed(),"Memory must reject expiry, stale epochs and mismatched IDs");
