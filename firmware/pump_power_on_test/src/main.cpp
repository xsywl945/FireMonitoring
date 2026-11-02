#include <Arduino.h>

// Wiring test only: a HIGH-triggered MOSFET stays ON until pump power is removed.
// This firmware has no run timer, host heartbeat, or serial STOP command.
constexpr uint8_t PUMP_PIN = 26;

void setup() {
  pinMode(PUMP_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, HIGH);

  Serial.begin(115200);
  Serial.println("PUMP_POWER_ON_TEST: GPIO26=HIGH; continuous output enabled.");
  Serial.println("Remove the pump's 12V supply to stop. No automatic shutdown.");
}

void loop() {
  Serial.println("PUMP_POWER_ON_TEST: GPIO26 commanded HIGH (no water-flow feedback).");
  delay(2000);
}
