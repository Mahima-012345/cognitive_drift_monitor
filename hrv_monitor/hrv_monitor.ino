/*
 * HRV Monitor - MAX30102 + Arduino UNO
 * Improved version with RR filtering and SDNN smoothing
 * 
 * Install libraries:
 * - SparkFun MAX3010x Pulse and Proximity Sensor Library
 * - ArduinoJson
 */

#include <Wire.h>
#include <MAX30105.h>
#include <heartRate.h>
#include <spo2_algorithm.h>

MAX30105 particleSensor;

// ====== SETTINGS ======
const byte RATE_SIZE = 30;        // Buffer size (increased from 20)
const int MIN_RR = 300;           // Min RR interval (ms)
const int MAX_RR = 1200;          // Max RR interval (ms)
const int RR_JUMP_THRESH = 200;   // Max allowed sudden jump (ms)
const int STABILIZE_MS = 3000;    // Wait time after finger detection (ms)
const float SMOOTH_ALPHA = 0.3;   // Smoothing factor (0.3 = 30% new, 70% old)
const int SAMPLE_RATE = 100;      // Sampling rate

// ====== GLOBALS ======
byte rates[RATE_SIZE];
byte rateSpot = 0;
long lastBeat = 0;
float beatsPerMinute = 0;
int beatAvg = 0;

unsigned long rrBuffer[RATE_SIZE];
int rrIndex = 0;
int rrCount = 0;

float currentSDNN = 0;
float smoothedSDNN = 0;
unsigned long lastIR = 0;

bool fingerDetected = false;
bool stabilized = false;
unsigned long fingerDetectTime = 0;

// ====== SETUP ======
void setup() {
  Serial.begin(115200);
  Wire.begin();
  
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println(F("MAX30105 not found!"));
    while (1);
  }
  
  particleSensor.setup();
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeGreen(0);
  
  Serial.println(F("{\"status\":\"hrv_module_started\"}"));
}

// ====== MAIN LOOP ======
void loop() {
  long irValue = particleSensor.getIR();
  
  // Check finger detection
  if (irValue > 50000) {
    if (!fingerDetected) {
      fingerDetected = true;
      fingerDetectTime = millis();
      stabilized = false;
      Serial.println(F("{\"status\":\"finger_detected\"}"));
    }
    
    // Wait for stabilization
    if (!stabilized) {
      if (millis() - fingerDetectTime >= STABILIZE_MS) {
        stabilized = true;
        Serial.println(F("{\"status\":\"stabilized\"}"));
      }
    }
    
    if (stabilized) {
      processHeartRate(irValue);
    }
    
  } else {
    if (fingerDetected) {
      fingerDetected = false;
      stabilized = false;
      beatAvg = 0;
      beatsPerMinute = 0;
      currentSDNN = 0;
      smoothedSDNN = 0;
      rrCount = 0;
      rrIndex = 0;
      Serial.println(F("{\"status\":\"no_finger\"}"));
    }
  }
  
  delay(10);
}

// ====== PROCESS HEART RATE ======
void processHeartRate(long irValue) {
  if (checkForBeat(irValue) == true) {
    long delta = millis() - lastBeat;
    lastBeat = millis();
    
    int rrInterval = delta;
    
    // Filter RR interval
    if (isValidRR(rrInterval)) {
      addRR(rrInterval);
      updateHeartRate();
      updateSDNN();
      sendJSON(irValue);
    }
  }
}

// ====== RR INTERVAL VALIDATION ======
bool isValidRR(int rr) {
  // Check range
  if (rr < MIN_RR || rr > MAX_RR) {
    return false;
  }
  
  // Check sudden jump from last RR
  if (rrCount > 0) {
    int lastRR = rrBuffer[(rrIndex - 1 + RATE_SIZE) % RATE_SIZE];
    if (abs(rr - lastRR) > RR_JUMP_THRESH) {
      return false;
    }
  }
  
  return true;
}

// ====== ADD RR TO BUFFER ======
void addRR(int rr) {
  rrBuffer[rrIndex] = rr;
  rrIndex = (rrIndex + 1) % RATE_SIZE;
  if (rrCount < RATE_SIZE) {
    rrCount++;
  }
}

// ====== UPDATE HEART RATE ======
void updateHeartRate() {
  long sum = 0;
  byte count = 0;
  
  for (byte i = 0; i < RATE_SIZE; i++) {
    if (rrBuffer[i] > 0) {
      sum += rrBuffer[i];
      count++;
    }
  }
  
  if (count > 0) {
    int avgRR = sum / count;
    beatsPerMinute = 60000.0 / avgRR;
    beatAvg = (int)beatsPerMinute;
    
    // Clamp BPM to realistic range
    if (beatAvg < 40) beatAvg = 40;
    if (beatAvg > 200) beatAvg = 200;
  }
}

// ====== UPDATE SDNN WITH SMOOTHING ======
void updateSDNN() {
  if (rrCount < 4) {
    currentSDNN = 0;
    smoothedSDNN = 0;
    return;
  }
  
  // Calculate SDNN from RR buffer
  long sum = 0;
  for (int i = 0; i < rrCount; i++) {
    sum += rrBuffer[i];
  }
  float meanRR = (float)sum / rrCount;
  
  float sumSq = 0;
  for (int i = 0; i < rrCount; i++) {
    float diff = rrBuffer[i] - meanRR;
    sumSq += diff * diff;
  }
  
  currentSDNN = sqrt(sumSq / rrCount);
  
  // Exponential smoothing
  if (smoothedSDNN == 0) {
    smoothedSDNN = currentSDNN;
  } else {
    smoothedSDNN = SMOOTH_ALPHA * currentSDNN + (1 - SMOOTH_ALPHA) * smoothedSDNN;
  }
}

// ====== GET STRESS LEVEL ======
const char* getStressLevel(float sdnn) {
  if (sdnn > 100) {
    return "Unstable";        // Noise/unstable
  } else if (sdnn >= 60) {
    return "Relaxed";         // Good HRV
  } else if (sdnn >= 30) {
    return "Moderate";        // Some stress
  } else {
    return "High Stress";    // Low HRV = high stress
  }
}

// ====== SEND JSON OUTPUT ======
void sendJSON(long irValue) {
  static unsigned long lastSend = 0;
  
  // Send every ~1 second
  if (millis() - lastSend < 1000) return;
  lastSend = millis();
  
  Serial.print(F("{\"ir\":"));
  Serial.print(irValue);
  Serial.print(F(",\"bpm\":"));
  Serial.print(beatAvg);
  Serial.print(F(",\"sdnn\":"));
  Serial.print(smoothedSDNN, 1);
  Serial.print(F(",\"stress\":\""));
  Serial.print(getStressLevel(smoothedSDNN));
  Serial.print(F("\"}"));
  Serial.println();
}
