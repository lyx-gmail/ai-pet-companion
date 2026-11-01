#pragma once
#include "pet_checkpoint.h"
#include "pet_menu.h"
#include "pet_actions.h"
#include "pet_sleep.h"
#include "pet_debug.h"
#include "pet_memory.h"
#include "pet_memory_menu.h"
#include <esp_timer.h>
#include <atomic>
#include <string>

class PetDisplay;
struct cJSON;

// All methods except the timer callback run on Application's scheduled thread.
// Owns pet_v1/checkpoint_v4, snapshot and shadow_v4, never network namespaces.
class PetRuntime {
public:
    void Begin(PetDisplay* display);
    void HandleKey(PetMenu::Key key,bool held);
    bool WakeIfSleeping();
    void Feed();
    void Pet();
    void ToggleSleep();
    void ToggleMute();
private:
    PetDisplay* display_ = nullptr;
    PetSnapshot snapshot_;
    PetTimeline timeline_;
    uint32_t timeline_elapsed_base_=0;
    PetMenu menu_;
    PetActions actions_;
    PetSleep sleep_;
    PetDebug usb_debug_;
    PetMemory memory_;
    bool memory_page_ = false;
    cJSON* MemoryOffer(const std::string& id,const std::string& label);
    cJSON* MemoryStatus(const std::string& id);
    void RefreshMemory();
    PetMemoryMenu admin_;
    bool admin_busy_=false;
    uint64_t admin_revision_=0;
    std::string admin_values_[5];
    std::string admin_id_;
    std::string admin_label_;
    std::string admin_target_;
    uint64_t admin_delete_revision_=0;
    std::string admin_error_;
    void AdminAction(PetMemoryMenu::Action action);
    void AdminReply(PetMemoryMenu::Action action,uint64_t generation,const std::string& id,int status,const std::string& body);
    void RenderAdmin();
    void ClearAdminValues();
    void PollUsb();
    cJSON* VoiceSleep(bool sleeping,uint32_t epoch,uint32_t request);
    void ApplySleep(bool value);
    cJSON* VoiceCare(bool petting,uint32_t epoch,uint32_t request);
    void RenderMenu();
    void CloseMenu();
    esp_timer_handle_t timer_ = nullptr;
    esp_timer_handle_t sleep_timer_ = nullptr;
    std::atomic<bool> tick_pending_{false};
    bool storage_ok_ = true;
    bool audio_restored_ = false;
    bool dirty_ = false;
    uint32_t persisted_revision_ = 0;
    const char* last_event_ = "none";
    int64_t last_event_second_ = -1;
    int64_t boot_second_ = 0;
    int64_t last_second_ = 0;
    int64_t last_save_second_ = 0;
    int64_t last_health_second_ = 0;
    int64_t save_due_ = 0;
    void Tick();
    void AdvanceNow();
    bool SyncOffline(int64_t second);
    uint64_t TimelineSecond(int64_t second) const;
    void RecordTimeline(PetTimeline::Kind kind);
    void Changed(bool immediate = false);
    void Save();
    bool CanCare();
    void StorageFault(const char* operation,int error);
    cJSON* ReadState();
    void RecordEvent(const char* event);
};
