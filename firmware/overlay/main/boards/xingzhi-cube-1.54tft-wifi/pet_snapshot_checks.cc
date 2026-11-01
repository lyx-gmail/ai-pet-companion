#include "pet_snapshot.h"

constexpr bool SnapshotRoundtrip() {
    PetSnapshot source;
    source.state.Advance(123);
    source.state.Feed();
    source.state.SetSleeping(true);
    source.saved_wall = 1793318400;
    source.muted = true;
    source.last_volume = 60;
    source.brightness = 85;
    source.sleep_pending = true;
    const auto bytes = source.Encode();
    PetSnapshot restored;
    if (!PetSnapshot::Decode(bytes,restored)) return false;
    const auto encoded = restored.Encode();
    for (size_t i=0;i<bytes.size();++i) if (bytes[i]!=encoded[i]) return false;
    return restored.state.satiety==85 && restored.state.sleeping && restored.muted && restored.brightness==85 && restored.sleep_pending;
}
constexpr bool RejectBrokenSnapshot() {
    PetSnapshot good;
    auto bytes = good.Encode();
    PetSnapshot sentinel;
    sentinel.state.mood = 17;
    bytes[8] = 101; // satiety beyond range
    if (PetSnapshot::Decode(bytes,sentinel) || sentinel.state.mood!=17) return false;
    bytes = good.Encode(); bytes[4] = 4; // future version must not be rewritten
    if (PetSnapshot::Decode(bytes,sentinel)) return false;
    bytes = good.Encode(); bytes[60] = 2; // sleeping must be boolean
    if (PetSnapshot::Decode(bytes,sentinel)) return false;
    bytes = good.Encode(); bytes[20] = 0xff; bytes[21] = 0xff; // residual beyond period
    return !PetSnapshot::Decode(bytes,sentinel);
}
static_assert(SnapshotRoundtrip(),"All pet clocks, state and settings must survive snapshot roundtrip");
static_assert(RejectBrokenSnapshot(),"Malformed/future snapshots must fail without changing caller state");
constexpr bool SnapshotMigration() {
    PetSnapshot original;
    original.state.Feed();
    auto bytes = original.Encode();
    PetSnapshot::Put(bytes,1,1);
    PetSnapshot restored;
    if (!PetSnapshot::DecodeSized(bytes,84,restored) || restored.state.satiety!=85 || restored.brightness!=75) return false;
    if (PetSnapshot::DecodeSized(bytes,88,restored)) return false;
    bytes = original.Encode(); PetSnapshot::Put(bytes,1,2); PetSnapshot::Put(bytes,21,85);
    if (!PetSnapshot::DecodeSized(bytes,88,restored) || restored.brightness!=85 || restored.sleep_pending) return false;
    bytes = original.Encode(); PetSnapshot::Put(bytes,22,2);
    if (PetSnapshot::Decode(bytes,restored)) return false;
    bytes = original.Encode(); PetSnapshot::Put(bytes,21,9);
    return !PetSnapshot::Decode(bytes,restored);
}
static_assert(SnapshotMigration(),"V1 must migrate without losing care state; malformed V2 brightness must fail");
