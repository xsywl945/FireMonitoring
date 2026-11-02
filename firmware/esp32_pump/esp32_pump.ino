// Arduino-ESP32, classic ESP32 Dev Module. No external Arduino libraries required.
// Verify the board's pinout and MOSFET input polarity before connecting the pump.
#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

#ifndef PUMP_PIN
#define PUMP_PIN 26
#endif
constexpr uint8_t PUMP_ON = HIGH;
constexpr uint8_t PUMP_OFF = LOW;
constexpr uint32_t MAX_RUN_MS = 30000;
constexpr uint32_t WATCHDOG_MS = 3000;
constexpr uint8_t BOOT_PIN = 0;
constexpr uint32_t DEBOUNCE_MS = 30;
bool manualRun = false;
bool bootRawPressed = false, bootStablePressed = false, bootBlocked = false;
uint32_t bootChangedAt = 0;
bool running = false;
uint32_t runStarted = 0, runDuration = 0, lastHeartbeat = 0;
char lastId[33] = "-";
char input[100];
size_t used = 0;
bool overflow = false;

void stopPump() {
  digitalWrite(PUMP_PIN, PUMP_OFF);
  running = false;
  manualRun = false;
}

void updateBootButton() {
  bool pressed = digitalRead(BOOT_PIN) == LOW;
  if (pressed != bootRawPressed) {
    bootRawPressed = pressed;
    bootChangedAt = millis();
  }
  if (uint32_t(millis() - bootChangedAt) < DEBOUNCE_MS ||
      bootStablePressed == bootRawPressed) return;
  bootStablePressed = bootRawPressed;
  if (!bootStablePressed) {
    bootBlocked = false;
    if (manualRun) stopPump();
  } else if (!bootBlocked) {
    bootBlocked = true;
    manualRun = running = true;
    memcpy(lastId, "BOOT", 5);
    runStarted = millis();
    runDuration = MAX_RUN_MS;
    digitalWrite(PUMP_PIN, PUMP_ON);
  }
}

bool validId(const char* id) {
  if (strlen(id) != 32) return false;
  for (size_t i = 0; i < 32; ++i) if (!isxdigit(id[i])) return false;
  return true;
}

void handleCommand(char* line) {
  if (strcmp(line, "HELLO") == 0) {
    Serial.println("READY FIRE_PUMP_V1");
  } else if (strcmp(line, "STATUS") == 0) {
    lastHeartbeat = millis();
    Serial.print(running ? "STATE ON " : "STATE OFF ");
    Serial.println(lastId);
  } else if (strcmp(line, "STOP") == 0) {
    stopPump();
    bootBlocked = bootStablePressed || bootRawPressed;
    Serial.println("STOPPED");
  } else if (strncmp(line, "RUN ", 4) == 0) {
    char* id = line + 4;
    char* space = strchr(id, ' ');
    if (!space) { Serial.println("ERR FORMAT"); return; }
    *space = '\0';
    char* durationText = space + 1;
    if (!validId(id) || !*durationText) { Serial.println("ERR FORMAT"); return; }
    for (char* p = durationText; *p; ++p) {
      if (!isdigit(*p)) { Serial.println("ERR DURATION"); return; }
    }
    if (strlen(durationText) > 5) { Serial.println("ERR DURATION"); return; }
    uint32_t duration = strtoul(durationText, nullptr, 10);
    if (duration < 100 || duration > MAX_RUN_MS) {
      Serial.println("ERR DURATION"); return;
    }
    if (bootStablePressed || bootRawPressed) { Serial.println("ERR BOOT_HELD"); return; }
    // Duplicate RUN never restarts or extends the deadline, including after STOP.
    if (strcmp(lastId, id) == 0) {
      Serial.print("ACK "); Serial.print(id);
      Serial.println(running ? " ON" : " OFF"); return;
    }
    if (running) { Serial.println("ERR BUSY"); return; }
    memcpy(lastId, id, sizeof(lastId));
    runStarted = lastHeartbeat = millis();
    runDuration = duration;
    running = true;
    digitalWrite(PUMP_PIN, PUMP_ON);
    Serial.print("ACK "); Serial.print(id); Serial.println(" ON");
  } else {
    Serial.println("ERR COMMAND");
  }
}

void setup() {
  digitalWrite(PUMP_PIN, PUMP_OFF);
  pinMode(PUMP_PIN, OUTPUT);
  stopPump();
  pinMode(BOOT_PIN, INPUT_PULLUP);
  bootRawPressed = bootStablePressed = digitalRead(BOOT_PIN) == LOW;
  bootBlocked = bootStablePressed;
  bootChangedAt = millis();
  Serial.begin(115200);
}

void loop() {
  updateBootButton();
  if (running && (uint32_t(millis() - runStarted) >= runDuration ||
                  (!manualRun && uint32_t(millis() - lastHeartbeat) >= WATCHDOG_MS))) stopPump();
  // Bound work per loop so malformed continuous input cannot starve the watchdog.
  for (int budget = 0; budget < 100 && Serial.available(); ++budget) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      input[used] = '\0';
      if (overflow) Serial.println("ERR TOO_LONG");
      else handleCommand(input);
      used = 0; overflow = false;
    } else if (used < sizeof(input) - 1 && !overflow) {
      input[used++] = c;
    } else {
      overflow = true;
    }
  }
}
