#pragma once
#include <cstdint>
#include <map>
#include <string>

constexpr uint8_t HIGH = 1, LOW = 0, OUTPUT = 1, INPUT = 0, INPUT_PULLUP = 2;

inline uint32_t testTime = 0;
inline uint32_t millis() { return testTime; }

struct PinState {
  uint8_t mode = INPUT;
  uint8_t level = HIGH;
};

inline std::map<uint8_t, PinState> pins;

inline void pinMode(uint8_t pin, uint8_t mode) { pins[pin].mode = mode; }
inline void digitalWrite(uint8_t pin, uint8_t level) { pins[pin].level = level; }
inline int digitalRead(uint8_t pin) {
  auto found = pins.find(pin);
  if (found == pins.end()) return HIGH;
  return found->second.level;
}

struct LedcChannel {
  uint8_t pin = 0;
  uint32_t freq = 0;
  uint8_t resolution = 0;
  uint32_t duty = 0;
  bool attached = false;
};

inline LedcChannel ledcChannels[8];

inline void ledcSetup(uint8_t channel, double freq, uint8_t resolution) {
  ledcChannels[channel].freq = static_cast<uint32_t>(freq);
  ledcChannels[channel].resolution = resolution;
}
inline void ledcAttachPin(uint8_t pin, uint8_t channel) {
  ledcChannels[channel].pin = pin;
  ledcChannels[channel].attached = true;
}
inline void ledcWrite(uint8_t channel, uint32_t duty) { ledcChannels[channel].duty = duty; }

struct TestSerial {
  std::string input, output;
  void begin(int) {}
  int available() { return static_cast<int>(input.size()); }
  char read() {
    char c = input.front();
    input.erase(0, 1);
    return c;
  }
  void print(const char* text) { output += text; }
  void println(const char* text) {
    output += text;
    output += '\n';
  }
};

inline TestSerial Serial;
