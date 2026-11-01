#include "pet_state.h"

// Compile-time executions of the real reducer: no simulated duplicate model.
constexpr bool CareChecks() {
    PetState p;
    if (p.Feed()!=PetState::Result::Ok || p.Satiety()!=85 || p.interactions!=1) return false;
    if (p.Feed()!=PetState::Result::Cooldown || p.Satiety()!=85) return false;
    p.Advance(60);
    if (p.Feed()!=PetState::Result::Ok || p.interactions!=1) return false;
    p.Advance(60);
    if (p.Feed()!=PetState::Result::Full) return false;
    p.SetSleeping(true);
    if (p.Feed()!=PetState::Result::Sleeping || p.Pet()!=PetState::Result::Sleeping) return false;
    return true;
}
constexpr bool TimeChecks() {
    PetState p;
    p.Advance(900);
    p.SetSleeping(true);
    p.Advance(1800);
    if (p.Satiety()!=69 || p.Energy()!=97) return false;
    p.SetSleeping(false);
    p.Advance(2700);
    return p.Mood()==69 && p.Energy()==94;
}
constexpr bool RelationshipChecks() {
    PetState absent;
    absent.Advance(86400*30);
    if (absent.closeness!=10 || absent.interactions!=0) return false;
    PetState active;
    active.Interaction(); active.Advance(600);
    active.Interaction(); active.Advance(600);
    active.Interaction(); active.Advance(86400-1200);
    if (active.closeness!=52 || active.interactions!=0 || active.window_seconds!=0) return false;
    active.Advance(86400*2);
    return active.closeness==46;
}
static_assert(CareChecks(),"Pet care cooldown/caps/sleep contract failed");
static_assert(TimeChecks(),"Partial time and sleep transition contract failed");
static_assert(RelationshipChecks(),"Interaction window and non-death relationship contract failed");
constexpr bool OfflineChecks() {
    PetState p;
    p.AdvanceOffline(86400*30);
    return p.closeness==29 && p.Satiety()==22 && p.Energy()==0 && p.Mood()==46;
}
static_assert(OfflineChecks(),"Offline catch-up must cap physiology at 24h and relationship at 7 days");
constexpr bool ResidualChecks() {
    PetState p;
    p.Advance(1);
    if (p.Satiety()!=70 || p.Mood()!=70 || p.Energy()!=80) return false;
    p.Advance(449);
    p.SetSleeping(true); p.Advance(150);
    if (p.Energy()!=80) return false;
    p.SetSleeping(false); p.Advance(450);
    if (p.Energy()!=79) return false;
    p.SetSleeping(true); p.Advance(150);
    return p.Energy()==82;
}
static_assert(ResidualChecks(),"Partial awake/sleep intervals must survive mode changes without premature decay");
