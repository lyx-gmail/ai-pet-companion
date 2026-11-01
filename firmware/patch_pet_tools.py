"""Bind care actions to transport identity, outside the model-visible schema."""


def apply(source,replace):
    if '    uint32_t PetVoiceEpoch() const' not in (source/'main/application.h').read_text(encoding='utf-8'):
        replace(source/'main/application.h','    void ReleasePetInput();',
            '''    void ReleasePetInput();
    uint32_t PetVoiceEpoch() const { return pet_voice_epoch_.load(); }
    bool PetToolAllowed(uint32_t epoch) const {
        return epoch == pet_voice_epoch_.load() && !pet_input_paused_ &&
               !pet_reply_blocked_ && device_state_ == kDeviceStateListening;
    }''')
    header = source/'main/mcp_server.h'
    replace(source/'main/application.h','    uint32_t PetVoiceEpoch() const',
            '    bool PetMemoryAllowed() const {\n'
            '        return !pet_input_paused_ && !pet_reply_blocked_ &&\n'
            '            (device_state_ == kDeviceStateListening || device_state_ == kDeviceStateSpeaking);\n'
            '    }\n    uint32_t PetVoiceEpoch() const')
    # TTS start is emitted before tool evaluation, so Speaking is an active turn
    # even when no speech samples have yet played. Keep epoch/cancel/pause gates.
    replace(source/'main/application.h',
            '        return epoch == pet_voice_epoch_.load() && !pet_input_paused_ &&\n'
            '               !pet_reply_blocked_ && device_state_ == kDeviceStateListening;',
            '        return epoch == pet_voice_epoch_.load() && PetMemoryAllowed();')
    mcp = source/'main/mcp_server.cc'
    replace(header,'void DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments);',
            'void DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments, int pet_request);')
    replace(mcp,'        DoToolCall(id_int, std::string(tool_name->valuestring), tool_arguments);',
            '''        auto meta = cJSON_GetObjectItem(params, "_meta");
        auto pet_id = cJSON_IsObject(meta) ? cJSON_GetObjectItem(meta, "pet_request_id") : nullptr;
        const int pet_request = cJSON_IsNumber(pet_id) && pet_id->valuedouble == pet_id->valueint && pet_id->valueint > 0 ? pet_id->valueint : -1;
        DoToolCall(id_int, std::string(tool_name->valuestring), tool_arguments, pet_request);''')
    replace(mcp,'void McpServer::DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments) {',
            'void McpServer::DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments, int pet_request) {')
    original = '''    // Use main thread to call the tool
    auto& app = Application::GetInstance();
    app.Schedule([this, id, tool_iter, arguments = std::move(arguments)]() {'''
    patched = '''    // Pet identity is adapter-owned. Extra model arguments cannot replace it.
    auto& app = Application::GetInstance();
    if (tool_name == "self.pet.feed" || tool_name == "self.pet.pet" || tool_name == "self.pet.set_sleep") {
        arguments.AddProperty(Property("_pet_epoch", kPropertyTypeInteger, static_cast<int>(app.PetVoiceEpoch())));
        arguments.AddProperty(Property("_pet_request_id", kPropertyTypeInteger, pet_request));
    }
    // Use main thread to call the tool
    app.Schedule([this, id, tool_iter, arguments = std::move(arguments)]() {'''
    previous = patched.replace('kPropertyTypeInteger, pet_request','kPropertyTypeInteger, id')
    text = mcp.read_text(encoding='utf-8')
    text = text.replace('tool_name == "self.pet.feed" || tool_name == "self.pet.pet")',
                        'tool_name == "self.pet.feed" || tool_name == "self.pet.pet" || tool_name == "self.pet.set_sleep")')
    if previous in text:
        text = text.replace(previous,patched)
    mcp.write_text(text,encoding='utf-8',newline='\n')
    replace(mcp,original,patched)
