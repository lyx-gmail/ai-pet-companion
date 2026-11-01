#include "pet_runtime.h"
#include "pet_display.h"
#include "application.h"
#include "board.h"
#include "mcp_server.h"
#include <nvs.h>
#include <esp_log.h>
#include <ctime>
#include <cstdio>
#include "sdkconfig.h"
#include "pet_endpoint.h"
#include "pet_memory_http.h"
#include <memory>
#include <new>
#include <cmath>
#include "hal/usb_serial_jtag_ll.h"
#include <cJSON.h>
#include <esp_wifi.h>

static_assert(CONFIG_BUTTON_PERIOD_TIME_MS*CONFIG_BUTTON_DEBOUNCE_TICKS==40,
              "Pet buttons require the configured 40ms hardware debounce");

namespace {
constexpr const char* kTag = "PetRuntime";
int64_t Second() { return esp_timer_get_time()/1000000; }
uint64_t Wall() {
    if (!pet_utc_synced.load()) return 0;
    const auto value = time(nullptr);
    return value>=1704067200 && uint64_t(value)<=4102444800 ? uint64_t(value) : 0;
}

// Development-only radio fault. A separate task guarantees a bounded restore
// even when the application thread is waiting for a voice connection.
void PauseWifiForCheck() {
    static std::atomic<bool> busy{false};
    wifi_ap_record_t ap{};
    if (esp_wifi_sta_get_ap_info(&ap)!=ESP_OK || busy.exchange(true)) {
        ESP_LOGW("PetWifiFault","rejected=1");
        return;
    }
    const auto created=xTaskCreate([](void*) {
        esp_wifi_disconnect();
        const auto stopped=esp_wifi_stop();
        ESP_LOGI("PetWifiFault","radio_stopped=%d",int(stopped));
        if (stopped==ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(20000));
            const auto started=esp_wifi_start();
            ESP_LOGI("PetWifiFault","radio_restarted=%d",int(started));
        }
        busy.store(false);
        vTaskDelete(nullptr);
    },"pet_wifi_fault",4096,nullptr,1,nullptr);
    if (created!=pdPASS) {
        busy.store(false);
        ESP_LOGW("PetWifiFault","task_failed=1");
    }
}
}

void PetRuntime::StorageFault(const char* operation,int error) {
    storage_ok_ = false;
    menu_.Exit();
    display_->HideMenu();
    ESP_LOGE(kTag,"Pet storage %s failed (%d); preserving existing data",operation,error);
    display_->ShowSystemPage(true);
    display_->SetChatMessage("system","宠物存档不可用，已保留原数据。请连接电脑排查，勿恢复出厂。");
}

