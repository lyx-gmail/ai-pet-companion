#include "pet_menu.h"

constexpr bool MenuEdits() {
    PetMenu menu;
    menu.Open(60,75,10);
    menu.Press(PetMenu::Key::Main,false,11);
    menu.Press(PetMenu::Key::Feed,false,12);
    if (menu.draft!=50 || menu.volume!=60) return false;
    if (menu.Press(PetMenu::Key::Main,false,13)!=PetMenu::Commit || menu.volume!=50) return false;
    menu.Press(PetMenu::Key::Pet,false,14);
    menu.Press(PetMenu::Key::Main,false,15);
    menu.Press(PetMenu::Key::Pet,false,16);
    if (menu.draft!=85 || menu.brightness!=75) return false;
    if (!menu.Timeout(46) || menu.active() || menu.brightness!=75 || menu.draft!=75) return false;
    return true;
}
constexpr bool MenuBoundaries() {
    PetMenu menu;
    menu.Open(0,10,0);
    menu.Press(PetMenu::Key::Main,false,0);
    menu.Press(PetMenu::Key::Feed,false,1);
    if (menu.draft!=0) return false;
    if (menu.Press(PetMenu::Key::Pet,true,2)!=PetMenu::None || menu.draft!=0) return false;
    if (menu.Press(PetMenu::Key::Main,true,3)!=PetMenu::Close || menu.active()) return false;
    menu.Open(100,100,4);
    menu.Press(PetMenu::Key::Main,false,5);
    menu.Press(PetMenu::Key::Pet,false,6);
    return menu.draft==100 && !menu.Timeout(35) && menu.Timeout(36);
}
static_assert(MenuEdits(),"Drafts must not commit on adjustment, exit or timeout");
static_assert(MenuBoundaries(),"Value bounds, ignored side long presses and timeout must hold");
