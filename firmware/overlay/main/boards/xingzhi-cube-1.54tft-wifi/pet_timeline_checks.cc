#include "pet_timeline.h"

constexpr bool SameState(const PetState& a,const PetState& b) {
    return a.satiety==b.satiety && a.mood==b.mood && a.energy==b.energy &&
        a.satiety_elapsed==b.satiety_elapsed && a.mood_elapsed==b.mood_elapsed &&
        a.awake_energy_elapsed==b.awake_energy_elapsed && a.sleep_energy_elapsed==b.sleep_energy_elapsed &&
        a.closeness==b.closeness && a.window_seconds==b.window_seconds && a.since_interaction==b.since_interaction &&
        a.feed_cooldown==b.feed_cooldown && a.pet_cooldown==b.pet_cooldown &&
        a.interactions==b.interactions && a.sleeping==b.sleeping;
}

constexpr bool DelayedClockKeepsChronology() {
    constexpr uint64_t anchor=1793318400;
    PetState base;PetState actual=base;PetTimeline timeline;
    timeline.Begin(base,anchor);
    actual.Advance(10);actual.Feed();timeline.Record(PetTimeline::Feed,10);
    actual.Advance(30);actual.Pet();timeline.Record(PetTimeline::Pet,40);
    actual.Advance(10);actual.SetSleeping(true);timeline.Record(PetTimeline::Sleep,50);
    actual.Advance(600);actual.SetSleeping(false);timeline.Record(PetTimeline::Wake,650);
    actual.Advance(50);
    const auto previous_revision=actual.revision;
    if (!timeline.Resolve(actual,anchor+3600+700,700)) return false;
    PetState expected=base;
    expected.AdvanceOffline(3600);expected.Advance(10);expected.Feed();
    expected.Advance(30);expected.Pet();expected.Advance(10);expected.SetSleeping(true);
    expected.Advance(600);expected.SetSleeping(false);expected.Advance(50);
    return SameState(actual,expected) && actual.revision==previous_revision+1 && !timeline.pending &&
        !timeline.Resolve(actual,anchor+3600+701,701);
}

constexpr bool BoundedGapAndRollback() {
    constexpr uint64_t anchor=1793318400;
    PetState actual;PetState expected=actual;PetTimeline timeline;
    timeline.Begin(actual,anchor);
    actual.Advance(120);
    if (timeline.Resolve(actual,0,120) || !timeline.pending) return false;
    expected.AdvanceOffline(7*86400);expected.Advance(120);
    if (!timeline.Resolve(actual,anchor+100*86400+120,120) || !SameState(actual,expected)) return false;
    PetState backward;PetState unchanged=backward;PetTimeline other;other.Begin(backward,anchor);
    backward.Advance(50);unchanged.Advance(50);
    return other.Resolve(backward,anchor-60,50) && SameState(backward,unchanged);
}

constexpr bool UnknownTimeAndBoundedJournalNeverRewriteCare() {
    constexpr uint64_t anchor=1793318400;
    PetState state;PetTimeline timeline;timeline.Begin(state,anchor);
    state.Feed();timeline.Record(PetTimeline::Feed,0);
    const auto satiety=state.satiety;
    // Without a clock, another power loss cannot reveal where its unknown gap
    // occurred. Freeze it explicitly instead of inventing a chronology.
    timeline.FreezeUnknown();
    if (timeline.Resolve(state,anchor+86400,0) || state.satiety!=satiety || !timeline.omitted) return false;
    timeline.Begin(state,anchor);
    for (unsigned i=0;i<PetTimeline::kCapacity;++i)
        if (!timeline.Record(PetTimeline::Sleep,i)) return false;
    if (timeline.Record(PetTimeline::Wake,PetTimeline::kCapacity) || !timeline.omitted || timeline.pending) return false;
    return state.satiety==satiety;
}

static_assert(DelayedClockKeepsChronology(),"Offline decay precedes accepted actions; reconcile once without rewinding revision");
static_assert(BoundedGapAndRollback(),"Unknown clock waits; catch-up caps and backward clock cannot double-debit");
static_assert(UnknownTimeAndBoundedJournalNeverRewriteCare(),"Ambiguous restart and capacity limits freeze explicitly, preserving accepted care");
