#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "display.h"
#include "panel.h"

constexpr uint32_t WATCHDOG_MS = 3000;
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t BLINK_MS = 250;

enum Mode { MODE_OFF, MODE_GREEN, MODE_YELLOW, MODE_RED_BLINK, MODE_RED_SOLID, MODE_ALT };

char input[80];
size_t used = 0;
bool overflow = false;
Mode hostMode = MODE_OFF;
bool linkUp = true;
bool mute = false;
bool muteRaw = false;
bool muteStable = false;
uint32_t muteChangedAt = 0;
uint32_t lastHost = 0;
bool sawMutePress = false;

const char* modeName(Mode mode) {
  switch (mode) {
    case MODE_OFF:
      return "OFF";
    case MODE_GREEN:
      return "GREEN";
    case MODE_YELLOW:
      return "YELLOW";
    case MODE_RED_BLINK:
      return "RED_BLINK";
    case MODE_RED_SOLID:
      return "RED_SOLID";
    case MODE_ALT:
      return "ALT";
  }
  return "OFF";
}

Mode effectiveMode() { return linkUp ? hostMode : MODE_ALT; }

void paint() {
  displayShow(modeName(effectiveMode()), mute ? "MUTE" : "SOUND");
}

void applyLamps() {
  Mode mode = effectiveMode();
  bool phase = ((millis() / BLINK_MS) % 2) == 0;
  bool red = false;
  bool yellow = false;
  bool green = false;
  bool buzz = false;
  if (mode == MODE_GREEN) green = true;
  else if (mode == MODE_YELLOW) yellow = phase;
  else if (mode == MODE_RED_BLINK) {
    red = phase;
    buzz = true;
  } else if (mode == MODE_RED_SOLID) {
    red = true;
    buzz = true;
  } else if (mode == MODE_ALT) {
    yellow = phase;
    red = !phase;
    buzz = true;
  }
  if (mute) buzz = false;
  digitalWrite(PIN_RED, red ? HIGH : LOW);
  digitalWrite(PIN_YELLOW, yellow ? HIGH : LOW);
  digitalWrite(PIN_GREEN, green ? HIGH : LOW);
  digitalWrite(PIN_BUZZER, buzz ? HIGH : LOW);
}

void noteHost() {
  lastHost = millis();
  if (!linkUp) {
    linkUp = true;
    paint();
  }
}

void handleCommand(char* line) {
  noteHost();
  if (strcmp(line, "HELLO") == 0) {
    Serial.println("READY FIRE_PANEL_V2");
  } else if (strcmp(line, "PING") == 0) {
    Serial.println("PONG");
  } else if (strcmp(line, "STATUS") == 0) {
    char lineOut[48];
    snprintf(lineOut, sizeof(lineOut), "STATE %s %s %s", modeName(effectiveMode()),
             mute ? "MUTE" : "OPEN", linkUp ? "UP" : "DOWN");
    Serial.println(lineOut);
  } else if (strncmp(line, "MODE ", 5) == 0) {
    const char* name = line + 5;
    Mode next = MODE_OFF;
    bool known = true;
    if (strcmp(name, "OFF") == 0) next = MODE_OFF;
    else if (strcmp(name, "GREEN") == 0) next = MODE_GREEN;
    else if (strcmp(name, "YELLOW") == 0) next = MODE_YELLOW;
    else if (strcmp(name, "RED_BLINK") == 0) next = MODE_RED_BLINK;
    else if (strcmp(name, "RED_SOLID") == 0) next = MODE_RED_SOLID;
    else if (strcmp(name, "ALT") == 0) next = MODE_ALT;
    else known = false;
    if (!known) {
      Serial.println("ERR MODE");
      return;
    }
    hostMode = next;
    paint();
    char reply[32];
    snprintf(reply, sizeof(reply), "MODE %s", name);
    Serial.println(reply);
  } else {
    Serial.println("ERR COMMAND");
  }
}

void setup() {
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_YELLOW, OUTPUT);
  pinMode(PIN_GREEN, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_RED, LOW);
  digitalWrite(PIN_YELLOW, LOW);
  digitalWrite(PIN_GREEN, LOW);
  digitalWrite(PIN_BUZZER, LOW);
  pinMode(PIN_MUTE, INPUT_PULLUP);
  muteRaw = muteStable = digitalRead(PIN_MUTE) == LOW;
  muteChangedAt = millis();
  lastHost = millis();
  displayBegin();
  paint();
  Serial.begin(115200);
}

void loop() {
  bool pressed = digitalRead(PIN_MUTE) == LOW;
  if (pressed != muteRaw) {
    muteRaw = pressed;
    muteChangedAt = millis();
  }
  if (static_cast<uint32_t>(millis() - muteChangedAt) >= DEBOUNCE_MS && muteStable != muteRaw) {
    muteStable = muteRaw;
    if (muteStable && !sawMutePress) {
      mute = !mute;
      paint();
    }
    sawMutePress = muteStable;
  }
  if (linkUp && static_cast<uint32_t>(millis() - lastHost) >= WATCHDOG_MS) {
    linkUp = false;
    paint();
  }
  for (int budget = 0; budget < 100 && Serial.available(); ++budget) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      input[used] = '\0';
      if (overflow) Serial.println("ERR TOO_LONG");
      else handleCommand(input);
      used = 0;
      overflow = false;
    } else if (used < sizeof(input) - 1 && !overflow) {
      input[used++] = c;
    } else {
      overflow = true;
    }
  }
  applyLamps();
}
