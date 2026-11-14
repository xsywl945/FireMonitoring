#include <cassert>
#include <iostream>
#include <string>

#include "Arduino.h"
#include "panel.h"

extern std::string displayLine1;
extern std::string displayLine2;

std::string send(const std::string& command) {
  Serial.input = command + "\n";
  Serial.output.clear();
  while (Serial.available()) loop();
  return Serial.output;
}

void settle(uint32_t milliseconds) {
  testTime += milliseconds;
  loop();
}

int main() {
  setup();
  assert(send("HELLO") == "READY FIRE_PANEL_V2\n");
  assert(send("MODE GREEN") == "MODE GREEN\n");
  assert(pins[PIN_GREEN].level == HIGH);
  assert(pins[PIN_RED].level == LOW);
  assert(pins[PIN_BUZZER].level == LOW);
  assert(displayLine1 == "GREEN");
  assert(send("MODE NOPE") == "ERR MODE\n");
  assert(send("MODE RED_SOLID") == "MODE RED_SOLID\n");
  assert(pins[PIN_RED].level == HIGH);
  assert(pins[PIN_BUZZER].level == HIGH);
  pins[PIN_MUTE].level = LOW;
  loop();
  settle(30);
  assert(pins[PIN_BUZZER].level == LOW);
  assert(pins[PIN_RED].level == HIGH);
  assert(send("STATUS").find("STATE RED_SOLID MUTE UP") == 0);
  pins[PIN_MUTE].level = HIGH;
  loop();
  settle(30);
  settle(3000);
  assert(displayLine1 == "ALT");
  bool yellow = pins[PIN_YELLOW].level == HIGH;
  bool red = pins[PIN_RED].level == HIGH;
  assert(yellow != red);
  settle(250);
  assert(displayLine1 == "ALT");
  assert(pins[PIN_YELLOW].level != yellow);
  assert(send("STATUS") == "STATE RED_SOLID MUTE UP\n");
  assert(send("PING") == "PONG\n");
  assert(send("MODE OFF") == "MODE OFF\n");
  assert(pins[PIN_RED].level == LOW);
  assert(pins[PIN_YELLOW].level == LOW);
  std::cout << "Panel firmware protocol tests passed\n";
}
