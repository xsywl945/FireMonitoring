#include <Arduino.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "actuator.h"

constexpr uint32_t MAX_RUN_MS = 30000;
constexpr uint32_t WATCHDOG_MS = 3000;
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr int32_t PAN_MIN = -12000;
constexpr int32_t PAN_MAX = 12000;
constexpr int32_t TILT_MIN = 0;
constexpr int32_t TILT_MAX = 6000;
constexpr int32_t RATE_CDEG_PER_MS = 9;
constexpr uint8_t CH_PAN = 0;
constexpr uint8_t CH_TILT = 1;

char input[100];
size_t used = 0;
bool overflow = false;
bool running = false;
bool laserOn = false;
bool estopRaw = false;
bool estopStable = false;
bool estopLatched = false;
bool resetRaw = false;
bool resetStable = false;
bool resetArmed = false;
uint32_t estopChangedAt = 0;
uint32_t resetChangedAt = 0;
uint32_t runStarted = 0;
uint32_t runDuration = 0;
uint32_t lastHost = 0;
uint32_t lastMotion = 0;
char lastId[33] = "-";
int32_t pan = 0;
int32_t tilt = 0;
int32_t panTarget = 0;
int32_t tiltTarget = 0;
bool driveServos = true;

uint32_t pulseDuty(int32_t centidegree) {
  int32_t micros = 1500 + centidegree * 2 / 27;
  if (micros < 500) micros = 500;
  if (micros > 2500) micros = 2500;
  return static_cast<uint32_t>(micros) * 65535u / 20000u;
}

void writeServos() {
  if (!driveServos) {
    ledcWrite(CH_PAN, 0);
    ledcWrite(CH_TILT, 0);
    return;
  }
  ledcWrite(CH_PAN, pulseDuty(pan));
  ledcWrite(CH_TILT, pulseDuty(tilt));
}

void killMotion() {
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_LASER, LOW);
  running = false;
  laserOn = false;
  panTarget = pan;
  tiltTarget = tilt;
  driveServos = false;
  writeServos();
}

int32_t approach(int32_t current, int32_t target, int32_t step) {
  int32_t delta = target - current;
  if (delta > step) return current + step;
  if (delta < -step) return current - step;
  return target;
}

void moveServos() {
  uint32_t now = millis();
  uint32_t elapsed = now - lastMotion;
  lastMotion = now;
  int32_t step = static_cast<int32_t>(elapsed) * RATE_CDEG_PER_MS;
  if (step < 0) step = 0;
  pan = approach(pan, panTarget, step);
  tilt = approach(tilt, tiltTarget, step);
  writeServos();
}

const char* latchName() {
  if (!estopLatched) return "CLEAR";
  if (resetArmed && !estopStable) return "ARMED";
  return "LATCHED";
}

void printStatus() {
  char line[80];
  snprintf(line, sizeof(line), "STATE %s %s %s %ld %ld", running ? "ON" : "OFF",
           laserOn ? "ON" : "OFF", latchName(), static_cast<long>(pan),
           static_cast<long>(tilt));
  Serial.println(line);
}

void noteHost() { lastHost = millis(); }

void debounce(bool pressed, bool& raw, bool& stable, uint32_t& changedAt) {
  if (pressed != raw) {
    raw = pressed;
    changedAt = millis();
  }
  if (static_cast<uint32_t>(millis() - changedAt) < DEBOUNCE_MS || stable == raw) return;
  stable = raw;
}

void updateButtons() {
  debounce(digitalRead(PIN_ESTOP) == LOW, estopRaw, estopStable, estopChangedAt);
  if (estopStable && !estopLatched) {
    estopLatched = true;
    resetArmed = false;
    killMotion();
  }
  if (estopStable) resetArmed = false;
  debounce(digitalRead(PIN_RESET) == LOW, resetRaw, resetStable, resetChangedAt);
  if (estopLatched && !estopStable && resetStable) resetArmed = true;
}

void enforceDeadlines() {
  if (running && static_cast<uint32_t>(millis() - runStarted) >= runDuration) {
    digitalWrite(PIN_PUMP, LOW);
    running = false;
  }
  if (static_cast<uint32_t>(millis() - lastHost) >= WATCHDOG_MS && (running || laserOn)) {
    digitalWrite(PIN_PUMP, LOW);
    digitalWrite(PIN_LASER, LOW);
    running = false;
    laserOn = false;
    panTarget = pan;
    tiltTarget = tilt;
  }
}

bool validId(const char* id) {
  if (strlen(id) != 32) return false;
  for (size_t i = 0; i < 32; ++i) {
    if (!isxdigit(static_cast<unsigned char>(id[i]))) return false;
  }
  return true;
}

