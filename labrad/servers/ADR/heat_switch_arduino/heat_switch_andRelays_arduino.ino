/*
heat_switch_arduino sketch
Sketch for an arduino to serve as heat switch controller.
---PINOUT---
Arduino  Heat Switch Box  purpose
2        1                interrupt to detect switch opening
3        3                interrupt to detect switch closing
4        2                open control pin
5        9                close control
6        4                4K - 1K touch detector
7        7                1K - 50mK touch
8        6                4K - 50mK touch
GND      11               signal ground
(before wiring, double check that the heat switch pin functions are correct)
---PROTOCOL---
We communicate with the computer over serial.
Commands end with \n, \r is ignored.
Timeout = 1 second.
Command    Response
*IDN?      MARTINISGROUP,HEATSWITCH,[version]
STATUS?    [0,1,2,3,4] for [unknown, open confirmed, close confirmed, open requested, close requested]
TOUCH? n   [0, 1] for [touch, no touch] for n=[1,2,3]->[4K-1K, 1K-50mK, 4k-50mK]
           Returns E for n != [1,2,3]
OPEN!      open the heat switch: close relays, wait, open switch, wait, open relays
CLOSE!     close the heat switch: close relays, open switch, close switch, open relays
OPENRELAYS     open the relays
CLOSERELAYS    close the relays
NOISY n    turn noisy (verbose) mode on (1) or off (0)
*/
const unsigned int sketchVersion = 5;
const int openPin = 4;
const int closePin = 5;
const int touch4K1Kpin = 6;
const int touch1K50mKpin = 7;
const int touch4K50mKpin = 8;
const int relayIn1 = 14; // A0
const int relayIn2 = 15; // A1
const int openingPin = 2;
const int closingPin = 3;

int noisy = 0;
volatile int switchState = 0;    // see STATUS? above

volatile unsigned long switchTime = 0;
volatile int closing = 0;
volatile int opening = 0;
const unsigned long relayInterval = 1000;
const unsigned long switchOn = 50;
const unsigned long openInterval = 10000;
const unsigned long closeInterval = 5000;

const byte commandSize = 64;
char currentCommand[commandSize] = "";
unsigned long lastSerialTime;
const unsigned long serialTimeout=1000;
const char terminator = '\n';
const char* ignoredChars = "\r";
boolean buildingCommand;
char c;
byte b;
int i;

void setup() {
  Serial.begin(9600);
  // interrupt 0,1 -> pins 2,3 for arduino uno
  attachInterrupt(0, openingInterrupt, CHANGE);
  attachInterrupt(1, closingInterrupt, CHANGE);
  pinMode(openingPin, INPUT_PULLUP);
  pinMode(closingPin, INPUT_PULLUP);
  pinMode(openPin, OUTPUT);
  pinMode(closePin, OUTPUT);
  pinMode(touch4K1Kpin, INPUT_PULLUP);
  pinMode(touch1K50mKpin, INPUT_PULLUP);
  pinMode(touch4K50mKpin, INPUT_PULLUP);
  pinMode(relayIn1, OUTPUT);
  pinMode(relayIn2, OUTPUT);
  
  openRelays();
  resetCommand();
}

void loop(){
  // handle command inputs
  // build up a command one character at a time
  while (Serial.available() > 0) {
    buildingCommand = true;
    lastSerialTime = millis();
    c = Serial.read();
    if (c == terminator) {
      handleCommand();
    } else {
      // check for ignored character, command size 
      b = strlen(currentCommand);
      if (strchr(ignoredChars, c))
        break;
      if (b < commandSize-1)
        currentCommand[strlen(currentCommand)] = c;
      else
        handleCommand();
    }
  }
  // check for serial timeout
  if (buildingCommand && millis() - lastSerialTime > serialTimeout) {
    //Serial.println(millis() - lastSerialTime);
    handleCommand();
  }
  
  // Open
  if (opening==1 && millis()-switchTime>relayInterval) {
    openSwitch();
    opening=2;
  } else if (opening==2 && millis()-switchTime>relayInterval+openInterval) {
    openRelays();
    opening=0;
  } 
  
  // Close
  if (closing==1 && millis()-switchTime>relayInterval) {
    openSwitch();
    closing=2;
  } else if (closing==2 && millis()-switchTime>relayInterval+openInterval) {
    closeSwitch();
    closing=3;
  } else if (closing==3 && millis()-switchTime>relayInterval+openInterval+closeInterval) {
    openRelays();
    closing=0;
  }
  
}
void handleCommand() {
  //Serial.print("command: ");
  //Serial.println(currentCommand);
  if (strcmp(currentCommand, "*IDN?") == 0) {
    sendIDN();
  } else if (strcmp(currentCommand, "STATUS?") == 0) {
    sendStatus();
  } else if (strncmp(currentCommand, "TOUCH?", 6) == 0) {
    sendTouch();
  } else if (strcmp(currentCommand, "OPEN!") == 0) {
    closeRelays();
    switchTime = millis();
    opening = 1;
  } else if (strcmp(currentCommand, "CLOSE!") == 0) {
    closeRelays();
    switchTime = millis();
    closing = 1;
  } else if (strcmp(currentCommand, "OPENRELAYS") == 0) {
    openRelays();
  } else if (strcmp(currentCommand, "CLOSERELAYS") == 0) {
    closeRelays();
  } else if (strcmp(currentCommand, "NOISY 0") == 0) {
    noisy = 0;
  } else if (strcmp(currentCommand, "NOISY 1") == 0) {
    noisy = 1;
  }
  resetCommand();
}
void resetCommand() {
  for (byte i = 0; i < commandSize; i++)
    currentCommand[i] = '\0';
  buildingCommand = false;
}
void sendIDN() {
  Serial.print("MARTINISGROUP,HEATSWITCH,");
  Serial.println(sketchVersion);
}
void sendStatus() {
  Serial.println(switchState);
}
void sendTouch() {
  b = atoi(currentCommand+7);
  i = -1;
  closeRelays();
  delay(1000);
  switch (b) {
    case 1:
      i = digitalRead(touch4K1Kpin);
    break;    
    case 2:
      i = digitalRead(touch1K50mKpin);
    break;
    case 3:
      i = digitalRead(touch4K50mKpin);
    break;
  }
  if (i == HIGH)
    Serial.println("0");
  else if (i == LOW)
    Serial.println("1");
  else
    Serial.println("E");
  delay(1000);
  openRelays();
}
// the 1ms delay is to make sure the rising edge triggers the switch
// this is a n00btastic way of doing it, because delay hangs the arduino
// we should record the time, and then compare using millis() in the main loop
// but it's only 1 ms, and it won't mess up serial comms (just delay), so whatever.
void openSwitch() {
  switchState = 3;
  digitalWrite(openPin, HIGH);
  delay(1);
  digitalWrite(openPin, LOW);
}
void closeSwitch() {
  switchState = 4;
  digitalWrite(closePin, HIGH);
  delay(1);
  digitalWrite(closePin, LOW);
}

void openRelays() {
      digitalWrite(relayIn1, LOW);
      digitalWrite(relayIn2, LOW);
      if (noisy)
        Serial.println("RELAYS OPENED");
}
void closeRelays() {
      digitalWrite(relayIn1, HIGH);
      digitalWrite(relayIn2, HIGH);
      if (noisy)
        Serial.println("RELAYS CLOSED");
}

void openingInterrupt() {
  if (switchState == 3) {
    switchState = 1;
  }
}

void closingInterrupt() {
  if (switchState == 4) {
    switchState = 2;
  }
}