void PetRuntime::Begin(PetDisplay* display) {
    display_ = display;
    boot_second_ = last_second_ = last_save_second_ = Second();
    PetCheckpoint loaded;
    bool migrated=false;
    nvs_handle_t handle;
    auto error = nvs_open("pet_v1",NVS_READONLY,&handle);
    if (error == ESP_OK) {
        size_t size = 0;
        const char* key="checkpoint_v4";
        error = nvs_get_blob(handle,key,nullptr,&size);
        if (error==ESP_ERR_NVS_NOT_FOUND) {
            key="snapshot";error=nvs_get_blob(handle,key,nullptr,&size);migrated=error==ESP_OK;
        }
        if (error == ESP_OK) {
            PetCheckpoint::Bytes bytes{};
            if ((!migrated && size!=bytes.size()) || (migrated && size!=PetSnapshot::kSize && size!=PetSnapshot::kLegacySize && size!=PetSnapshot::kV2Size)) error = ESP_ERR_INVALID_SIZE;
            else {
                error = nvs_get_blob(handle,key,bytes.data(),&size);
                if (error==ESP_OK && !PetCheckpoint::DecodeSized(bytes,size,loaded)) error = ESP_ERR_INVALID_STATE;
            }
        }
        if (error==ESP_OK && !migrated) {
            PetSnapshot::Bytes marker{},shadow{};
            size_t marker_size=marker.size(),shadow_size=shadow.size();
            const auto marker_error=nvs_get_blob(handle,"shadow_v4",marker.data(),&marker_size);
            const auto shadow_error=nvs_get_blob(handle,"snapshot",shadow.data(),&shadow_size);
            if ((marker_error!=ESP_OK && marker_error!=ESP_ERR_NVS_NOT_FOUND) ||
                    (shadow_error!=ESP_OK && shadow_error!=ESP_ERR_NVS_NOT_FOUND)) error=ESP_ERR_INVALID_STATE;
            else {
                PetSnapshot legacy;
                if ((marker_error==ESP_OK && marker_size!=marker.size()) ||
                        (shadow_error==ESP_OK && (shadow_size!=shadow.size() || !PetSnapshot::Decode(shadow,legacy)))) error=ESP_ERR_INVALID_STATE;
                else if (marker_error==ESP_OK && shadow_error==ESP_OK && loaded.PreferLegacyShadow(marker,shadow)) {
                    loaded=PetCheckpoint{};loaded.snapshot=legacy;
                    loaded.timeline.Begin(legacy.state,legacy.saved_wall);
                    loaded.legacy_wall=legacy.saved_wall!=0;migrated=true;
                }
            }
        }
        nvs_close(handle);
    }
    if (error!=ESP_OK && error!=ESP_ERR_NVS_NOT_FOUND) StorageFault("read",error);
    const bool frozen=loaded.legacy_wall || (loaded.timeline.pending && loaded.timeline.count);
    loaded.PrepareBoot();snapshot_=loaded.snapshot;timeline_=loaded.timeline;timeline_elapsed_base_=loaded.elapsed;
    if (storage_ok_ && (migrated || frozen)) { dirty_=true;save_due_=Second()+2; }
    persisted_revision_ = snapshot_.state.revision;
    if (storage_ok_ && snapshot_.sleep_pending) {
        snapshot_.state.SetSleeping(true);
        RecordTimeline(PetTimeline::Sleep);
        snapshot_.sleep_pending = false;
        dirty_ = true;
        save_due_ = Second()+2;
        RecordEvent("restored_sleep");
    }
    display_->SetPetState(snapshot_.state);
    McpServer::GetInstance().AddTool("self.pet.get_state",
        "Read the real pet's satiety, mood, energy, closeness, sleep, cooldowns and recent local event. "
        "Call before answering pet-status questions; never invent values or claim a care action from this read-only result. "
        "A storage error means state is unavailable. No account or Wi-Fi credentials are returned.",
        PropertyList(),[this](const PropertyList&) -> ReturnValue { return ReadState(); });
    for (bool petting : {false,true}) {
        McpServer::GetInstance().AddTool(petting ? "self.pet.pet" : "self.pet.feed",
            petting ? "Pet this companion once, only when the user explicitly asks. Report the real result; never invent a reward. Retries do not repeat the action." :
                      "Feed this companion once, only when the user explicitly asks. Report the real result; never invent a reward. Retries do not repeat the action.",
            PropertyList(),[this,petting](const PropertyList& arguments) -> ReturnValue {
                return VoiceCare(petting,static_cast<uint32_t>(arguments["_pet_epoch"].value<int>()),
                                 static_cast<uint32_t>(arguments["_pet_request_id"].value<int>()));
            });
    }
    McpServer::GetInstance().AddTool("self.pet.set_sleep",
        "Only on an explicit user request: sleeping=true commits sleep, then allows a brief goodnight before closing eyes (5 second fallback). "
        "Report pending versus actual state honestly. sleeping=false explicitly wakes or withdraws pending sleep. Voice cancellation alone does not withdraw it.",
        PropertyList({Property("sleeping",kPropertyTypeBoolean)}),
        [this](const PropertyList& arguments) -> ReturnValue {
            return VoiceSleep(arguments["sleeping"].value<bool>(),
                static_cast<uint32_t>(arguments["_pet_epoch"].value<int>()),
                static_cast<uint32_t>(arguments["_pet_request_id"].value<int>()));
        });
    esp_timer_create_args_t args{};
    McpServer::GetInstance().AddTool("self.pet.memory_offer",
        "Internal memory adapter: show a short-lived confirmation in memory settings. This never saves a fact. Only an explicit device-key decision can confirm it.",
        PropertyList({Property("id",kPropertyTypeString),Property("label",kPropertyTypeString)}),
        [this](const PropertyList& args) -> ReturnValue {
            return MemoryOffer(args["id"].value<std::string>(),args["label"].value<std::string>());
        });
    McpServer::GetInstance().AddTool("self.pet.memory_status",
        "Internal memory adapter: read the matching volatile device-key decision; this cannot create consent or save a fact.",
        PropertyList({Property("id",kPropertyTypeString)}),
        [this](const PropertyList& args) -> ReturnValue { return MemoryStatus(args["id"].value<std::string>()); });
    args.name = "pet_tick";
    args.arg = this;
    args.skip_unhandled_events = true;
    args.callback = [](void* context) {
        auto* self = static_cast<PetRuntime*>(context);
        if (!self->tick_pending_.exchange(true)) {
            Application::GetInstance().Schedule([self]() {
                self->Tick();
                self->tick_pending_ = false;
            });
        }
    };
    ESP_ERROR_CHECK(esp_timer_create(&args,&timer_));
    ESP_ERROR_CHECK(esp_timer_start_periodic(timer_,1000000));
    args.name = "pet_sleep_due";
    ESP_ERROR_CHECK(esp_timer_create(&args,&sleep_timer_));
}

