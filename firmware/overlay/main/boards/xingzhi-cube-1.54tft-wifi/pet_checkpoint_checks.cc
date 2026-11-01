#include "pet_checkpoint.h"

constexpr bool PendingCheckpointRoundtrip() {
    PetCheckpoint saved;saved.snapshot.saved_wall=1793318400;
    saved.timeline.Begin(saved.snapshot.state,saved.snapshot.saved_wall);
    saved.snapshot.state.Advance(10);saved.snapshot.state.Feed();
    saved.timeline.Record(PetTimeline::Feed,10);saved.elapsed=10;
    PetCheckpoint restored;
    const auto bytes=saved.Encode();
    if (!PetCheckpoint::DecodeSized(bytes,bytes.size(),restored)) return false;
    if (restored.snapshot.state.satiety!=85 || restored.timeline.count!=1 ||
            !restored.timeline.pending || restored.elapsed!=10) return false;
    auto again=restored.Encode();
    for (unsigned i=0;i<bytes.size();++i) if (bytes[i]!=again[i]) return false;
    return restored.timeline.Resolve(restored.snapshot.state,1793318400+3600+10,10) &&
        restored.snapshot.state.satiety==83;
}

constexpr bool StrictCheckpointDecode() {
    PetCheckpoint source;source.snapshot.saved_wall=1793318400;
    source.timeline.Begin(source.snapshot.state,source.snapshot.saved_wall);
    source.timeline.Record(PetTimeline::Feed,10);source.elapsed=10;
    PetCheckpoint output;output.snapshot.state.mood=17;
    auto bytes=source.Encode();PetCheckpoint::Put(bytes,3,129);
    if (PetCheckpoint::DecodeSized(bytes,bytes.size(),output) || output.snapshot.state.mood!=17) return false;
    bytes=source.Encode();PetCheckpoint::Put(bytes,2,3); // pending and omitted contradict
    if (PetCheckpoint::DecodeSized(bytes,bytes.size(),output)) return false;
    bytes=source.Encode();PetCheckpoint::Put(bytes,PetCheckpoint::kEventWord+1,99);
    if (PetCheckpoint::DecodeSized(bytes,bytes.size(),output)) return false;
    bytes=source.Encode();PetCheckpoint::Put(bytes,4,9); // event lies beyond accounted runtime
    if (PetCheckpoint::DecodeSized(bytes,bytes.size(),output)) return false;
    bytes=source.Encode();PetCheckpoint::Put(bytes,1,5);
    return !PetCheckpoint::DecodeSized(bytes,bytes.size(),output);
}

constexpr bool LegacyCheckpointMigration() {
    PetSnapshot old;old.state.Feed();old.saved_wall=1793318400;
    for (unsigned version=1;version<=3;++version) {
        auto core=old.Encode();PetSnapshot::Put(core,1,version);
        PetCheckpoint::Bytes bytes{};
        const auto length=version==1 ? PetSnapshot::kLegacySize : version==2 ? PetSnapshot::kV2Size : PetSnapshot::kSize;
        for (unsigned i=0;i<length;++i) bytes[i]=core[i];
        PetCheckpoint restored;
        if (!PetCheckpoint::DecodeSized(bytes,length,restored) || restored.snapshot.state.satiety!=85 ||
                !restored.timeline.pending || restored.timeline.count || restored.elapsed) return false;
    }
    return true;
}
static_assert(PendingCheckpointRoundtrip(),"Persist one current snapshot and its pending chronology in one bounded blob");
static_assert(StrictCheckpointDecode(),"Malformed/future journals fail without changing the caller's state");
static_assert(LegacyCheckpointMigration(),"Read V1/V2/V3 states without dropping committed care or inventing elapsed time");

constexpr bool BootPolicyKeepsAcknowledgedState() {
    PetCheckpoint legacy;legacy.snapshot.state.Feed();legacy.snapshot.saved_wall=1793318400;
    legacy.legacy_wall=true;legacy.timeline.Begin(legacy.snapshot.state,legacy.snapshot.saved_wall);
    legacy.PrepareBoot();
    if (legacy.snapshot.state.satiety!=85 || legacy.snapshot.saved_wall || legacy.timeline.pending ||
            !legacy.timeline.omitted || legacy.legacy_wall) return false;
    PetCheckpoint pending;pending.snapshot.saved_wall=1793318400;
    pending.timeline.Begin(pending.snapshot.state,pending.snapshot.saved_wall);
    pending.snapshot.state.Advance(100);pending.elapsed=100;
    pending.PrepareBoot();
    if (!pending.timeline.pending || pending.elapsed!=100) return false;
    auto expected=pending.timeline.anchor;expected.AdvanceOffline(3600);expected.Advance(120);
    if (!pending.timeline.Resolve(pending.snapshot.state,1793318400+3600+120,120) ||
            pending.snapshot.state.satiety!=expected.satiety) return false;
    PetCheckpoint changed;changed.snapshot.saved_wall=1793318400;
    changed.timeline.Begin(changed.snapshot.state,changed.snapshot.saved_wall);
    changed.snapshot.state.Feed();changed.timeline.Record(PetTimeline::Feed,0);
    changed.PrepareBoot();
    return changed.snapshot.state.satiety==85 && !changed.timeline.pending && changed.timeline.omitted;
}
static_assert(BootPolicyKeepsAcknowledgedState(),"Legacy time basis and ambiguous power loss freeze explicitly; known runtime survives a no-action restart");

constexpr bool RollbackHandoffPreservesLaterLegacyWrites() {
    PetCheckpoint saved;
    auto marker=saved.LegacyShadow(),shadow=marker;
    if (saved.PreferLegacyShadow(marker,shadow)) return false;
    PetSnapshot old=saved.snapshot;old.state.Feed();shadow=old.Encode();
    if (!saved.PreferLegacyShadow(marker,shadow)) return false;
    marker[8]++; // An interrupted handoff must not select an older shadow.
    return !saved.PreferLegacyShadow(marker,shadow);
}
static_assert(RollbackHandoffPreservesLaterLegacyWrites(),"A completed shadow handoff detects old-firmware writes without overriding newer primary commits");
