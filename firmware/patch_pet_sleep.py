"""Expose guarded TTS completion and real queued/in-flight playback state."""


def apply(source,replace):
    app_h = source/'main/application.h'
    replace(app_h,'    void StopListening();',
            '    uint32_t PetSpeechStopSerial() const { return pet_speech_stop_serial_.load(); }\n    void StopListening();')
    replace(app_h,'    std::mutex mutex_;',
            '    std::mutex mutex_;\n    std::atomic<uint32_t> pet_speech_stop_serial_{0};')
    app = source/'main/application.cc'
    stop = '''            } else if (strcmp(state->valuestring, "stop") == 0) {
                Schedule([this, pet_epoch]() {
                    if (pet_reply_blocked_ || pet_epoch != pet_voice_epoch_.load()) return;'''
    replace(app,stop,stop+'\n                    ++pet_speech_stop_serial_;')
    header = source/'main/audio/audio_service.h'
    audio = source/'main/audio/audio_service.cc'
    replace(header,'    bool IsIdle();','    bool IsPetPlaybackDrained();\n    bool IsIdle();')
    replace(header,'    std::mutex audio_queue_mutex_;',
            '    std::mutex audio_queue_mutex_;\n    bool pet_decode_busy_ = false;\n    bool pet_playback_busy_ = false;')
    replace(audio,'bool AudioService::IsIdle() {', '''bool AudioService::IsPetPlaybackDrained() {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    return audio_decode_queue_.empty() && audio_playback_queue_.empty() &&
           !pet_decode_busy_ && !pet_playback_busy_;
}

bool AudioService::IsIdle() {''')
    replace(audio,'            audio_decode_queue_.pop_front();',
            '            audio_decode_queue_.pop_front();\n            pet_decode_busy_ = true;')
    replace(audio,'            debug_statistics_.decode_count++;',
            '            pet_decode_busy_ = false;\n            debug_statistics_.decode_count++;')
    replace(audio,'        audio_playback_queue_.pop_front();',
            '        audio_playback_queue_.pop_front();\n        pet_playback_busy_ = true;')
    if 'pet_remote_playback_serial_' not in audio.read_text(encoding='utf-8'):
        replace(audio,'        codec_->OutputData(task->pcm);',
                '        codec_->OutputData(task->pcm);\n        { std::lock_guard<std::mutex> output_lock(audio_queue_mutex_); pet_playback_busy_ = false; }')