uint64_t PetRuntime::TimelineSecond(int64_t second) const {
    return uint64_t(timeline_elapsed_base_)+uint64_t(second>boot_second_ ? second-boot_second_ : 0);
}

void PetRuntime::RecordTimeline(PetTimeline::Kind kind) {
    const bool pending=timeline_.pending;
    timeline_.Record(kind,TimelineSecond(last_second_));
    if (pending && !timeline_.pending) {
        snapshot_.saved_wall=0;
        ESP_LOGW(kTag,"Unprovable offline interval frozen; current care preserved");
    }
}

bool PetRuntime::SyncOffline(int64_t second) {
    const uint64_t wall = Wall();
    const bool pending=timeline_.pending;
    if (!timeline_.Resolve(snapshot_.state,wall,TimelineSecond(second))) {
        if (pending && !timeline_.pending) snapshot_.saved_wall=0;
        return false;
    }
    snapshot_.saved_wall=wall;dirty_=true;
    if (!save_due_) save_due_=second+2;
    ESP_LOGI(kTag,"Offline timeline reconciled once using UTC");
    return true;
}

void PetRuntime::AdvanceNow() {
    const auto now = Second();
    if (SyncOffline(now)) { last_second_=now;return; }
    const auto elapsed = now-last_second_;
    if (elapsed>0) {
        snapshot_.state.Advance(static_cast<uint32_t>(elapsed));
        dirty_ = true;
        last_second_ = now;
    }
}

void PetRuntime::Tick() {
    PollUsb();
    RefreshMemory();
    if (Second()-last_health_second_>=10) {
        last_health_second_ = Second();
        ESP_LOGI(kTag,"pet alive: rev=%lu sat=%d mood=%d energy=%d closeness=%d sleep=%d pending=%d storage=%d",
            static_cast<unsigned long>(snapshot_.state.revision),snapshot_.state.satiety,snapshot_.state.mood,
            snapshot_.state.energy,snapshot_.state.closeness,int(snapshot_.state.sleeping),
            int(snapshot_.sleep_pending),int(storage_ok_));
    }
    if (!storage_ok_) return;
    if (!audio_restored_) {
        Board::GetInstance().GetAudioCodec()->SetOutputVolume(snapshot_.muted ? 0 : snapshot_.last_volume);
        Board::GetInstance().GetBacklight()->SetBrightness(snapshot_.state.sleeping ? 10 : snapshot_.brightness);
        audio_restored_ = true;
    }
    AdvanceNow();
    if (menu_.mode==PetMenu::Mode::Memory) {
        const auto action=admin_.Timeout(Second());
        if (action!=PetMemoryMenu::None) { AdminAction(action);RenderAdmin(); }
    }
    if (menu_.Timeout(Second())) CloseMenu();
    if (menu_.active() && Application::GetInstance().GetDeviceState()!=kDeviceStateIdle) CloseMenu();
    auto& app = Application::GetInstance();
    if(app.PetChat().Complete(app.PetVoiceEpoch(),app.GetAudioService().PetRemotePlaybackSerial(),
        app.GetAudioService().IsPetPlaybackDrained(),app.PetChatAllowed() && !menu_.active() &&
        !memory_page_ && !snapshot_.state.sleeping) && snapshot_.state.Chat()) {
        RecordTimeline(PetTimeline::Chat);
        RecordEvent("voice_chat");
        Changed();
    }
    if (sleep_.Ready(esp_timer_get_time()/1000,app.PetVoiceEpoch(),app.PetSpeechStopSerial(),
                     app.GetAudioService().IsPetPlaybackDrained())) {
        app.CancelPetChat(menu_.active());
        ApplySleep(true);
    }
    // A voice/wake-word request also wakes the logical pet.
    if (snapshot_.state.sleeping && (app.GetDeviceState()==kDeviceStateConnecting ||
        app.GetDeviceState()==kDeviceStateListening || app.GetDeviceState()==kDeviceStateSpeaking)) {
        snapshot_.state.SetSleeping(false);
        RecordTimeline(PetTimeline::Wake);
        RecordEvent("wake");
        Board::GetInstance().GetBacklight()->SetBrightness(snapshot_.brightness);
        Changed();
    }
    display_->SetPetState(snapshot_.state);
    if (dirty_ && ((save_due_ && last_second_>=save_due_) || last_second_-last_save_second_>=300)) Save();
}

