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
STATUS?    [0,1,2] for [unknown, open, closed]
TOUCH? n   [0, 1] for [touch, no touch] for n=[1,2,3]->[4K-1K, 1K-50mK, 4k-50mK]
           Returns E for n != [1,2,3]
OPEN!      open the heat switch
CLOSE!     close the heat switch

*/

const unsigned int sketchVersion = 1;

const int openPin = 4;
const int closePin = 5;
const int touch4K1Kpin = 6;
const int touch1K50mKpin = 7;
const int touch4K50mKpin = 8;

volatile int state = 0;

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
  attachInterrupt(0, openInterrupt, CHANGE);
  attachInterrupt(1, closeInterrupt, CHANGE);
  pinMode(openPin, OUTPUT);
  pinMode(closePin, OUTPUT);
  pinMode(touch4K1Kpin, INPUT);
  pinMode(touch1K50mKpin, INPUT);
  pinMode(touch4K50mKpin, INPUT);
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
    Serial.println(millis() - lastSerialTime);
    handleCommand();
  }
  //delay(1);
}

void handleCommand() {
  Serial.print("command: ");
  Serial.println(currentCommand);
  if (strcmp(currentCommand, "*IDN?") == 0) {
    sendIDN();
  } else if (strcmp(currentCommand, "STATUS?") == 0) {
    sendStatus();
  } else if (strncmp(currentCommand, "TOUCH?", 6) == 0) {
    sendTouch();
  } else if (strcmp(currentCommand, "OPEN!") == 0) {
    openSwitch();
  } else if (strcmp(currentCommand, "CLOSE!") == 0) {
    closeSwitch();
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
  Serial.println(state);
}

void sendTouch() {
  b = atoi(currentCommand+7);
  i = -1;
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
    Serial.println("1");
  else if (i == LOW)
    Serial.println("0");
  else
    Serial.println("E");
}


// digitalWrite is relatively slow; according to a random website
// doing a HIGH then LOW will give give a waveform high time of about
// 3.3 microseconds, which is fine for our purposes.
void openSwitch() {
  digitalWrite(openPin, HIGH);
  digitalWrite(openPin, LOW);
}

void closeSwitch() {
  digitalWrite(closePin, HIGH);
  digitalWrite(closePin, LOW);
}

void openInterrupt() {
  state = 1;
}
void closeInterrupt() {
  state = 2;
}
