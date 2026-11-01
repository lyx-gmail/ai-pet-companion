// LVGL adapter only. Movement/shape algorithms are upstream FluxGarage RoboEyes.
// This file and its linked RoboEyes firmware module are GPL-3.0-or-later.
#include "pet_display.h"
#include "device_state_event.h"
#include <esp_timer.h>
#include <esp_random.h>
#include <array>
#include <cstring>

namespace pet_robo {
using byte = uint8_t;
static uint32_t millis() { return static_cast<uint32_t>(esp_timer_get_time() / 1000); }
static long random(long upper) { return upper > 0 ? esp_random() % upper : 0; }
#include "FluxGarage_RoboEyes.h"
}

struct PetDisplay::Eyes {
    struct Shape { bool triangle; int a, b, c, d, e, f; uint8_t color; };
    // At most 9 primitives in the upstream renderer, including three sweat drops.
    std::array<Shape, 16> shapes{};
    size_t count = 0;
    lv_obj_t* object = nullptr;
    lv_timer_t* timer = nullptr;
    DeviceState state = kDeviceStateStarting;
    bool system_page = false;
    bool sleeping = false;
    bool eyes_closed = false;
    uint8_t base_mood = DEFAULT;
    uint8_t voice_mood = DEFAULT;
    int64_t voice_until = 0;
    uint8_t action_mood = DEFAULT;
    int64_t action_until = 0;
    pet_robo::RoboEyes<Eyes> engine;

    Eyes() : engine(*this) {}
    void clearDisplay() { count = 0; }
    void display() { if (object) lv_obj_invalidate(object); }
    void fillRoundRect(int x, int y, int w, int h, int r, uint8_t color) {
        if (w > 0 && h > 0 && count < shapes.size()) shapes[count++] = {false,x,y,w,h,r,0,color};
    }
    void fillTriangle(int x1, int y1, int x2, int y2, int x3, int y3, uint8_t color) {
        if (count < shapes.size()) shapes[count++] = {true,x1,y1,x2,y2,x3,y3,color};
    }
    void Draw(lv_layer_t* layer) {
        lv_area_t origin;
        lv_obj_get_coords(object, &origin);
        for (size_t i = 0; i < count; ++i) {
            const auto& s = shapes[i];
            auto color = s.color ? lv_color_white() : lv_color_black();
            if (s.triangle) {
                lv_draw_triangle_dsc_t d;
                lv_draw_triangle_dsc_init(&d);
                d.color = color; d.opa = LV_OPA_COVER;
                d.p[0] = {static_cast<lv_value_precise_t>(origin.x1+s.a), static_cast<lv_value_precise_t>(origin.y1+s.b)};
                d.p[1] = {static_cast<lv_value_precise_t>(origin.x1+s.c), static_cast<lv_value_precise_t>(origin.y1+s.d)};
                d.p[2] = {static_cast<lv_value_precise_t>(origin.x1+s.e), static_cast<lv_value_precise_t>(origin.y1+s.f)};
                lv_draw_triangle(layer, &d);
            } else {
                lv_draw_rect_dsc_t d;
                lv_draw_rect_dsc_init(&d);
                d.bg_color = color; d.bg_opa = LV_OPA_COVER; d.radius = s.e;
                lv_area_t area = {origin.x1+s.a,origin.y1+s.b,origin.x1+s.a+s.c-1,origin.y1+s.b+s.d-1};
                lv_draw_rect(layer, &d, &area);
            }
        }
    }
    bool Normal() const {
        return !system_page && (state == kDeviceStateIdle || state == kDeviceStateConnecting ||
                               state == kDeviceStateListening || state == kDeviceStateSpeaking);
    }
    void Visibility() {
        if (Normal()) { lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN); lv_obj_move_foreground(object); }
        else lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
    }
    void Resolve() {
        const auto now = esp_timer_get_time();
        const bool sleep_face = sleeping && state==kDeviceStateIdle;
        if (sleep_face!=eyes_closed) {
            eyes_closed = sleep_face;
            engine.setAutoblinker(!sleep_face,4,4);
            if (sleep_face) engine.close();
            else engine.open();
            if (timer) lv_timer_set_period(timer,sleep_face ? 100 : 33);
        }
        engine.setIdleMode(state==kDeviceStateIdle && !sleep_face && now>=action_until,4,4);
        engine.setCuriosity(state==kDeviceStateListening);
        uint8_t mood = base_mood;
        if (state==kDeviceStateSpeaking && now<voice_until) mood = voice_mood;
        if ((state==kDeviceStateIdle || state==kDeviceStateListening) && now<action_until) mood = action_mood;
        if (sleep_face) mood = TIRED;
        engine.setMood(mood);
    }
};