void PetRuntime::PollUsb() {
    if constexpr (!kPetUsbDiagnostics) return;
    uint8_t bytes[64];
    const auto count=usb_serial_jtag_ll_read_rxfifo(bytes,sizeof(bytes));
    for (uint32_t i=0;i<count;++i) {
        const auto command=usb_debug_.Push(static_cast<char>(bytes[i]));
        if (command==PetDebug::Command::None) continue;
        ESP_LOGI("PetUsb","dispatch=%d",static_cast<int>(command));
        if (command==PetDebug::Command::State) {
            auto* state=ReadState();
            wifi_ap_record_t ap{};
            cJSON_AddBoolToObject(state,"wifi_connected",esp_wifi_sta_get_ap_info(&ap)==ESP_OK);
            char* text=cJSON_PrintUnformatted(state);
            if (text) { ESP_LOGI("PetUsb","state=%s",text); cJSON_free(text); }
            cJSON_Delete(state);
        } else if (command==PetDebug::Command::WifiPause) {
            PauseWifiForCheck();
        } else if (command==PetDebug::Command::MemoryDemo || command==PetDebug::Command::QueryState || command==PetDebug::Command::RequestFeed) {
            const char* text=command==PetDebug::Command::MemoryDemo ? "请记住，以后叫我测试伙伴" :
                command==PetDebug::Command::QueryState ? "请读取宠物真实状态，告诉我现在的饱食度" : "请给你自己喂食一次，调用工具后告诉我真实结果";
            ESP_LOGI("PetUsb","text_sent=%d",int(Application::GetInstance().SendPetDiagnosticText(text)));
        } else {
            const auto key=(command==PetDebug::Command::Main || command==PetDebug::Command::MainHold) ? PetMenu::Key::Main :
                (command==PetDebug::Command::Feed || command==PetDebug::Command::FeedHold) ? PetMenu::Key::Feed : PetMenu::Key::Pet;
            const bool held=command==PetDebug::Command::MainHold || command==PetDebug::Command::FeedHold || command==PetDebug::Command::PetHold;
            HandleKey(key,held);
        }
    }
}

void PetRuntime::Save() {
    if (!storage_ok_) return;
    AdvanceNow();
    if (const auto wall=Wall();wall && !timeline_.pending) snapshot_.saved_wall=wall;
    PetCheckpoint checkpoint;
    checkpoint.snapshot=snapshot_;checkpoint.timeline=timeline_;
    if (timeline_.pending) {
        const auto elapsed=TimelineSecond(last_second_);
        if (elapsed>UINT32_MAX) {
            timeline_.FreezeUnknown();snapshot_.saved_wall=0;
            checkpoint.snapshot=snapshot_;checkpoint.timeline=timeline_;
        }
        else checkpoint.elapsed=static_cast<uint32_t>(elapsed);
    }
    const auto bytes=checkpoint.Encode();
    const auto legacy=checkpoint.LegacyShadow();
    nvs_handle_t handle;
    auto error = nvs_open("pet_v1",NVS_READWRITE,&handle);
    if (error==ESP_OK) {
        error = nvs_set_blob(handle,"checkpoint_v4",bytes.data(),bytes.size());
        if (error==ESP_OK) error = nvs_commit(handle);
        // The new single blob is authoritative. A shadow failure is reported;
        // the two keys are deliberately not treated as an atomic transaction.
        if (error==ESP_OK) error=nvs_set_blob(handle,"snapshot",legacy.data(),legacy.size());
        if (error==ESP_OK) error=nvs_commit(handle);
        if (error==ESP_OK) error=nvs_set_blob(handle,"shadow_v4",legacy.data(),legacy.size());
        if (error==ESP_OK) error=nvs_commit(handle);
        nvs_close(handle);
    }
    if (error!=ESP_OK) { StorageFault("commit",error); return; }
    dirty_ = false;
    persisted_revision_ = snapshot_.state.revision;
    save_due_ = 0;
    last_save_second_ = Second();
}

