"""Track ASR + reply text + real remote PCM output, then credit a completed turn."""

def apply(source,replace):
    header=source/'main/application.h'
    app=source/'main/application.cc'
    abort='void Application::AbortSpeaking(AbortReason reason) {'
    replace(app,abort,abort+'\n    pet_conversation_.Cancel();')
    audio_h=source/'main/audio/audio_service.h'
    audio=source/'main/audio/audio_service.cc'
    protocol=source/'main/protocols/protocol.h'
    replace(header,'#include <atomic>', '#include <atomic>\n#include "boards/xingzhi-cube-1.54tft-wifi/pet_conversation.h"')
    replace(header,'    uint32_t PetSpeechStopSerial() const',
        '    PetConversation& PetChat() { return pet_conversation_; }\n'
        '    bool PetChatAllowed() const { return !pet_input_paused_ && !pet_reply_blocked_; }\n'
        '    uint32_t PetSpeechStopSerial() const')
    replace(header,'    std::atomic<uint32_t> pet_speech_stop_serial_{0};',
        '    std::atomic<uint32_t> pet_speech_stop_serial_{0};\n    PetConversation pet_conversation_;')
    # This flag is local queue metadata, not part of the binary wire header.
    replace(protocol,'    std::vector<uint8_t> payload;',
        '    std::vector<uint8_t> payload;\n    bool pet_remote = false;')
    replace(audio_h,'    AudioTaskType type;', '    AudioTaskType type;\n    bool pet_remote = false;')
    replace(audio_h,'    bool IsPetPlaybackDrained();',
        '    uint32_t PetRemotePlaybackSerial();\n    bool IsPetPlaybackDrained();')
    replace(audio_h,'    bool pet_playback_busy_ = false;',
        '    bool pet_playback_busy_ = false;\n    uint32_t pet_remote_playback_serial_ = 0;')
    replace(audio,'bool AudioService::IsPetPlaybackDrained() {',
        'uint32_t AudioService::PetRemotePlaybackSerial() {\n'
        '    std::lock_guard<std::mutex> lock(audio_queue_mutex_);\n'
        '    return pet_remote_playback_serial_;\n}\n\n'
        'bool AudioService::IsPetPlaybackDrained() {')
    replace(audio,'            task->timestamp = packet->timestamp;',
        '            task->timestamp = packet->timestamp;\n            task->pet_remote = packet->pet_remote;')
    replace(audio,'        { std::lock_guard<std::mutex> output_lock(audio_queue_mutex_); pet_playback_busy_ = false; }',
        '        { std::lock_guard<std::mutex> output_lock(audio_queue_mutex_);\n'
        '          if(task->pet_remote && !task->pcm.empty()) ++pet_remote_playback_serial_;\n'
        '          pet_playback_busy_ = false; }')
    incoming='    protocol_->OnIncomingAudio([this](std::unique_ptr<AudioStreamPacket> packet) {'
    replace(app,incoming,incoming+'\n        packet->pet_remote = true;')
    start='''                    aborted_ = false;
                    if (device_state_ == kDeviceStateIdle || device_state_ == kDeviceStateListening) {'''
    replace(app,start,'''                    pet_conversation_.Start(pet_epoch,audio_service_.PetRemotePlaybackSerial());
'''+start)
    replace(app,'                    ++pet_speech_stop_serial_;',
        '                    ++pet_speech_stop_serial_;\n                    pet_conversation_.Stop(pet_epoch);')
    replace(app,'                        display->SetChatMessage("assistant", message.c_str());',
        '                        pet_conversation_.Reply(pet_epoch,message.find_first_not_of(" \\t\\r\\n")!=std::string::npos);\n'
        '                        display->SetChatMessage("assistant", message.c_str());')
    old='''                Schedule([this, pet_epoch, display, message = std::string(text->valuestring)]() {
                    if (pet_reply_blocked_ || pet_epoch != pet_voice_epoch_.load()) return;
                    display->SetChatMessage("user", message.c_str());'''
    new='''                const auto audio_origin=cJSON_GetObjectItem(root,"pet_audio");
                const auto input_turn=cJSON_GetObjectItem(root,"pet_turn");
                const bool pet_audio=cJSON_IsTrue(audio_origin);
                const uint32_t pet_turn=cJSON_IsNumber(input_turn) && input_turn->valuedouble==input_turn->valueint && input_turn->valueint>0 ? input_turn->valueint : 0;
                Schedule([this, pet_epoch, pet_audio, pet_turn, display, message = std::string(text->valuestring)]() {
                    if (pet_reply_blocked_ || pet_epoch != pet_voice_epoch_.load()) return;
                    pet_conversation_.Transcript(pet_epoch,pet_turn,pet_audio && message.find_first_not_of(" \\t\\r\\n")!=std::string::npos,audio_service_.PetRemotePlaybackSerial());
                    display->SetChatMessage("user", message.c_str());'''
    replace(app,old,new)
