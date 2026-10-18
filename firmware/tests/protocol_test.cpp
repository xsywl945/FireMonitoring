#include <cassert>
#include <iostream>
#include "../esp32_pump/esp32_pump.ino"

std::string send(const std::string& command) {
  Serial.input = command + "\n";
  Serial.output.clear();
  while (Serial.available()) loop();
  return Serial.output;
}

int main() {
  const std::string id = "0123456789abcdef0123456789abcdef";
  const std::string other = "abcdef0123456789abcdef0123456789";
  setup();
  assert(outputLevel == LOW);
  assert(send("HELLO") == "READY FIRE_PUMP_V1\n");
  assert(send("RUN bad 5000") == "ERR FORMAT\n");
  assert(send("RUN " + id + " 30001") == "ERR DURATION\n");
  assert(send("RUN " + id + " 9999999999999") == "ERR DURATION\n");
  assert(send("RUN " + id + " -1") == "ERR DURATION\n");
  assert(outputLevel == LOW);
  testTime = 100;
  assert(send("RUN " + id + " 5000") == "ACK " + id + " ON\n");
  assert(outputLevel == HIGH);
  testTime = 1100;
  assert(send("RUN " + id + " 30000") == "ACK " + id + " ON\n");
  assert(send("RUN " + other + " 5000") == "ERR BUSY\n");
  for (testTime = 2100; testTime < 5100; testTime += 1000) send("STATUS");
  loop();
  assert(outputLevel == LOW); // Duplicate did not extend the original 5 seconds.
  assert(send("RUN " + id + " 5000") == "ACK " + id + " OFF\n");
  assert(send("RUN " + other + " 5000") == "ERR COOLDOWN\n");
  testTime = 60100;
  assert(send("RUN " + other + " 30000") == "ACK " + other + " ON\n");
  testTime = 63100;
  loop();
  assert(outputLevel == LOW); // No host heartbeat for 3 seconds.
  assert(send("STOP") == "STOPPED\n");
  assert(send(std::string(130, 'X')) == "ERR TOO_LONG\n");
  assert(send("STATUS") == "STATE OFF " + other + "\n");
  // millis() rollover still enforces the run deadline.
  testTime = UINT32_MAX - 100;
  assert(send("RUN " + id + " 100") == "ACK " + id + " ON\n");
  testTime = 0;
  loop();
  assert(outputLevel == LOW);
  // BOOT works without the host, overrides cooldown, and stops on release.
  testTime = 100;
  buttonLevel = LOW; loop(); testTime += 35; loop();
  assert(outputLevel == HIGH);
  assert(send("STATUS") == "STATE ON BOOT\n");
  testTime += 4000; loop();
  assert(outputLevel == HIGH); // Physical button does not depend on host heartbeat.
  buttonLevel = HIGH; loop(); testTime += 35; loop();
  assert(outputLevel == LOW);
  buttonLevel = LOW; loop(); testTime += 35; loop();
  assert(outputLevel == HIGH);
  assert(send("STOP") == "STOPPED\n");
  testTime += 100; loop();
  assert(outputLevel == LOW); // Holding BOOT cannot undo an emergency stop.
  assert(send("RUN " + other + " 5000") != "ACK " + other + " ON\n");
  buttonLevel = HIGH; loop(); testTime += 35; loop();
  buttonLevel = LOW; loop(); testTime += 35; loop();
  assert(outputLevel == HIGH);
  testTime += 30000; loop();
  assert(outputLevel == LOW);
  testTime += 1000; loop();
  assert(outputLevel == LOW); // Must release and press again after the limit.
  buttonLevel = HIGH; loop(); testTime += 35; loop();
  // Firmware never starts merely because the button was already held at setup.
  buttonLevel = LOW;
  setup();
  testTime += 100; loop();
  assert(outputLevel == LOW);
  buttonLevel = HIGH; loop(); testTime += 35; loop();
  buttonLevel = LOW; loop(); testTime += 35; loop();
  assert(outputLevel == HIGH);
  buttonLevel = HIGH; loop(); testTime += 35; loop();
  assert(outputLevel == LOW);
  std::cout << "Pump firmware protocol tests passed\n";
}
