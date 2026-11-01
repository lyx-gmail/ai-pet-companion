#pragma once
#include "pet_snapshot.h"
#include "pet_timeline.h"

// One bounded NVS value keeps the current state and pending clock history
// together. Legacy core snapshots remain readable; never rewrite an unknown format.
struct PetCheckpoint {
    static constexpr unsigned kCurrentWord=5;
    static constexpr unsigned kAnchorWord=kCurrentWord+PetSnapshot::kSize/4;
    static constexpr unsigned kEventWord=kAnchorWord+PetSnapshot::kSize/4;
    static constexpr size_t kSize=4*kEventWord+8*PetTimeline::kCapacity;
    using Bytes=std::array<uint8_t,kSize>;
    PetSnapshot snapshot;
    PetTimeline timeline;
    uint32_t elapsed=0;
    bool legacy_wall=false;

    constexpr PetSnapshot::Bytes LegacyShadow() const {
        auto shadow=snapshot;shadow.saved_wall=0;
        return shadow.Encode();
    }
    constexpr bool PreferLegacyShadow(const PetSnapshot::Bytes& marker,const PetSnapshot::Bytes& shadow) const {
        const auto expected=LegacyShadow();bool changed=false;
        for (unsigned i=0;i<expected.size();++i) {
            if (marker[i]!=expected[i]) return false; // Primary/shadow handoff was not completed.
            changed=changed || shadow[i]!=marker[i];
        }
        return changed; // An older firmware wrote after the completed handoff.
    }

    constexpr void PrepareBoot() {
        if (legacy_wall || (timeline.pending && timeline.count)) {
            // Older firmware did not identify the timestamp basis. Another
            // clockless boot after actions also leaves gap placement ambiguous.
            // Keep committed state, freeze only the unprovable gap, then re-anchor.
            timeline.FreezeUnknown();snapshot.saved_wall=0;elapsed=0;legacy_wall=false;
        } else if (!timeline.pending) {
            timeline.Begin(snapshot.state,snapshot.saved_wall);elapsed=0;
        }
    }

    static constexpr void Put(Bytes& bytes,size_t word,uint32_t value) {
        for (unsigned i=0;i<4;++i) bytes[4*word+i]=static_cast<uint8_t>(value>>(8*i));
    }
    static constexpr uint32_t Get(const Bytes& bytes,size_t word) {
        uint32_t value=0;
        for (unsigned i=0;i<4;++i) value|=uint32_t(bytes[4*word+i])<<(8*i);
        return value;
    }
    constexpr Bytes Encode() const {
        Bytes bytes{};
        Put(bytes,0,0x34544550);Put(bytes,1,4);
        Put(bytes,2,(timeline.pending?1u:0u)|(timeline.omitted?2u:0u)|(legacy_wall?4u:0u));
        Put(bytes,3,timeline.count);Put(bytes,4,timeline.pending?elapsed:0);
        const auto current=snapshot.Encode();
        PetSnapshot base=snapshot;base.state=timeline.anchor;base.saved_wall=timeline.anchor_wall;
        const auto anchor=base.Encode();
        for (unsigned i=0;i<PetSnapshot::kSize;++i) {
            bytes[4*kCurrentWord+i]=current[i];bytes[4*kAnchorWord+i]=anchor[i];
        }
        for (unsigned i=0;i<timeline.count && i<PetTimeline::kCapacity;++i) {
            Put(bytes,kEventWord+2*i,timeline.events[i].second);
            Put(bytes,kEventWord+2*i+1,timeline.events[i].kind);
        }
        return bytes;
    }
    static constexpr bool DecodeSized(const Bytes& bytes,size_t length,PetCheckpoint& output) {
        PetCheckpoint decoded;
        if (length==PetSnapshot::kSize || length==PetSnapshot::kV2Size || length==PetSnapshot::kLegacySize) {
            PetSnapshot::Bytes core{};
            for (unsigned i=0;i<length;++i) core[i]=bytes[i];
            if (!PetSnapshot::DecodeSized(core,length,decoded.snapshot)) return false;
            decoded.timeline.Begin(decoded.snapshot.state,decoded.snapshot.saved_wall);
            decoded.legacy_wall=decoded.snapshot.saved_wall!=0;
        } else {
            if (length!=kSize || Get(bytes,0)!=0x34544550 || Get(bytes,1)!=4) return false;
            const auto flags=Get(bytes,2),count=Get(bytes,3);
            if (flags>6 || (flags&3)==3 || count>PetTimeline::kCapacity || (!(flags&1) && (count || Get(bytes,4)))) return false;
            PetSnapshot::Bytes current{},anchor{};
            for (unsigned i=0;i<PetSnapshot::kSize;++i) {
                current[i]=bytes[4*kCurrentWord+i];anchor[i]=bytes[4*kAnchorWord+i];
            }
            PetSnapshot base;
            if (!PetSnapshot::Decode(current,decoded.snapshot) || !PetSnapshot::Decode(anchor,base)) return false;
            decoded.timeline.anchor=base.state;decoded.timeline.anchor_wall=base.saved_wall;
            decoded.timeline.pending=flags&1;decoded.timeline.omitted=flags&2;
            decoded.legacy_wall=flags&4;
            if (decoded.timeline.pending != (base.saved_wall!=0)) return false;
            decoded.timeline.count=count;decoded.elapsed=Get(bytes,4);
            uint32_t previous=0;
            for (unsigned i=0;i<PetTimeline::kCapacity;++i) {
                const auto second=Get(bytes,kEventWord+2*i),kind=Get(bytes,kEventWord+2*i+1);
                if (i>=count) { if (second || kind) return false;continue; }
                if (kind>PetTimeline::Chat || second<previous || second>decoded.elapsed) return false;
                decoded.timeline.events[i]={second,static_cast<PetTimeline::Kind>(kind)};previous=second;
            }
        }
        output=decoded;return true;
    }
};
