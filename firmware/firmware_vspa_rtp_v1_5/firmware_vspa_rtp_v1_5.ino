/*
  VSPA:PE hardware validation and RTP firmware v1.5
  Documentation revision: executable tokens and serial commands remain unchanged.
  Exact pre-documentation bytes are retained in archive/acquisition_v1_8/.
  Uno R3 + TCA9548A at 0x70 + 5 DRV2605L at 0x5A (one per mux channel).
  Channel 0 pinky, 1 ring, 2 middle, 3 index, 4 thumb.

  Serial: 9600, commands terminated by newline:
    PING                     -> READY,VSPA_PE_RTP_1.5,mask=<five bits>
    SCAN                     -> MUX,OK / ERR,MUX_MISSING and CH,0,OK etc.
    REG,0                    -> diagnostic register values, not measured vibration
    TESTFX,0                 -> brief effect-library pulse on channel 0
    PLAY,0,1000,48           -> request one second in real-time playback mode
    STOP                     -> stop current active motor
    STATUS                   -> state of controller

  This firmware is not a measurement instrument and makes no assertions about
  actual motor amplitude, frequency, voltage, velocity or skin-contact force.
  Keep actuator disconnected from the body for first bench tests. Do not use
  with unknown supply voltage, damaged wiring or unverified motor/clamp settings.
*/
#include <Wire.h>
#include <Adafruit_DRV2605.h>
#include <string.h>
#include <stdlib.h>

const uint8_t MUX_ADDR = 0x70;
const uint8_t DRIVER_ADDR = 0x5A;
const uint8_t COUNT = 5;
const uint16_t MIN_MS = 100;
const uint16_t MAX_MS = 3000;
const uint8_t MAX_RTP = 80;  // cautious *command limit*, NOT calibrated volts
const uint16_t EFFECT_DIAG_MS = 400;

Adafruit_DRV2605 drv[COUNT];
bool available[COUNT] = {false, false, false, false, false};
bool busy = false;
bool effectMode = false;
uint8_t active = 0;
uint32_t pulseStart = 0;
uint16_t pulseDuration = 0;
char input[64];
uint8_t inputLen = 0;

// Select one downstream bus so identical driver addresses remain independently accessible.
bool muxSelect(uint8_t ch) {
  if (ch >= COUNT) return false;
  Wire.beginTransmission(MUX_ADDR);
  Wire.write((uint8_t)(1U << ch));
  return Wire.endTransmission() == 0;
}

// Probe an I2C address for acknowledgement; this checks communication, not actuator motion.
bool responds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

// Emit the five cached startup-availability flags in pinky-to-thumb channel order.
void printMask() {
  for (uint8_t i=0; i<COUNT; ++i) Serial.print(available[i] ? '1' : '0');
}

// Return the fixed firmware signature and startup mask required by the host handshake.
void identify() {
  Serial.print(F("READY,VSPA_PE_RTP_1.5,mask="));
  printMask();
  Serial.println();
}

// Recheck the upstream mux and report cached startup driver availability for each channel.
void reportScan() {
  Wire.beginTransmission(MUX_ADDR);
  bool muxPresent = (Wire.endTransmission() == 0);
  Serial.println(muxPresent ? F("MUX,OK") : F("ERR,MUX_MISSING"));
  for (uint8_t i=0; i<COUNT; ++i) {
    Serial.print(F("CH,")); Serial.print(i); Serial.print(',');
    Serial.println(available[i] ? F("OK") : F("MISSING"));
  }
}

// Clear the active playback request and report elapsed firmware time without a motion sensor.
void stopMotor() {
  // Idle STOP has no active timer to report; parse() still sends OK,STOP.
  if (!busy) return;
  if (muxSelect(active) && available[active]) {
    if (effectMode) drv[active].stop();
    else drv[active].setRealtimeValue(0);
    // Clearing playback mode after RTP follows the TI device datasheet.
    drv[active].setMode(DRV2605_MODE_INTTRIG);
  }
  Serial.print(F("DONE,")); Serial.print(active);
  Serial.print(','); Serial.println(millis() - pulseStart);
  busy = false;
  effectMode = false;
}