void PetRuntime::Changed(bool immediate) {
    dirty_ = true;
    if (!save_due_) save_due_ = Second()+2;
    display_->SetPetState(snapshot_.state);
    if (immediate) Save();
}

bool PetRuntime::WakeIfSleeping() {
    if (!storage_ok_) return true;
    AdvanceNow();
    if (!snapshot_.state.sleeping) return false;
    ApplySleep(false);
    return true;
}

bool PetRuntime::CanCare() {
    if (!storage_ok_) return false;
    if (sleep_.pending) { display_->PlayCare(false,false); return false; }
    if (Application::GetInstance().GetDeviceState()!=kDeviceStateIdle) {
        display_->PlayCare(false,false);
        return false;
    }
    return !WakeIfSleeping();
}

void PetRuntime::Feed() {
    if (!CanCare()) return;
    const bool success = snapshot_.state.Feed()==PetState::Result::Ok;
    if (success) { RecordTimeline(PetTimeline::Feed);Application::GetInstance().PetChat().Care(Application::GetInstance().PetVoiceEpoch()); RecordEvent("feed"); Changed(); }
    display_->PlayCare(success,false);
}

void PetRuntime::Pet() {
    if (!CanCare()) return;
    const bool success = snapshot_.state.Pet()==PetState::Result::Ok;
    if (success) { RecordTimeline(PetTimeline::Pet);Application::GetInstance().PetChat().Care(Application::GetInstance().PetVoiceEpoch()); RecordEvent("pet"); Changed(); }
    display_->PlayCare(success,true);
}

void PetRuntime::ToggleSleep() {
    if (!storage_ok_) return;
    AdvanceNow();
    // Busy-voice cancellation is a separate integration gate; don't mutate
    // sleep underneath an active microphone/network transaction.
    if (Application::GetInstance().GetDeviceState()!=kDeviceStateIdle) {
        display_->PlayCare(false,false);
        return;
    }
    ApplySleep(!snapshot_.state.sleeping);
}

void PetRuntime::ApplySleep(bool value) {
    AdvanceNow();
    if (snapshot_.sleep_pending) ++snapshot_.state.revision;
    snapshot_.sleep_pending = false;
    sleep_.Clear();
    if (sleep_timer_) esp_timer_stop(sleep_timer_); // inactive timer is harmless
    const bool changed=snapshot_.state.sleeping!=value;
    snapshot_.state.SetSleeping(value);
    if (changed) RecordTimeline(value ? PetTimeline::Sleep : PetTimeline::Wake);
    RecordEvent(value ? "sleep" : "wake");
    auto* backlight = Board::GetInstance().GetBacklight();
    if (value && !menu_.active() && Application::GetInstance().GetDeviceState()==kDeviceStateIdle) backlight->SetBrightness(10);
    else backlight->SetBrightness(snapshot_.brightness);
    Changed(true);
}

void PetRuntime::ToggleMute() {
    if (!storage_ok_) return;
    AdvanceNow();
    auto* codec = Board::GetInstance().GetAudioCodec();
    if (!snapshot_.muted && codec->output_volume()>0) snapshot_.last_volume = codec->output_volume();
    snapshot_.muted = !snapshot_.muted;
    if (snapshot_.muted) Application::GetInstance().CancelPetChat(false);
    RecordEvent(snapshot_.muted ? "mute" : "unmute");
    codec->SetOutputVolume(snapshot_.muted ? 0 : snapshot_.last_volume);
    Changed();
    display_->PlayCare(true,true);
}

void PetRuntime::CloseMenu() {
    if (admin_.phase!=PetMemoryMenu::Phase::Closed) {
        if (admin_.phase==PetMemoryMenu::Phase::Pending) AdminAction(PetMemoryMenu::Cancel);
        admin_.Close();ClearAdminValues();
    }
    menu_.Exit();
    Board::GetInstance().GetBacklight()->SetBrightness(snapshot_.state.sleeping ? 10 : snapshot_.brightness);
    display_->HideMenu();
    display_->ShowSystemPage(false);
    Application::GetInstance().ReleasePetInput();
}

