#pragma once
#include <cstdint>

// Volatile consent only. No profile text or confirmation survives a restart.
class PetMemory {
public:
    enum class Status { Unknown,Pending,Confirmed,Cancelled,Expired };
    constexpr bool Offer(const char* id,uint32_t epoch,int64_t now) {
        Refresh(epoch,now);
        if (!Valid(id) || status_==Status::Pending || Same(id)) return false;
        for (int i=0;i<37;++i) id_[i]=id[i];
        epoch_=epoch; deadline_=now+30; status_=Status::Pending;
        return true;
    }
    constexpr Status Get(const char* id,uint32_t epoch,int64_t now) {
        Refresh(epoch,now);
        return Same(id) ? status_ : Status::Unknown;
    }
    constexpr bool pending() const { return status_==Status::Pending; }
    constexpr bool Decide(bool yes,uint32_t epoch,int64_t now) {
        Refresh(epoch,now);
        if (!pending()) return false;
        status_=yes ? Status::Confirmed : Status::Cancelled;
        return true;
    }
    constexpr void Refresh(uint32_t epoch,int64_t now) {
        if (status_==Status::Pending || status_==Status::Confirmed) {
            if (epoch!=epoch_) status_=Status::Cancelled;
            else if (now>=deadline_) status_=Status::Expired;
        }
    }
private:
    char id_[37]{};
    Status status_=Status::Unknown;
    uint32_t epoch_=0;
    int64_t deadline_=0;
    constexpr bool Same(const char* id) const {
        if (!id || !id_[0]) return false;
        for (int i=0;i<37;++i) { if (id_[i]!=id[i]) return false; if (!id[i]) return true; }
        return false;
    }
    static constexpr bool Valid(const char* id) {
        if (!id) return false;
        for (int i=0;i<36;++i) {
            const auto c=id[i];
            if (i==8 || i==13 || i==18 || i==23) { if (c!='-') return false; }
            else if (!((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
        }
        return !id[36];
    }
};
