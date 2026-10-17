#pragma once
#include <cstdint>
#include <string>

constexpr uint8_t HIGH = 1, LOW = 0, OUTPUT = 1;
inline uint32_t testTime = 0;
inline uint8_t outputLevel = HIGH;
inline uint32_t millis() { return testTime; }
inline void digitalWrite(uint8_t, uint8_t level) { outputLevel = level; }
inline void pinMode(uint8_t, uint8_t) {}
struct TestSerial {
  std::string input, output;
  void begin(int) {}
  int available() { return static_cast<int>(input.size()); }
  char read() { char c = input.front(); input.erase(0, 1); return c; }
  void print(const char* text) { output += text; }
  void println(const char* text) { output += text; output += '\n'; }
};
inline TestSerial Serial;
