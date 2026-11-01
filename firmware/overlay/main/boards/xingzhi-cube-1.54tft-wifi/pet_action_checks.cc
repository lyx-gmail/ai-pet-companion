#include "pet_actions.h"

constexpr bool CareResults() {
    PetState state;
    PetActions actions;
    auto result = actions.Apply(state,1,3,false,true);
    if (result.code!=PetActions::Code::Ok || result.delta!=15 || state.satiety!=85) return false;
    state.Advance(61);
    result = actions.Apply(state,1,3,false,true);
    if (result.code!=PetActions::Code::Duplicate || result.delta || state.satiety!=85 || result.original!=PetActions::Code::Ok) return false;
    result = actions.Apply(state,1,4,false,true);
    if (result.code!=PetActions::Code::Ok || state.satiety!=100) return false;
    result = actions.Apply(state,1,5,false,true);
    if (result.code!=PetActions::Code::Cooldown || result.delta) return false;
    state.Advance(60);
    if (actions.Apply(state,1,6,false,true).code!=PetActions::Code::Full) return false;
    state.SetSleeping(true);
    if (actions.Apply(state,1,7,true,true).code!=PetActions::Code::Asleep) return false;
    return true;
}

constexpr bool GateAndReplayWindow() {
    PetState state;
    PetActions actions;
    if (actions.Apply(state,1,3,true,false).code!=PetActions::Code::Busy || state.mood!=70) return false;
    if (actions.Apply(state,1,3,true,true).delta!=8) return false;
    // A different action with the same transport ID is still a duplicate.
    if (actions.Apply(state,1,3,false,true).code!=PetActions::Code::Duplicate || state.satiety!=70) return false;
    // Force ring eviction. Older requests must be rejected, never re-executed.
    if (actions.Apply(state,1,80,true,true).code!=PetActions::Code::Cooldown) return false;
    state.Advance(11);
    if (actions.Apply(state,1,3,true,true).code!=PetActions::Code::Invalid || state.mood!=78) return false;
    // Transport IDs may restart on a genuinely new validated voice channel.
    return actions.Apply(state,2,3,true,true).code==PetActions::Code::Ok && state.mood==86;
}

static_assert(CareResults(),"Care results and retry after cooldown must reflect actual mutations");
static_assert(GateAndReplayWindow(),"Busy, cross-tool duplicate, old replay and new-channel ID reuse must be safe");
constexpr bool SleepIdentityOnly() {
    PetState state;
    PetActions actions;
    auto result = actions.Apply(state,1,1,PetActions::Action::SetSleep,true);
    if (result.code!=PetActions::Code::Ok || result.delta || state.sleeping || state.revision) return false;
    if (actions.Apply(state,1,1,false,true).code!=PetActions::Code::Duplicate || state.satiety!=70) return false;
    return actions.Apply(state,1,2,PetActions::Action::SetSleep,false).code==PetActions::Code::Busy;
}
static_assert(SleepIdentityOnly(),"Sleep identity cannot reward care or change state before durable intent handling");