void handleCommand(char* line) {
  noteHost();
  if (strcmp(line, "HELLO") == 0) {
    Serial.println("READY FIRE_ACTUATOR_V2");
  } else if (strcmp(line, "PING") == 0) {
    Serial.println("PONG");
  } else if (strcmp(line, "STATUS") == 0) {
    printStatus();
  } else if (strcmp(line, "STOP") == 0) {
    digitalWrite(PIN_PUMP, LOW);
    digitalWrite(PIN_LASER, LOW);
    running = false;
    laserOn = false;
    panTarget = pan;
    tiltTarget = tilt;
    Serial.println("STOPPED");
  } else if (strcmp(line, "UNLOCK") == 0) {
    if (!estopLatched) {
      Serial.println("UNLOCKED");
    } else if (estopStable) {
      Serial.println("ERR ESTOP");
    } else if (!resetArmed) {
      Serial.println("ERR RESET");
    } else {
      estopLatched = false;
      resetArmed = false;
      driveServos = true;
      writeServos();
      Serial.println("UNLOCKED");
    }
  } else if (strncmp(line, "LASER ", 6) == 0) {
    if (estopLatched) {
      Serial.println("ERR ESTOP");
      return;
    }
    if (strcmp(line + 6, "ON") == 0) {
      laserOn = true;
      digitalWrite(PIN_LASER, HIGH);
      Serial.println("LASER ON");
    } else if (strcmp(line + 6, "OFF") == 0) {
      laserOn = false;
      digitalWrite(PIN_LASER, LOW);
      Serial.println("LASER OFF");
    } else {
      Serial.println("ERR FORMAT");
    }
  } else if (strncmp(line, "AIM ", 4) == 0) {
    if (estopLatched) {
      Serial.println("ERR ESTOP");
      return;
    }
    char* tiltText = strchr(line + 4, ' ');
    if (tiltText == nullptr || strchr(tiltText + 1, ' ') != nullptr) {
      Serial.println("ERR FORMAT");
      return;
    }
    *tiltText = '\0';
    char* end = nullptr;
    long panValue = strtol(line + 4, &end, 10);
    if (end == line + 4 || *end != '\0') {
      Serial.println("ERR FORMAT");
      return;
    }
    long tiltValue = strtol(tiltText + 1, &end, 10);
    if (end == tiltText + 1 || *end != '\0') {
      Serial.println("ERR FORMAT");
      return;
    }
    if (panValue < PAN_MIN || panValue > PAN_MAX || tiltValue < TILT_MIN || tiltValue > TILT_MAX) {
      Serial.println("ERR LIMIT");
      return;
    }
    panTarget = static_cast<int32_t>(panValue);
    tiltTarget = static_cast<int32_t>(tiltValue);
    driveServos = true;
    char reply[40];
    snprintf(reply, sizeof(reply), "AIM %ld %ld", panValue, tiltValue);
    Serial.println(reply);
  } else if (strncmp(line, "RUN ", 4) == 0) {
    char* id = line + 4;
    char* space = strchr(id, ' ');
    if (space == nullptr) {
      Serial.println("ERR FORMAT");
      return;
    }
    *space = '\0';
    char* durationText = space + 1;
    if (!validId(id) || *durationText == '\0' || strchr(durationText, ' ') != nullptr) {
      Serial.println("ERR FORMAT");
      return;
    }
    for (char* p = durationText; *p; ++p) {
      if (!isdigit(static_cast<unsigned char>(*p))) {
        Serial.println("ERR DURATION");
        return;
      }
    }
    if (strlen(durationText) > 5) {
      Serial.println("ERR DURATION");
      return;
    }
    uint32_t duration = strtoul(durationText, nullptr, 10);
    if (duration < 100 || duration > MAX_RUN_MS) {
      Serial.println("ERR DURATION");
      return;
    }
    if (estopLatched) {
      Serial.println("ERR ESTOP");
      return;
    }
    if (strcmp(lastId, id) == 0) {
      char reply[48];
      snprintf(reply, sizeof(reply), "ACK %s %s", id, running ? "ON" : "OFF");
      Serial.println(reply);
      return;
    }
    if (running) {
      Serial.println("ERR BUSY");
      return;
    }
    memcpy(lastId, id, sizeof(lastId));
    runStarted = lastHost = millis();
    runDuration = duration;
    running = true;
    digitalWrite(PIN_PUMP, HIGH);
    char reply[48];
    snprintf(reply, sizeof(reply), "ACK %s ON", id);
    Serial.println(reply);
  } else {
    Serial.println("ERR COMMAND");
  }
}

void setup() {
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_LASER, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_LASER, LOW);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_RESET, INPUT_PULLUP);
  ledcSetup(CH_PAN, 50, 16);
  ledcSetup(CH_TILT, 50, 16);
  ledcAttachPin(PIN_PAN, CH_PAN);
  ledcAttachPin(PIN_TILT, CH_TILT);
  driveServos = true;
  writeServos();
  estopRaw = estopStable = digitalRead(PIN_ESTOP) == LOW;
  resetRaw = resetStable = digitalRead(PIN_RESET) == LOW;
  estopChangedAt = resetChangedAt = millis();
  if (estopStable) {
    estopLatched = true;
    driveServos = false;
    writeServos();
  }
  lastHost = lastMotion = millis();
  Serial.begin(115200);
}

void loop() {
  updateButtons();
  moveServos();
  enforceDeadlines();
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
}
