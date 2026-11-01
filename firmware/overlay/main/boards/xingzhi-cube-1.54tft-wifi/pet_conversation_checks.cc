#include "pet_conversation.h"
#include "pet_state.h"

constexpr bool CompletedConversation() {
    PetConversation c;
    c.Transcript(2,1,true,20);
    c.Start(2,20); c.Reply(2,true); c.Stop(2);
    if(c.Complete(2,20,true,true) || c.Complete(2,21,false,true)) return false;
    if(!c.Complete(2,21,true,true) || c.Complete(2,22,true,true)) return false;
    // A duplicated STT for the consumed turn cannot create another completion.
    c.Transcript(2,1,true,22); c.Start(2,22); c.Reply(2,true); c.Stop(2);
    if(c.Complete(2,23,true,true)) return false;
    c.Transcript(2,2,true,23); c.Start(2,23); c.Reply(2,true); c.Stop(2);
    if(!c.Complete(2,24,true,true)) return false;
    c.Transcript(2,1,true,24); c.Start(2,24); c.Reply(2,true); c.Stop(2);
    return !c.Complete(2,25,true,true); // old turn replay cannot regain credit
}
constexpr bool RejectedConversation() {
    PetConversation c;
    c.Transcript(1,1,false,0); c.Start(1,0); c.Reply(1,true); c.Stop(1);
    if(c.Complete(1,1,true,true)) return false; // wake/debug/display, not ASR
    c.Transcript(1,2,true,1); c.Start(1,1); c.Stop(1);
    if(c.Complete(1,2,true,true)) return false; // no reply text
    c.Transcript(1,3,true,2); c.Start(1,2); c.Reply(1,true); c.Stop(1);
    if(c.Complete(2,3,true,true)) return false; // cancelled / replaced channel
    c.Transcript(2,4,true,3); c.Start(2,3); c.Reply(2,true); c.Stop(2);
    if(c.Complete(2,4,true,false) || c.Complete(2,5,true,true)) return false;
    c.Transcript(2,5,true,5); c.Start(2,5); c.Reply(2,true); c.Care(2); c.Stop(2);
    if(c.Complete(2,6,true,true)) return false; // long same-turn care + chat still count once
    c.Transcript(2,6,true,6); c.Start(2,6); c.Reply(2,true);
    c.Cancel(); c.Stop(2);
    return !c.Complete(2,7,true,true); // plain AbortSpeaking, same epoch
}
constexpr bool ChatRelationship() {
    PetState p;
    if(!p.Chat() || p.interactions!=1 || p.satiety!=70 || p.mood!=70 || p.energy!=80) return false;
    if(p.Chat()) return false;
    p.Advance(600); if(!p.Chat() || p.interactions!=2) return false;
    p.Advance(600); if(!p.Chat() || p.interactions!=3) return false;
    p.Advance(600); if(p.Chat()) return false;
    p.Advance(86400-1800);
    if(p.closeness!=52 || p.interactions!=0) return false;
    p.SetSleeping(true); return !p.Chat();
}
static_assert(CompletedConversation(),"Chat requires remote playback and drains; once per turn");
static_assert(RejectedConversation(),"No credit for empty, cancelled, diagnostic, or same-turn care");
static_assert(ChatRelationship(),"Chat shares the ten-minute spacing and three-per-window cap");