// Validate the cached channel state and current mux selection before a driver operation.
bool allowed(uint8_t channel) {
  if (channel >= COUNT || !available[channel]) {
    Serial.print(F("ERR,CHANNEL_UNAVAILABLE,")); Serial.println(channel);
    return false;
  }
  if (!muxSelect(channel)) {
    Serial.print(F("ERR,MUX_CHANNEL,")); Serial.println(channel);
    return false;
  }
  return true;
}

// Print diagnostic register readbacks; these values are not measured vibration or skin force.
void dumpRegs(uint8_t ch) {
  if (!allowed(ch)) return;
  // Hexadecimal readbacks help distinguish communication from actuation issues.
  const uint8_t addr[] = {DRV2605_REG_STATUS, DRV2605_REG_MODE,
    DRV2605_REG_RTPIN, DRV2605_REG_RATEDV, DRV2605_REG_CLAMPV,
    DRV2605_REG_FEEDBACK, DRV2605_REG_CONTROL3};
  Serial.print(F("REG,")); Serial.print(ch);
  for (uint8_t k=0; k<sizeof(addr); ++k) {
    Serial.print(F(",0x")); Serial.print(addr[k], HEX); Serial.print(F("=0x"));
    Serial.print(drv[ch].readRegister8(addr[k]), HEX);
  }
  Serial.println();
}

// Accept only a nonempty sequence of decimal digits before command fields are converted.
bool numeric(const char *s) {
  if (!s || !*s) return false;
  for (const char *p=s; *p; ++p) if (*p < '0' || *p > '9') return false;
  return true;
}

// Dispatch one complete serial line, rejecting unsupported commands, ranges and overlapping plays.
void parse(char *line) {
  if (!strcmp(line, "PING")) { identify(); return; }
  if (!strcmp(line, "SCAN")) { reportScan(); return; }
  if (!strcmp(line, "STATUS")) {
    Serial.print(F("STATUS,")); Serial.println(busy ? F("BUSY") : F("IDLE")); return;
  }
  if (!strcmp(line, "STOP")) { stopMotor(); Serial.println(F("OK,STOP")); return; }
  if (!strncmp(line, "REG,", 4)) {
    if (!numeric(line+4)) { Serial.println(F("ERR,FORMAT")); return; }
    long c = atol(line+4);
    if (c<0 || c>=COUNT) { Serial.println(F("ERR,OUT_OF_RANGE")); return; }
    dumpRegs((uint8_t)c); return;
  }
  // Library-effect diagnostics are a bench path; acquisition uses PLAY in RTP mode.
  if (!strncmp(line, "TESTFX,", 7)) {
    if (busy) { Serial.println(F("ERR,BUSY")); return; }
    if (!numeric(line+7)) { Serial.println(F("ERR,FORMAT")); return; }
    long c = atol(line+7);
    if (c<0 || c>=COUNT) { Serial.println(F("ERR,OUT_OF_RANGE")); return; }
    if (!allowed((uint8_t)c)) return;
    // Built-in LRA library pulse isolates motor wiring/actuation from RTP config.
    drv[c].selectLibrary(6);
    drv[c].setMode(DRV2605_MODE_INTTRIG);
    drv[c].setWaveform(0, 1);
    drv[c].setWaveform(1, 0);
    drv[c].go();
    active = (uint8_t)c; busy = true; effectMode = true;
    pulseStart = millis(); pulseDuration = EFFECT_DIAG_MS;
    Serial.print(F("STARTFX,")); Serial.println(c);
    return;
  }
  if (strncmp(line, "PLAY,", 5)) { Serial.println(F("ERR,UNKNOWN_COMMAND")); return; }
  if (busy) { Serial.println(F("ERR,BUSY")); return; }

  // Require three nonempty numeric tokens before any driver register is changed.
  // The retained strtok_r parser skips repeated and trailing commas.
  char *save = NULL;
  char *chToken = strtok_r(line+5, ",", &save);
  char *msToken = strtok_r(NULL, ",", &save);
  char *rtpToken = strtok_r(NULL, ",", &save);
  if (!chToken || !msToken || !rtpToken || strtok_r(NULL, ",", &save) ||
      !numeric(chToken) || !numeric(msToken) || !numeric(rtpToken)) {
    Serial.println(F("ERR,FORMAT")); return;
  }
  long channel = atol(chToken), ms = atol(msToken), level = atol(rtpToken);
  if (channel<0 || channel>=COUNT || ms<MIN_MS || ms>MAX_MS || level<1 || level>MAX_RTP) {
    Serial.println(F("ERR,OUT_OF_RANGE")); return;
  }
  uint8_t c = (uint8_t)channel;
  if (!allowed(c)) return;
  drv[c].setMode(DRV2605_MODE_REALTIME);
  drv[c].setRealtimeValue((uint8_t)level);
  // START is emitted only after mode/RTP readback matches; it is not a sensed motor onset.
  uint8_t mode = (uint8_t)(drv[c].readRegister8(DRV2605_REG_MODE) & 0x07);
  uint8_t rtp = drv[c].readRegister8(DRV2605_REG_RTPIN);
  if (mode != DRV2605_MODE_REALTIME || rtp != (uint8_t)level) {
    drv[c].setRealtimeValue(0);
    drv[c].setMode(DRV2605_MODE_INTTRIG);
    Serial.print(F("ERR,REGISTER_READBACK,")); Serial.println(c);
    return;
  }
  // Start the firmware duration clock after successful configuration, before printing START.
  active = c; busy = true; effectMode = false;
  pulseStart = millis(); pulseDuration = (uint16_t)ms;
  Serial.print(F("START,")); Serial.print(c); Serial.print(',');
  Serial.print(ms); Serial.print(','); Serial.println(level);
}

