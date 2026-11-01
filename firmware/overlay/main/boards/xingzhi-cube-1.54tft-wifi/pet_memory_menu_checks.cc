#include "pet_memory_menu.h"

constexpr bool MemoryNavigation() {
    PetMemoryMenu view;
    if (view.Open()!=PetMemoryMenu::Load || view.valid) return false;
    view.Loaded(1);
    if (view.Press(PetMenu::Key::Pet,false,0)!=PetMemoryMenu::None || view.page!=1) return false;
    if (view.Press(PetMenu::Key::Main,false,0)!=PetMemoryMenu::None) return false; // empty preference
    view.Press(PetMenu::Key::Feed,false,0);
    if (view.Press(PetMenu::Key::Main,false,1)!=PetMemoryMenu::Create) return false;
    if (view.Press(PetMenu::Key::Main,false,2)!=PetMemoryMenu::None) return false;
    view.Draft(2,25);
    if (view.Press(PetMenu::Key::Feed,false,3)!=PetMemoryMenu::Cancel) return false;
    return !view.valid && !view.unresolved;
}
constexpr bool MemoryConfirmation() {
    PetMemoryMenu view;view.Open();view.Loaded(1);
    view.Press(PetMenu::Key::Main,false,0);view.Draft(1,25);
    if (view.Press(PetMenu::Key::Main,false,2)!=PetMemoryMenu::Confirm || !view.unresolved) return false;
    view.Failed(PetMemoryMenu::Confirm,false);
    if (view.phase!=PetMemoryMenu::Phase::Uncertain || view.valid) return false;
    view.Close();
    if (view.Open()!=PetMemoryMenu::None || view.phase!=PetMemoryMenu::Phase::Uncertain) return false;
    return view.Press(PetMenu::Key::Main,false,3)==PetMemoryMenu::Confirm;
}
constexpr bool MemoryTimeout() {
    PetMemoryMenu view;view.Open();view.Loaded(0);view.page=5;
    if (view.Press(PetMenu::Key::Main,false,0)!=PetMemoryMenu::Create) return false;
    view.Draft(1,25);
    if (view.Timeout(25)!=PetMemoryMenu::None) return false;
    if (view.Timeout(26)!=PetMemoryMenu::Cancel || view.unresolved) return false;
    view.Loaded(1);view.Press(PetMenu::Key::Main,false,30);view.Draft(31,1);
    return view.Press(PetMenu::Key::Main,false,32)==PetMemoryMenu::Cancel;
}
static_assert(MemoryNavigation(),"Navigation and empty slots must never delete");
static_assert(MemoryConfirmation(),"Uncertain commits retry the existing transaction, including after exit");
static_assert(MemoryTimeout(),"Expired confirmation cannot commit, including at the boundary");
