"""Target overlay for pausing/cancelling pet voice without stale reply callbacks."""
import re


def apply(source,replace):
    header = source/'main/application.h'
    app = source/'main/application.cc'
    if '    bool SendPetDiagnosticText(const std::string& text);' not in header.read_text(encoding='utf-8'):
        replace(header,'    void ToggleChatState();',
            '    bool SendPetDiagnosticText(const std::string& text);\n    void ToggleChatState();')
    if 'bool Application::SendPetDiagnosticText(' not in app.read_text(encoding='utf-8'):
        replace(app,'void Application::ToggleChatState() {', '''bool Application::SendPetDiagnosticText(const std::string& text) {
    if (device_state_!=kDeviceStateListening || pet_input_paused_ || pet_reply_blocked_ ||
        !protocol_ || !protocol_->IsAudioChannelOpened()) return false;
    protocol_->SendWakeWordDetected(text);
    return true;
}

void Application::ToggleChatState() {''')
    text = header.read_text(encoding='utf-8')
    declarations = '    bool CancelPetChat(bool pause_input = false);\n    void ReleasePetInput();\n    void ToggleChatState();'
    if text.count('    void ReleasePetInput();')==2 and declarations in text:
        header.write_text(text.replace(declarations,'    void ToggleChatState();'),encoding='utf-8',newline='\n')
    replace(header,'#include <deque>','#include <deque>\n#include <atomic>')
    if '    void ReleasePetInput();' not in header.read_text(encoding='utf-8'):
        replace(header,'    void ToggleChatState();',
                '    bool CancelPetChat(bool pause_input = false);\n    void ReleasePetInput();\n    void ToggleChatState();')
    replace(header,'    std::mutex mutex_;',
            '    std::atomic<bool> pet_input_paused_{false};\n    std::atomic<bool> pet_reply_blocked_{false};\n    std::atomic<uint32_t> pet_voice_epoch_{0};\n    std::mutex mutex_;')
    # Upgrade an already-patched checkout without inserting a second cancel helper.
    current=app.read_text(encoding='utf-8')
    if current.count('bool Application::CancelPetChat(bool pause_input) {')==2:
        current,count=re.subn(r'bool Application::CancelPetChat\(bool pause_input\) \{.*?\n\}\n\nvoid Application::ReleasePetInput\(\) \{.*?\n\}\n\n','',current,count=1,flags=re.S)
        if count!=1: raise RuntimeError('Duplicate cancel helper upgrade context changed')
        app.write_text(current,encoding='utf-8',newline='\n')
    if 'bool Application::CancelPetChat(bool pause_input) {' not in app.read_text(encoding='utf-8'):
        replace(app,'void Application::ToggleChatState() {', '''bool Application::CancelPetChat(bool pause_input) {
    if (device_state_ != kDeviceStateIdle && device_state_ != kDeviceStateConnecting &&
        device_state_ != kDeviceStateListening && device_state_ != kDeviceStateSpeaking) return false;
    ++pet_voice_epoch_;
    pet_reply_blocked_ = true;
    pet_input_paused_ = pause_input;
    if (device_state_ == kDeviceStateSpeaking) AbortSpeaking(kAbortReasonNone);
    if (protocol_) protocol_->CloseAudioChannel();
    audio_service_.EnableVoiceProcessing(false);
    audio_service_.DiscardConversationAudio();
    SetDeviceState(kDeviceStateIdle);
    audio_service_.EnableWakeWordDetection(!pause_input);
    return true;
}

void Application::ReleasePetInput() {
    pet_input_paused_ = false;
    if (device_state_ == kDeviceStateIdle) audio_service_.EnableWakeWordDetection(true);
}

void Application::ToggleChatState() {''')
    for method in ['ToggleChatState()','StartListening()','OnWakeWordDetected()',
                   'WakeWordInvoke(const std::string& wake_word)','SetListeningMode(ListeningMode mode)']:
        old = 'void Application::'+method+' {'
        replace(app,old,old+'\n    if (pet_input_paused_) return;')
    original_open = '        board.SetPowerSaveMode(false);\n        if (protocol_->server_sample_rate()'
    previous_open = '        if (pet_input_paused_) return;\n        pet_reply_blocked_ = false;\n'+original_open
    text = app.read_text(encoding='utf-8')
    if previous_open in text:
        app.write_text(text.replace(previous_open,original_open),encoding='utf-8',newline='\n')
    replace(app,original_open,
            '        if (pet_input_paused_) return;\n        ++pet_voice_epoch_;\n        pet_reply_blocked_ = false;\n'+original_open)
    legacy_close = '        board.SetPowerSaveMode(true);\n        const auto closed_epoch = pet_voice_epoch_.load();\n        Schedule([this, closed_epoch]() {\n            if (closed_epoch != pet_voice_epoch_.load()) return;'
    guarded_close = '        board.SetPowerSaveMode(true);\n        pet_reply_blocked_ = true;\n        const auto closed_epoch = ++pet_voice_epoch_;\n        Schedule([this, closed_epoch]() {\n            if (closed_epoch != pet_voice_epoch_.load()) return;\n            audio_service_.DiscardConversationAudio();'
    if legacy_close in app.read_text(encoding='utf-8'):
        replace(app,legacy_close,guarded_close)
    replace(app,'        board.SetPowerSaveMode(true);\n        Schedule([this]() {',guarded_close)
    replace(app,'        if (device_state_ == kDeviceStateSpeaking) {\n            audio_service_.PushPacketToDecodeQueue',
            '        if (!pet_reply_blocked_ && device_state_ == kDeviceStateSpeaking) {\n            audio_service_.PushPacketToDecodeQueue')
    replace(app,'            audio_service_.EnableWakeWordDetection(true);\n            break;',
            '            audio_service_.EnableWakeWordDetection(!pet_input_paused_);\n            break;')
    # Protect queued voice-open tasks as well as their public entry points.
    text = app.read_text(encoding='utf-8')
    marker = '            if (!protocol_->IsAudioChannelOpened()) {'
    guarded = '            if (pet_input_paused_) return;\n'+marker
    if guarded not in text:
        count = text.count(marker)
        if not 1<=count<=4:
            raise RuntimeError('Voice open-task overlay context changed')
        app.write_text(text.replace(marker,guarded),encoding='utf-8',newline='\n')
    text = app.read_text(encoding='utf-8')
    start = text.index('    protocol_->OnIncomingJson(')
    end = text.index('        } else if (strcmp(type->valuestring, "mcp")',start)
    segment = text[start:end]
    if 'const auto pet_epoch' not in segment:
        segment = segment.replace('        // Parse JSON data',
            '        const auto pet_epoch = pet_voice_epoch_.load();\n        // Parse JSON data')
        segment = segment.replace('        auto type = cJSON_GetObjectItem(root, "type");',
            '        auto type = cJSON_GetObjectItem(root, "type");\n        if (!cJSON_IsString(type)) return;\n        if (pet_reply_blocked_ && (strcmp(type->valuestring,"tts")==0 || strcmp(type->valuestring,"stt")==0 || strcmp(type->valuestring,"llm")==0)) return;')
        segment = segment.replace('            auto state = cJSON_GetObjectItem(root, "state");',
            '            auto state = cJSON_GetObjectItem(root, "state");\n            if (!cJSON_IsString(state)) return;')
        segment,count = re.subn(r'Schedule\(\[this([^\]]*)\]\(\) \{',
            r'Schedule([this, pet_epoch\1]() {\n                    if (pet_reply_blocked_ || pet_epoch != pet_voice_epoch_.load()) return;',segment)
        if count!=5:
            raise RuntimeError('Voice reply overlay context changed')
        app.write_text(text[:start]+segment+text[end:],encoding='utf-8',newline='\n')
    # Drop queued encoder/decoder work from the cancelled conversation. Generation
    # checks prevent an in-flight conversion from repopulating the cleared queues.
    audio_h = source/'main/audio/audio_service.h'
    audio = source/'main/audio/audio_service.cc'
    replace(audio_h,'    void ResetDecoder();','    void DiscardConversationAudio();\n    void ResetDecoder();')
    replace(audio_h,'    std::mutex audio_queue_mutex_;',
            '    uint32_t conversation_generation_ = 0; // protected by audio_queue_mutex_\n    std::mutex audio_queue_mutex_;')
    old_discard = '''void AudioService::DiscardConversationAudio() {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    ++conversation_generation_;
    audio_encode_queue_.clear(); audio_send_queue_.clear();
    audio_decode_queue_.clear(); audio_playback_queue_.clear();
    audio_testing_queue_.clear(); timestamp_queue_.clear();
    audio_queue_cv_.notify_all();
}'''
    new_discard = old_discard.replace('    ++conversation_generation_;\n    audio_encode_queue_.clear(); audio_send_queue_.clear();',
            '    ++conversation_generation_;\n    const auto queued_decode = audio_decode_queue_.size();\n'
            '    const auto queued_playback = audio_playback_queue_.size();\n'
            '    audio_encode_queue_.clear(); audio_send_queue_.clear();')
    new_discard = new_discard.replace('    audio_testing_queue_.clear(); timestamp_queue_.clear();\n    audio_queue_cv_.notify_all();',
            '    audio_testing_queue_.clear(); timestamp_queue_.clear();\n'
            '    ESP_LOGI("PetAudio", "discard generation=%u decode=%u playback=%u remaining=%u",\n'
            '        unsigned(conversation_generation_), unsigned(queued_decode), unsigned(queued_playback),\n'
            '        unsigned(audio_decode_queue_.size()+audio_playback_queue_.size()));\n'
            '    audio_queue_cv_.notify_all();')
    if old_discard in audio.read_text(encoding='utf-8'):
        replace(audio,old_discard,new_discard)
    replace(audio,'void AudioService::ResetDecoder() {',new_discard+'\n\nvoid AudioService::ResetDecoder() {')
    replace(audio,'            auto packet = std::move(audio_decode_queue_.front());',
            '            const auto generation = conversation_generation_;\n            auto packet = std::move(audio_decode_queue_.front());')
    replace(audio,'                audio_playback_queue_.push_back(std::move(task));',
            '                if (generation == conversation_generation_) audio_playback_queue_.push_back(std::move(task));')
    replace(audio,'            auto task = std::move(audio_encode_queue_.front());',
            '            const auto generation = conversation_generation_;\n            auto task = std::move(audio_encode_queue_.front());')
    replace(audio,'                    audio_send_queue_.push_back(std::move(packet));',
            '                    if (generation == conversation_generation_) audio_send_queue_.push_back(std::move(packet));')
    replace(audio,'                audio_testing_queue_.push_back(std::move(packet));',
            '                if (generation == conversation_generation_) audio_testing_queue_.push_back(std::move(packet));')