void PetRuntime::RenderMenu() {
    static const char* names[] = {"音量","亮度","记忆","诊断","返回"};
    std::string text;
    if (menu_.mode==PetMenu::Mode::List) {
        text = "设置\n";
        for (int i=0;i<5;++i) text += std::string(i==menu_.page ? "> " : "  ")+names[i]+"\n";
    } else if (menu_.mode==PetMenu::Mode::Edit) {
        text = std::string(names[menu_.page])+"\n\n"+std::to_string(menu_.draft)+"%\n\n侧键调整\n主键保存，长按取消";
    } else if (menu_.mode==PetMenu::Mode::Memory) {
        RenderAdmin();return;
    } else {
        char buffer[240];
        if (menu_.diagnostic_page==0) std::snprintf(buffer,sizeof(buffer),"宠物状态\n饱腹 %d  心情 %d\n精力 %d  亲密 %d\n存档版本 %lu\n主键返回，侧键翻页",snapshot_.state.satiety,snapshot_.state.mood,snapshot_.state.energy,snapshot_.state.closeness,static_cast<unsigned long>(persisted_revision_));
        else if (menu_.diagnostic_page==1) std::snprintf(buffer,sizeof(buffer),"时间与存档\n时钟：%s\n存档：%s\n离线间隔省略：%s\n主键返回，侧键翻页",Wall() ? "已校准" : "未校准",storage_ok_ ? "可用" : "异常",timeline_.omitted ? "是" : "否");
        else std::snprintf(buffer,sizeof(buffer),"音频\n设置期间暂停语音输入\n音量 %d%%\n静音：%s\n主键返回，侧键翻页",menu_.volume,snapshot_.muted ? "是" : "否");
        text = buffer;
    }
    display_->ShowMenu(text);
}

void PetRuntime::HandleKey(PetMenu::Key key,bool held) {
    if (!storage_ok_) return;
    auto& app = Application::GetInstance();
    RefreshMemory();
    if (memory_page_) {
        if (held || key==PetMenu::Key::Main || key==PetMenu::Key::Pet) {
            memory_.Decide(!held && key==PetMenu::Key::Main,app.PetVoiceEpoch(),Second());
            memory_page_=false;
            display_->HideMenu();
        }
        return; // Confirmation presses never also feed, pet or start another chat.
    }
    if (menu_.active()) {
        if (menu_.mode==PetMenu::Mode::Memory) {
            menu_.last_input=Second();
            const bool cancel_on_exit=held && key==PetMenu::Key::Main && admin_.phase==PetMemoryMenu::Phase::Pending;
            const auto action=admin_.Press(key,held,Second());
            if (action==PetMemoryMenu::Back) {
                if (cancel_on_exit) AdminAction(PetMemoryMenu::Cancel);
                ClearAdminValues();
                if (held) CloseMenu();
                else { menu_.mode=PetMenu::Mode::List;RenderMenu(); }
            } else { AdminAction(action);RenderAdmin(); }
            return;
        }
        const auto effect = menu_.Press(key,held,Second());
        if (effect==PetMenu::Close) { CloseMenu(); return; }
        if (effect==PetMenu::Preview && menu_.page==1)
            Board::GetInstance().GetBacklight()->SetBrightness(menu_.draft);
        if (effect==PetMenu::Commit) {
            if (menu_.page==0) {
                snapshot_.muted = menu_.volume==0;
                if (menu_.volume>0) snapshot_.last_volume = menu_.volume;
                Board::GetInstance().GetAudioCodec()->SetOutputVolume(menu_.volume);
            } else snapshot_.brightness = menu_.brightness;
            Changed(true);
            if (!storage_ok_) return;
        }
        if (menu_.mode==PetMenu::Mode::Memory) AdminAction(admin_.Open());
        RenderMenu();
        return;
    }
    if (key==PetMenu::Key::Main) {
        if (held) {
            if (!app.CancelPetChat(true)) return;
            menu_.Open(snapshot_.muted ? 0 : snapshot_.last_volume,snapshot_.brightness,Second());
            Board::GetInstance().GetBacklight()->SetBrightness(snapshot_.brightness);
            RenderMenu();
        } else if (!WakeIfSleeping()) {
            if (app.GetDeviceState()==kDeviceStateIdle) app.ToggleChatState();
            else app.CancelPetChat(false);
        }
    } else if (key==PetMenu::Key::Feed) {
        if (held) { if (app.CancelPetChat(false)) ToggleSleep(); }
        else Feed();
    } else if (held) ToggleMute();
    else Pet();
}

void PetRuntime::RecordEvent(const char* event) {
    last_event_ = event;
    last_event_second_ = Second();
}

void PetRuntime::RefreshMemory() {
    memory_.Refresh(Application::GetInstance().PetVoiceEpoch(),Second());
    if (memory_page_ && !memory_.pending()) {
        memory_page_=false;
        display_->HideMenu();
    }
}

