#pragma once
#include "display/lcd_display.h"
#include "device_state.h"
#include "pet_state.h"
#include <esp_event.h>

class PetDisplay : public SpiLcdDisplay {
public:
    PetDisplay(esp_lcd_panel_io_handle_t io, esp_lcd_panel_handle_t panel,
               int width, int height, int ox, int oy, bool mx, bool my, bool swap);
    ~PetDisplay() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void ShowSystemPage(bool visible);
    void ShowMenu(const std::string& text);
    void HideMenu();
    void SetPetState(const PetState& state);
    void PlayCare(bool success,bool petting,bool from_voice = false);
private:
    struct Eyes;
    Eyes* eyes_ = nullptr;
    lv_obj_t* menu_ = nullptr;
    lv_obj_t* menu_label_ = nullptr;
    esp_event_handler_instance_t state_handler_ = nullptr;
    void OnState(DeviceState state);
};
