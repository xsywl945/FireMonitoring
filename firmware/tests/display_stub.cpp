#include <string>

#include "display.h"

std::string displayLine1;
std::string displayLine2;

void displayBegin() {}

void displayShow(const char* line1, const char* line2) {
  displayLine1 = line1;
  displayLine2 = line2;
}