cJSON* PetRuntime::MemoryOffer(const std::string& id,const std::string& label) {
    auto& app=Application::GetInstance();
    RefreshMemory();
    bool valid=!label.empty() && label.size()<=100;
    for (unsigned char c:label) if (c<32 || c==127) valid=false;
    if (valid && storage_ok_ && !menu_.active() && !snapshot_.state.sleeping && !sleep_.pending &&
        app.PetMemoryAllowed() && memory_.Offer(id.c_str(),app.PetVoiceEpoch(),Second())) {
        memory_page_=true;
        display_->HideMenu(); // Confirmation is spoken; keep the full-screen eyes visible.
        return MemoryStatus(id);
    }
    auto* root=cJSON_CreateObject();
    cJSON_AddBoolToObject(root,"ok",false);
    cJSON_AddStringToObject(root,"code","MEMORY_CONFIRMATION_UNAVAILABLE");
    return root;
}

cJSON* PetRuntime::MemoryStatus(const std::string& id) {
    RefreshMemory();
    const auto status=memory_.Get(id.c_str(),Application::GetInstance().PetVoiceEpoch(),Second());
    static const char* names[]={"unknown","pending","confirmed","cancelled","expired"};
    auto* root=cJSON_CreateObject();
    cJSON_AddBoolToObject(root,"ok",status!=PetMemory::Status::Unknown);
    cJSON_AddStringToObject(root,"id",id.c_str());
    cJSON_AddStringToObject(root,"status",names[static_cast<int>(status)]);
    return root;
}

cJSON* PetRuntime::VoiceCare(bool petting,uint32_t epoch,uint32_t request) {
    auto* root = cJSON_CreateObject();
    if (!root) throw std::runtime_error("Pet action allocation failed");
    if (!storage_ok_) {
        cJSON_AddBoolToObject(root,"ok",false);
        cJSON_AddStringToObject(root,"code","STORAGE_ERROR");
        cJSON_AddNumberToObject(root,"delta",0);
        return root;
    }
    AdvanceNow();
    const auto result = actions_.Apply(snapshot_.state,epoch,request,petting,
        !menu_.active() && !memory_page_ && !sleep_.pending && Application::GetInstance().PetToolAllowed(epoch));
    if (result.code==PetActions::Code::Ok) {
        RecordTimeline(petting ? PetTimeline::Pet : PetTimeline::Feed);
        Application::GetInstance().PetChat().Care(epoch);
        RecordEvent(petting ? "voice_pet" : "voice_feed");
        Changed(true);
        if (storage_ok_) display_->PlayCare(true,petting,true);
    }
    cJSON_AddBoolToObject(root,"ok",storage_ok_ && result.code==PetActions::Code::Ok);
    cJSON_AddStringToObject(root,"code",storage_ok_ ? PetActions::Name(result.code) : "STORAGE_ERROR");
    cJSON_AddStringToObject(root,"original_code",PetActions::Name(result.original));
    cJSON_AddNumberToObject(root,"delta",result.delta);
    cJSON_AddNumberToObject(root,"revision",snapshot_.state.revision);
    cJSON_AddNumberToObject(root,"request_revision",result.revision);
    cJSON_AddNumberToObject(root,"persisted_revision",persisted_revision_);
    cJSON_AddBoolToObject(root,"durable",storage_ok_ && !dirty_);
    cJSON_AddNumberToObject(root,"satiety",snapshot_.state.satiety);
    cJSON_AddNumberToObject(root,"mood",snapshot_.state.mood);
    cJSON_AddNumberToObject(root,"cooldown_seconds",petting ? snapshot_.state.pet_cooldown : snapshot_.state.feed_cooldown);
    return root;
}

