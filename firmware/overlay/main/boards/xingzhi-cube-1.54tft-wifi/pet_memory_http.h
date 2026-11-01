#pragma once
#include <string>

struct PetMemoryHttpReply { int status=0;std::string body; };
PetMemoryHttpReply PetMemoryHttpPost(const std::string& body);
