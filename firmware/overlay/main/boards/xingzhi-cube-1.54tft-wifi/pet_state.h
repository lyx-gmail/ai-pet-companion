#pragma once
#include <cstdint>

// Integer values plus residual clocks preserve partial decay across sleep transitions.
// The owner serializes calls and persists all fields, not just the display values.
struct PetState {
    enum class Result { Ok, Sleeping, Cooldown, Full, NoGain };
    int satiety = 70;
    int mood = 70;
    int energy = 80;
    uint32_t satiety_elapsed = 0;
    uint32_t mood_elapsed = 0;
    uint32_t awake_energy_elapsed = 0;
    uint32_t sleep_energy_elapsed = 0;
    int closeness = 50;
    uint32_t window_seconds = 0;
    uint32_t since_interaction = 600;
    uint32_t feed_cooldown = 0;
    uint32_t pet_cooldown = 0;
    uint8_t interactions = 0;
    bool sleeping = false;
    uint32_t revision = 0;

    static constexpr int Clamp(int64_t v, int low, int high) {
        return v < low ? low : v > high ? high : static_cast<int>(v);
    }
    static constexpr uint32_t Subtract(uint32_t v, uint32_t seconds) {
        return v > seconds ? v-seconds : 0;
    }
    constexpr int Satiety() const { return satiety; }
    constexpr int Mood() const { return mood; }
    constexpr int Energy() const { return energy; }

    static constexpr uint32_t Periods(uint32_t& residual,uint64_t elapsed,uint32_t period) {
        const uint64_t total = residual+elapsed;
        residual = total%period;
        return static_cast<uint32_t>(total/period);
    }

    constexpr void Advance(uint32_t seconds) {
        satiety = Clamp(int64_t(satiety)-Periods(satiety_elapsed,uint64_t(seconds)*(sleeping?1:2),3600),0,100);
        if (sleeping) energy = Clamp(int64_t(energy)+3*uint64_t(Periods(sleep_energy_elapsed,seconds,300)),0,100);
        else {
            mood = Clamp(int64_t(mood)-Periods(mood_elapsed,seconds,3600),0,100);
            energy = Clamp(int64_t(energy)-Periods(awake_energy_elapsed,seconds,900),0,100);
        }
        feed_cooldown = Subtract(feed_cooldown,seconds);
        pet_cooldown = Subtract(pet_cooldown,seconds);
        since_interaction = Clamp(int64_t(since_interaction)+seconds,0,600);
        AdvanceRelationship(seconds);
        if (seconds) ++revision;
    }
    constexpr void AdvanceRelationship(uint32_t seconds) {
        uint64_t elapsed = uint64_t(window_seconds)+seconds;
        while (elapsed >= 86400) {
            closeness = Clamp(closeness+(interactions==0?-3:interactions==1?-1:interactions==2?0:2),10,100);
            interactions = 0;
            elapsed -= 86400;
        }
        window_seconds = static_cast<uint32_t>(elapsed);
    }
    constexpr void AdvanceOffline(uint32_t seconds) {
        const uint32_t physiology = seconds > 86400 ? 86400 : seconds;
        Advance(physiology);
        const uint32_t relationship = seconds > 7*86400 ? 7*86400 : seconds;
        AdvanceRelationship(relationship-physiology);
    }
    constexpr void Interaction() {
        if (since_interaction >= 600 && interactions < 3) {
            ++interactions;
            since_interaction = 0;
        }
    }
    constexpr bool Chat() {
        if(sleeping || since_interaction<600 || interactions>=3) return false;
        Interaction(); ++revision;
        return true;
    }
    constexpr Result Feed() {
        if (sleeping) return Result::Sleeping;
        if (feed_cooldown) return Result::Cooldown;
        if (satiety >= 95) return Result::Full;
        satiety = Clamp(satiety+15,0,100);
        feed_cooldown = 60;
        Interaction(); ++revision;
        return Result::Ok;
    }
    constexpr Result Pet() {
        if (sleeping) return Result::Sleeping;
        if (pet_cooldown) return Result::Cooldown;
        if (mood >= 100) return Result::NoGain;
        mood = Clamp(mood+8,0,100);
        pet_cooldown = 10;
        Interaction(); ++revision;
        return Result::Ok;
    }
    constexpr void SetSleeping(bool value) {
        if (sleeping != value) { sleeping = value; ++revision; }
    }
};