// Initialize the serial/I2C buses and cache which of the five selected drivers initialized.
void setup() {
  Serial.begin(9600);
  Wire.begin();
  // Detect all channels; don't freeze without a useful error message.
  for (uint8_t ch=0; ch<COUNT; ++ch) {
    if (!muxSelect(ch)) continue;
    if (!responds(DRIVER_ADDR)) continue;
    if (!drv[ch].begin()) continue;
    drv[ch].useLRA();
    drv[ch].selectLibrary(6);
    // The Adafruit library initializes ERM_OPEN_LOOP (CONTROL3 bit 5) by
    // default; LRA mode is selected above. Explicitly leave LRA_OPEN_LOOP
    // (bit 0) cleared, and keep signed-RTP input (bit 3) as default.
    uint8_t ctrl = drv[ch].readRegister8(DRV2605_REG_CONTROL3);
    drv[ch].writeRegister8(DRV2605_REG_CONTROL3, (uint8_t)(ctrl & ~0x09));
    drv[ch].setMode(DRV2605_MODE_INTTRIG);
    drv[ch].setRealtimeValue(0);
    available[ch] = true;
  }
  identify();
  reportScan();
}

// Check the active software timer while collecting bounded newline-terminated serial commands.
void loop() {
  // Unsigned subtraction keeps the elapsed-duration comparison valid across millis() rollover.
  if (busy && (uint32_t)(millis() - pulseStart) >= pulseDuration) stopMotor();
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    // Parse only completed lines; reserve one buffer byte for the terminating null character.
    if (c == '\n') {
      input[inputLen] = '\0';
      if (inputLen > 0) parse(input);
      inputLen = 0;
    } else if (inputLen < sizeof(input)-1) input[inputLen++] = c;
    else { inputLen=0; Serial.println(F("ERR,LINE_TOO_LONG")); }
  }
}
