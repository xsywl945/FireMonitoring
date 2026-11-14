#include <cassert>
#include <iostream>
#include <string>

#include "Arduino.h"
#include "actuator.h"

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
  const std::string id = "0123456789abcdef0123456789abcdef";
  const std::string other = "abcdef0123456789abcdef0123456789";
  setup();
  assert(pins[PIN_PUMP].level == LOW);
  assert(pins[PIN_LASER].level == LOW);
  assert(send("HELLO") == "READY FIRE_ACTUATOR_V2\n");
  assert(send("PING") == "PONG\n");
  assert(send("RUN bad 5000") == "ERR FORMAT\n");
  assert(send("RUN " + id + " 30001") == "ERR DURATION\n");
  assert(send("AIM 13000 0") == "ERR LIMIT\n");
  assert(send("AIM 0 7000") == "ERR LIMIT\n");
  assert(send("AIM -12000 6000") == "AIM -12000 6000\n");
  settle(5000);
  assert(send("AIM 0 0") == "AIM 0 0\n");
  settle(5000);
  loop();
  assert(send("AIM 9000 0") == "AIM 9000 0\n");
  settle(100);
  assert(send("STATUS").find("STATE OFF OFF CLEAR 900 ") == 0);

  assert(send("RUN " + id + " 5000") == "ACK " + id + " ON\n");
  assert(pins[PIN_PUMP].level == HIGH);
  assert(send("RUN " + id + " 5000") == "ACK " + id + " ON\n");
  assert(send("LASER ON") == "LASER ON\n");
  assert(pins[PIN_LASER].level == HIGH);
  settle(3000);
  assert(pins[PIN_PUMP].level == LOW);
  assert(pins[PIN_LASER].level == LOW);
  assert(send("STATUS").find("STATE OFF OFF CLEAR ") == 0);
  assert(send("RUN " + id + " 1000") == "ACK " + id + " OFF\n");

  testTime += 100;
  assert(send("RUN " + other + " 5000") == "ACK " + other + " ON\n");
  pins[PIN_ESTOP].level = LOW;
  loop();
  settle(30);
  assert(pins[PIN_PUMP].level == LOW);
  assert(send("RUN " + id + " 5000") == "ERR ESTOP\n");
  assert(send("AIM 0 0") == "ERR ESTOP\n");
  assert(send("UNLOCK") == "ERR ESTOP\n");
  pins[PIN_ESTOP].level = HIGH;
  loop();
  settle(30);
  assert(send("UNLOCK") == "ERR RESET\n");
  pins[PIN_RESET].level = LOW;
  loop();
  settle(30);
  pins[PIN_RESET].level = HIGH;
  loop();
  settle(30);
  assert(send("UNLOCK") == "UNLOCKED\n");
  assert(send("RUN " + id + " 1000") == "ACK " + id + " ON\n");
  assert(pins[PIN_PUMP].level == HIGH);
  assert(send("STOP") == "STOPPED\n");
  assert(pins[PIN_PUMP].level == LOW);
  assert(send(std::string(130, 'X')) == "ERR TOO_LONG\n");
  std::cout << "Actuator firmware protocol tests passed\n";
}