PetDisplay::PetDisplay(esp_lcd_panel_io_handle_t io, esp_lcd_panel_handle_t panel,
        int width, int height, int ox, int oy, bool mx, bool my, bool swap)
    : SpiLcdDisplay(io,panel,width,height,ox,oy,mx,my,swap) {
    DisplayLockGuard lock(this);
    eyes_ = new Eyes();
    auto& e = *eyes_;
    e.object = lv_obj_create(lv_screen_active());
    lv_obj_set_size(e.object,width,height);
    lv_obj_set_pos(e.object,0,0);
    lv_obj_set_style_bg_color(e.object,lv_color_black(),0);
    lv_obj_set_style_bg_opa(e.object,LV_OPA_COVER,0);
    lv_obj_set_style_border_width(e.object,0,0);
    lv_obj_set_style_pad_all(e.object,0,0);
    lv_obj_set_style_radius(e.object,0,0);
    lv_obj_remove_flag(e.object,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(e.object,[](lv_event_t* event) {
        static_cast<Eyes*>(lv_event_get_user_data(event))->Draw(lv_event_get_layer(event));
    },LV_EVENT_DRAW_MAIN,&e);
    e.engine.begin(width,height,30);
    e.engine.setWidth(78,78); e.engine.setHeight(88,88);
    e.engine.setBorderradius(25,25); e.engine.setSpacebetween(24);
    e.engine.setCuriosity(true);
    e.engine.setAutoblinker(true,4,4); e.engine.setIdleMode(true,4,4);
    e.Visibility();
    e.timer = lv_timer_create([](lv_timer_t* timer) {
        auto* eyes = static_cast<Eyes*>(lv_timer_get_user_data(timer));
        if (eyes->Normal()) { eyes->Resolve(); eyes->engine.drawEyes(); }
    },33,&e);
    DeviceStateEventManager::GetInstance();
    ESP_ERROR_CHECK(esp_event_handler_instance_register(XIAOZHI_STATE_EVENTS,XIAOZHI_STATE_CHANGED_EVENT,
        [](void* instance,esp_event_base_t,int32_t,void* data) {
            static_cast<PetDisplay*>(instance)->OnState(static_cast<device_state_event_data_t*>(data)->current_state);
        },this,&state_handler_));
}

PetDisplay::~PetDisplay() {
    if (state_handler_) esp_event_handler_instance_unregister(XIAOZHI_STATE_EVENTS,XIAOZHI_STATE_CHANGED_EVENT,state_handler_);
    DisplayLockGuard lock(this);
    if (eyes_) { lv_timer_delete(eyes_->timer); lv_obj_delete(eyes_->object); delete eyes_; }
    if (menu_) lv_obj_delete(menu_);
}

void PetDisplay::ShowMenu(const std::string& text) {
    DisplayLockGuard lock(this);
    eyes_->system_page = true;
    eyes_->Visibility();
    if (!menu_) {
        menu_ = lv_obj_create(lv_screen_active());
        lv_obj_set_size(menu_,240,240);
        lv_obj_set_pos(menu_,0,0);
        lv_obj_set_style_bg_color(menu_,lv_color_black(),0);
        lv_obj_set_style_bg_opa(menu_,LV_OPA_COVER,0);
        lv_obj_set_style_border_width(menu_,0,0);
        lv_obj_set_style_radius(menu_,0,0);
        lv_obj_set_style_pad_all(menu_,10,0);
        lv_obj_remove_flag(menu_,LV_OBJ_FLAG_SCROLLABLE);
        menu_label_ = lv_label_create(menu_);
        lv_obj_set_width(menu_label_,220);
        lv_obj_set_style_text_color(menu_label_,lv_color_white(),0);
        lv_obj_set_style_text_font(menu_label_,lv_obj_get_style_text_font(chat_message_label_,LV_PART_MAIN),0);
    }
    lv_label_set_text(menu_label_,text.c_str());
    lv_obj_remove_flag(menu_,LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(menu_);
}

void PetDisplay::HideMenu() {
    DisplayLockGuard lock(this);
    if (menu_) lv_obj_add_flag(menu_,LV_OBJ_FLAG_HIDDEN);
}

void PetDisplay::OnState(DeviceState state) {
    DisplayLockGuard lock(this);
    eyes_->state = state;
    if (state!=kDeviceStateIdle) {
        eyes_->action_until = 0;
        eyes_->engine.laugh = false;
        eyes_->engine.confused = false;
    }
    if (state != kDeviceStateIdle) eyes_->engine.setPosition(DEFAULT);
    eyes_->Resolve();
    eyes_->Visibility();
}

void PetDisplay::ShowSystemPage(bool visible) {
    DisplayLockGuard lock(this);
    eyes_->system_page = visible;
    eyes_->Visibility();
}

void PetDisplay::SetEmotion(const char* emotion) {
    if (!eyes_ || !emotion) return;
    DisplayLockGuard lock(this);
    auto& engine = eyes_->engine;
    unsigned char mood = DEFAULT;
    if (!strcmp(emotion,"happy") || !strcmp(emotion,"delicious") || !strcmp(emotion,"loving") || !strcmp(emotion,"laughing")) mood = HAPPY;
    else if (!strcmp(emotion,"sleepy") || !strcmp(emotion,"sad")) mood = TIRED;
    else if (!strcmp(emotion,"angry")) mood = ANGRY;
    eyes_->voice_mood = mood;
    eyes_->voice_until = esp_timer_get_time()+6000000;
    eyes_->Resolve();
    if (!strcmp(emotion,"laughing")) engine.anim_laugh();
    if (!strcmp(emotion,"confused")) engine.anim_confused();
    if (!strcmp(emotion,"winking")) engine.blink(true,false);
}

void PetDisplay::SetPetState(const PetState& state) {
    DisplayLockGuard lock(this);
    eyes_->sleeping = state.sleeping;
    eyes_->base_mood = state.energy<25 || state.satiety<20 || state.mood<30 ? TIRED :
        state.mood>=85 ? HAPPY : DEFAULT;
    eyes_->Resolve();
}

void PetDisplay::PlayCare(bool success,bool petting,bool from_voice) {
    DisplayLockGuard lock(this);
    if ((success && eyes_->state!=kDeviceStateIdle && !(from_voice && eyes_->state==kDeviceStateListening)) || eyes_->sleeping) return;
    eyes_->action_mood = success ? HAPPY : DEFAULT;
    eyes_->action_until = esp_timer_get_time()+(success ? 1500000 : 700000);
    eyes_->engine.setPosition(DEFAULT);
    if (success && petting) eyes_->engine.anim_laugh();
    else if (!success) eyes_->engine.anim_confused();
    eyes_->Resolve();
}

void PetDisplay::SetChatMessage(const char* role,const char* content) {
    // Keep the original text model available for explicit system/diagnostic pages.
    // The opaque face covers it in pet mode, including asynchronous notifications.
    SpiLcdDisplay::SetChatMessage(role,content);
}