cJSON* PetRuntime::VoiceSleep(bool sleeping,uint32_t epoch,uint32_t request) {
    auto* root = cJSON_CreateObject();
    if (!root) throw std::runtime_error("Pet sleep allocation failed");
    if (!storage_ok_) {
        cJSON_AddBoolToObject(root,"ok",false);
        cJSON_AddStringToObject(root,"code","STORAGE_ERROR");
        return root;
    }
    AdvanceNow();
    auto& app = Application::GetInstance();
    const auto result = actions_.Apply(snapshot_.state,epoch,request,PetActions::Action::SetSleep,
        !menu_.active() && !memory_page_ && app.PetToolAllowed(epoch));
    if (result.code==PetActions::Code::Ok) {
        if (!sleeping) ApplySleep(false);
        else if (!snapshot_.state.sleeping && !snapshot_.sleep_pending) {
            snapshot_.sleep_pending = true;
            ++snapshot_.state.revision;
            RecordEvent("sleep_requested");
            Changed(true); // commit intent before acknowledging, not after TTS
            if (storage_ok_) {
                sleep_.Request(esp_timer_get_time()/1000,epoch,app.PetSpeechStopSerial());
                // Only while waiting: check every 100ms so goodnight completion
                // does not wait for the normal 1-second state tick.
                ESP_ERROR_CHECK(esp_timer_start_periodic(sleep_timer_,100000));
            }
        }
    }
    cJSON_AddBoolToObject(root,"ok",storage_ok_ && result.code==PetActions::Code::Ok);
    cJSON_AddStringToObject(root,"code",storage_ok_ ? PetActions::Name(result.code) : "STORAGE_ERROR");
    cJSON_AddStringToObject(root,"original_code",PetActions::Name(result.original));
    cJSON_AddBoolToObject(root,"sleeping",snapshot_.state.sleeping);
    cJSON_AddBoolToObject(root,"sleep_pending",snapshot_.sleep_pending);
    cJSON_AddBoolToObject(root,"memory_confirmation_pending",memory_page_ && memory_.pending());
    cJSON_AddNumberToObject(root,"revision",snapshot_.state.revision);
    cJSON_AddNumberToObject(root,"delta",0);
    cJSON_AddBoolToObject(root,"durable",storage_ok_ && !dirty_);
    return root;
}

cJSON* PetRuntime::ReadState() {
    auto* root = cJSON_CreateObject();
    if (!root) throw std::runtime_error("Pet state allocation failed");
    cJSON_AddBoolToObject(root,"ok",storage_ok_);
    cJSON_AddStringToObject(root,"code",storage_ok_ ? "OK" : "STORAGE_ERROR");
    if (!storage_ok_) return root; // Do not expose fresh defaults as recovered data.
    AdvanceNow();
    const auto& state = snapshot_.state;
    cJSON_AddNumberToObject(root,"satiety",state.satiety);
    cJSON_AddNumberToObject(root,"mood",state.mood);
    cJSON_AddNumberToObject(root,"energy",state.energy);
    cJSON_AddNumberToObject(root,"closeness",state.closeness);
    cJSON_AddNumberToObject(root,"relationship_interactions",state.interactions);
    cJSON_AddNumberToObject(root,"relationship_window_seconds",state.window_seconds);
    cJSON_AddNumberToObject(root,"relationship_spacing_seconds",state.since_interaction);
    cJSON_AddBoolToObject(root,"sleeping",state.sleeping);
    cJSON_AddBoolToObject(root,"sleep_pending",snapshot_.sleep_pending);
    cJSON_AddBoolToObject(root,"muted",snapshot_.muted);
    cJSON_AddBoolToObject(root,"memory_confirmation_pending",memory_page_ && memory_.pending());
    cJSON_AddNumberToObject(root,"feed_cooldown_seconds",state.feed_cooldown);
    cJSON_AddNumberToObject(root,"pet_cooldown_seconds",state.pet_cooldown);
    cJSON_AddNumberToObject(root,"revision",state.revision);
    cJSON_AddNumberToObject(root,"persisted_revision",persisted_revision_);
    cJSON_AddBoolToObject(root,"unsaved_changes",dirty_);
    cJSON_AddBoolToObject(root,"time_trusted",Wall()!=0);
    cJSON_AddBoolToObject(root,"offline_catchup_pending",timeline_.pending);
    cJSON_AddBoolToObject(root,"offline_gap_omitted",timeline_.omitted);
    cJSON_AddNumberToObject(root,"offline_journal_events",timeline_.count);
    cJSON_AddStringToObject(root,"recent_event",last_event_);
    cJSON_AddNumberToObject(root,"memory_admin_phase",static_cast<int>(admin_.phase));
    cJSON_AddNumberToObject(root,"memory_admin_page",admin_.page);
    cJSON_AddNumberToObject(root,"memory_admin_revision",admin_revision_);
    cJSON_AddBoolToObject(root,"memory_admin_valid",admin_.valid);
    cJSON_AddBoolToObject(root,"memory_admin_unresolved",admin_.unresolved);
    cJSON_AddBoolToObject(root,"memory_admin_busy",admin_busy_);
    if (last_event_second_>=0) cJSON_AddNumberToObject(root,"event_elapsed_seconds",Second()-last_event_second_);
    else cJSON_AddNullToObject(root,"event_elapsed_seconds");
    return root;
}
