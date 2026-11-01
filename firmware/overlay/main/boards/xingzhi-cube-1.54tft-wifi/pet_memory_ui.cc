#include "pet_runtime.h"
#include "pet_display.h"
#include "pet_memory_http.h"
#include "application.h"
#include <cJSON.h>
#include <esp_log.h>
#include <memory>
#include <new>
#include <cmath>
#include <ctime>

namespace {
int64_t Now() { return esp_timer_get_time()/1000000; }
const char* fields[]={"name","preference0","preference1","preference2","preference3","all"};
const char* titles[]={"称呼","偏好 1","偏好 2","偏好 3","偏好 4","全部记忆（含经历）","如何更正","返回设置"};
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
const cJSON* Item(const cJSON* root,const char* key) { return cJSON_GetObjectItemCaseSensitive(root,key); }
bool Is(const cJSON* value,const char* text) { return cJSON_IsString(value) && value->valuestring && std::string(value->valuestring)==text; }
bool Number(const cJSON* value,uint64_t& result) {
    if (!cJSON_IsNumber(value) || !std::isfinite(value->valuedouble) || value->valuedouble<0 ||
        value->valuedouble>9007199254740991.0 || std::floor(value->valuedouble)!=value->valuedouble) return false;
    result=static_cast<uint64_t>(value->valuedouble);return true;
}
bool Text(const cJSON* value,std::string& result,size_t limit) {
    if (!cJSON_IsString(value) || !value->valuestring) return false;
    result=value->valuestring;
    if (result.empty() || result.size()>limit) return false;
    for (unsigned char c:result) if (c<32 || c==127) return false;
    return true;
}
bool Uuid(const std::string& id) {
    if (id.size()!=36) return false;
    for (size_t i=0;i<36;++i) {
        const auto c=id[i];
        if (i==8 || i==13 || i==18 || i==23) { if (c!='-') return false; }
        else if (!((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
    }
    return true;
}
struct AdminJob {
    PetRuntime* self;
    PetMemoryMenu::Action action;
    uint64_t generation;
    std::string id,body;
};
}

void PetRuntime::ClearAdminValues() { for (auto& value:admin_values_) value.clear(); }

void PetRuntime::AdminAction(PetMemoryMenu::Action action) {
    using View=PetMemoryMenu;
    if (action==View::None || action==View::Back) return;
    if (admin_busy_) {
        admin_.Failed(action,false);ClearAdminValues();admin_error_="请求尚未结束，请稍后重试";return;
    }
    Json root(cJSON_CreateObject(),cJSON_Delete);
    if (!root) { admin_.Failed(action,false);admin_error_="内存不足";return; }
    if (action==View::Load) {
        ClearAdminValues();admin_.valid=false;
        cJSON_AddStringToObject(root.get(),"action","profile");
    } else if (action==View::Create) {
        if (!admin_.valid || admin_.page<0 || admin_.page>5 || admin_.unresolved) return;
        admin_target_=fields[admin_.page];admin_delete_revision_=admin_revision_;
        admin_label_=titles[admin_.page];
        if (admin_.page<5) admin_label_+="\n"+admin_values_[admin_.page];
        cJSON_AddStringToObject(root.get(),"action","delete");
        cJSON_AddStringToObject(root.get(),"field",admin_target_.c_str());
        cJSON_AddNumberToObject(root.get(),"revision",admin_delete_revision_);
    } else {
        if (!Uuid(admin_id_)) {
            admin_.Failed(action,true);admin_error_="确认请求已失效，请刷新";return;
        }
        cJSON_AddStringToObject(root.get(),"action",action==View::Confirm ? "confirm" : "cancel");
        cJSON_AddStringToObject(root.get(),"id",admin_id_.c_str());
    }
    char* encoded=cJSON_PrintUnformatted(root.get());
    if (!encoded) { admin_.Failed(action,false);admin_error_="内存不足";return; }
    std::string body(encoded);cJSON_free(encoded);
    auto* job=new(std::nothrow) AdminJob{this,action,admin_.generation,admin_id_,std::move(body)};
    if (!job) { admin_.Failed(action,false);admin_error_="内存不足";return; }
    admin_busy_=true;
    const auto started=xTaskCreate([](void* argument) {
        {
            std::unique_ptr<AdminJob> request(static_cast<AdminJob*>(argument));
            PetMemoryHttpReply reply;
            try { reply=PetMemoryHttpPost(request->body); } catch (...) {}
            auto* self=request->self;const auto action=request->action;const auto generation=request->generation;
            Application::GetInstance().Schedule([self,action,generation,id=std::move(request->id),reply=std::move(reply)]() {
                self->AdminReply(action,generation,id,reply.status,reply.body);
            });
        }
        vTaskDelete(nullptr);
    },"pet_mem_http",6144,job,2,nullptr);
    if (started!=pdPASS) {
        delete job;admin_busy_=false;admin_.Failed(action,false);admin_error_="无法启动请求";
    }
}

void PetRuntime::AdminReply(PetMemoryMenu::Action action,uint64_t generation,const std::string& id,int status,const std::string& body) {
    using View=PetMemoryMenu;
    admin_busy_=false;
    const bool visible=menu_.mode==PetMenu::Mode::Memory && admin_.generation==generation;
    const char* end=nullptr;
    Json root(body.find('\0')==std::string::npos ? cJSON_ParseWithOpts(body.c_str(),&end,true) : nullptr,cJSON_Delete);
    const bool object=root && cJSON_IsObject(root.get());
    uint64_t receipt=0;
    const bool all=admin_target_=="all";
    const bool committed=action==View::Confirm && id==admin_id_ && status==200 && object &&
        cJSON_IsTrue(Item(root.get(),"ok")) && Number(Item(root.get(),"revision"),receipt) &&
        receipt==admin_delete_revision_+1 && Is(Item(root.get(),"operation"),all ? "delete_all" : "delete") &&
        (all ? cJSON_IsNull(Item(root.get(),"field")) : Is(Item(root.get(),"field"),admin_target_.c_str()));
    if (!visible) {
        if (action==View::Confirm && id==admin_id_ && (committed || (status>=400 && status<500))) {
            admin_.unresolved=false;admin_id_.clear();admin_label_.clear();
        }
        if (action==View::Cancel && id==admin_id_ && status==200) { admin_id_.clear();admin_label_.clear(); }
        return;
    }
    bool good=false;
    if (status==200 && object) {
        if (action==View::Load) {
            uint64_t revision=0;unsigned present=0;std::string values[5];
            bool valid=Number(Item(root.get(),"revision"),revision);
            const auto name=Item(root.get(),"name");
            if (cJSON_IsNull(name)) {}
            else if (Text(name,values[0],24)) present|=1;
            else valid=false;
            const auto prefs=Item(root.get(),"preferences");
            valid=valid && cJSON_IsArray(prefs) && cJSON_GetArraySize(prefs)<=4;
            if (valid) {
                const cJSON* entry=nullptr;
                cJSON_ArrayForEach(entry,prefs) {
                    int slot=-1;
                    for (int i=1;i<5;++i) if (Is(Item(entry,"slot"),fields[i])) slot=i;
                    if (slot<0 || (present&(1u<<slot)) || !Text(Item(entry,"value"),values[slot],80)) { valid=false;break; }
                    present|=1u<<slot;
                }
            }
            if (valid) {
                for (int i=0;i<5;++i) admin_values_[i]=std::move(values[i]);
                admin_revision_=revision;admin_.Loaded(present);good=true;
            }
        } else if (action==View::Create) {
            std::string token;uint64_t expected=0,expires=0;
            if (Is(Item(root.get(),"status"),"PENDING") && Is(Item(root.get(),"kind"),"profile") &&
                Is(Item(root.get(),"op"),all ? "delete_all" : "delete") &&
                (all ? cJSON_IsNull(Item(root.get(),"field")) : Is(Item(root.get(),"field"),admin_target_.c_str())) &&
                Number(Item(root.get(),"expectedRevision"),expected) && expected==admin_delete_revision_ &&
                Number(Item(root.get(),"expiresAt"),expires) && Text(Item(root.get(),"id"),token,36) && Uuid(token)) {
                admin_id_=token;
                // The server enforces absolute expiry. Keep the local UI on
                // monotonic time: vendor wall time includes a timezone offset.
                admin_.Draft(Now(),25);good=true;
            }
        } else if (action==View::Confirm && committed) {
            admin_.unresolved=false;admin_.phase=View::Phase::Done;
            admin_.valid=false;ClearAdminValues();admin_id_.clear();admin_label_.clear();good=true;
        } else if (action==View::Cancel && cJSON_IsBool(Item(root.get(),"cancelled"))) {
            admin_id_.clear();admin_label_.clear();admin_.unresolved=false;
            admin_.phase=View::Phase::Loading;AdminAction(View::Load);good=true;
        }
    }
    if (!good) {
        const bool definite=status>=400 && status<500;
        admin_.Failed(action,definite);ClearAdminValues();
        if (!admin_.unresolved) { admin_id_.clear();admin_label_.clear(); }
        admin_error_=status==409 ? "资料已变化或确认已过期" : status==401 || status==403 ? "设备认证失败，请检查电脑服务" : "服务不可用，请检查电脑和网络";
    }
    ESP_LOGI("PetAdmin","action=%d phase=%d page=%d valid=%d revision=%lu",int(action),int(admin_.phase),admin_.page,int(admin_.valid),static_cast<unsigned long>(admin_revision_));
    RenderAdmin();
}

void PetRuntime::RenderAdmin() {
    using Phase=PetMemoryMenu::Phase;
    if (menu_.mode!=PetMenu::Mode::Memory) return;
    std::string text="记忆管理\n";
    if (admin_.phase==Phase::Browse) {
        text+=std::string(titles[admin_.page])+"\n\n";
        if (admin_.page<5) text+=admin_values_[admin_.page].empty() ? "尚未保存\n\n左右翻页" : admin_values_[admin_.page]+"\n\n中键：准备删除\n左右翻页";
        else if (admin_.page==5) text+="包括称呼、偏好和经历\n中键：准备删除\n左右翻页";
        else text+="中键：打开\n左右翻页";
    } else if (admin_.phase==Phase::Pending) text="确认删除\n"+admin_label_+"\n\n中键：删除\n任一侧键：取消\n超时自动取消";
    else if (admin_.phase==Phase::Uncertain) text+="\n删除结果未知\n请勿重复创建删除请求\n中键：重试原请求\n侧键：返回设置";
    else if (admin_.phase==Phase::Error) text+="\n"+admin_error_+"\n\n中键：刷新\n侧键：返回设置";
    else if (admin_.phase==Phase::Done) text+="\n已删除\n\n中键：刷新资料\n侧键：返回设置";
    else if (admin_.phase==Phase::Help) text+="\n退出设置后说：\n请记住，以后叫我……\n偏好也可按此更正\n须按键确认后才保存\n任意短按：返回";
    else text+="\n正在请求电脑服务……\n\n长按中键可退出";
    display_->ShowMenu(text);
}
